import os
import json
import asyncio
import threading

from nio import AsyncClient, LoginResponse
from config import MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD, TOKEN_FILE, MATRIX_ROOM_ID

matrix_queue = asyncio.Queue()
matrix_loop = asyncio.new_event_loop()

def ensure_token_dir():
    token_dir = os.path.dirname(TOKEN_FILE)
    if token_dir:
        os.makedirs(token_dir, exist_ok=True)


async def get_matrix_client() -> AsyncClient:
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER)

    # Sicherstellen, dass das Verzeichnis existiert
    ensure_token_dir()

    # 1) Session laden (falls vorhanden)
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            session = json.load(f)

        client.access_token = session.get("access_token")
        client.user_id = session.get("user_id")
        client.device_id = session.get("device_id")
        client.sync_token = session.get("sync_token")

        if client.access_token:
            print("Matrix-Session geladen.")

    # 2) Login nur wenn nötig
    if not client.access_token:
        print("Matrix Login (First Run)...")
        resp = await client.login(MATRIX_PASSWORD)

        if not isinstance(resp, LoginResponse):
            raise RuntimeError(f"Matrix login failed: {resp}")

        # Atomisch schreiben
        tmp_file = f"{TOKEN_FILE}.tmp"
        with open(tmp_file, "w") as f:
            json.dump(
                {
                    "access_token": resp.access_token,
                    "user_id": resp.user_id,
                    "device_id": resp.device_id,
                },
                f,
            )

        os.replace(tmp_file, TOKEN_FILE)
        print("Matrix-Session gespeichert.")

    return client

async def matrix_worker(client):
    while True:
        content = await matrix_queue.get()
        try:
            await client.room_send(
                room_id=MATRIX_ROOM_ID,
                message_type="m.room.message",
                content=content,
            )
        except Exception as e:
            print(f"[WARN] Matrix send failed: {e}", flush=True)
        finally:
            matrix_queue.task_done()

def start_matrix_worker(client):
    global matrix_queue

    asyncio.set_event_loop(matrix_loop)
    matrix_queue = asyncio.Queue()

    matrix_loop.create_task(
        client.sync_forever(timeout=30000, full_state=False)
    )

    matrix_loop.create_task(matrix_worker(client))
    matrix_loop.run_forever()

def send_matrix_message(content: dict):
    asyncio.run_coroutine_threadsafe(
        matrix_queue.put(content),
        matrix_loop,
    )