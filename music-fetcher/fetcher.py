import os
import time
import threading
from dataclasses import dataclass
from typing import Optional
import subprocess
import psycopg2
from contextlib import closing
from logger import log
from config import DB_CONFIG

BEETS_IMPORT_DIR = "/import"
MUSIC_LIBRARY_DIR = "/music"
WORKER_COUNT = 1
POLL_INTERVAL = 5  # seconds
YTDLP_FORMAT = "flac"

@dataclass
class Track:
    track_id: int
    artist: str
    title: str
    album: str
    youtube_code: str

class YtdlpWorker:

    def _build_output_path(self, track: Track) -> str:
        filename = f"{track.track_id}.%(ext)s"
        return os.path.join(BEETS_IMPORT_DIR, filename)
    
    def run(self, track: Track) -> str:
        output_path = self._build_output_path(track)
        url = f"https://music.youtube.com/watch?v={track.youtube_code}"
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", YTDLP_FORMAT,
            "--audio-quality", "0",
            "--embed-metadata",
            "--embed-thumbnail",
            "--no-playlist",
            "-o", output_path,
            url
    ]
        log.debug(f"Running yt-dlp command: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        
        for ext in ["flac", "mp3", "m4a", "opus"]:
            path = os.path.join(BEETS_IMPORT_DIR, f"{track.track_id}.{ext}")
            if os.path.exists(path):
                return path
        
        raise RuntimeError("Downloaded file not found after yt-dlp execution")
    

class BeetsWorker:

    def run(self, file_path: str) -> str:
        beets_cmd = [
            "beet",
            "import",
            "-c",
            "/beets/beets_config.yaml",
            "--copy",
            "--quiet",
            file_path,
        ]
        log.debug(f"Running beets command: {' '.join(beets_cmd)}")
        proc = subprocess.run(beets_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr)
        # Assuming beets moves the file to its library, we need to find the new path
        # This is a placeholder; actual implementation may vary
        final_path = file_path.replace(BEETS_IMPORT_DIR, MUSIC_LIBRARY_DIR).replace("%(ext)s", YTDLP_FORMAT)
        return final_path


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
                """,
                (track.track_id,),
            )
        self.conn.commit()
        return True

    def mark_done(self, track: Track, file_path: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET download_status = 'done', file_path = %s, downloaded_at = NOW(), audio_format = %s
                WHERE id = %s
                """,
                (file_path, YTDLP_FORMAT, track.track_id),
            )
        self.conn.commit()
        return True

    def mark_error(self, track: Track, error_msg: str) -> bool:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE tracks
                SET download_status = 'error', error_msg = %s
                WHERE id = %s
                """,
                (error_msg, track.track_id),
            )
        self.conn.commit()
        return True


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
                JOIN albums al ON t.album_id = al.id
                WHERE t.download_status = 'queued'
                ORDER BY t.created_at ASC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row:
                return Track(track_id=row[0],
                             artist=row[1],
                             title=row[2],
                             album=row[3],
                             youtube_code=row[4])
            return None
    

def worker_loop(worker_id):
    print(f"[worker-{worker_id}] started")
    with closing(psycopg2.connect(**DB_CONFIG)) as conn:
        db_writer = DatabaseWriter(conn)
        while True:
            try:
                track = DatabaseReader(conn).fetch_track()
                db_writer.mark_downloading(track)
                if not track:
                    time.sleep(POLL_INTERVAL)
                    continue

                track_id = track.track_id
                print(f"[worker-{worker_id}] downloading {track_id}")

                path = YtdlpWorker().run(track)
                #final_path = BeetsWorker().run(path)
                #DatabaseWriter(conn).mark_done(track, final_path)

                print(f"[worker-{worker_id}] done {track_id}")

            except Exception as e:
                print(f"[worker-{worker_id}] error: {e}")
                if 'track' in locals():
                    #DatabaseWriter(conn).mark_error(track, str(e))
                    time.sleep(2)

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