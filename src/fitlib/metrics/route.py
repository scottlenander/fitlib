"""Route fingerprints: the set of ~150 m grid cells a ride passed through.

Cells are geohashes of 7 characters (about 153 m by 153 m at the equator, narrower east to
west further north). Two rides on the same roads pass through mostly the same cells, so
comparing cell sets finds rides on the same route, outdoors or in Zwift (whose files carry
the virtual world's coordinates).

Cells are location data: they're stored apart from other figures and never logged.
"""

from __future__ import annotations

from functools import lru_cache

import polars as pl

from fitlib.models import Route

PRECISION = 7
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_DECODE = {char: index for index, char in enumerate(_BASE32)}
# A 7-character geohash has 35 bits: 18 for longitude and 17 for latitude, interleaved
# starting with longitude.
_LON_BITS = (PRECISION * 5 + 1) // 2
_LAT_BITS = PRECISION * 5 // 2
_LON_CELLS = 1 << _LON_BITS
_LAT_CELLS = 1 << _LAT_BITS


def cell_index(lat: float, lon: float) -> tuple[int, int]:
    """Find the grid row and column of a point.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        ``(row, column)``: the cell's latitude and longitude indices.
    """
    row = min(int((lat + 90) / 180 * _LAT_CELLS), _LAT_CELLS - 1)
    column = min(int((lon + 180) / 360 * _LON_CELLS), _LON_CELLS - 1)
    return row, column


def encode_index(row: int, column: int) -> str:
    """Name a grid cell by its geohash.

    Args:
        row: The cell's latitude index.
        column: The cell's longitude index.

    Returns:
        The 7-character geohash.
    """
    value = 0
    lon_bit, lat_bit = _LON_BITS - 1, _LAT_BITS - 1
    for i in range(PRECISION * 5):
        if i % 2 == 0:
            value = value << 1 | (column >> lon_bit) & 1
            lon_bit -= 1
        else:
            value = value << 1 | (row >> lat_bit) & 1
            lat_bit -= 1
    return "".join(_BASE32[(value >> shift) & 31] for shift in range(30, -1, -5))


# Cached: rides on the same route share most of their cells.
@lru_cache(maxsize=1 << 16)
def decode_index(cell: str) -> tuple[int, int]:
    """Find a geohash cell's grid row and column.

    Args:
        cell: A 7-character geohash.

    Returns:
        ``(row, column)``.

    Raises:
        ValueError: The text isn't a 7-character geohash.
    """
    if len(cell) != PRECISION or any(char not in _DECODE for char in cell):
        raise ValueError(f"Not a {PRECISION}-character geohash: {cell!r}")
    value = 0
    for char in cell:
        value = value << 5 | _DECODE[char]
    row = column = 0
    for i in range(PRECISION * 5):
        bit = (value >> (PRECISION * 5 - 1 - i)) & 1
        if i % 2 == 0:
            column = column << 1 | bit
        else:
            row = row << 1 | bit
    return row, column


def encode(lat: float, lon: float) -> str:
    """Name the cell a point lies in.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        The point's 7-character geohash.
    """
    return encode_index(*cell_index(lat, lon))


def neighbours(cell: str) -> set[str]:
    """List the up to 8 cells around a cell.

    Longitude wraps around at ±180°; there are no cells beyond the poles.

    Args:
        cell: A 7-character geohash.

    Returns:
        The surrounding cells, not including ``cell``.
    """
    row, column = decode_index(cell)
    around = set()
    for d_row in (-1, 0, 1):
        for d_column in (-1, 0, 1):
            r = row + d_row
            if (d_row or d_column) and 0 <= r < _LAT_CELLS:
                around.add(encode_index(r, (column + d_column) % _LON_CELLS))
    return around


def fingerprint(frame: pl.DataFrame) -> Route:
    """Find the cells a ride passed through.

    The samples are first reduced to distinct grid cells with polars, so only a few hundred
    cells per ride are named, however long the ride.

    Args:
        frame: The ride's 1 Hz samples, with ``lat`` and ``lon`` columns (missing where the
            device had no fix).

    Returns:
        The ride's cells; empty when it has no positions.
    """
    if "lat" not in frame.columns or "lon" not in frame.columns:
        return frozenset()
    cells = (
        frame.select("lat", "lon")
        .drop_nulls()
        .select(
            ((pl.col("lat") + 90) / 180 * _LAT_CELLS)
            .floor()
            .cast(pl.Int64)
            .clip(0, _LAT_CELLS - 1)
            .alias("row"),
            ((pl.col("lon") + 180) / 360 * _LON_CELLS)
            .floor()
            .cast(pl.Int64)
            .clip(0, _LON_CELLS - 1)
            .alias("column"),
        )
        .unique()
    )
    return frozenset(encode_index(r, c) for r, c in cells.iter_rows())


def dilate(cells: Route) -> set[tuple[int, int]]:
    """Grow a set of cells by one cell all round, as grid positions.

    Comparing one ride's cells with another's grown set tolerates GPS drift and routes that
    run along a cell edge.

    Args:
        cells: The cells to grow.

    Returns:
        The ``(row, column)`` of every cell and of every cell touching one.
    """
    grown = set()
    for cell in cells:
        row, column = decode_index(cell)
        for r in (row - 1, row, row + 1):
            if 0 <= r < _LAT_CELLS:
                for c in (column - 1, column, column + 1):
                    grown.add((r, c % _LON_CELLS))
    return grown


def overlap(mine: Route, theirs_grown: set[tuple[int, int]]) -> float:
    """Measure how much of a route another ride covered.

    Args:
        mine: One ride's cells.
        theirs_grown: The other ride's cells, grown with ``dilate``.

    Returns:
        The fraction of ``mine`` that lies in or next to the other ride's cells, from 0 to 1;
        0 when ``mine`` is empty.
    """
    if not mine:
        return 0.0
    return sum(decode_index(cell) in theirs_grown for cell in mine) / len(mine)
