"""
YouTube Reader Listener
"""
import select
from dataclasses import dataclass
import json
import time
from typing import Optional, Any, Dict
import psycopg2
from logger import log

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicError

from config import DB_CONFIG, CHANNEL


@dataclass
class SongPayload:
    track_id: int
    title: str
    artist_id: int
    workflow_id: str

@dataclass
class SongEnriched(SongPayload):
    artist: str
    youtube_code: str

class YouTubeClient:
    _ytmusic_client: Optional[YTMusic] = None

    def __init__(self, song: Song):
        self.song = song

    def _get_ytmusic_client(self) -> Optional[YTMusic]:
        """Return a cached YTMusic client or create one.

        Returns None if the client cannot be created.
        """
        if self._ytmusic_client is not None:
            return self._ytmusic_client

        try:
            self._ytmusic_client = YTMusic()
            log.debug("Initialized YTMusic client")
            return self._ytmusic_client
        except Exception:
            log.error("Failed to initialize YTMusic client")
            return None
    
    def search_song(self) -> Optional[str]:
        """
        Fetch the YouTube video ID for the given artist and track name.

        :param artist_name: Artist name
        :type artist_name: str
        :param track_name: Track name
        :type track_name: str
        """
        if not self.song.artist or not self.song.title:
            log.warning("Empty artist or track name provided",
                        artist_name=self.song.artist,
                        track_name=self.song.title)

        client = self._get_ytmusic_client()
        if client is None:
            log.warning("No YTMusic client available")

        query = f"{self.song.artist} {self.song.title}"
        try:
            results = client.search(query, filter="songs", limit=5)
        except YTMusicError:
            log.warning("YTMusic search failed",
                          artist_name=self.song.artist,
                          track_name=self.song.title,
                          query=query)

        except Exception:
            log.warning("Unexpected error during YTMusic search",
                          artist_name=self.song.artist,
                          track_name=self.song.title,
                          query=query)

        if not results:
            log.debug("No YouTube results found", artist_name=self.song.artist, track_name=self.song.title)

        video_id = results[0].get("videoId")
        if not video_id:
            log.warning("No video ID in first YouTube result",
                        artist_name=self.song.artist,
                        track_name=self.song.title)

        log.debug("Fetched YouTube video ID",
                  artist_name=self.song.artist,
                  track_name=self.song.title,
                  video_id=video_id)
        
        self.song.youtube_code = video_id

class DatabaseWriter:
    def __init__(self, conn, song: Song):
        self.conn = conn
        self.song = song

    def process_song(self):
        """
        Process the song: fetch artist name and write YouTube code to DB.
        """
        self._get_artist_name()
        if not self.song.artist:
            log.info("No artist name found, skipping YouTube search",
                     artist_id=self.song.artist_id,
                     track_id=self.song.track_id)
            return

        yt_client = YouTubeClient(self.song)
        yt_client.search_song()
        if not self.song.youtube_code:
            log.info("No YouTube code found for track",
                     track_id=self.song.track_id,
                     artist_name=self.song.artist,
                     track_name=self.song.title)
            return

        self._insert_youtube_code()
        self._finish_task()

    def _get_artist_name(self):
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
                    (self.song.artist_id,),
                )
                result = cur.fetchone()

            if not result:
                log.warning("Artist not found", artist_id=self.song.artist_id)

            self.song.artist = result[0] if result else ""
            log.debug("Fetched artist name", artist_id=self.song.artist_id, artist_name=self.song.artist)

        except psycopg2.Error:
            log.error("Database error while fetching artist name", artist_id=self.song.artist_id)
        
    def _insert_youtube_code(self):
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE tracks
                    SET youtube_code = %s
                    WHERE id = %s
                    """,
                    (self.song.youtube_code or None, self.song.track_id),
                )
                rowcount = cur.rowcount

            if rowcount == 0:
                log.warning("No track row updated when writing YouTube code",
                            artist_id=self.song.artist_id,
                            youtube_code=self.song.youtube_code)
                return False

            log.info("Wrote YouTube code to DB", artist_id=self.song.artist_id, youtube_code=self.song.youtube_code)
            return True

        except psycopg2.Error:
            log.error("Database error while writing YouTube code",
                          artist_id=self.song.artist_id,
                          youtube_code=self.song.youtube_code)
            return False
        
    def _finish_task(self) -> bool:
        """
        Mark the workflow task as done in the database.

        Returns True if the workflow state row was updated.
        
        :param conn: Database connection
        :param workflow_id: Workflow ID
        :type workflow_id: int
        """

        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_state
                    SET yt_done = true
                    WHERE workflow_id = %s
                    """,
                    (self.song.workflow_id,),
                )
                rowcount = cur.rowcount

            if rowcount == 0:
                log.warning("No workflow row updated when finishing task", workflow_id=self.song.workflow_id)
                return False

            log.debug("Finished workflow task", workflow_id=self.song.workflow_id)
            return True

        except psycopg2.Error:
            log.error("Database error while finishing workflow task", workflow_id=self.song.workflow_id)
            return False


def handle_notify(payload: Dict[str, Any], song: Song):
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

        song.track_id = int(track_id_raw)
        song.title = payload.get('title', '')
        song.artist_id = payload.get('artist_id')
        song.workflow_id = payload.get('workflow_id')

        log.info("Handled notification", track_id=song.track_id, track_name=song.title)
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
            with psycopg2.connect(**DB_CONFIG) as conn:
                cur = conn.cursor()
                cur.execute(f"LISTEN {CHANNEL};")

                while True:
                    ready = select.select([conn], [], [], 5.0)
                    if not ready[0]:
                        log.debug("Select timeout, still listening...")
                        continue

                    conn.poll()
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        log.debug("Received notification", pid=notify.pid)
                        payload = json.loads(notify.payload)
                        song = Song(
                            track_id=0,
                            title="",
                            artist_id=0,
                            artist="",
                            youtube_code="",
                            workflow_id="",
                        )
                        handle_notify(payload, song)
                        db_writer = DatabaseWriter(conn, song)
                        db_writer.process_song()
        except psycopg2.OperationalError as e:
            log.warning("Database connection error, will retry", error=str(e), exc_info=True)
            time.sleep(5)
            continue
        except KeyboardInterrupt:
            log.info("Listener interrupted; shutting down gracefully")
            break
        except Exception as e:
            log.error("Uncaught error in listener loop", error=str(e), exc_info=True)
            time.sleep(5)

if __name__ == "__main__":
    listen_forever()
