"""
Genre Reader Listener
"""
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Optional, List
from contextlib import closing
import threading
import time

import psycopg2
import requests
from listener_framework import NotificationListener

from config import DB_CONFIG, CHANNEL, LASTFM_API_KEY, LASTFM_BASE
from logger import log

WORKER_COUNT = 1
POLL_INTERVAL = 5  # seconds

# Data models

@dataclass(frozen=True)
class ArtistPayload:
    artist_id: int
    artist_name: str

# Genre Reader

class GenreReader:
    _request_session: Optional[requests.Session] = None

    def _get_session(self) -> Optional[requests.Session]:
        """
        Return a cached requests session or create one.

        :return: requests session or None if creation failed
        :rtype: Optional[requests.Session]
        """
        if self._request_session:
            return self._request_session

        self._request_session = requests.Session()
        log.debug("Initialized requests session for Last.fm API")
        return self._request_session
    
    def fetch_genres(self, artist_name: str) -> Optional[List[str]]:
        """
        Fetch genres for the given artist name from Last.fm API.

        :param artist_name: Name of the artist
        :type artist_name: str
        :return: List of genres or None if fetching failed
        :rtype: Optional[list[str]]
        """
        if not artist_name:
            log.warning("Empty artist name in notification; skipping")
            return None

        params = {
            "method": "artist.getTopTags",
            "api_key": LASTFM_API_KEY,
            "artist": artist_name,
            "format": "json",
        }

        session = self._get_session()
        if not session:
            return None

        try:
            response = session.get(LASTFM_BASE, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            log.error("Error fetching genres from Last.fm",
                      artist_name=artist_name,
                      error=str(e))
            return None

        try:
            data = response.json()
        except JSONDecodeError as e:
            log.error("Invalid JSON from Last.fm", artist_name=artist_name, error=str(e))
            return None

        log.debug("Last.fm API response", artist_name=artist_name, data=data)

        tags = data.get("toptags", {}).get("tag", [])
        if not isinstance(tags, list):
            log.warning("Last.fm returned unexpected tag structure", artist_name=artist_name)
            return None

        try:
            genres = [tag["name"] for tag in tags if "name" in tag and tag.get("count", 0) > 50]
        except (TypeError, KeyError) as e:
            log.error("Error parsing genres from Last.fm response",
                      artist_name=artist_name,
                      error=str(e))
            return None

        if not genres:
            log.debug("No genres passed threshold for artist", artist_name=artist_name)
        else:
            log.info("Fetched genres for artist", artist_name=artist_name, genres=genres)
        return genres


class DatabaseWriter:

    def __init__(self, conn):
        self.conn = conn

    def process_artist_genres(self, artist: ArtistPayload, genres: list) -> bool:
        """
        Fetch genres for the artist and write them to the database.

        :param artist: Artist payload with artist_id, artist_name
        :type artist: ArtistPayload
        :param genres: List of genres
        :type genres: list[str]
        :return: True if successful, False otherwise
        :rtype: bool
        """
        if genres is None:
            return False
        
        if genres == []:
            return True

        if self._write_genres_to_db(artist, genres):
            return self._finish_task(artist)
        return False

    def _write_genres_to_db(self, artist: ArtistPayload, genres: List[str])  -> bool:
        """
        Write genres to the database and associate them with the artist.

        :param artist: Artist payload with artist_id, artist_name
        :type artist: ArtistPayload
        :param genres: List of genres
        :type genres: list[str]
        :return: True if all genres were written successfully.
        :rtype: bool
        """
        for genre in genres:
            try:
                with self.conn.cursor() as cur:
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
                        (artist.artist_id, genre),
                    )
            except psycopg2.Error as e:
                # Attempt to rollback any failed transaction; safe when autocommit is set.
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                log.error("Error writing genre to database",
                          artist_id=artist.artist_id,
                          genre=genre,
                          error=str(e))
                continue
            log.debug("Wrote genre to database", artist_id=artist.artist_id, genre=genre)
        return True
    
    def mark_loading(self, artist: ArtistPayload) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE artists
                SET genre_status = 'loading'
                WHERE id = %s
                AND genre_status = 'none'
                """,
                (artist.artist_id,),
            )
        self.conn.commit()
        return cur.rowcount > 0
    
    def mark_error(self, artist: ArtistPayload):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE artists
                SET genre_status = 'error'
                WHERE id = %s
                """,
                (artist.artist_id,),
            )
        self.conn.commit()

    def _finish_task(self, artist: ArtistPayload):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE artists
                SET genre_status = 'done'
                WHERE id = %s
                """,
                (artist.artist_id,),
            )
        self.conn.commit()
        return cur.rowcount > 0
    

class DatabaseReader:
    def __init__(self, conn):
        self.conn = conn

    def fetch_artist(self) -> Optional[ArtistPayload]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.id,
                    a.name
                FROM artists a
                WHERE a.genre_status = 'none'
                ORDER BY a.id ASC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

        if not row:
            return None

        return ArtistPayload(
            artist_id=row[0],
            artist_name=row[1],
        )

# Worker Loop

def worker_loop(worker_id: int):
    log.info(f"[worker-{worker_id}] started")

    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        reader = DatabaseReader(conn)
        writer = DatabaseWriter(conn)

        while True:
            artist = None
            try:
                artist = reader.fetch_artist()

                if not artist:
                    time.sleep(POLL_INTERVAL)
                    continue

                if not writer.mark_loading(artist):
                    log.debug(f"[worker-{worker_id}] artist already claimed")
                    time.sleep(POLL_INTERVAL)
                    continue

                log.info(f"[worker-{worker_id}] processing artist {artist.artist_id}")

                genres = GenreReader().fetch_genres(artist.artist_name)
                if not genres:
                    log.info(f"[worker-{worker_id}] fetching genres failed for {artist.artist_id}")
                    time.sleep(POLL_INTERVAL)
                    continue

                writer.process_artist_genres(artist, genres)
                log.info(f"[worker-{worker_id}] finished artist {artist.artist_id}")

            except Exception as e:
                log.error(f"[worker-{worker_id}] error: {e}", exc_info=True)
                if artist:
                    writer.mark_error(artist)
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