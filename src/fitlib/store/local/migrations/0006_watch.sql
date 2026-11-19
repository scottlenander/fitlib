-- Phase 6: folders watched for new rides, and the files found in them. Both hold this
-- computer's paths, so they're never synced.
CREATE TABLE watch_folders (
    path     TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL
);

-- One row per file found: its size and modification time when imported (an unchanged file is
-- never read again) and what happened. Not tied to rides: a ride can be deleted.
CREATE TABLE watch_files (
    path     TEXT PRIMARY KEY,
    folder   TEXT NOT NULL,
    size     INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    outcome  TEXT NOT NULL CHECK (outcome IN ('imported', 'duplicate', 'skipped', 'failed')),
    detail   TEXT,
    ride_id  TEXT,
    seen_at  INTEGER NOT NULL
);
CREATE INDEX watch_files_seen ON watch_files (seen_at);
