"""Numbers out of polars."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from fitlib.metrics.scalars import as_float


def test_numbers_from_polars_come_back_as_floats():
    """A numeric column's max, min and mean are taken as floats.

    Given: An integer column and a float column.
    Expect: Their max, min and mean as floats.
    """
    ints, floats = pl.Series([1, 5, 3]), pl.Series([0.5, 2.5])

    assert (as_float(ints.max()), as_float(ints.min())) == (5.0, 1.0)
    assert as_float(floats.mean()) == 1.5


@pytest.mark.parametrize("value", [None, True, "5", date(2025, 8, 1)])
def test_anything_else_is_refused(value: object):
    """Values that aren't numbers are refused rather than passed on.

    Given: ``None`` (as from an empty column), a boolean, a string or a date.
    Expect: ``TypeError``.
    """
    with pytest.raises(TypeError):
        as_float(value)
