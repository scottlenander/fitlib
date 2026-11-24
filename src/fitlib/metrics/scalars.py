"""Numbers out of polars, typed as numbers.

polars types a column's ``max()``, ``mean()`` and the like as any Python value (a date, a
string, a list...), since it can't know the column's type ahead of time. For numeric
columns, ``as_float`` says what the value is, and checks it.
"""

from __future__ import annotations


def as_float(value: object) -> float:
    """Take a number polars returned for a numeric column.

    Args:
        value: The value, e.g. from ``Series.max()``.

    Returns:
        It, as a float.

    Raises:
        TypeError: It isn't a number (e.g. ``None`` from an empty column).
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"Expected a number from polars, got {value!r}")
    return float(value)
