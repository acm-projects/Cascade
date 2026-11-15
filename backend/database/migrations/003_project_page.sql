-- Extend existing project records; no sidebar/filter tables are needed.
UPDATE cascade_app.records
SET payload = jsonb_build_object(
        'updated_at', extract(epoch FROM updated_at),
        'thumbnail_key', NULL
    ) || payload
WHERE key ~ '^projects/[0-9a-f]{64}/[0-9a-f]{32}\.json$'
  AND (NOT payload ? 'updated_at' OR NOT payload ? 'thumbnail_key');

CREATE OR REPLACE VIEW cascade_app.projects AS
SELECT payload->>'id' AS id, payload->>'user_id' AS user_id,
       payload->>'name' AS name, payload,
       COALESCE(to_timestamp((payload->>'updated_at')::double precision), updated_at) AS updated_at,
       to_timestamp((payload->>'created_at')::double precision) AS created_at,
       payload->>'thumbnail_key' AS thumbnail_key
FROM cascade_app.records WHERE key ~ '^projects/[0-9a-f]{64}/[0-9a-f]{32}\.json$';
