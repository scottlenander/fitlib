"""Helpers the catalog contract tests share."""

from __future__ import annotations

from datetime import datetime, timedelta

from tests.unit.factories import DEFAULT_START


def ids(page) -> list[str]:
    """Get the ride ids on a page of search results.

    Args:
        page: The page.

    Returns:
        The ids, in result order.
    """
    return [ride.id for ride in page.items]


def at(days: int) -> datetime:
    """A time a number of days after the default ride start (2 Aug 2025, 06:30 UTC).

    Args:
        days: Days to add.

    Returns:
        The time, in UTC.
    """
    return DEFAULT_START + timedelta(days=days)
