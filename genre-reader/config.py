from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
}

CHANNEL = os.getenv("POSTGRES_CHANNEL", "artists_inserted")

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_BASE = os.getenv("LASTFM_BASE", "http://ws.audioscrobbler.com/2.0")

ENVIRONMENT = os.getenv("ENVIRONMENT", "dev")