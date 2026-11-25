"""Catalog contract: library settings, and rides by where their time zone came from.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from fitlib.models import (
    Filters,
    OffsetSource,
)
from fitlib.store.interfaces import (
    CatalogStore,
    RideNotFound,
)
from tests.unit.factories import DEFAULT_START, make_ride


def test_settings_are_set_read_and_cleared(catalog: CatalogStore):
    """A library setting holds one value per key until cleared.

    Given: an empty catalog.
    Expect: nothing at first; the latest value after setting twice; nothing after clearing.
    """
    before = catalog.get_setting("default_time_zone")
    catalog.set_setting("default_time_zone", "Europe/Paris")
    catalog.set_setting("default_time_zone", "Asia/Tokyo")
    after_set = catalog.get_setting("default_time_zone")
    catalog.set_setting("default_time_zone", None)

    assert before is None
    assert after_set == "Asia/Tokyo"
    assert catalog.get_setting("default_time_zone") is None


def test_rides_are_found_by_where_their_time_zone_came_from(catalog: CatalogStore):
    """Rides can be listed by the source of their time zone, oldest first.

    Given: rides whose time zones came from the device, the file name, the default and none.
    Expect: asking for default and none lists those two, with start and offset; the source
        survives being stored.
    """
    rides = {}
    for day, (offset, source) in enumerate(
        [
            (7200, OffsetSource.DEVICE),
            (-14400, OffsetSource.FILE_NAME),
            (-18000, OffsetSource.DEFAULT),
            (None, OffsetSource.NONE),
        ]
    ):
        ride = make_ride(
            start=DEFAULT_START + timedelta(days=day),
            utc_offset_s=offset,
            utc_offset_source=source,
        )
        catalog.add_ride(ride)
        rides[source] = ride

    found = catalog.rides_by_offset_source([OffsetSource.NONE, OffsetSource.DEFAULT])

    default, none = rides[OffsetSource.DEFAULT], rides[OffsetSource.NONE]
    assert found == [
        (default.id, default.summary.start, -18000),
        (none.id, none.summary.start, None),
    ]
    assert catalog.get_ride(rides[OffsetSource.FILE_NAME].id).summary.utc_offset_source == (
        OffsetSource.FILE_NAME
    )


def test_changing_a_rides_time_zone_keeps_the_rest_and_moves_its_date(catalog: CatalogStore):
    """A new time zone changes only the offset, and the date its default name and search use.

    Given: an unnamed Garmin ride starting 03:00 UTC on 2 Aug 2025, with no time zone.
    Expect: after moving it to -5 h (the default), it is named for 22:00 on 1 Aug and found
        by searching "2025-08-01" (it wasn't before); its other figures are unchanged. An
        unknown ride refuses the change.
    """
    ride = make_ride(start=datetime(2025, 8, 2, 3, 0, tzinfo=UTC), utc_offset_s=None)
    catalog.add_ride(ride)
    found_before = catalog.search(Filters(text="2025-08-01")).items

    catalog.set_utc_offsets({ride.id: (-18000, OffsetSource.DEFAULT)})
    after = catalog.get_ride(ride.id)

    assert (after.summary.utc_offset_s, after.summary.utc_offset_source) == (
        -18000,
        OffsetSource.DEFAULT,
    )
    assert after.summary == replace(
        ride.summary, utc_offset_s=-18000, utc_offset_source=OffsetSource.DEFAULT
    )
    assert (ride.display_name, after.display_name) == (
        "Garmin 2025-08-02 03:00 UTC",
        "Garmin 2025-08-01 22:00",
    )
    assert found_before == (), "on 2 Aug in UTC, a search for 1 Aug shouldn't find it"
    assert [r.id for r in catalog.search(Filters(text="2025-08-01")).items] == [ride.id]
    with pytest.raises(RideNotFound):
        catalog.set_utc_offsets({"no-such-ride": (0, OffsetSource.DEFAULT)})
