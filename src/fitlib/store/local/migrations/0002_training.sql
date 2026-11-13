-- Phase 1b: training figures that don't depend on FTP, best efforts, histograms, athlete
-- history. FTP-based figures (IF, TSS, W/kg, zone times) are computed when read.
ALTER TABLE rides ADD COLUMN np REAL;
ALTER TABLE rides ADD COLUMN kj REAL;
ALTER TABLE rides ADD COLUMN vi REAL;
ALTER TABLE rides ADD COLUMN decoupling_pct REAL;
CREATE INDEX rides_metrics_version ON rides (metrics_version);

-- Best average power ('power') or heart rate ('hr') per duration.
CREATE TABLE ride_curves (
    ride_id    TEXT NOT NULL REFERENCES rides (id) ON DELETE CASCADE,
    kind       TEXT NOT NULL CHECK (kind IN ('power', 'hr')),
    duration_s INTEGER NOT NULL,
    value      REAL NOT NULL,
    PRIMARY KEY (ride_id, kind, duration_s)
);
CREATE INDEX ride_curves_kind_duration ON ride_curves (kind, duration_s);

-- Riding seconds at each whole watt ('power') or bpm ('hr').
CREATE TABLE ride_bins (
    ride_id TEXT NOT NULL REFERENCES rides (id) ON DELETE CASCADE,
    kind    TEXT NOT NULL CHECK (kind IN ('power', 'hr')),
    value   INTEGER NOT NULL,
    seconds INTEGER NOT NULL,
    PRIMARY KEY (ride_id, kind, value)
) WITHOUT ROWID;

-- Dated FTP / weight / max HR. NULL means "unchanged by this entry".
CREATE TABLE athlete_history (
    effective_from TEXT PRIMARY KEY,  -- ISO date, local time
    ftp            INTEGER,
    weight_kg      REAL,
    max_hr         INTEGER
);
