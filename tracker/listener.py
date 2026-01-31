"""
Listener for MusicStream local API 
to track currently playing songs 
and log play events to the database.
"""
import time
from dataclasses import dataclass
from json import JSONDecodeError
from enum import Enum
from datetime import datetime
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, LOCAL_MUSICSTREAM_URL
from logger import log
from sql_queries import INSERT_SQL, NEW_WORKFLOW_SQL, UPDATE_WORKFLOW_SQL

# Models and State

@dataclass
class Song:
    """
    Represents a song with title and artist.
    """
    title: str
    artist: str
    album: str
    duration: int
    position: int
    playing: bool

    @property
    def track_key(self) -> str:
        return f"{self.artist} - {self.title}"

@dataclass
class PlaybackState:
    last_song: Song | None = None
    accumulated_playtime: int = 0
    last_position: int = 0
    start_ts: int = 0

class ApiState(Enum):
    UP = "up"
    DOWN = "down"

@dataclass
class HealthStatus:
    poll_interval: int
    last_health_log: int
    DEFAULT_POLL_INTERVAL = 2
    HEALTH_LOG_INTERVAL = 60

# Helpers

def now_ms() -> int:
    """
    Get the current timestamp in milliseconds.

    :return: Current timestamp in milliseconds
    :rtype: int
    """
    return int(time.time() * 1000)

class MusicStreamClient:
    from config import LOCAL_MUSICSTREAM_URL

    def __init__(self, health_status: HealthStatus):
        self.health_status = health_status
        self.state = ApiState.UP

    def fetch_song(self) -> Song | None:
        try:
            resp = requests.get(f"{LOCAL_MUSICSTREAM_URL}/api/data", timeout=5)
            resp.raise_for_status()
            if self.state == ApiState.DOWN:
                log.info("MusicStream API is back online")
                self.health_status.poll_interval = HealthStatus.DEFAULT_POLL_INTERVAL
            self.state = ApiState.UP
            self.health_status.last_health_log = now_ms()
        except requests.RequestException as e:
            self._handle_down(e)
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
        album = data.get("album", "")
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

        return Song(
            title,
            artist,
            album,
            duration,
            position,
            bool(playing)
        )

    def _handle_down(self, error: Exception):
        self.health_status.poll_interval = min(
            self.health_status.poll_interval * 2,
            HealthStatus.HEALTH_LOG_INTERVAL
        )
        if self.state == ApiState.UP:
            log.warning("MusicStream API went offline", error=str(error))
            self.state = ApiState.DOWN
        else:
            log.debug("MusicStream API still offline")


class DatabaseWriter:
    def __init__(self, conn):
        self.conn = conn
        
    def insert_track_play(self, song: Song, played_at: datetime, skipped: bool):
        workflow_id = self._new_workflow()

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(INSERT_SQL, {
                    "artist_name": song.artist,
                    "album_title": song.album,
                    "track_title": song.title,
                    "duration_ms": song.duration,
                    "played_at": played_at,
                    "skipped": skipped,
                    "workflow_id": workflow_id,
                })
            self.conn.commit()
            log.debug("Inserted track play", track_title=song.title, played_at=played_at.isoformat())
        except psycopg2.Error as e:
            log.error("Error inserting track play", error=str(e), exc_info=True)
            self.conn.rollback()
        self._finish_workflow(workflow_id)

    def _new_workflow(self) -> str:
        try:
            with self.conn.cursor() as cur:
                cur.execute(NEW_WORKFLOW_SQL)
                workflow_id = cur.fetchone()[0]
                self.conn.commit()
            if not workflow_id:
                log.error("Failed to create new workflow; no ID returned")
                return ""
            else:
                log.debug("Created new workflow", workflow_id=workflow_id)
                return workflow_id
        except psycopg2.Error as e:
            log.error("Error creating new workflow", error=str(e), exc_info=True)
            return ""

    def _finish_workflow(self, workflow_id: str):
        try:
            with self.conn.cursor() as cur:
                cur.execute(UPDATE_WORKFLOW_SQL, (workflow_id,))
                self.conn.commit()
                log.debug("Updated workflow to done", workflow_id=workflow_id)
                rowcount = cur.rowcount

            if rowcount == 0:
                log.warning("No workflow row updated when finishing task", workflow_id=workflow_id)
        except psycopg2.Error as e:
            log.error("Error updating workflow to done", error=str(e), exc_info=True)

class SongProcessor:
    SKIP_THRESHOLD = 0.9
    MIN_SKIP_MS = 5000

    def __init__(self, db: DatabaseWriter):
        self.state = PlaybackState()
        self.db = db

    def process(self, song: Song):
        if self._is_new_song(song):
            self._finalize_previous()
            self._reset(song)

        self._update_playtime(song)

    def _is_new_song(self, song: Song) -> bool:
        return not self.state.last_song or song.track_key != self.state.last_song.track_key

    def _update_playtime(self, song: Song):
        if song.playing:
            delta = max(0, song.position - self.state.last_position)
            self.state.accumulated_playtime += delta

        self.state.last_position = song.position
        self.state.last_song = song

    def _finalize_previous(self):
        song = self.state.last_song
        if not song or self.state.accumulated_playtime < 100:
            log.debug("Song playtime below threshold; not finalizing previous song",
                     track_key=song.track_key if song else "N/A",
                     accumulated_playtime=self.state.accumulated_playtime)
            return

        ratio = self.state.accumulated_playtime / song.duration
        if (song.duration * (1 - self.SKIP_THRESHOLD)) <= self.MIN_SKIP_MS:
            skipped = (song.duration - self.state.accumulated_playtime) > self.MIN_SKIP_MS
        else:
            skipped = ratio < self.SKIP_THRESHOLD

        if (not skipped and
            (now_ms() - self.state.start_ts) < song.duration * self.SKIP_THRESHOLD):
            log.debug("Adjusting for early song end; marking as skipped",
                     track_key=song.track_key,
                     accumulated_playtime=self.state.accumulated_playtime,
                     start_timestamp=self.state.start_ts,
                     end_timestamp=now_ms())
            skipped = True

        log.info("Song ended",
                 track_key=song.track_key,
                 accumulated_playtime=self.state.accumulated_playtime,
                 skipped=skipped,
                 start_timestamp=self.state.start_ts,
                 end_timestamp=now_ms())

        # self.db.insert_track_play(
        #     song=song,
        #     played_at=datetime.fromtimestamp(self.state.start_ts / 1000),
        #     skipped=skipped,
        # )

    def _reset(self, song: Song):
        self.state = PlaybackState(
            last_song=song,
            accumulated_playtime=0,
            last_position=0,
            start_ts=now_ms(),
        )

# Main Loop

def listen_forever():
    health_status = HealthStatus(
        poll_interval=HealthStatus.DEFAULT_POLL_INTERVAL,
        last_health_log=0,
    )
    client = MusicStreamClient(health_status=health_status)

    while True:
        try:
            log.info("Connecting to database...")
            with psycopg2.connect(**DB_CONFIG) as conn:
                db = DatabaseWriter(conn)
                tracker = SongProcessor(db)

                while True:
                    song = client.fetch_song()
                    if song:
                        tracker.process(song)
                    time.sleep(health_status.poll_interval)
        except psycopg2.OperationalError as e:
            log.warning("Database connection error, will retry", error=str(e), exc_info=True)
            time.sleep(health_status.poll_interval)
            continue
        except KeyboardInterrupt:
            log.info("Shutting down")
            break
        except Exception as e:
            log.error("Fatal error", error=str(e), exc_info=True)
            time.sleep(5)

if __name__ == "__main__":
    listen_forever()
