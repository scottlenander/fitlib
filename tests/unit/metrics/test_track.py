"""Simplifying a ride's positions for a map."""

from __future__ import annotations

import math

import polars as pl

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics.track import ride_track, simplify
from tests.fixtures.generate import committed_bytes

METRES_PER_DEGREE = 111_195.0


def frame_of(name: str) -> pl.DataFrame:
    """Decode a fixture ride to its 1 Hz stream.

    Args:
        name: The fixture spec's name.

    Returns:
        The stream.
    """
    return to_frame(decode(committed_bytes(name)).records)


def straight_frame(points: int, with_distance: bool = True) -> pl.DataFrame:
    """A ride due north along one meridian, one point a second.

    Args:
        points: How many seconds.
        with_distance: Record distance too.

    Returns:
        A stream with ``t``, ``lat``, ``lon`` and ``distance``.
    """
    lat = [50.0 + i * 5 / METRES_PER_DEGREE for i in range(points)]
    return pl.DataFrame(
        {
            "t": list(range(points)),
            "lat": lat,
            "lon": [3.0] * points,
            "distance": [i * 5.0 for i in range(points)] if with_distance else [None] * points,
        },
        schema={"t": pl.Int32, "lat": pl.Float64, "lon": pl.Float64, "distance": pl.Float64},
    )


def test_straight_line_keeps_only_its_ends():
    """A straight road needs only its two ends.

    Given: 600 points in a straight line, 5 m apart.
    Expect: Two points, the first and last, with their times and distances.
    """
    track = ride_track(straight_frame(600))

    assert track is not None
    assert [(p.t, p.distance_m) for p in track.points] == [(0, 0.0), (599, 2995.0)]


def test_simplify_keeps_corners_and_drops_wobble():
    """Bends beyond the tolerance stay; wobble within it goes.

    Given: An L shape (100 m east, then 100 m north) with 1 m of zig-zag on every point,
        simplified at 3 m.
    Expect: The two ends and the corner, nothing else.
    """
    east = [(float(i), (-1.0) ** i) for i in range(100)]
    north = [(100.0 + (-1.0) ** i, float(i)) for i in range(101)]
    x, y = [p[0] for p in east + north], [p[1] for p in east + north]

    kept = simplify(x, y, tolerance=3.0)

    assert kept == [0, 100, 200]


def test_simplify_handles_a_loop_whose_ends_meet():
    """A closed loop (same start and finish) keeps its shape.

    Given: A square loop, 400 points, ending where it started.
    Expect: Its four corners are kept along with the shared start and end.
    """
    side = 100
    xs = list(range(side)) + [side] * side + list(range(side, 0, -1)) + [0] * (side + 1)
    ys = [0] * side + list(range(side)) + [side] * side + list(range(side, -1, -1))
    kept = simplify([float(v) for v in xs], [float(v) for v in ys], tolerance=3.0)
    corners = {(xs[i], ys[i]) for i in kept}

    assert {(0, 0), (side, 0), (side, side), (0, side)} <= corners
    assert len(kept) <= 8


def test_long_tracks_are_capped():
    """However wiggly, a track never exceeds the point cap.

    Given: 5,000 points zig-zagging 50 m either side of a line, capped at 300.
    Expect: At most 300 points, still including the first and last.
    """
    n = 5_000
    lat = [50.0 + i * 5 / METRES_PER_DEGREE for i in range(n)]
    lon = [
        3.0 + ((-1) ** i) * 50 / (METRES_PER_DEGREE * math.cos(math.radians(50))) for i in range(n)
    ]
    frame = pl.DataFrame({"t": list(range(n)), "lat": lat, "lon": lon, "distance": [None] * n})

    track = ride_track(frame, max_points=300)

    assert track is not None
    assert 2 <= len(track.points) <= 300
    assert (track.points[0].t, track.points[-1].t) == (0, n - 1)


def test_fixture_loop_track():
    """A real fixture loop comes back as a few hundred points around its bounds.

    Given: The 5x4 interval ride, laps of the Nord loop.
    Expect: Fewer than 1,000 points; every point inside the bounds; the start-to-finish
        distance matching the first and last positions (to a metre); distances rising.
    """
    frame = frame_of("garmin_nord_intervals_5x4").drop_nulls(["lat", "lon"])
    track = ride_track(frame)
    first, last = frame.row(0, named=True), frame.row(-1, named=True)
    north_m = (last["lat"] - first["lat"]) * METRES_PER_DEGREE
    east_m = (last["lon"] - first["lon"]) * METRES_PER_DEGREE * math.cos(math.radians(50.4))

    assert track is not None
    south, west, north, east = track.bounds
    assert 10 < len(track.points) < 1_000
    assert all(south <= p.lat <= north and west <= p.lon <= east for p in track.points)
    assert math.isclose(track.start_finish_m, math.hypot(north_m, east_m), abs_tol=1.0)
    distances = [p.distance_m for p in track.points if p.distance_m is not None]
    assert distances == sorted(distances)


def test_no_positions_no_track():
    """An indoor ride without GPS has no track.

    Given: The indoor fixture ride.
    Expect: ``None``.
    """
    assert ride_track(frame_of("garmin_indoor_no_hr")) is None


def test_track_without_distance():
    """Positions without distance still make a track, with no distances.

    Given: A straight line with no distance recorded.
    Expect: Its two ends, distance ``None``.
    """
    track = ride_track(straight_frame(100, with_distance=False))

    assert track is not None
    assert [p.distance_m for p in track.points] == [None, None]
