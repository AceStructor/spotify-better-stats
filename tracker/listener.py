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
from config import DB_CONFIG, LOCAL_MUSICSTREAM_URL, NAVIDROME_USER, NAVIDROME_PASSWORD
from logger import log
from sql_queries import INSERT_SQL, NEW_WORKFLOW_SQL, UPDATE_WORKFLOW_SQL

# Models and State

@dataclass
class Song:
    title: str
    artist: str
    album: str
    duration: int

    @property
    def track_key(self) -> str:
        return f"{self.artist} - {self.title}"

@dataclass
class PlaybackState:
    user_id: str = "local_user"
    client_id: str = "local_musicstream"
    song: Song | None = None
    accumulated_playtime: int = 0
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

# Key: (user_id, client_id)
lastPlaybacks = {}
currentPlaybacks = {}

# Helpers

def now_ms() -> int:
    """
    Get the current timestamp in milliseconds.

    :return: Current timestamp in milliseconds
    :rtype: int
    """
    return int(time.time() * 1000)

def parse_ts(payload):
    return datetime.fromisoformat(payload["timestamp"])

def playback_key(user_id, client_id):
    return (user_id, client_id)

# Classes

class MusicStreamClient:
    from config import LOCAL_MUSICSTREAM_URL

    def __init__(self, health_status: HealthStatus):
        self.health_status = health_status
        self.state = ApiState.UP

    def fetch_songs(self) -> None:
        currentPlaybacks.clear()
        try:
            url = f"{LOCAL_MUSICSTREAM_URL}/rest/getNowPlaying"
            params = {'u': NAVIDROME_USER, 'p': NAVIDROME_PASSWORD, 'v': '1.8.0', 'c': 'music-analytics'}
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            if self.state == ApiState.DOWN:
                log.info("Navidrome is back online")
                self.health_status.poll_interval = HealthStatus.DEFAULT_POLL_INTERVAL
            self.state = ApiState.UP
            self.health_status.last_health_log = now_ms()
        except requests.RequestException as e:
            self._handle_down(e)
            return None

        try:
            data = resp.json()
        except JSONDecodeError as e:
            log.error("Invalid JSON from Navidrome", error=str(e), data=data)
            return None

        if not isinstance(data, dict):
            log.error("Unexpected JSON structure from Navidrome", data=data)
            return None
        
        try:
            entries = data["subsonic-response"]["nowPlaying"]["entry"]
            if not entries:
                log.info("No song currently playing (empty entries)")
                return None
        except (KeyError, TypeError) as e:
            log.error("Missing expected fields in Navidrome response", error=str(e), data=data)
            return None

        log.debug("Fetched data from Navidrome", entries=entries)

        for entry in entries:
            self._handle_entry(entry)

    
    def _handle_entry(self, entry):
        navidrome_user_id = entry["username"]
        client_id = entry["playerName"]
        song = Song(
            title=entry["title"],
            artist=entry["artist"],
            album=entry["album"],
            duration=entry["duration"]*1000
        )

        key = playback_key(navidrome_user_id, client_id)
        currentPlaybacks[key] = PlaybackState(
            user_id=navidrome_user_id,
            client_id=client_id,
            song=song,
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
                artist_names = song.artist.split(" & ")
                cur.execute(INSERT_SQL, {
                    "artist_names": artist_names,
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
        self.db = db

    def process(self):
        for key in lastPlaybacks.keys():
            if key not in currentPlaybacks:
                self._finalize_previous(key)
        for key, state in currentPlaybacks.items():
            if self._is_new_song(key, state):
                self._finalize_previous(key)
                self._reset(key, state)

            self._update_playtime(key)

    def _is_new_song(self, key: str, state: PlaybackState) -> bool:
        lastState = lastPlaybacks.get(key)
        if not lastState:
            return True
        if lastState.song.track_key != state.song.track_key:
            return True
        return False

    def _update_playtime(self, key: str):
        start_ts = lastPlaybacks[key].start_ts
        lastPlaybacks[key].accumulated_playtime = now_ms() - start_ts

    def _finalize_previous(self, key: str):
        lastState = lastPlaybacks.get(key)
        if not lastState:
            log.debug("No previous playback state to finalize", key=key)
            return

        if not lastState.song or lastState.accumulated_playtime < 100:
            log.debug("Song playtime below threshold; not finalizing previous song",
                     track_key=lastState.song.track_key if lastState.song else "N/A",
                     accumulated_playtime=lastState.accumulated_playtime)
            return

        ratio = lastState.accumulated_playtime / lastState.song.duration
        if (lastState.song.duration * (1 - self.SKIP_THRESHOLD)) <= self.MIN_SKIP_MS:
            skipped = (lastState.song.duration - lastState.accumulated_playtime) > self.MIN_SKIP_MS
        else:
            skipped = ratio < self.SKIP_THRESHOLD

        log.info("Song ended",
                 track_key=lastState.song.track_key,
                 accumulated_playtime=lastState.accumulated_playtime,
                 skipped=skipped,
                 start_timestamp=lastState.start_ts,
                 end_timestamp=now_ms())

        self.db.insert_track_play(
            song=lastState.song,
            played_at=datetime.fromtimestamp(lastState.start_ts / 1000),
            skipped=skipped,
        )

        del lastPlaybacks[key]

    def _reset(self, key: str, state: PlaybackState):
        lastPlaybacks[key] = state
        lastPlaybacks[key].start_ts = now_ms()
        lastPlaybacks[key].accumulated_playtime = 0

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
                    client.fetch_songs()
                    tracker.process()
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
