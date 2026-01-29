"""
Matrix Song Bot Listener
"""
import select
import json
import time
import asyncio
import threading
from typing import Optional

import psycopg2

from config import DB_CONFIG, CHANNEL
from matrix_client import get_matrix_client, start_matrix_worker, send_matrix_message
from logger import log

listener_state = {"matrix_client": None}


def on_new_row(track_play: dict, previous_track_play: dict) -> None:
    """Handle a new track play row and post it to Matrix if appropriate.

    Performs validation of required fields and logs clearly when a post is skipped.
    
    :param track_play: Current track play data
    :type track_play: dict
    :param previous_track_play: Previous track play data
    :type previous_track_play: dict
    """
    try:
        title = track_play["title"]
        artist = track_play["artist"]
        youtube_code = track_play["youtube_code"]
        skipped = bool(track_play.get("skipped", False))
    except KeyError as e:
        log.warning("Missing required track_play field",
                    missing_field=str(e),
                    track_play=track_play)
        return

    song_url = f"https://music.youtube.com/watch?v={youtube_code}"
    genres = track_play.get("genres") or []
    genre_string = ", ".join(g for g in genres if g)

    msg = (
        f"**Title:** [{artist} - {title}]({song_url})\n"
        f"**Genre:** {genre_string}\n"
        f"**---**"
    )

    log.info("Prepared message for posting", title=title, artist=artist, youtube_code=youtube_code)
    log.debug("Message content preview", message=msg)

    # Determine if this is a repeat or skipped track
    repeat = (
        previous_track_play
        and previous_track_play.get("title") == title
        and previous_track_play.get("artist") == artist
    )

    if skipped or repeat:
        reason = "skipped" if skipped else "repeat"
        log.info("Not posting track", title=title, artist=artist, reason=reason)
        return

    content = {
        "msgtype": "m.text",
        "body": (
            f"Title: {artist} - {title}\n"
            f"Genre: {genre_string}"
        ),
        "format": "org.matrix.custom.html",
        "formatted_body": (
            f"<strong>Title:</strong> "
            f"<a href=\"{song_url}\">{artist} - {title}</a><br>"
            f"<strong>Genre:</strong> {genre_string}<br><hr>"
        ),
    }

    log.info(msg)

    repeat = (track_play['title'] == previous_track_play['title']) \
            and (track_play['artist'] == previous_track_play['artist'])

    if (track_play['skipped'] or repeat):
        log.info("This song will not be posted!")
        return

    try:
        send_matrix_message(content)
        log.info("Posted message to Matrix", title=title, artist=artist)
    except Exception as e:
        log.error("Failed to send Matrix message",
                title=title,
                artist=artist,
                error=str(e),
                exc_info=True)


def get_track_play_by_id(conn, track_plays_id: int) -> Optional[dict]:
    """
    Fetch track play data by its ID. Returns None if not found or on error.
    
    :param conn: Database connection
    :param track_plays_id: Track plays ID
    :type track_plays_id: int
    :return: Track play data or None
    :rtype: Optional[dict]
    """

    if not isinstance(track_plays_id, int) or track_plays_id <= 0:
        log.warning("Invalid track_plays_id requested", track_plays_id=track_plays_id)
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    t.title,
                    a.name      AS artist,
                    array_agg(g.name ORDER BY g.name) AS genres,
                    tp.skipped,
                    t.youtube_code
                FROM track_plays tp
                JOIN tracks t   ON t.id = tp.track_id
                JOIN artists a  ON a.id = t.artist_id
                LEFT JOIN artist_genres ag ON ag.artist_id = a.id
                LEFT JOIN genres g         ON g.id = ag.genre_id
                WHERE tp.id = %s
                GROUP BY
                    t.title,
                    a.name,
                    tp.skipped,
                    t.youtube_code
                """,
                (track_plays_id,),
            )
            row = cur.fetchone()
            log.debug("Database query executed for track play", track_plays_id=track_plays_id)
    except psycopg2.Error as e:
        log.error("Error fetching track play by ID",
                  track_plays_id=track_plays_id,
                  error=str(e),
                  exc_info=True)
        return None

    if not row:
        log.debug("No track play found for ID", track_plays_id=track_plays_id)
        return None

    try:
        return {
            "title": row[0],
            "artist": row[1],
            "genres": row[2],
            "skipped": row[3],
            "youtube_code": row[4],
        }
    except Exception as e:
        log.error("Malformed row returned from DB",
                  track_plays_id=track_plays_id,
                  error=str(e),
                  exc_info=True)
        return None


def get_track_plays_id(conn, workflow_id: int) -> Optional[int]:
    """
    Fetch the track plays ID for the given workflow ID.

    :param conn: Database connection
    :param workflow_id: Workflow ID
    :type workflow_id: int
    :return: Track plays ID or None
    :rtype: Optional[int]
    """

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM track_plays
                WHERE workflow_id = %s
                """,
                (workflow_id,),
            )
            result = cur.fetchone()
            log.debug("Queried track_plays for workflow", workflow_id=workflow_id)
            if result:
                return result[0]
            return None
    except psycopg2.Error as e:
        log.error("Error fetching track plays ID",
                  workflow_id=workflow_id,
                  error=str(e),
                  exc_info=True)
        return None


def handle_notify(conn, payload: dict) -> None:
    """
    Handle the notification payload from the database.
    
    :param conn: Database connection
    :param payload: Notification payload from the database
    """

    if not isinstance(payload, dict):
        log.warning("Invalid payload type", payload=payload)
        return

    workflow_id = payload.get("workflow_id")
    if workflow_id is None:
        log.warning("Payload missing workflow_id", payload=payload)
        return

    log.debug("Handling notification", workflow_id=workflow_id, payload=payload)

    genre_required = payload.get("genre_required")
    yt_required = payload.get("yt_required")
    genre_done = payload.get("genre_done")
    yt_done = payload.get("yt_done")
    init_done = payload.get("init_done")

    if not init_done:
        log.info("Workflow not initialized yet, skipping", workflow_id=workflow_id)
        return

    if genre_required and not genre_done:
        log.info("Waiting for genre resolution", workflow_id=workflow_id)
        return

    if yt_required and not yt_done:
        log.info("Waiting for YouTube resolution", workflow_id=workflow_id)
        return

    track_plays_id = get_track_plays_id(conn, workflow_id)
    if not track_plays_id:
        log.info("No track plays ID found for workflow", workflow_id=workflow_id)
        return

    track_play = get_track_play_by_id(conn, track_plays_id)
    if not track_play:
        log.warning("Track play not found", track_plays_id=track_plays_id, workflow_id=workflow_id)
        return

    log.info("Track Play loaded", track_plays_id=track_plays_id, track_play=track_play)

    previous_track_play = get_track_play_by_id(conn, track_plays_id - 1)
    if not previous_track_play:
        log.debug("Previous track play not found, continuing anyway",
                  previous_id=track_plays_id - 1)

    on_new_row(track_play, previous_track_play or {})


def listen_forever() -> None:
    """Listen for notifications from the database and handle them.

    This function will attempt to reconnect if the database connection fails and
    supports graceful shutdown via KeyboardInterrupt.
    """
    while True:
        try:
            log.info("Connecting to database...")
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            except psycopg2.OperationalError as e:
                log.error("Database connection error, will retry", error=str(e), exc_info=True)
                time.sleep(5)
                continue

            try:
                cur = conn.cursor()
                cur.execute(f"LISTEN {CHANNEL};")
                log.info("Listening on channel", channel=CHANNEL)

                while True:
                    ready = select.select([conn], [], [], 5.0)
                    if not ready[0]:
                        log.debug("Select timeout, still listening...")
                        continue

                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        log.debug("Received notification", pid=notify.pid)
                        try:
                            payload = json.loads(notify.payload)
                        except json.JSONDecodeError as e:
                            log.error("Invalid JSON payload in notification",
                                      payload=notify.payload,
                                      error=str(e))
                            continue

                        handle_notify(conn, payload)
            finally:
                try:
                    conn.close()
                    log.debug("Database connection closed")
                except Exception:
                    pass

        except KeyboardInterrupt:
            log.info("Listener interrupted; shutting down gracefully")
            break
        except Exception as e:
            log.error("Uncaught error in listener loop", error=str(e), exc_info=True)
            time.sleep(5)


if __name__ == "__main__":
    try:
        listener_state["matrix_client"] = asyncio.run(get_matrix_client())
    except Exception as e:
        log.error("Failed to initialize matrix client", error=str(e), exc_info=True)
        raise

    threading.Thread(
        target=start_matrix_worker,
        args=(listener_state["matrix_client"],),
        daemon=True,
    ).start()

    listen_forever()
