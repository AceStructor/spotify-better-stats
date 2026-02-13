INSERT_SQL = """
WITH artist AS (
    INSERT INTO artists (name)
    VALUES (%(artist_name)s)
    ON CONFLICT (name) DO UPDATE
        SET name = EXCLUDED.name
    RETURNING id
),
album AS (
    INSERT INTO albums (artist_id, title)
    SELECT id, %(album_title)s
    FROM artist
    ON CONFLICT (artist_id, title) DO UPDATE
        SET title = EXCLUDED.title
    RETURNING id
),
track AS (
    INSERT INTO tracks (
        artist_id,
        title,
        duration_ms
    )
    SELECT
        artist.id,
        %(track_title)s,
        %(duration_ms)s
    FROM artist
    ON CONFLICT (artist_id, title)
    DO UPDATE SET
        duration_ms = EXCLUDED.duration_ms
    RETURNING id
),
album_track AS (
    INSERT INTO album_tracks (
        album_id,
        track_id
    )
    SELECT
        album.id,
        track.id
    FROM album, track
    ON CONFLICT (album_id, track_id) DO NOTHING
)
SELECT 1;
"""