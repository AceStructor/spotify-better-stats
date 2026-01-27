package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	_ "github.com/lib/pq"
)

const recentlyPlayedURL = "https://api.spotify.com/v1/me/player/recently-played?limit=1"
const artistURL = "https://api.spotify.com/v1/artists/"

type RecentlyPlayed struct {
	Items []struct {
		PlayedAt time.Time `json:"played_at"`
		Track    Track     `json:"track"`
	} `json:"items"`
}

type Track struct {
	ID         string `json:"id"`
	Name       string `json:"name"`
	DurationMs int    `json:"duration_ms"`
	Album      struct {
		Name string `json:"name"`
	} `json:"album"`
	Artists []struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	} `json:"artists"`
}

type Artist struct {
	Genres []string `json:"genres"`
}

func spotifyGET(url, token string, target interface{}) error {
	req, _ := http.NewRequest("GET", url, nil)
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return fmt.Errorf("spotify api returned %d", resp.StatusCode)
	}

	return json.NewDecoder(resp.Body).Decode(target)
}

func main() {
	token := os.Getenv("SPOTIFY_TOKEN")
	dbURL := os.Getenv("DATABASE_URL")

	if token == "" || dbURL == "" {
		log.Fatal("SPOTIFY_TOKEN or DATABASE_URL not set")
	}

	db, err := sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatal(err)
	}
	defer db.Close()

	// --- Fetch recently played ---
	var rp RecentlyPlayed
	if err := spotifyGET(recentlyPlayedURL, token, &rp); err != nil {
		log.Fatal(err)
	}

	if len(rp.Items) == 0 {
		log.Println("no recently played tracks")
		return
	}

	item := rp.Items[0]

	// --- Fetch artist genres ---
	var artist Artist
	artistID := item.Track.Artists[0].ID
	_ = spotifyGET(artistURL+artistID, token, &artist)

	// --- Insert current track ---
	res, err := db.Exec(`
		INSERT INTO spotify_tracks
		    (track_id, title, artist, album, genres, duration_ms, played_at)
		VALUES
		    ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (track_id, played_at) DO NOTHING
	`,
		item.Track.ID,
		item.Track.Name,
		item.Track.Artists[0].Name,
		item.Track.Album.Name,
		pqStringArray(artist.Genres),
		item.Track.DurationMs,
		item.PlayedAt,
	)

	if err != nil {
		log.Fatal(err)
	}

	rows, _ := res.RowsAffected()
	if rows == 0 {
		log.Println("track already recorded")
		return
	}

	log.Printf("stored: %s - %s", item.Track.Artists[0].Name, item.Track.Name)

	// --- Skip detection ---
	markPreviousIfSkipped(db, item.PlayedAt)
}

func markPreviousIfSkipped(db *sql.DB, currentPlayedAt time.Time) {
	var (
		id         int
		playedAt   time.Time
		durationMs int
	)

	err := db.QueryRow(`
		SELECT id, played_at, duration_ms
		FROM spotify_tracks
		WHERE played_at < $1
		ORDER BY played_at DESC
		LIMIT 1
	`, currentPlayedAt).Scan(&id, &playedAt, &durationMs)

	if err != nil {
		return
	}

	actualPlaytime := currentPlayedAt.Sub(playedAt)
	expected := time.Duration(durationMs) * time.Millisecond

	if actualPlaytime < expected*9/10 {
		_, _ = db.Exec(`
			UPDATE spotify_tracks
			SET skipped = true
			WHERE id = $1
		`, id)

		log.Printf("marked track %d as skipped", id)
	}
}

func pqStringArray(a []string) interface{} {
	if len(a) == 0 {
		return "{}"
	}
	out := "{"
	for i, v := range a {
		if i > 0 {
			out += ","
		}
		out += `"` + v + `"`
	}
	return out + "}"
}
