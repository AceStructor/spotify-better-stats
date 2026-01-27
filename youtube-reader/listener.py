import psycopg2
import select
import json
import requests
import time
from ytmusicapi import YTMusic


from config import DB_CONFIG, CHANNEL

def get_artist_name(conn, artist_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT name
            FROM artists
            WHERE id = %s
            """,
            (artist_id,),
        )
        result = cur.fetchone()
        return result[0] if result else ""

def get_youtube_code(artist_name: str, track_name: str) -> str:
    ytmusic = YTMusic()

    query = f"{artist_name} {track_name}"
    results = ytmusic.search(query, filter="songs", limit=5)

    if not results:
        return None

    # Erstes Ergebnis nehmen
    video_id = results[0].get("videoId")
    if not video_id:
        return None

    return video_id

def write_youtube_code_to_db(conn, track_id: int, youtube_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tracks
            SET youtube_code = %s
            WHERE id = %s
            """,
            (youtube_code, track_id),
        )

def finish_task(conn, workflow_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE workflow_state
            SET yt_done = true
            WHERE workflow_id = %s
            """,
            (workflow_id,),
        )

def handle_notify(conn, payload):
    track_id = int(payload.get('id'))
    track_name = payload.get('title')
    artist_id = payload.get('artist_id')
    title_workflow_id = payload.get('workflow_id')
    print(f"Handling notification for track ID: {track_id}, Name: {track_name}")

    artist_name = get_artist_name(conn, artist_id)

    youtube_code = get_youtube_code(artist_name, track_name)

    write_youtube_code_to_db(conn, track_id, youtube_code)
    finish_task(conn, title_workflow_id)

def listen_forever():
    while True:
        try:
            print("entered try...")
            conn = psycopg2.connect(**DB_CONFIG)
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)

            cur = conn.cursor()
            cur.execute(f"LISTEN {CHANNEL};")

            while True:
                print("entered listening loop...")
                select.select([conn], [], [])
                conn.poll()

                while conn.notifies:
                    print("notified!")
                    notify = conn.notifies.pop(0)
                    payload = json.loads(notify.payload)
                    handle_notify(conn, payload)

        except Exception as e:
            print(f"Fehler: {e}")
            time.sleep(5)

if __name__ == "__main__":
    listen_forever()
