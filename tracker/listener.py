"""
Listener for MusicStream local API 
to track currently playing songs 
and log play events to the database.
"""
import time
from json import JSONDecodeError
from enum import Enum
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from config import DB_CONFIG, LOCAL_MUSICSTREAM_URL
from logger import log
from sql_queries import INSERT_SQL, NEW_WORKFLOW_SQL, UPDATE_WORKFLOW_SQL
from flask import Flask, request, jsonify
from datetime import datetime
import threading
from dataclasses import dataclass

app = Flask(__name__)

lock = threading.Lock()

# Konfiguration 

MIN_LISTEN_RATIO = 0.9
MIN_LISTEN_SECONDS = 240
LOOP_THRESHOLD_SECONDS = 10

# Models and State

@dataclass
class Song:
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
    user_id: str
    client_id: str
    last_event_ts: datetime
    last_song: Song | None = None
    accumulated_playtime: int = 0
    last_position: int = 0
    start_ts: int = 0
    navidrome_completed: bool = False

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
playbacks = {}

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
    
    def handle_start(self, payload: PlaybackState, ts):
        navidrome_user_id = payload.user_id
        client_id = payload.client_id
        last_song = payload.last_song
        duration = payload.last_song.duration
        position = payload.last_position

        key = playback_key(navidrome_user_id, client_id)
        state = playbacks.get(key)

        if not state:
            playbacks[key] = PlaybackState(
                user_id=navidrome_user_id,
                client_id=client_id,
                last_song=last_song,
                track_duration=duration,
                play_started_at=ts,
                last_event_ts=ts,
                last_position=position
            )
            return

        # Trackwechsel
        if state.last_song.track_key != last_song.track_key:
            self.update_playtime(state, ts)
            self.finalize_play(state)
            del playbacks[key]

            playbacks[key] = PlaybackState(
                user_id=navidrome_user_id,
                client_id=client_id,
                last_song=last_song,
                track_duration=duration,
                play_started_at=ts,
                last_event_ts=ts,
                last_position=position
            )
            return

        # gleicher Track → Loop oder Resume?
        if state.accumulated_playtime < LOOP_THRESHOLD_SECONDS:
            self.update_playtime(state, ts)
            self.finalize_play(state, detected_loop=True)
            del playbacks[key]

            playbacks[key] = PlaybackState(
                user_id=navidrome_user_id,
                client_id=client_id,
                last_song=last_song,
                track_duration=duration,
                play_started_at=ts,
                last_event_ts=ts,
                last_position=position
            )
            return

        # Resume
        state.last_event_ts = ts

    def handle_stop(self, payload: PlaybackState, ts):
        navidrome_user_id = payload.user_id
        client_id = payload.client_id
        position = payload.last_position

        key = playback_key(navidrome_user_id, client_id)
        state = playbacks.get(key)

        if not state:
            return

        self.update_playtime(state, ts)
        state.last_position = position


    def handle_complete(self, payload: PlaybackState, ts):
        navidrome_user_id = payload.user_id
        client_id = payload.client_id

        key = playback_key(navidrome_user_id, client_id)
        state = playbacks.get(key)

        if not state:
            return

        self.update_playtime(state, ts)
        state.navidrome_completed = True

    def update_playtime(self, state: PlaybackState, now: datetime):
        delta = (now - state.last_event_ts).total_seconds()
        if delta > 0:
            state.accumulated_playtime += int(delta)
        state.last_event_ts = now


    def is_listened(self, state: PlaybackState):
        required = min(
            state.track_duration * MIN_LISTEN_RATIO,
            MIN_LISTEN_SECONDS
        )
        return state.accumulated_playtime >= required
    

    def finalize_play(self, state: PlaybackState, detected_loop=False):
        listened = self.is_listened(state)

        app.db_writer.insert_track_play(
            song=state.last_song,
            played_at=state.play_started_at,
            skipped=not listened,
            user_id=state.user_id,
        )

        print("FINALIZE", {
            "user_id": state.user_id,
            "client_id": state.client_id,
            "last_song": state.last_song,
            "playtime": state.accumulated_playtime,
            "song_finished": listened,
            "skipped": not listened,
            "navidrome_completed": state.navidrome_completed,
            "detected_loop": detected_loop
        })


class DatabaseWriter:
    def __init__(self, conn):
        self.conn = conn
        
    def insert_track_play(self, song: Song, played_at: datetime, skipped: bool, user_id: str):
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
                    "user_id": user_id,
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


app = Flask(__name__)

@app.route("/scrobble", methods=["POST"])
def scrobble():
    log.info("Received scrobble request", payload=request.json)
    payload = request.json
    event = payload["event"]
    ts = parse_ts(payload)

    with lock:
        if event == "start":
            log.info("Received start event", payload=payload)
            #app.music_stream_client.handle_start(payload, ts)

        elif event == "stop":
            log.info("Received stop event", payload=payload)
            #app.music_stream_client.handle_stop(payload, ts)

        elif event == "complete":
            log.info("Received complete event", payload=payload)
            #app.music_stream_client.handle_complete(payload, ts)

    return jsonify({"status": "ok"})

def create_app():
    try:
        conn = psycopg2.connect(**DB_CONFIG) 
    except psycopg2.OperationalError as e:
        log.warning("Database connection error, will retry", error=str(e), exc_info=True)

    app.db_writer = DatabaseWriter(conn)
    app.music_stream_client = MusicStreamClient()

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


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

        self.db.insert_track_play(
            song=song,
            played_at=datetime.fromtimestamp(self.state.start_ts / 1000),
            skipped=skipped,
        )

    def _reset(self, song: Song):
        self.state = PlaybackState(
            last_song=song,
            accumulated_playtime=0,
            last_position=0,
            start_ts=now_ms(),
        )
