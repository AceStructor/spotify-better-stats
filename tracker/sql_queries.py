INSERT_SQL = """
WITH inserted_user AS (
    INSERT INTO users (username)
    VALUES (%(username)s)
    ON CONFLICT (username)
    DO UPDATE SET username = EXCLUDED.username
    RETURNING id
),
track_row AS (
    SELECT id
    FROM tracks
    WHERE mbid = %(mbid)s
)

INSERT INTO track_plays (
    track_id,
    played_at,
    user_id,
    skipped
)
SELECT
    t.id,
    %(played_at)s,
    u.id,
    %(skipped)s
FROM track_row t
CROSS JOIN inserted_user u
ON CONFLICT (user_id, track_id, played_at)
DO NOTHING;
"""