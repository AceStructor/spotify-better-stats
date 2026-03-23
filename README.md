
# Music Analytics

A comprehensive system for tracking and analyzing music listening statistics from Navidrome using the Subsonic API. This project aggregates play data, enriches metadata with genres, YouTube links, and more, and provides an API to quickly add new albums to the library.

## Features

- **Real-time Listening Tracking**: Monitors currently playing tracks from Navidrome via Subsonic API
- **Metadata Enrichment**:
  - Automatic genre fetching from Last.fm
  - YouTube video links for tracks
  - MusicBrainz integration for accurate metadata
- **Social Integration**: Posts newly listened tracks to Matrix channels
- **Music Library Management**: Flask-based API to add or remove albums to the database via musicbrainz ID
- **Docker-based Deployment**: Easy setup with Docker Compose

## Architecture

The system consists of multiple microservices:

- **tracker**: Polls Navidrome's Subsonic API for current playback and logs listening events
- **genre-reader**: Fetches artist genres from Last.fm and updates the database
- **youtube-reader**: Retrieves YouTube Music video codes for tracks
- **matrix-song-bot**: Posts listening updates to Matrix chat rooms
- **music-fetcher**: Handles music file imports with yt-dlp
- **music-librarian**: API to manage music library
- **postgres**: PostgreSQL database for storing all data

## Prerequisites

- Docker and Docker Compose
- Navidrome server with Subsonic API enabled
- Optional: Last.fm API key for genre data
- Optional: Matrix server for social features

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd music-analytics
   ```

2. Copy `.env.example` to `.env` and edit (or create `.env` manually):
   ```bash
   cp .env.example .env
   ```

3. Ensure `COMPOSE_PROJECT_NAME` is set (e.g. `music_analytics`).

4. Start all services:
   ```bash
   docker-compose up -d --build
   ```

5. Confirm service health:
   ```bash
   docker-compose ps
   ```

6. Access music-librarian on `http://localhost:5000` (or configured host/port).

## Environment Variables

Create a `.env` file in the project root with these values (or use `.env.example`):

```env
# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=15432
POSTGRES_DB=navidrome_stats
POSTGRES_USER=navidrome
POSTGRES_PASSWORD=your_secure_password

# Navidrome / Subsonic API
LOCAL_MUSICSTREAM_URL=http://your-navidrome-server:4533
NAVIDROME_USER=your_navidrome_user
NAVIDROME_PASSWORD=your_navidrome_password

# Optional Last.fm
LASTFM_BASE=http://ws.audioscrobbler.com/2.0
LASTFM_API_KEY=your_lastfm_api_key

# Optional Matrix
MATRIX_HOMESERVER=https://your-matrix-server
MATRIX_USER=@your-user:your-server
MATRIX_PASSWORD=your_password
MATRIX_ROOM_ID=!room-id:server

# Docker/Env
COMPOSE_PROJECT_NAME=music_analytics
ENVIRONMENT=prod
ENV_FILE=.env
```

## Usage

### Start/Stop Services

- Start (detached): `docker-compose up -d --build`
- Stop: `docker-compose down`
- View logs: `docker-compose logs -f tracker genre-reader youtube-reader matrix-song-bot music-fetcher music-librarian`

### Verify ingestion

- Trigger a Navidrome play, then query the database via psql:
  - `SELECT * FROM track_plays ORDER BY created_at DESC LIMIT 5;`

### Librarian

- Access `http://localhost:5000/albums` to add a new album. Use mbid as payload in a JSON body.

## Development

1. Set `ENVIRONMENT=dev` in `.env`.
2. Optionally create `docker-compose.override.yml` with volume mounts for source code.
3. Start services in debug mode:
   ```bash
   docker-compose up --build
   ```
4. Use IDE breakpoints in `tracker/listener.py`, `genre-reader/listener.py`, `youtube-reader/listener.py`, `music-librarian/app.py`.

## AI Disclaimer

This repository contains code and experimentation driven by AI-assisted development. The intent is to reflect a personal prototype workflow, not a polished commercial product.

- AI tools were used for generating prototypes, SQL queries, API logic, and refactor suggestions.
- The codebase includes handcrafted refactors and AI-suggested snippets side-by-side.
- Some modules are intentionally "vibe-coded": they work for my use case but retain technical debt.
- Consider this project a living experiment with explicit non-production assumptions.

### Areas with known rough edges (as of last update)

- `tracker/listener.py`: core playback capture is functional but could be cleaned into clear layers.
- `genre-reader` / `youtube-reader`: engine and helpers are mature, but shared service abstractions are incomplete.
- `music-fetcher`: file discovery and import logic should be reorganized into clearer pipelines.
- `matrix-song-bot`: works for notifications, can be refactored for better message templating.

### What this means for contributors

- You can freely improve or rework pieces; these are not final design constraints.
- Keep AI provenance in commit notes or comments if you reuse generated patterns.
- This README is direct about the experimental, non-UI-first nature of the code.

## Contributing

1. Fork repo
2. Create branch `feature/<name>`
3. Code + tests
4. Commit with clear message
5. Open PR

## Acknowledgments

- Navidrome for the music server API
- Subsonic API for playback metadata
- Last.fm for genre lookup
- MusicBrainz for canonical identifiers
- Matrix for notification integration

