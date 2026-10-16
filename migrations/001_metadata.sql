-- Additive migration: existing public users/projects/clips tables are untouched.
-- Clerk user IDs are strings; no passwords or duplicate authentication are stored.
CREATE SCHEMA IF NOT EXISTS cascade_app;
CREATE TABLE IF NOT EXISTS cascade_app.records (
    key TEXT PRIMARY KEY,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS records_user_id ON cascade_app.records ((payload->>'user_id'));
CREATE INDEX IF NOT EXISTS records_project_id ON cascade_app.records ((payload->>'project_id'));

CREATE OR REPLACE VIEW cascade_app.projects AS
SELECT payload->>'id' AS id, payload->>'user_id' AS user_id,
       payload->>'name' AS name, payload, updated_at
FROM cascade_app.records WHERE key ~ '^projects/[0-9a-f]{64}/[0-9a-f]{32}\.json$';

CREATE OR REPLACE VIEW cascade_app.settings AS
SELECT split_part(key, '/', 2) AS user_id_hash, payload AS preferences, updated_at
FROM cascade_app.records WHERE key ~ '^projects/[0-9a-f]{64}/settings/preferences\.json$';

CREATE OR REPLACE VIEW cascade_app.jobs AS
SELECT split_part(o.key, '/', 1) AS id, o.payload->>'user_id' AS user_id,
       o.payload->>'project_id' AS project_id, o.payload AS owner,
       r.payload AS results, p.payload AS progress, f.payload AS failure
FROM cascade_app.records o
LEFT JOIN cascade_app.records r ON r.key = split_part(o.key, '/', 1) || '/results.json'
LEFT JOIN cascade_app.records p ON p.key = split_part(o.key, '/', 1) || '/progress.json'
LEFT JOIN cascade_app.records f ON f.key = split_part(o.key, '/', 1) || '/failure.json'
WHERE o.key ~ '^[0-9a-f]{32}/owner\.json$';

CREATE OR REPLACE VIEW cascade_app.clips AS
SELECT j.id AS job_id, j.user_id, j.project_id, c.ordinality - 1 AS clip_index, c.clip
FROM cascade_app.jobs j
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(j.results->'clips', '[]'::jsonb))
WITH ORDINALITY AS c(clip, ordinality);
