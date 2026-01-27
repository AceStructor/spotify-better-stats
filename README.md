
# Spotify Better Stats

A project to track and manage listening behavior across multiple platforms.

## Services

- **tracker**: Polls currently played tracks
- **genre-reader**: Fetches Last.fm tags for new artists
- **youtube-reader**: Retrieves YouTube Music video codes for new tracks using ytmusicapi
- **matrix-song-bot**: Posts newly listened tracks to a Matrix channel
- **postgres**: Database for storing track and artist data

## Setup

### Prerequisites

- Docker and Docker Compose
- A `.env` file (not included in repo)

### Environment Variables

Create a `.env` file in the project root with the following variables:

```
POSTGRES_HOST=localhost
POSTGRES_PORT=15432
POSTGRES_DB=spotify
POSTGRES_USER=spotify
POSTGRES_PASSWORD=spotify

MATRIX_HOMESERVER=https://your-matrix-server
MATRIX_USER=@your-user:your-server
MATRIX_PASSWORD=your-password
MATRIX_ROOM_ID=!room-id:server

LASTFM_API_KEY=your-api-key

SPOTIFY_TOKEN=your-token
```

## Running

```bash
docker-compose up
```
