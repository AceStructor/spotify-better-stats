import os
import time
import requests
from flask import Flask, request, jsonify
from typing import Optional, List
from dataclasses import dataclass

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extras import execute_values

from logger import log
from config import DB_CONFIG
from sql_queries import INSERT_SQL

app = Flask(__name__)

MB_BASE = "https://musicbrainz.org/ws/2"
USER_AGENT = "MusikmanagementApp/1.0 (your@email.com)"


@dataclass
class Track:
    artist: str
    album: str
    title: str
    duration: int


class DatabaseWriter:

    def __init__(self, conn):
        self.conn = conn

    def insert_track(self, track: Track) -> None:
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(INSERT_SQL, {
                    "artist_name": track.artist,
                    "album_title": track.album,
                    "track_title": track.title,
                    "duration_ms": track.duration,
                })
            self.conn.commit()
            log.debug("Inserted track", track_title=track.title)
        except psycopg2.Error as e:
            log.error("Error inserting track", error=str(e), exc_info=True)
            self.conn.rollback()

    def bulk_insert_tracks(self, tracks: list[Track]) -> int:
        if not tracks:
            return 0

        values = [
            (t.artist, t.album, t.title, t.duration)
            for t in tracks
        ]

        try:
            with self.conn.cursor() as cur:
                execute_values(cur, INSERT_SQL, values)
            self.conn.commit()
            return len(values)
        except psycopg2.Error as e:
            self.conn.rollback()
            log.error("Bulk insert failed", error=str(e), exc_info=True)
            return 0


class MusicBrainzClient:

    _session: Optional[requests.Session] = None
    _last_request_time: float = 0.0

    def __init__(self):
        self.base_url = MB_BASE

    def _get_session(self) -> requests.Session:
        if not self._session:
            self._session = requests.Session()
            self._session.headers.update({
                "User-Agent": USER_AGENT
            })
        return self._session

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

    def _get(self, endpoint: str, params: dict) -> dict:
        self._rate_limit()
        session = self._get_session()

        url = f"{self.base_url}/{endpoint}"
        params["fmt"] = "json"

        response = session.get(url, params=params, timeout=10)
        response.raise_for_status()

        self._last_request_time = time.time()
        return response.json()

    # -----------------------------------
    # Fetch single recording by MBID
    # -----------------------------------

    def fetch_recording(self, mbid: str) -> Track:
        data = self._get(f"recording/{mbid}", {
            "inc": "artists+releases"
        })

        artist = data["artist-credit"][0]["name"]
        album = None

        if "releases" in data and data["releases"]:
            album = data["releases"][0]["title"]

        return Track(
            artist=artist,
            album=album,
            title=data["title"],
            duration=data.get("length")
        )

    # -----------------------------------
    # Fetch release (album) by MBID
    # -----------------------------------

    def fetch_release(self, mbid: str) -> List[Track]:
        data = self._get(f"release/{mbid}", {
            "inc": "recordings+artists"
        })

        tracks = []

        for medium in data["media"]:
            for t in medium["tracks"]:
                recording = t["recording"]

                tracks.append(
                    Track(
                        artist=recording["artist-credit"][0]["name"],
                        album=data["title"],
                        title=recording["title"],
                        duration=recording.get("length")
                    )
                )

        return tracks

    # -----------------------------------
    # Fetch artist recordings (paged)
    # -----------------------------------

    def fetch_artist_recordings(self, artist_mbid: str) -> List[Track]:
        tracks = []
        offset = 0
        limit = 100

        while True:
            data = self._get("recording", {
                "artist": artist_mbid,
                "limit": limit,
                "offset": offset
            })

            recordings = data.get("recordings", [])
            if not recordings:
                break

            for r in recordings:
                tracks.append(
                    Track(
                        artist=r["artist-credit"][0]["name"],
                        album=None,
                        title=r["title"],
                        duration=r.get("length")
                    )
                )

            offset += limit

        return tracks


# -------------------------
# API Endpoints
# -------------------------
app = Flask(__name__)


@app.route("/album", methods=["POST"])
def add_album():
    mbid = request.json.get("mbid")

    if not mbid:
        return {"error": "mbid missing"}, 400

    tracks = MusicBrainzClient().fetch_release(mbid)
    log.info("Fetched album tracks", mbid=mbid, track_count=len(tracks))
    log.debug("Track details", tracks=[t.__dict__ for t in tracks])
    inserted =  app.db_writer.bulk_insert_tracks(tracks)

    return jsonify({
        "mbid": mbid,
        "tracks_fetched": len(tracks),
        "tracks_inserted": inserted
    })


@app.route("/track", methods=["POST"])
def add_track():
    mbid = request.json.get("mbid")

    if not mbid:
        return {"error": "mbid missing"}, 400

    track = MusicBrainzClient().fetch_recording(mbid)
    log.info("Fetched track", mbid=mbid, title=track.title)
    log.debug("Track details", track=track.__dict__)
    inserted = app.db_writer.batch_insert_tracks([track])

    return jsonify({
        "mbid": mbid,
        "tracks_inserted": inserted
    })


def create_app():
    try:
        conn = psycopg2.connect(**DB_CONFIG) 
    except psycopg2.OperationalError as e:
        log.warning("Database connection error, will retry", error=str(e), exc_info=True)

    app.db_writer = DatabaseWriter(conn)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
