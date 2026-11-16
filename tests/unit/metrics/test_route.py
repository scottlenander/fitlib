"""Route fingerprints: geohash cells, neighbours, and the cells the fixture rides pass through."""

from __future__ import annotations

import polars as pl
import pytest

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics.route import decode_index, encode, fingerprint, neighbours
from tests.fixtures.generate import committed_bytes
from tests.fixtures.specs import ride


def frame_of(name: str) -> pl.DataFrame:
    """Decode a committed fixture ride into its 1 Hz frame.

    Args:
        name: The fixture's name, without ``.fit``.

    Returns:
        The ride's samples.
    """
    return to_frame(decode(committed_bytes(name)).records)


@pytest.mark.parametrize(
    ("lat", "lon", "cell"),
    [(57.64911, 10.40744, "u4pruyd"), (-25.382708, -49.265506, "6gkzwgj"), (0.0, 0.0, "s000000")],
    ids=["denmark", "brazil", "origin"],
)
def test_encode_matches_known_geohashes(lat: float, lon: float, cell: str):
    """Cells are standard geohashes, so they agree with other tools.

    Given: points with published 7-character geohashes.
    Expect: the same geohash for each.
    """
    assert encode(lat, lon) == cell


def test_decode_reverses_encode():
    """A cell's name turns back into its grid position.

    Given: the cell of a point near Roubaix.
    Expect: decoding and re-encoding its row and column gives the same cell.
    """
    cell = encode(50.3967, 3.4153)

    row, column = decode_index(cell)

    assert (
        encode((row + 0.5) / (1 << 17) * 180 - 90, (column + 0.5) / (1 << 18) * 360 - 180) == cell
    )


def test_decode_rejects_bad_cells():
    """Anything but a 7-character geohash is refused.

    Given: a too-short name and one with a letter geohashes don't use ("a").
    Expect: ``ValueError`` for both.
    """
    for bad in ("u4pru", "u4pruya"):
        with pytest.raises(ValueError):
            decode_index(bad)


def test_neighbours_surround_the_cell():
    """Each cell has 8 neighbours, all touching it.

    Given: a cell near Roubaix.
    Expect: 8 distinct cells, not including the cell, each within one row and column of it.
    """
    cell = encode(50.3967, 3.4153)
    row, column = decode_index(cell)

    around = neighbours(cell)

    assert len(around) == 8
    assert cell not in around
    for other in around:
        r, c = decode_index(other)
        assert abs(r - row) <= 1 and abs(c - column) <= 1, f"{other} should touch {cell}"


def test_neighbours_wrap_at_the_date_line():
    """Longitude wraps around, so cells either side of ±180° are neighbours.

    Given: a cell just east of -180°.
    Expect: its neighbours include the cell just west of +180° at the same latitude.
    """
    east_of_line = encode(10.0, -179.9995)

    around = neighbours(east_of_line)

    assert encode(10.0, 179.9995) in around


def test_fingerprint_of_a_loop():
    """A 5 km loop passes through a ring of cells around its centre.

    Given: the fixture ride doing 30 minutes on the 5 km Nord loop (radius ~800 m).
    Expect: a few dozen cells (a 5 km ring of ~150 m cells), none at the loop's centre.
    """
    cells = fingerprint(frame_of("garmin_nord_pause_10min"))

    centre = encode(
        ride("garmin_nord_pause_10min").loop.center_lat,
        ride("garmin_nord_pause_10min").loop.center_lon,
    )
    assert 30 <= len(cells) <= 80, f"a 5 km ring should cross a few dozen cells, got {len(cells)}"
    assert centre not in cells, "the loop goes round its centre, not through it"


def test_same_loop_same_cells_other_loop_none():
    """Rides on the same loop share almost all their cells; rides elsewhere share none.

    A route that runs along a cell edge can clip a cell on one ride and not another, which is
    why matching also counts neighbouring cells.

    Given: two fixture rides on the Nord loop and the Zwift ride in Watopia.
    Expect: the Nord rides share at least 95 % of their cells, and every cell only one of
    them has touches a shared cell; the Zwift ride shares no cell with them.
    """
    first = fingerprint(frame_of("garmin_nord_pause_10min"))
    second = fingerprint(frame_of("garmin_nord_intervals_5x4"))
    zwift = fingerprint(frame_of("zwift_watopia_steady_60min"))

    shared = first & second
    assert len(shared) >= 0.95 * len(first | second), "both rides do laps of the same loop"
    for cell in first ^ second:
        assert neighbours(cell) & shared, f"{cell} should be next to the shared route"
    assert not first & zwift


def test_no_positions_no_fingerprint():
    """Rides without GPS have an empty fingerprint.

    Given: the indoor fixture ride (no positions), and a frame with no position columns.
    Expect: empty fingerprints.
    """
    indoor = fingerprint(frame_of("garmin_indoor_no_hr"))
    no_columns = fingerprint(pl.DataFrame({"t": [0, 1]}))

    assert indoor == frozenset()
    assert no_columns == frozenset()
