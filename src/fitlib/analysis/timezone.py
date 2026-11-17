"""The library's default time zone, for rides whose files don't say where they were ridden.

Changing it updates those rides at once: their offset from UTC is worked out again for their
own date (daylight saving included), with no need to recompute. Rides whose time zone came
from their file or file name are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from fitlib.ingest.localtime import DEFAULT_ZONE_SETTING, check_zone, offset_in_zone
from fitlib.models import OffsetSource
from fitlib.store.interfaces import CatalogStore

# Rides that follow the default: those that used it, and those with no time zone at all.
_FOLLOWS_DEFAULT = (OffsetSource.DEFAULT, OffsetSource.NONE)


@dataclass(frozen=True)
class ZoneChange:
    """What changing the default time zone did.

    Attributes:
        zone: The new default, or ``None`` for none (UTC).
        updated: Rides whose time zone changed.
        bikes_to_check: Of those, rides whose date moved to another day and whose bike came
            from a default bike: the default for the new day may be a different bike, which
            "Apply defaults" on the Bikes page sorts out.
    """

    zone: str | None
    updated: int
    bikes_to_check: int


def default_zone(catalog: CatalogStore) -> str | None:
    """Read the library's default time zone.

    Args:
        catalog: The library's catalog.

    Returns:
        An IANA name such as ``"America/New_York"``, or ``None`` if none is set.
    """
    return catalog.get_setting(DEFAULT_ZONE_SETTING)


def _local_date(start: datetime, offset: int | None) -> date:
    """The day a ride started on, as shown.

    Args:
        start: Its start, in UTC.
        offset: Its offset from UTC, or ``None`` for UTC.

    Returns:
        The date.
    """
    return (start + timedelta(seconds=offset or 0)).date()


def set_default_zone(catalog: CatalogStore, zone: str | None) -> ZoneChange:
    """Set (or clear) the default time zone and update the rides that follow it.

    Args:
        catalog: The library's catalog.
        zone: An IANA name such as ``"America/New_York"``, or ``None`` for none.

    Returns:
        How many rides changed, and how many may need their default bike checked.

    Raises:
        UnknownTimeZone: The zone isn't in the time zone database (nothing is changed).
    """
    if zone is not None:
        check_zone(zone)
    source = OffsetSource.DEFAULT if zone else OffsetSource.NONE
    changes: dict[str, tuple[int | None, OffsetSource]] = {}
    moved_day: list[str] = []
    for ride_id, start, old in catalog.rides_by_offset_source(_FOLLOWS_DEFAULT):
        new = offset_in_zone(zone, start) if zone else None
        if new == old:
            continue
        changes[ride_id] = (new, source)
        if _local_date(start, old) != _local_date(start, new):
            moved_day.append(ride_id)
    catalog.set_setting(DEFAULT_ZONE_SETTING, zone)
    catalog.set_utc_offsets(changes)
    bikes_to_check = sum(
        1
        for ride_id in moved_day
        if (meta := catalog.get_ride(ride_id).meta).bike_id and meta.bike_from_default
    )
    return ZoneChange(zone=zone, updated=len(changes), bikes_to_check=bikes_to_check)
