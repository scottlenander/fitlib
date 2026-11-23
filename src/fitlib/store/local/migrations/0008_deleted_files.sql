-- Files of rides the user deleted. Importing them again (a folder, a Garmin export zip, a
-- watched folder) skips them unless asked to bring them back; adding the ride again removes
-- its row. Not tied to rides, which are gone.
CREATE TABLE deleted_files (
    sha256     TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    deleted_at INTEGER NOT NULL
);
