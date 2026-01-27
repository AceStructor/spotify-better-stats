import psycopg2
import select
import json
import requests
from ytmusicapi import YTMusic


from config import DB_CONFIG, CHANNEL
from listener import get_artist_name, get_youtube_code, write_youtube_code_to_db

def update_old_entries():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, artist_id, title
            FROM tracks
            WHERE youtube_code IS NULL
            """
        )
        tracks = cur.fetchall()
    for track_id, artist_id, track_name in tracks:
        artist_name = get_artist_name(conn, artist_id)
        youtube_code = get_youtube_code(artist_name, track_name)
        write_youtube_code_to_db(conn, track_id, youtube_code)
    conn.commit()
    conn.close()

