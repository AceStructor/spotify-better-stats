INSERT_SQL = """
WITH inserted_artists AS (
    INSERT INTO artists (name, workflow_id)
    SELECT UNNEST(%(artist_names)s), %(workflow_id)s
    ON CONFLICT (name) DO UPDATE
        SET name = EXCLUDED.name
    RETURNING id, name
),

album AS (
    INSERT INTO albums (title)
    VALUES (%(album_title)s)
    ON CONFLICT (title) DO UPDATE
        SET title = EXCLUDED.title
    RETURNING id
),

track AS (
    INSERT INTO tracks (
        title,
        duration_ms,
        workflow_id
    )
    VALUES (
        %(track_title)s,
        %(duration_ms)s,
        %(workflow_id)s
    )
    ON CONFLICT (title)
    DO UPDATE SET
        duration_ms = EXCLUDED.duration_ms
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

INSERT INTO track_plays (
    track_id,
    played_at,
    skipped,
    workflow_id
)
SELECT
    track.id,
    %(played_at)s,
    %(skipped)s,
    %(workflow_id)s
FROM track
ON CONFLICT (track_id, played_at) DO NOTHING;
"""

NEW_WORKFLOW_SQL = """
INSERT INTO workflow_state (init_done)
VALUES (False)
RETURNING workflow_id;
"""

UPDATE_WORKFLOW_SQL = """
UPDATE workflow_state
SET init_done = True
WHERE workflow_id = %s;
"""