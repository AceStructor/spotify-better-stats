"""
YouTube Reader Listener
"""

import sys
import select
import json
import time
import logging
from typing import Optional, Any, Dict
import psycopg2
import structlog

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicError

from config import DB_CONFIG, CHANNEL

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

log = structlog.get_logger(service="youtube-reader")

# Timeouts and retry delays
SELECT_TIMEOUT = 5  # seconds for select.select timeout
DB_RETRY_DELAY = 5  # seconds to wait before retrying DB connect

# Cached YTMusic client for reuse
_ytmusic_client: Optional[YTMusic] = None

def get_ytmusic_client() -> Optional[YTMusic]:
    """Return a cached YTMusic client or create one.

    Returns None if the client cannot be created.
    """
    global _ytmusic_client
    if _ytmusic_client is not None:
        return _ytmusic_client

    try:
        _ytmusic_client = YTMusic()
        log.debug("Initialized YTMusic client")
        return _ytmusic_client
    except Exception:
        log.error("Failed to initialize YTMusic client")
        return None


def get_artist_name(conn, artist_id: int) -> str:
    """
    Fetch the artist name from the database given the artist ID.
    
    :param conn: Database connection
    :param artist_id: Artist ID
    :type artist_id: int
    :return: Artist name
    :rtype: str
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name
                FROM artists
                WHERE id = %s
                """,
                (artist_id,),
            )
            result = cur.fetchone()

        if not result:
            log.warning("Artist not found", artist_id=artist_id)
            return ""

        artist_name = result[0]
        log.debug("Fetched artist name", artist_id=artist_id, artist_name=artist_name)
        return artist_name

    except psycopg2.Error:
        log.error("Database error while fetching artist name", artist_id=artist_id)
        return ""


def get_youtube_code(artist_name: str, track_name: str) -> str:
    """
    Fetch the YouTube video ID for the given artist and track name.

    :param artist_name: Artist name
    :type artist_name: str
    :param track_name: Track name
    :type track_name: str
    :return: YouTube video ID
    :rtype: str
    """
    if not artist_name or not track_name:
        log.warning("Empty artist or track name provided",
                    artist_name=artist_name,
                    track_name=track_name)
        return ""

    client = get_ytmusic_client()
    if client is None:
        log.error("No YTMusic client available")
        return ""

    query = f"{artist_name} {track_name}"
    try:
        results = client.search(query, filter="songs", limit=5)
    except YTMusicError:
        log.error("YTMusic search failed",
                      artist_name=artist_name,
                      track_name=track_name,
                      query=query)
        return ""
    except Exception:
        log.error("Unexpected error during YTMusic search",
                      artist_name=artist_name,
                      track_name=track_name,
                      query=query)
        return ""

    if not results:
        log.info("No YouTube results found", artist_name=artist_name, track_name=track_name)
        return ""

    video_id = results[0].get("videoId")
    if not video_id:
        log.warning("No video ID in first YouTube result",
                    artist_name=artist_name,
                    track_name=track_name)
        return ""

    log.debug("Fetched YouTube video ID",
              artist_name=artist_name,
              track_name=track_name,
              video_id=video_id)
    return video_id


def write_youtube_code_to_db(conn, track_id: int, youtube_code: str) -> bool:
    """
    Write the YouTube video ID to the database for the given track ID.

    Returns True if a row was updated, False otherwise.

    :param conn: Database connection
    :param track_id: Track ID
    :type track_id: int
    :param youtube_code: YouTube video ID
    :type youtube_code: str
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET youtube_code = %s
                WHERE id = %s
                """,
                (youtube_code or None, track_id),
            )
            rowcount = cur.rowcount

        if rowcount == 0:
            log.warning("No track row updated when writing YouTube code",
                        track_id=track_id,
                        youtube_code=youtube_code)
            return False

        log.info("Wrote YouTube code to DB", track_id=track_id, youtube_code=youtube_code)
        return True

    except psycopg2.Error:
        log.error("Database error while writing YouTube code",
                      track_id=track_id,
                      youtube_code=youtube_code)
        return False


def finish_task(conn, workflow_id: int) -> bool:
    """
    Mark the workflow task as done in the database.

    Returns True if the workflow state row was updated.
    
    :param conn: Database connection
    :param workflow_id: Workflow ID
    :type workflow_id: int
    """

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE workflow_state
                SET yt_done = true
                WHERE workflow_id = %s
                """,
                (workflow_id,),
            )
            rowcount = cur.rowcount

        if rowcount == 0:
            log.warning("No workflow row updated when finishing task", workflow_id=workflow_id)
            return False

        log.debug("Finished workflow task", workflow_id=workflow_id)
        return True

    except psycopg2.Error:
        log.error("Database error while finishing workflow task", workflow_id=workflow_id)
        return False


def safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    """
    Safely parse a JSON string, returning None on failure.
    
    :param s: JSON string
    :type s: str
    :return: Parsed JSON object or None
    :rtype: Optional[Dict[str, Any]]
    """
    try:
        return json.loads(s)
    except Exception:
        log.error("Failed to parse notification payload as JSON", payload=s)
        return None


def handle_notify(conn, payload: Dict[str, Any]):
    """
    Handle the notification payload from the database.
    """
    # Validate payload
    if not payload:
        log.warning("Empty payload received, skipping")
        return

    try:
        track_id_raw = payload.get('id')
        if track_id_raw is None:
            log.warning("Payload missing 'id', skipping", payload=payload)
            return

        track_id = int(track_id_raw)
        track_name = payload.get('title', '')
        artist_id = payload.get('artist_id')
        workflow_id = payload.get('workflow_id')

        log.info("Handling notification", track_id=track_id, track_name=track_name)

        if artist_id is None:
            log.warning("Payload missing 'artist_id', skipping", payload=payload)
            return

        artist_name = get_artist_name(conn, int(artist_id))
        if not artist_name:
            log.info("No artist name found, skipping YouTube search",
                     artist_id=artist_id,
                     track_id=track_id)
            return

        youtube_code = get_youtube_code(artist_name, track_name)
        if not youtube_code:
            log.info("No YouTube code found for track",
                     track_id=track_id,
                     artist_name=artist_name,
                     track_name=track_name)
            # still mark workflow as done to avoid stuck tasks
            if workflow_id is not None:
                finish_task(conn, workflow_id)
            return

        write_ok = write_youtube_code_to_db(conn, track_id, youtube_code)
        if write_ok and workflow_id is not None:
            finish_task(conn, workflow_id)

    except (ValueError, TypeError):
        log.error("Invalid payload data types", payload=payload)
    except Exception:
        log.error("Unhandled error while processing notification", payload=payload)


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
    listen_forever()
