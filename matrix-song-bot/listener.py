import psycopg2
import select
import json
import time
import asyncio
import threading

from nio.exceptions import LocalProtocolError
from config import DB_CONFIG, CHANNEL, MATRIX_ROOM_ID
from matrix_client import get_matrix_client, start_matrix_worker, send_matrix_message

listener_state = {"matrix_client": None}

# class MatrixSendError(Exception):
#     pass

# async def send_matrix_message(client, msgContent: dict):
#     try:
#         await client.room_send(
#             room_id=MATRIX_ROOM_ID,
#             message_type="m.room.message",
#             content=msgContent,
#         )

#     except LocalProtocolError as e:
#         # z. B. kaputte Session / closed transport
#         raise MatrixSendError(f"Matrix protocol error: {e}") from e

#     except Exception as e:
#         raise MatrixSendError(f"Matrix send failed: {e}") from e

def on_new_row(track_play: dict, previous_track_play: dict):
    song_url = f'https://music.youtube.com/watch?v={track_play["youtube_code"]}'
    # msg = (
    #     "📢 New DB Row!:\n"
    #     f"🆔 Title: {track_play['title']}\n"
    #     f"📦 Artist: {track_play['artist']}\n"
    #     f"🕒 Genres: {track_play['genres']}\n"
    #     f"🕒 Skipped: {track_play['skipped']}\n"
    #     f"🕒 URL: {song_url}"
    # )
    genres = track_play.get('genres') or []
    genreString = ', '.join(g for g in genres if g)
    
    msg = (
        f"**Title:** [{track_play['artist']} - {track_play['title']}]({song_url})\n"
        f"**Genre:** {track_play['genres']}\n"
        f"**---**"
    )
    content = {
        "msgtype": "m.text",
        "body": (
            f"Title: {track_play['artist']} - {track_play['title']}\n"
            f"Genre: {genreString}"
        ),
        "format": "org.matrix.custom.html",
        "formatted_body": (
            f"<strong>Title:</strong> "
            f"<a href=\"{song_url}\">"
            f"{track_play['artist']} - {track_play['title']}"
            f"</a><br>"
            f"<strong>Genre:</strong> {genreString}<br>"
            f"<hr>"
        ),
    }

    print(msg)

    repeat = (track_play['title'] == previous_track_play['title']) and (track_play['artist'] == previous_track_play['artist'])

    if (track_play['skipped'] or repeat):
        print("This song will not be posted!")
        return
    
    send_matrix_message(content)

def get_track_play_by_id(conn, track_plays_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.title,
                a.name      AS artist,
                array_agg(g.name ORDER BY g.name) AS genres,
                tp.skipped,
                t.youtube_code
            FROM track_plays tp
            JOIN tracks t   ON t.id = tp.track_id
            JOIN artists a  ON a.id = t.artist_id
            LEFT JOIN artist_genres ag ON ag.artist_id = a.id
            LEFT JOIN genres g         ON g.id = ag.genre_id
            WHERE tp.id = %s
            GROUP BY
                t.title,
                a.name,
                tp.skipped,
	            t.youtube_code
            """,
            (track_plays_id,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "title": row[0],
        "artist": row[1],
        "genres": row[2],
        "skipped": row[3],
        "youtube_code": row[4],
    }

def get_track_plays_id(conn, workflow_id: int) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM track_plays
            WHERE workflow_id = %s
            """,
            (workflow_id,),
        )
        result = cur.fetchone()
        if result:
            return result[0]
        return None

def handle_notify(conn, payload):
    workflow_id = payload.get('workflow_id')
    genre_required = payload.get('genre_required')
    yt_required = payload.get('yt_required')
    genre_done = payload.get('genre_done')
    yt_done = payload.get('yt_done')    
    init_done = payload.get('init_done')

    if not init_done:
        print(f"Workflow {workflow_id} not initialized yet. Waiting...", flush=True)
        return
    
    if genre_required and not genre_done:
        print(f"Genre for workflow {workflow_id} not done yet. Waiting...", flush=True)
        return

    if yt_required and not yt_done:
        print(f"YouTube for workflow {workflow_id} not done yet. Waiting...", flush=True)
        return
    
    track_plays_id = get_track_plays_id(conn, workflow_id)
    if not track_plays_id:
        print(f"No track plays ID found for workflow {workflow_id}", flush=True)
        return

    track_play = get_track_play_by_id(conn, track_plays_id)
    if not track_play:
        print(f"Track Play {track_plays_id} nicht gefunden", flush=True)
        return

    print(f"Track Play geladen: {track_play}", flush=True)

    previous_track_play = get_track_play_by_id(conn, track_plays_id-1)
    if not previous_track_play:
        print(f"Track Play {track_plays_id-1} nicht gefunden", flush=True)
        return

    on_new_row(track_play, previous_track_play)

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
    listener_state["matrix_client"] = asyncio.run(get_matrix_client())
    threading.Thread(
        target=start_matrix_worker,
        args=(listener_state["matrix_client"],),
        daemon=True,
    ).start()
    listen_forever()
