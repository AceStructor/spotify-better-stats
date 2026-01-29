"""
Matrix Client Module
"""
import os
import json
import asyncio

from nio import AsyncClient, LoginResponse
from nio.exceptions import LocalProtocolError
from config import MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD, TOKEN_FILE, MATRIX_ROOM_ID
from logger import log

matrix_queue = asyncio.Queue()
matrix_loop = asyncio.new_event_loop()

def ensure_token_dir():
    """
    Ensure that the directory for the token file exists.
    """
    token_dir = os.path.dirname(TOKEN_FILE)
    if token_dir:
        try:
            os.makedirs(token_dir, exist_ok=True)
            log.debug("Ensured token directory exists", token_dir=token_dir)
        except OSError as e:
            log.error("Failed to ensure token directory exists", error=str(e), token_dir=token_dir)
            raise


async def get_matrix_client() -> AsyncClient:
    """
    Get and return a logged-in Matrix AsyncClient.
    
    :return: Logged-in Matrix AsyncClient
    :rtype: AsyncClient
    """
    client = AsyncClient(MATRIX_HOMESERVER, MATRIX_USER)

    # Sicherstellen, dass das Verzeichnis existiert
    ensure_token_dir()

    # 1) Load session (if available)
    if os.path.isfile(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                session = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Could not load Matrix session file, will perform login",
                        error=str(e),
                        token_file=TOKEN_FILE)
            session = {}

        client.access_token = session.get("access_token")
        client.user_id = session.get("user_id")
        client.device_id = session.get("device_id")
        client.sync_token = session.get("sync_token")

        if client.access_token:
            log.info("Matrix session loaded", user_id=client.user_id)
        else:
            log.debug("No access token found in session file; login required")

    # 2) Login nur wenn nötig
    if not client.access_token:
        log.info("Matrix login required (first run or no valid session)")
        try:
            resp = await client.login(MATRIX_PASSWORD)
            if not isinstance(resp, LoginResponse):
                log.error("Matrix login returned unexpected response", response=repr(resp))
                raise RuntimeError(f"Matrix login failed: {resp}")
        except LocalProtocolError:
            log.error("Matrix login protocol error")
            raise
        except Exception:
            log.error("Matrix login unexpected error")
            raise

        # Save session atomically with error handling
        tmp_file = f"{TOKEN_FILE}.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": resp.access_token,
                        "user_id": resp.user_id,
                        "device_id": resp.device_id,
                    },
                    f,
                )
            os.replace(tmp_file, TOKEN_FILE)
            log.info("Matrix session saved", user_id=resp.user_id)
        except OSError:
            log.error("Failed to save Matrix session to disk")
            try:
                os.remove(tmp_file)
            except OSError:
                pass
            raise

    log.debug("Matrix client ready", user_id=client.user_id)
    return client

async def matrix_worker(client):
    """
    Worker to send messages to Matrix.
    
    :param client: Logged-in Matrix AsyncClient
    :type client: AsyncClient
    """
    while True:
        try:
            content = await matrix_queue.get()
        except asyncio.CancelledError:
            log.info("Matrix worker cancelled, stopping")
            break

        try:
            resp = await client.room_send(
                room_id=MATRIX_ROOM_ID,
                message_type="m.room.message",
                content=content,
            )
            log.debug("Matrix message queued for send", content=content, response=repr(resp))
        except LocalProtocolError:
            log.error("Matrix send protocol error", content=content)
            # Avoid tight busy loop
            await asyncio.sleep(1)
        except Exception:
            log.error("Unexpected error sending Matrix message", content=content)
            await asyncio.sleep(1)
        finally:
            try:
                matrix_queue.task_done()
            except Exception:
                log.error("Failed to mark matrix_queue task done")

        log.debug("Finished processing matrix message", content=content)

def start_matrix_worker(client):
    """
    Start the Matrix worker in a separate thread.
    
    :param client: Logged-in Matrix AsyncClient
    :type client: AsyncClient
    """
    global matrix_queue

    try:
        asyncio.set_event_loop(matrix_loop)
    except RuntimeError as e:
        log.warning("Could not set matrix event loop", error=str(e))

    matrix_queue = asyncio.Queue()

    matrix_loop.create_task(
        client.sync_forever(timeout=30000, full_state=False)
    )

    matrix_loop.create_task(matrix_worker(client))
    log.info("Starting matrix event loop and worker")
    try:
        matrix_loop.run_forever()
    except KeyboardInterrupt:
        log.info("Matrix event loop stopped by KeyboardInterrupt")
    finally:
        # Attempt a graceful shutdown
        try:
            tasks = list(asyncio.all_tasks())
            for t in tasks:
                t.cancel()
            matrix_loop.stop()
            log.info("Matrix worker stopped")
        except Exception:
            log.error("Error during matrix loop shutdown")

def send_matrix_message(content: dict):
    """
    Send a message to Matrix via the worker.
    
    :param content: Message content dictionary
    :type content: dict
    """
    if not isinstance(content, dict):
        log.error("send_matrix_message called with invalid content type",
                  content_type=type(content))
        raise TypeError("content must be a dict")

    try:
        future = asyncio.run_coroutine_threadsafe(matrix_queue.put(content), matrix_loop)
        # Wait briefly so we surface scheduling errors early
        future.result(timeout=5)
        log.debug("Enqueued matrix message", content=content)
    except Exception:
        log.error("Failed to enqueue matrix message", content=content)
        raise
