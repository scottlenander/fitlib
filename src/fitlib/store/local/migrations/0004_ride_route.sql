-- Route fingerprints: the ~150 m cells (7-character geohashes) each ride passed through.
-- Location data, like ride_geo: kept in its own table so it can be left out of (or encrypted
-- for) any sync. Indexed by cell to find rides that share cells with a given ride.
CREATE TABLE ride_route (
    ride_id TEXT NOT NULL REFERENCES rides (id) ON DELETE CASCADE,
    cell    TEXT NOT NULL,
    PRIMARY KEY (ride_id, cell)
) WITHOUT ROWID;
CREATE INDEX ride_route_cell ON ride_route (cell, ride_id);
