-- All active Cascade application data belongs to cascade_app.
-- Clerk handles authentication; only app identity and first-seen time live here.
CREATE TABLE IF NOT EXISTS cascade_app.users (
    clerk_user_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Preserve existing app registration dates, excluding unrelated sample users.
SET LOCAL TIME ZONE 'UTC';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'clerk_user_id') THEN
        EXECUTE $copy$
            INSERT INTO cascade_app.users (clerk_user_id, created_at)
            SELECT clerk_user_id, COALESCE(created_at::timestamptz, now()) FROM public.users
            WHERE NULLIF(clerk_user_id, '') IS NOT NULL
            ON CONFLICT (clerk_user_id) DO NOTHING
        $copy$;
    END IF;
END $$;

-- Backfill accounts from existing app records without changing those records.
INSERT INTO cascade_app.users (clerk_user_id)
SELECT DISTINCT payload->>'user_id' FROM cascade_app.records
WHERE NULLIF(payload->>'user_id', '') IS NOT NULL
ON CONFLICT (clerk_user_id) DO NOTHING;

ALTER TABLE cascade_app.records ADD COLUMN IF NOT EXISTS owner_clerk_user_id TEXT
    GENERATED ALWAYS AS (payload->>'user_id') STORED;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
               WHERE conrelid = 'cascade_app.records'::regclass AND conname = 'records_clerk_user_fk'
                 AND confrelid <> 'cascade_app.users'::regclass) THEN
        ALTER TABLE cascade_app.records DROP CONSTRAINT records_clerk_user_fk;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'cascade_app.records'::regclass AND conname = 'records_clerk_user_fk') THEN
        ALTER TABLE cascade_app.records ADD CONSTRAINT records_clerk_user_fk
            FOREIGN KEY (owner_clerk_user_id) REFERENCES cascade_app.users (clerk_user_id);
    END IF;
END $$;
