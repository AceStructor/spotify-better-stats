import psycopg2
import select
import json
import requests


from config import DB_CONFIG, CHANNEL, LASTFM_API_KEY
from listener import get_artist_genres, write_genres_to_db

def update_old_entries():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM artist_genres
            """
        )
        cur.execute(
            """
            SELECT id, name
            FROM artists
            """
        )
        artists = cur.fetchall()
    for artist_id, artist_name in artists:
        genres = get_artist_genres(artist_name)
        write_genres_to_db(conn, artist_id, genres)
    conn.commit()
    conn.close()