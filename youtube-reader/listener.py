"""
YouTube Reader Listener
"""
import json
import select
import threading
import time
from dataclasses import dataclass
from typing import Optional, Any, Dict
from contextlib import closing

import psycopg2
from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicError

from config import DB_CONFIG, CHANNEL
from logger import log

WORKER_COUNT = 4
POLL_INTERVAL = 5  # seconds

# Data models

@dataclass(frozen=True)
class Track:
    track_id: int
    title: str
    artist: str
    workflow_id: str


@dataclass(frozen=True)
class SongEnriched(Track):
    youtube_code: str


# YouTube

class YouTubeClient:
    _ytmusic_client: Optional[YTMusic] = None

    def _get_client(self) -> Optional[YTMusic]:
        """
        Return a cached YTMusic client or create one.

        :return: YTMusic client or None if creation failed
        :rtype: Optional[YTMusic]
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
        
    def fetch_track(self) -> Optional[Track]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, a.name, t.title, t.workflow_id
                FROM tracks t
                JOIN artists a ON t.artist_id = a.id
                JOIN albums al ON t.album_id = al.id
                WHERE t.youtube_code IS NULL
                ORDER BY t.created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()

        if not row:
            return None

        return Track(
            track_id=row[0],
            artist=row[1],
            title=row[2],
            workflow_id=row[3],
        )


class DatabaseWriter:
    def __init__(self, conn):
        self.conn = conn

    def write_song(self, song: SongEnriched) -> bool:
        """
        Write the YouTube code for the song into the database.

        :param song: Enriched song with YouTube code
        :type song: SongEnriched
        :return: True if successful, False otherwise
        :rtype: bool
        """
        with self.conn:
            if not self._insert_youtube_code(song):
                return False
            if song.workflow_id:
                return self._finish_task(song.workflow_id)
            return True

    def _insert_youtube_code(self, song: SongEnriched) -> bool:
        """
        Insert the YouTube code into the tracks table.
        
        :param song: Enriched song with YouTube code
        :type song: SongEnriched
        :return: True if successful, False otherwise
        :rtype: bool
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tracks
                    SET youtube_code = %s,
                        download_status = 'queued'
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
        
    def mark_loading(self, track: Track) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET youtube_code = 'loading'
                WHERE id = %s
                AND youtube_code IS NULL
                """,
                (track.track_id,),
            )
        self.conn.commit()
        return cur.rowcount > 0
    
    def mark_error(self, track: Track):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET youtube_code = 'error'
                WHERE id = %s
                """,
                (track.track_id,),
            )
        self.conn.commit()
    

# Helpers

def enrich_song(track: Track) -> Optional[SongEnriched]:
    """
    Enrich the song payload with artist name and YouTube code.
    
    :param conn: Database connection
    :param track: Track object
    :type track: Track
    :return: Enriched song or None if enrichment failed
    :rtype: Optional[SongEnriched]
    """
    youtube_code = YouTubeClient().search_song(track.artist, track.title)
    if not youtube_code:
        return None

    return SongEnriched(
        **track.__dict__,
        youtube_code=youtube_code,
    )


# Worker Loop

def worker_loop(worker_id: int):
    log.info(f"[worker-{worker_id}] started")

    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        reader = DatabaseReader(conn)
        writer = DatabaseWriter(conn)

        while True:
            track = None
            try:
                track = reader.fetch_track()

                if not track:
                    time.sleep(POLL_INTERVAL)
                    continue

                if not writer.mark_loading(track):
                    log.debug(f"[worker-{worker_id}] track already claimed")
                    time.sleep(POLL_INTERVAL)
                    continue

                log.info(f"[worker-{worker_id}] processing track {track.track_id}")

                updated_track = enrich_song(track)
                if not updated_track:
                    log.info(f"[worker-{worker_id}] enrichment failed for track {track.track_id}")
                    time.sleep(POLL_INTERVAL)
                    continue

                writer.write_song(updated_track)
                log.info(f"[worker-{worker_id}] finished track {track.track_id}")

            except Exception as e:
                log.error(f"[worker-{worker_id}] error: {e}", exc_info=True)
                if track:
                    writer.mark_error(track)
                time.sleep(2)


# Entrypoint

def main():
    threads = []

    for i in range(WORKER_COUNT):
        t = threading.Thread(target=worker_loop, args=(i,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()


if __name__ == "__main__":
    main()