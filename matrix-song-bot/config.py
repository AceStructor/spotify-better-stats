from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB", "database"),
    "user": os.getenv("POSTGRES_USER", "user"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
}

CHANNEL = os.getenv("POSTGRES_CHANNEL", "track_plays_inserted")

MATRIX_HOMESERVER = os.getenv("MATRIX_HOMESERVER", "https://matrix.org")
MATRIX_USER = os.getenv("MATRIX_USER", "@bot:matrix.org")
MATRIX_PASSWORD = os.getenv("MATRIX_PASSWORD", "password")
MATRIX_ROOM_ID = os.getenv("MATRIX_ROOM_ID", "!yourroomid:matrix.org")

TOKEN_FILE = os.getenv("MATRIX_TOKEN_FILE", "/app/matrix_session/matrix_session.json")

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")