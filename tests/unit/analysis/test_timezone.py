"""The library's default time zone, and the rides that follow it."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitlib.analysis.timezone import default_zone, set_default_zone
from fitlib.ingest.localtime import UnknownTimeZone
from fitlib.models import Bike, OffsetSource, Ride, RideMeta
from fitlib.store.memory import MemoryCatalog
from tests.unit.factories import make_ride

HOUR = 3600
WINTER = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
SUMMER = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def add(
    catalog: MemoryCatalog,
    start: datetime,
    offset: int | None,
    source: OffsetSource,
    meta: RideMeta | None = None,
) -> Ride:
    """Add a ride with a time zone from a given source.

    Args:
        catalog: The catalog to add it to.
        start: Its start, in UTC.
        offset: Its offset from UTC, or ``None``.
        source: Where the offset came from.
        meta: Its metadata, if any.

    Returns:
        The ride.
    """
    ride = make_ride(start=start, utc_offset_s=offset, utc_offset_source=source, meta=meta)
    catalog.add_ride(ride)
    return ride


def offset_of(catalog: MemoryCatalog, ride: Ride) -> tuple[int | None, OffsetSource]:
    """Read a ride's time zone back.

    Args:
        catalog: The catalog.
        ride: The ride.

    Returns:
        Its offset and where it came from.
    """
    summary = catalog.get_ride(ride.id).summary
    return summary.utc_offset_s, summary.utc_offset_source


def test_setting_a_zone_updates_only_rides_without_their_own():
    """Rides with no time zone take the default; rides with their own keep it.

    Given: a ride with its file's time zone, one from its file name, and two with none
        (winter and summer).
    Expect: New York's -5 h and -4 h for the two without; the others untouched; 2 updated.
    """
    catalog = MemoryCatalog()
    device = add(catalog, WINTER, 2 * HOUR, OffsetSource.DEVICE)
    named = add(catalog, WINTER, -4 * HOUR, OffsetSource.FILE_NAME)
    winter = add(catalog, WINTER, None, OffsetSource.NONE)
    summer = add(catalog, SUMMER, None, OffsetSource.NONE)

    change = set_default_zone(catalog, "America/New_York")

    assert (change.zone, change.updated) == ("America/New_York", 2)
    assert default_zone(catalog) == "America/New_York"
    assert offset_of(catalog, winter) == (-5 * HOUR, OffsetSource.DEFAULT)
    assert offset_of(catalog, summer) == (-4 * HOUR, OffsetSource.DEFAULT), "daylight saving"
    assert offset_of(catalog, device) == (2 * HOUR, OffsetSource.DEVICE)
    assert offset_of(catalog, named) == (-4 * HOUR, OffsetSource.FILE_NAME)


def test_changing_and_clearing_the_zone_moves_the_rides_that_used_it():
    """A new default replaces the old one's offsets; clearing it goes back to UTC.

    Given: a ride on the New York default.
    Expect: Tokyo's +9 h after changing; no offset (UTC) after clearing; setting the same
        zone again changes nothing.
    """
    catalog = MemoryCatalog()
    ride = add(catalog, WINTER, None, OffsetSource.NONE)
    set_default_zone(catalog, "America/New_York")

    again = set_default_zone(catalog, "America/New_York")
    set_default_zone(catalog, "Asia/Tokyo")
    tokyo = offset_of(catalog, ride)
    cleared = set_default_zone(catalog, None)

    assert again.updated == 0, "the same zone again should change nothing"
    assert tokyo == (9 * HOUR, OffsetSource.DEFAULT)
    assert cleared.updated == 1
    assert offset_of(catalog, ride) == (None, OffsetSource.NONE)
    assert default_zone(catalog) is None


def test_an_unknown_zone_changes_nothing():
    """A made-up zone is refused before anything is saved.

    Given: a ride without a time zone.
    Expect: UnknownTimeZone; no default saved and the ride unchanged.
    """
    catalog = MemoryCatalog()
    ride = add(catalog, WINTER, None, OffsetSource.NONE)

    with pytest.raises(UnknownTimeZone):
        set_default_zone(catalog, "Mars/Olympus_Mons")

    assert default_zone(catalog) is None
    assert offset_of(catalog, ride) == (None, OffsetSource.NONE)


def test_rides_moved_to_another_day_with_a_default_bike_are_counted():
    """A ride whose date moves may need a different default bike, so those are counted.

    Given: rides at 02:00 UTC (the evening before in New York): one with a default bike,
        one with a bike set by hand, one with none; and one at noon with a default bike.
    Expect: 4 updated; only the first needs its bike checked.
    """
    catalog = MemoryCatalog()
    catalog.add_bike(Bike(id="b1", name="Kickr"))
    late = datetime(2026, 7, 15, 2, 0, tzinfo=UTC)
    from_default = RideMeta(bike_id="b1", bike_from_default=True)
    add(catalog, late, None, OffsetSource.NONE, from_default)
    add(catalog, late, None, OffsetSource.NONE, RideMeta(bike_id="b1"))
    add(catalog, late, None, OffsetSource.NONE)
    add(catalog, SUMMER, None, OffsetSource.NONE, from_default)

    change = set_default_zone(catalog, "America/New_York")

    assert change.updated == 4
    assert change.bikes_to_check == 1
