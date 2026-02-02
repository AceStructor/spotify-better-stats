import json
import select
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import psycopg2


class NotificationListener(ABC):

    def __init__(self, *, db_config: dict, logger):
        self.db_config = db_config
        self.log = logger

    channel: str

    def run(self) -> None:
        while True:
            try:
                self.log.info("Connecting to database", channel=self.channel)
                with psycopg2.connect(**self.db_config) as conn:
                    self._listen(conn)
            except psycopg2.OperationalError:
                self.log.exception("Database connection error, retrying")
                time.sleep(5)
            except KeyboardInterrupt:
                self.log.info("Listener interrupted, shutting down")
                break
            except Exception:
                self.log.exception("Unhandled listener error")
                time.sleep(5)

    def _listen(self, conn) -> None:
        with conn.cursor() as cur:
            cur.execute(f"LISTEN {self.channel};")
            self.log.info("Listening", channel=self.channel)

        while True:
            ready, _, _ = select.select([conn], [], [], 5.0)
            if not ready:
                self.log.debug("Waiting for notifications", channel=self.channel)
                continue

            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                self._handle_notify(conn, notify)

    def _handle_notify(self, conn, notify) -> None:
        try:
            payload_raw = json.loads(notify.payload)
        except json.JSONDecodeError:
            self.log.warning("Invalid JSON payload", payload=notify.payload)
            return

        payload = self.parse_payload(payload_raw)
        if payload is None:
            return

        try:
            self.handle(conn, payload)
        except Exception:
            self.log.exception("Error handling notification", payload=payload)

    # ---------- Hooks ----------

    @abstractmethod
    def parse_payload(self, payload: dict) -> Optional[Any]:
        pass

    @abstractmethod
    def handle(self, conn, payload: Any) -> None:
        pass

    # ---------- End of Hooks ----------    
