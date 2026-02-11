INSERT_SQL = """
WITH artist AS (
    INSERT INTO artists (name, workflow_id)
    VALUES (%(artist_name)s, %(workflow_id)s)
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
        duration_ms,
        workflow_id
    )
    SELECT
        artist.id,
        %(track_title)s,
        %(duration_ms)s,
        %(workflow_id)s
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