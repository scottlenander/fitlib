-- Phase 1c: dated default bikes per kind of ride. A NULL bike stops defaulting from that date.
CREATE TABLE bike_defaults (
    slot           TEXT NOT NULL CHECK (slot IN ('zwift', 'indoor', 'outdoor')),
    effective_from TEXT NOT NULL,  -- ISO date, local time
    bike_id        TEXT REFERENCES bikes (id),
    PRIMARY KEY (slot, effective_from)
);

CREATE INDEX ride_meta_bike ON ride_meta (bike_id);

-- 1 when the ride's bike came from the default bikes (a backfill may change it); 0 when the
-- user chose it (never changed automatically).
ALTER TABLE ride_meta ADD COLUMN bike_from_default INTEGER NOT NULL DEFAULT 0;
