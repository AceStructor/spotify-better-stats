import sys
import select
import json
import time
import logging
import requests
from json import JSONDecodeError
import psycopg2
import structlog

from config import DB_CONFIG, LOCAL_MUSICSTREAM_URL

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

log = structlog.get_logger(service="tracker")

class Song:
    """
    Represents a song with title and artist.
    """

    def __init__(self, title: str, artist: str, album: str, duration: int, position: int, playing: bool):
        self.title = title
        self.artist = artist
        self.trackKey = f"{artist} - {title}"
        self.album = album
        self.duration = duration
        self.position = position
        self.playing = playing

def get_ms_timestamp() -> int:
    """
    Get the current timestamp in milliseconds.

    :return: Current timestamp in milliseconds
    :rtype: int
    """
    return int(time.time() * 1000)

poll_interval = 2 # seconds
accumulated_playtime = 0
last_position = 0
last_start_timestamp = get_ms_timestamp()
skip_threshold = 0.9
MIN_SKIP_TOLERANCE = 5000


currently_playing_song = Song("", "", "", 0, 0, False)
last_sent_song = Song("", "", "", 0, 0, False)


def poll_musicstream() -> Song | None:
    """
    Poll the MusicStream api for currently playing track and send updates.

    :return: Currently playing song or None if no song is playing
    :rtype: Song | None
    """
    try:
        resp = requests.get(f"{LOCAL_MUSICSTREAM_URL}/api/data", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error("Error fetching data from MusicStream",
                  error=str(e))
        return None

    try:
        data = resp.json()
    except JSONDecodeError as e:
        log.error("Invalid JSON from MusicStream", error=str(e))
        return None

    if not isinstance(data, dict):
        log.error("Unexpected JSON structure from MusicStream", data=data)
        return None

    log.debug("Fetched data from MusicStream", data=data)

    title = data.get("title")
    artist = data.get("artist")
    album = data.get("album")
    duration = data.get("duration", 0) or 0
    position = data.get("position", 0) or 0
    playing = data.get("playing", False)

    try:
        duration = int(duration)
    except (ValueError, TypeError):
        duration = 0

    try:
        position = int(position)
    except (ValueError, TypeError):
        position = 0

    if (not title or not artist or duration == 0):
        log.info("No song currently playing")
        return None

    return Song(title, artist, album or "", duration, position, bool(playing))

def process_song(conn, song: Song):
    """
    Process the currently playing song and send updates if necessary.

    :param conn: Database connection
    :type conn: psycopg2.extensions.connection
    :param song: Currently playing song
    :type song: Song
    """
    global last_sent_song, accumulated_playtime, last_position, last_start_timestamp

    is_same_song = (song.trackKey == last_sent_song.trackKey)

    if(not is_same_song and last_sent_song.trackKey != " - "):
        log.info("New song detected", song=song.trackKey)
        emit_song_end(conn)
        reset_playtime()

    if(is_same_song and last_position > 0 and song.position < last_position):
        backward_skip = last_position - song.position
        tolerance = song.duration * 0.15

        if abs(backward_skip - song.duration) < tolerance:
            # Song looped
            log.info("Song loop detected", song=song.trackKey)
            emit_song_end(conn)
            reset_playtime()

    if(song.playing):
        elapsed = song.position - last_position
        accumulated_playtime += elapsed
    
    last_position = song.position
    last_sent_song = song

def reset_playtime():
    global accumulated_playtime, last_position, last_start_timestamp
    accumulated_playtime = 0
    last_position = 0
    last_start_timestamp = get_ms_timestamp()

def emit_song_end(conn):
    global accumulated_playtime, last_sent_song, last_position, last_start_timestamp, skip_threshold

    if accumulated_playtime < 100:
        log.debug("Song playtime below threshold; not emitting song end",
                 trackKey=last_sent_song.trackKey,
                 accumulated_playtime=accumulated_playtime)
        return
    
    ratio_played = accumulated_playtime / last_sent_song.duration
    if((last_sent_song.duration * (1 - skip_threshold)) <= MIN_SKIP_TOLERANCE):
        skipped = (last_sent_song.duration - accumulated_playtime) > MIN_SKIP_TOLERANCE
    else:
        skipped = ratio_played < skip_threshold
    end_timestamp = get_ms_timestamp()

    if(not skipped and end_timestamp - last_start_timestamp < last_sent_song.duration * skip_threshold):
        log.debug("Adjusting for early song end; marking as skipped",
                 trackKey=last_sent_song.trackKey,
                 accumulated_playtime=accumulated_playtime,
                 start_timestamp=last_start_timestamp,
                 end_timestamp=end_timestamp)
        skipped = True

    log.info("Song ended",
             trackKey=last_sent_song.trackKey,
             accumulated_playtime=accumulated_playtime,
             skipped=skipped,
             start_timestamp=last_start_timestamp,
             end_timestamp=end_timestamp)
    

def get_health_status() -> bool:
    """
    Get the health status of the api.

    :return: Health status dictionary
    :rtype: dict
    """
    try:
        resp = requests.get(f"{LOCAL_MUSICSTREAM_URL}/health", timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.warning("Failed to get health status", error=str(e))
        return False
    data = resp.json()
    log.debug("Health status fetched", data=data)
    return data == "ok"

def listen_forever():
    """
    Listen for notifications from the database and handle them.
    """
    while True:
        try:
            if not get_health_status():
                time.sleep(poll_interval)
                continue
            log.info("Connecting to database...")
            try:
                conn = psycopg2.connect(**DB_CONFIG)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
            except psycopg2.OperationalError as e:
                log.warning("Database connection error, will retry", error=str(e), exc_info=True)
                time.sleep(poll_interval)
                continue

            try:
                while True:
                    song = poll_musicstream()
                    if song is not None:
                        process_song(conn, song)
                    time.sleep(poll_interval)
                    
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
