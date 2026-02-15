INSERT_SQL = """
WITH inserted_artists AS (
    INSERT INTO artists (name)
    SELECT UNNEST(%(artist_names)s)
    ON CONFLICT (name) DO UPDATE
        SET name = EXCLUDED.name
    RETURNING id, name
),

album AS (
    INSERT INTO albums (title, mbid)
    VALUES (%(album_title)s, %(album_mbid)s)
    ON CONFLICT (mbid) DO UPDATE
        SET title = EXCLUDED.title,
            mbid = EXCLUDED.mbid
    RETURNING id
),

track AS (
    INSERT INTO tracks (
        title,
        duration_ms,
        download_status,
        mbid
    )
    VALUES (
        %(track_title)s,
        %(duration_ms)s,
        'pending',
        %(track_mbid)s
    )
    ON CONFLICT (mbid)
    DO UPDATE SET
        title = EXCLUDED.title,
        duration_ms = EXCLUDED.duration_ms,
        mbid = EXCLUDED.mbid
    RETURNING id
),

artist_track_links AS (
    INSERT INTO artist_tracks (artist_id, track_id)
    SELECT inserted_artists.id, track.id
    FROM inserted_artists, track
    ON CONFLICT DO NOTHING
),

artist_album_links AS (
    INSERT INTO artist_albums (artist_id, album_id)
    SELECT inserted_artists.id, album.id
    FROM inserted_artists, album
    ON CONFLICT DO NOTHING
),

album_track_link AS (
    INSERT INTO album_tracks (album_id, track_id)
    SELECT album.id, track.id
    FROM album, track
    ON CONFLICT DO NOTHING
)
SELECT 1;
"""