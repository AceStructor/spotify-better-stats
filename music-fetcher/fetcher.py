import os
import time
import threading
import subprocess
import psycopg2

from dataclasses import dataclass
from typing import Optional
from contextlib import closing

from logger import log
from config import DB_CONFIG

# Constants

BEETS_IMPORT_DIR = "/import"
WORKER_COUNT = 4
POLL_INTERVAL = 5  # seconds
YTDLP_FORMAT = "flac"


# Models

@dataclass
class Track:
    track_id: int
    artist: str
    title: str
    youtube_code: str


# yt-dlp Worker

class YtdlpWorker:

    def _build_output_path(self, track: Track) -> str:
        return os.path.join(BEETS_IMPORT_DIR, f"{track.track_id}.%(ext)s")

    def run(self, track: Track) -> str:
        url = f"https://music.youtube.com/watch?v={track.youtube_code}"
        output_path = self._build_output_path(track)

        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", YTDLP_FORMAT,
            "--audio-quality", "0",
            "--embed-metadata",
            "--embed-thumbnail",
            "--no-playlist",
            "-o", output_path,
            url,
        ]

        log.info(f"[yt-dlp] Downloading track {track.track_id}: {track.artist} - {track.title}")
        log.debug(f"[yt-dlp] Command: {' '.join(cmd)}")

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if proc.returncode != 0:
            log.error(f"[yt-dlp] Failed: {proc.stderr.strip()}")
            raise RuntimeError(proc.stderr.strip())

        # Datei finden (yt-dlp entscheidet Extension)
        for ext in ("flac", "mp3", "m4a", "opus"):
            path = os.path.join(BEETS_IMPORT_DIR, f"{track.track_id}.{ext}")
            if os.path.exists(path):
                log.debug(f"[yt-dlp] Downloaded file: {path}")
                return path

        raise RuntimeError("yt-dlp finished successfully but no output file was found")


# Database Access

class DatabaseWriter:

    def __init__(self, conn):
        self.conn = conn

    def mark_downloading(self, track: Track) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET download_status = 'downloading'
                WHERE id = %s
                AND download_status = 'queued'
                """,
                (track.track_id,),
            )
        self.conn.commit()
        return cur.rowcount > 0

    def mark_done(self, track: Track, file_path: str):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET download_status = 'done',
                    file_path = %s,
                    downloaded_at = NOW(),
                    audio_format = %s
                WHERE id = %s
                """,
                (file_path, YTDLP_FORMAT, track.track_id),
            )
        self.conn.commit()

    def mark_error(self, track: Track, error_msg: str):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET download_status = 'error',
                    download_error = %s
                WHERE id = %s
                """,
                (error_msg[:1000], track.track_id),
            )
        self.conn.commit()


class DatabaseReader:

    def __init__(self, conn):
        self.conn = conn

    def fetch_track(self) -> Optional[Track]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id, a.name, t.title, al.title, t.youtube_code
                FROM tracks t
                JOIN artists a ON t.artist_id = a.id
                WHERE t.download_status = 'queued'
                ORDER BY t.created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()

        if not row:
            return None

        return Track(
            track_id=row[0],
            artist=row[1],
            title=row[2],
            youtube_code=row[4],
        )


# Worker Loop

def worker_loop(worker_id: int):
    log.info(f"[worker-{worker_id}] started")

    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        reader = DatabaseReader(conn)
        writer = DatabaseWriter(conn)

        while True:
            track = None
            try:
                track = reader.fetch_track()

                if not track:
                    time.sleep(POLL_INTERVAL)
                    continue

                if not writer.mark_downloading(track):
                    log.debug(f"[worker-{worker_id}] track already claimed")
                    time.sleep(POLL_INTERVAL)
                    continue

                log.info(f"[worker-{worker_id}] processing track {track.track_id}")

                downloaded_path = YtdlpWorker().run(track)

                writer.mark_done(track, downloaded_path)
                log.info(f"[worker-{worker_id}] finished track {track.track_id}")

            except Exception as e:
                log.error(f"[worker-{worker_id}] error: {e}", exc_info=True)
                if track:
                    writer.mark_error(track, str(e))
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
