-- Rides: what the file says and what fitlib computed. Times are Unix seconds (UTC).
CREATE TABLE rides (
    id              TEXT PRIMARY KEY,
    sha256          TEXT NOT NULL UNIQUE,
    source_name     TEXT NOT NULL,
    imported_at     INTEGER NOT NULL,
    metrics_version INTEGER NOT NULL,
    start_ts        INTEGER NOT NULL,
    utc_offset_s    INTEGER,
    source          TEXT NOT NULL,
    device          TEXT,
    sport           TEXT NOT NULL,
    sub_sport       TEXT,
    indoor          INTEGER NOT NULL,
    elapsed_s       INTEGER NOT NULL,
    moving_s        INTEGER NOT NULL,
    distance_m      REAL,
    ascent_m        REAL,
    avg_speed_mps   REAL,
    max_speed_mps   REAL,
    avg_power       REAL,
    max_power       INTEGER,
    avg_hr          REAL,
    max_hr          INTEGER,
    avg_cadence     REAL,
    has_power       INTEGER NOT NULL,
    has_hr          INTEGER NOT NULL,
    has_gps         INTEGER NOT NULL
);
CREATE INDEX rides_start ON rides (start_ts);
CREATE INDEX rides_source_start ON rides (source, start_ts);

CREATE TABLE laps (
    ride_id        TEXT NOT NULL REFERENCES rides (id) ON DELETE CASCADE,
    lap_index      INTEGER NOT NULL,
    start_offset_s INTEGER NOT NULL,
    elapsed_s      INTEGER NOT NULL,
    distance_m     REAL,
    avg_power      REAL,
    max_power      INTEGER,
    avg_hr         REAL,
    max_hr         INTEGER,
    PRIMARY KEY (ride_id, lap_index)
);

-- Location lives in its own table so it can be left out of (or encrypted for) any sync.
CREATE TABLE ride_geo (
    ride_id   TEXT PRIMARY KEY REFERENCES rides (id) ON DELETE CASCADE,
    start_lat REAL NOT NULL,
    start_lon REAL NOT NULL,
    min_lat   REAL NOT NULL,
    min_lon   REAL NOT NULL,
    max_lat   REAL NOT NULL,
    max_lon   REAL NOT NULL
);

-- What the user adds. Never touched by import or recompute.
CREATE TABLE bikes (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE COLLATE NOCASE,
    kind    TEXT,
    retired INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ride_meta (
    ride_id TEXT PRIMARY KEY REFERENCES rides (id) ON DELETE CASCADE,
    name    TEXT,
    notes   TEXT,
    rpe     INTEGER CHECK (rpe BETWEEN 1 AND 10),
    bike_id TEXT REFERENCES bikes (id)
);

CREATE TABLE tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE ride_tags (
    ride_id TEXT NOT NULL REFERENCES rides (id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags (id),
    PRIMARY KEY (ride_id, tag_id)
);

-- Full-text search, maintained by the catalog code whenever a ride or its metadata changes.
CREATE VIRTUAL TABLE rides_fts USING fts5 (
    ride_id UNINDEXED,
    name,
    notes,
    tags,
    source,
    device,
    bike,
    tokenize = 'unicode61'
);
