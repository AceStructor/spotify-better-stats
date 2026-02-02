"""
Genre Reader Listener
"""
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Optional, List

import psycopg2
import requests
from listener_framework import NotificationListener

from config import DB_CONFIG, CHANNEL, LASTFM_API_KEY, LASTFM_BASE
from logger import log

# Data models

@dataclass(frozen=True)
class ArtistPayload:
    artist_id: int
    artist_name: str
    workflow_id: str

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

        :param artist: Artist payload with artist_id, artist_name, and workflow_id
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

        if self._write_genres_to_db(artist.artist_id, genres):
            return self._finish_task(artist.workflow_id)
        return False

    def _write_genres_to_db(self, artist: ArtistPayload, genres: List[str])  -> bool:
        """
        Write genres to the database and associate them with the artist.

        :param artist: Artist payload with artist_id, artist_name, and workflow_id
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

    def _finish_task(self, artist: ArtistPayload) -> bool:
        """
        Mark the workflow task as done in the database.

        :param artist: Artist payload with artist_id, artist_name, and workflow_id
        :type artist: ArtistPayload
        :return: True if the workflow state row was updated.
        :rtype: bool
        """
        workflow_id = artist.workflow_id
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE workflow_state
                    SET genre_done = true
                    WHERE workflow_id = %s
                    """,
                    (workflow_id,),
                )
        except psycopg2.Error as e:
            log.error("Error finishing workflow task", workflow_id=workflow_id, error=str(e))
            try:
                self.conn.rollback()
            except Exception:
                pass
            return False
        log.debug("Finished workflow task", workflow_id=workflow_id)
        return True


class GenreListener(NotificationListener):
    channel = CHANNEL

    def __init__(self):
        super().__init__(
            db_config=DB_CONFIG,
            logger=log,
        )

    def parse_payload(self, payload: dict) -> Optional[ArtistPayload]:
        """
        Parse the notification payload from the database.

        :param payload: Notification payload from the database
        :return: Parsed payload with artist ID, name, and workflow ID
        :rtype: Optional[ArtistPayload]
        """
        if not isinstance(payload, dict):
            log.warning("Invalid notification payload (not a dict)", payload=payload)
            return None

        try:
            return ArtistPayload(
                artist_id=int(payload["id"]),
                artist_name=payload["name"],
                workflow_id=payload["workflow_id"],
            )
        except (TypeError, ValueError, KeyError) as e:
            log.warning("Malformed notification payload; missing or invalid fields",
                        payload=payload,
                        error=str(e))
            return None

    def handle(self, conn, payload: ArtistPayload) -> None:
        log.info("Processing artist for genre fetching", artist_id=payload.artist_id, artist_name=payload.artist_name)

        genres = GenreReader().fetch_genres(payload.artist_name)
        DatabaseWriter(conn).process_artist_genres(payload, genres)


if __name__ == "__main__":
    GenreListener().run()
