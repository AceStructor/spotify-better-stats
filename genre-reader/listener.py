"""
Genre Reader Listener
"""
import sys
import select
import json
import time
import logging
from json import JSONDecodeError
from typing import List

import psycopg2
import structlog
import requests


from config import DB_CONFIG, CHANNEL, LASTFM_API_KEY

LASTFM_BASE = "http://ws.audioscrobbler.com/2.0"

logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.DEBUG,
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
)

log = structlog.get_logger(service="genre-reader")


def get_artist_genres(artist_name: str) -> List[str]:
    """
    Fetch genres for the given artist name from Last.fm API.

    :param artist_name: Name of the artist
    :type artist_name: str
    :return: List of genres
    :rtype: list[str]
    """
    if not artist_name:
        log.warning("Empty artist name in notification; skipping")
        return []

    params = {
        "method": "artist.getTopTags",
        "api_key": LASTFM_API_KEY,
        "artist": artist_name,
        "format": "json",
    }

    try:
        response = requests.get(LASTFM_BASE, params=params, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        log.error("Error fetching genres from Last.fm",
                  artist_name=artist_name,
                  error=str(e))
        return []

    try:
        data = response.json()
    except JSONDecodeError as e:
        log.error("Invalid JSON from Last.fm", artist_name=artist_name, error=str(e))
        return []

    log.debug("Last.fm API response", artist_name=artist_name, data=data)

    tags = data.get("toptags", {}).get("tag", [])
    if not isinstance(tags, list):
        log.warning("Last.fm returned unexpected tag structure", artist_name=artist_name)
        return []

    try:
        genres = [tag["name"] for tag in tags if "name" in tag and tag.get("count", 0) > 50]
    except (TypeError, KeyError) as e:
        log.error("Error parsing genres from Last.fm response",
                  artist_name=artist_name,
                  error=str(e))
        return []

    if not genres:
        log.debug("No genres passed threshold for artist", artist_name=artist_name)
    else:
        log.info("Fetched genres for artist", artist_name=artist_name, genres=genres)
    return genres


def write_genres_to_db(conn, artist_id: int, genres: List[str]):
    """
    Write genres to the database and associate them with the artist.

    :param conn: Database connection
    :param artist_id: Artist ID
    :type artist_id: int
    :param genres: List of genres
    :type genres: list[str]
    """
    if not genres:
        log.debug("No genres to write to DB", artist_id=artist_id)
        return

    for genre in genres:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO genres (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                    """,
                    (genre,),
                )
                cur.execute(
                    """
                    INSERT INTO artist_genres (artist_id, genre_id)
                    SELECT
                        %s,
                        g.id
                    FROM genres g
                    WHERE g.name = %s
                    ON CONFLICT DO NOTHING
                    """,
                    (artist_id, genre),
                )
        except psycopg2.Error as e:
            # Attempt to rollback any failed transaction; safe when autocommit is set.
            try:
                conn.rollback()
            except Exception:
                pass
            log.error("Error writing genre to database",
                      artist_id=artist_id,
                      genre=genre,
                      error=str(e))
            continue
        log.debug("Wrote genre to database", artist_id=artist_id, genre=genre)


def finish_task(conn, workflow_id: int):
    """
    Mark the workflow task as done in the database.

    :param conn: Database connection
    :param workflow_id: Workflow ID
    :type workflow_id: int
    """

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE workflow_state
                SET genre_done = true
                WHERE workflow_id = %s
                """,
                (workflow_id,),
            )
    except psycopg2.Error as e:
        log.error("Error finishing workflow task", workflow_id=workflow_id, error=str(e))
        try:
            conn.rollback()
        except Exception:
            pass
        return
    log.debug("Finished workflow task", workflow_id=workflow_id)


def get_workflow_status(conn, workflow_id: int) -> bool:
    """
    Check if the workflow has been initialized.

    :param conn: Database connection
    :param workflow_id: Workflow ID
    :type workflow_id: int
    :return: True if initialized, False otherwise
    :rtype: bool
    """

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT init_done
                FROM workflow_state
                WHERE workflow_id = %s
                """,
                (workflow_id,),
            )
            result = cur.fetchone()
            log.debug("Checked workflow status", workflow_id=workflow_id, result=result)
            if result:
                return bool(result[0])
            return False
    except psycopg2.Error as e:
        log.error("Error checking workflow status", workflow_id=workflow_id, error=str(e))
        return False


def handle_notify(conn, payload: dict):
    """
    Handle the notification payload from the database.

    :param conn: Database connection
    :param payload: Notification payload from the database
    """
    if not isinstance(payload, dict):
        log.warning("Invalid notification payload (not a dict)", payload=payload)
        return

    try:
        artist_id = int(payload.get("id"))
        artist_name = payload.get("name")
        artist_workflow_id = payload.get("workflow_id")
    except (TypeError, ValueError) as e:
        log.warning("Malformed notification payload; missing or invalid fields",
                    payload=payload,
                    error=str(e))
        return

    # Wait until workflow is initialized; use debug for polling messages.
    while True:
        status = get_workflow_status(conn, artist_workflow_id)
        if status:
            break
        log.debug("Workflow not initialized yet; waiting", workflow_id=artist_workflow_id)
        time.sleep(2)

    log.debug("Handling notification",
              artist_id=artist_id,
              artist_name=artist_name,
              workflow_id=artist_workflow_id)

    genres = get_artist_genres(artist_name)

    if not genres:
        log.debug("No genres found for artist", artist_id=artist_id, artist_name=artist_name)
    else:
        log.debug("Genres for artist", artist_id=artist_id, artist_name=artist_name, genres=genres)

    write_genres_to_db(conn, artist_id, genres)
    finish_task(conn, artist_workflow_id)


def listen_forever():
    """
    Listen for notifications from the database and handle them.
    """
    while True:
        try:
            log.info("Connecting to database...")
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            except psycopg2.OperationalError as e:
                log.warning("Database connection error, will retry", error=str(e), exc_info=True)
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
                            log.warning("Invalid JSON payload in notification",
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
    listen_forever()
