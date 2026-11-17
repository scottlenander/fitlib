-- Where each ride's time zone came from: its file ('device'), its file name ('file_name',
-- e.g. Zwift's local start time), the library's default ('default'), or nowhere ('none').
-- Rides imported before this had an offset only from their file.
ALTER TABLE rides ADD COLUMN utc_offset_source TEXT NOT NULL DEFAULT 'none';
UPDATE rides SET utc_offset_source = 'device' WHERE utc_offset_s IS NOT NULL;

-- Library-wide settings, such as the default time zone.
CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;
