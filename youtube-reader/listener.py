"""
YouTube Reader Listener
"""
import json
import select
import time
from dataclasses import dataclass
from typing import Optional, Any, Dict

import psycopg2
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicError

from config import DB_CONFIG, CHANNEL
from logger import log


# Data models

@dataclass(frozen=True)
class SongPayload:
    track_id: int
    title: str
    artist_id: int
    workflow_id: str


@dataclass(frozen=True)
class SongEnriched(SongPayload):
    artist: str
    youtube_code: str


# YouTube

class YouTubeClient:
    _ytmusic_client: Optional[YTMusic] = None

    def _get_client(self) -> Optional[YTMusic]:
        """
        Return a cached YTMusic client or create one.

        Returns None if the client cannot be created.
        """
        if self._ytmusic_client:
            return self._ytmusic_client

        try:
            self._ytmusic_client = YTMusic()
            log.debug("Initialized YTMusic client")
            return self._ytmusic_client
        except Exception:
            log.error("Failed to initialize YTMusic client")
            return None

    def search_song(self, artist: str, title: str) -> Optional[str]:
        """
        Fetch the YouTube video ID for the given artist and track name.

        :param artist: Artist name
        :type artist: str
        :param title: Track name
        :type title: str
        :return: YouTube video ID or None if not found
        :rtype: Optional[str]
        """
        if not artist or not title:
            log.warning("Artist or title empty",
                        artist=artist,
                        title=title)
            return None

        client = self._get_client()
        if not client:
            return None

        query = f"{artist} {title}"
        try:
            results = client.search(query, filter="songs", limit=5)
        except YTMusicError:
            log.warning("YTMusic search failed", query=query)
            return None
        except Exception:
            log.warning("Unexpected error during YTMusic search", query=query)
            return None

        if not results:
            log.debug("No YouTube results found", query=query)
            return None

        video_id = results[0].get("videoId")
        if not video_id:
            log.warning("No videoId in YouTube result", query=query)
            return None

        log.debug("Fetched YouTube video ID", query=query, video_id=video_id)
        return video_id


# Database

class DatabaseReader:
    def __init__(self, conn):
        self.conn = conn

    def fetch_artist_name(self, artist_id: int) -> Optional[str]:
        """
        Fetch the artist name from the database given the artist ID.
        
        :param conn: Database connection
        :param artist_id: Artist ID
        :type artist_id: int
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT name
                    FROM artists
                    WHERE id = %s
                    """,
                    (artist_id,),
                )
                row = cur.fetchone()

            if not row:
                log.warning("Artist not found", artist_id=artist_id)
                return None

            return row[0]

        except psycopg2.Error:
            log.error("Database error while fetching artist", artist_id=artist_id)
            return None


class DatabaseWriter:
    def __init__(self, conn):
        self.conn = conn

    def write_song(self, song: SongEnriched) -> bool:
        with self.conn:
            if not self._insert_youtube_code(song):
                return False
            return self._finish_task(song.workflow_id)

    def _insert_youtube_code(self, song: SongEnriched) -> bool:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tracks
                    SET youtube_code = %s
                    WHERE id = %s
                    """,
                    (song.youtube_code, song.track_id),
                )

            if cur.rowcount == 0:
                log.warning(
                    "No track updated",
                    track_id=song.track_id,
                    youtube_code=song.youtube_code,
                )
                return False

            log.info(
                "YouTube code written",
                track_id=song.track_id,
                youtube_code=song.youtube_code,
            )
            return True

        except psycopg2.Error:
            log.error("Database error while writing YouTube code", track_id=song.track_id)
            return False

    def _finish_task(self, workflow_id: str) -> bool:
        """
        Mark the workflow task as done in the database.

        Returns True if the workflow state row was updated.
        
        :param workflow_id: Workflow ID
        :type workflow_id: int
        :return: True if updated, False otherwise
        :rtype: bool
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_state
                    SET yt_done = true
                    WHERE workflow_id = %s
                    """,
                    (workflow_id,),
                )

            if cur.rowcount == 0:
                log.warning("No workflow updated", workflow_id=workflow_id)
                return False

            log.debug("Workflow finished", workflow_id=workflow_id)
            return True

        except psycopg2.Error:
            log.exception("Database error while finishing workflow", workflow_id=workflow_id)
            return False


# Notification handling

def parse_payload(payload: Dict[str, Any]) -> Optional[SongPayload]:
    if not payload:
        log.warning("Empty payload received")
        return None

    try:
        return SongPayload(
            track_id=int(payload["id"]),
            title=payload.get("title", ""),
            artist_id=int(payload["artist_id"]),
            workflow_id=str(payload["workflow_id"]),
        )
    except (KeyError, TypeError, ValueError):
        log.error("Invalid payload", payload=payload)
        return None


def enrich_song(conn, payload: SongPayload) -> Optional[SongEnriched]:
    reader = DatabaseReader(conn)
    artist = reader.fetch_artist_name(payload.artist_id)
    if not artist:
        return None

    youtube_code = YouTubeClient().search_song(artist, payload.title)
    if not youtube_code:
        return None

    return SongEnriched(
        **payload.__dict__,
        artist=artist,
        youtube_code=youtube_code,
    )


def handle_notification(conn, notify) -> None:
    payload_raw = json.loads(notify.payload)
    payload = parse_payload(payload_raw)
    if not payload:
        return

    log.info("Processing track", track_id=payload.track_id, title=payload.title)

    enriched = enrich_song(conn, payload)
    if not enriched:
        log.info("Song enrichment failed", track_id=payload.track_id)
        return

    DatabaseWriter(conn).write_song(enriched)


# Listener

def listen_forever() -> None:
    while True:
        try:
            log.info("Connecting to database")
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"LISTEN {CHANNEL};")

                while True:
                    ready, _, _ = select.select([conn], [], [], 5.0)
                    if not ready:
                        log.debug("Waiting for notifications...")
                        continue

                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        handle_notification(conn, notify)

        except psycopg2.OperationalError:
            log.exception("Database connection error, retrying")
            time.sleep(5)
        except KeyboardInterrupt:
            log.info("Listener interrupted, shutting down")
            break
        except Exception:
            log.exception("Unhandled listener error")
            time.sleep(5)


if __name__ == "__main__":
    listen_forever()
