import psycopg2
import select
import json
import requests
import time


from config import DB_CONFIG, CHANNEL, LASTFM_API_KEY

LASTFM_BASE = "http://ws.audioscrobbler.com/2.0"

def get_artist_genres(artist_name: str) -> list[str]:
    params = {
        "method": "artist.getTopTags",
        "api_key": LASTFM_API_KEY,
        "artist": artist_name,
        "format": "json"
    }
    response = requests.get(LASTFM_BASE, params=params)
    data = response.json()
    print(data)
    tags = data.get("toptags", {}).get("tag", [])
    print(tags)
    genres = [tag["name"] for tag in tags if "name" in tag and tag.get("count", 0) > 50]
    print(genres)
    return genres

def write_genres_to_db(conn, artist_id: int, genres: list[str]):
    for genre in genres:
        with conn.cursor() as cur:
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
                (artist_id, genre),
            )
                
def finish_task(conn, workflow_id: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE workflow_state
            SET genre_done = true
            WHERE workflow_id = %s
            """,
            (workflow_id,),
        )

def get_workflow_status(conn, workflow_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT init_done
            FROM workflow_state
            WHERE workflow_id = %s
            """,
            (workflow_id,),
        )
        result = cur.fetchone()
        if result:
            return result[0]
        return False

def handle_notify(conn, payload):
    artist_id = int(payload.get('id'))
    artist_name = payload.get('name')
    artist_workflow_id = payload.get('workflow_id')

    while True:
         status = get_workflow_status(conn, artist_workflow_id)
         if status:
             break
         print(f"Workflow {artist_workflow_id} not initialized yet. Waiting...")
         time.sleep(2)

    print(f"Handling notification for artist ID: {artist_id}, Name: {artist_name}")

    genres = get_artist_genres(artist_name)
    print(f"Genres for artist {artist_name}: {genres}")

    write_genres_to_db(conn, artist_id, genres)
    finish_task(conn, artist_workflow_id)

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
