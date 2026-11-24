"""Working out a ride's time zone (its offset from UTC) when the file doesn't say.

In order: the file's own local time (Garmin devices); the file's name, when it is the local
start time as Zwift writes it (``2026-04-29-07-23-09.fit``); the library's default time zone;
otherwise none, and times are shown in UTC.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fitlib.ingest.decoder import MAX_UTC_OFFSET_S, MIN_UTC_OFFSET_S
from fitlib.models import OffsetSource

# The library setting holding the default time zone, an IANA name like "America/New_York".
DEFAULT_ZONE_SETTING = "default_time_zone"

# A local date and time, then anything (e.g. " (1)" for a copy), then ".fit".
_NAME = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})(?!\d).*\.fit$", re.IGNORECASE)
# Every real time zone is a whole number of quarter hours from UTC, and its minutes past the
# hour (counting forward, so -9:30 is :30 and -3:45 would be :15) are among these.
_QUARTER_HOUR_S = 900
_ZONE_MINUTES = {0, 30, 45}
# How far a file name's time may be from the first record (after taking off the offset):
# Zwift names the file about 18 s before its first record; more than this and the name is
# taken not to be the start time (a renamed file, or a clock that was off).
NAME_TOLERANCE_S = 300


class UnknownTimeZone(ValueError):
    """A time zone name that isn't in the time zone database."""

    def __init__(self, name: str) -> None:
        """Name the unknown zone.

        Args:
            name: The name given.
        """
        super().__init__(f"Unknown time zone {name!r}; use a name like 'America/New_York'")
        self.name = name


def time_zones() -> list[str]:
    """List the time zones that can be the default.

    Returns:
        IANA names such as ``"Europe/Paris"``, sorted.
    """
    return sorted(available_timezones())


def check_zone(name: str) -> str:
    """Make sure a time zone name is known.

    Args:
        name: An IANA name such as ``"America/New_York"``.

    Returns:
        The name, unchanged.

    Raises:
        UnknownTimeZone: It isn't in the time zone database.
    """
    if name not in available_timezones():
        raise UnknownTimeZone(name)
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UnknownTimeZone(name) from exc
    return name


def offset_from_name(name: str | None, start: datetime) -> int | None:
    """Work out the offset from a file named after its local start time.

    Args:
        name: The file's name (no folders), e.g. ``"2026-04-29-07-23-09.fit"``.
        start: The ride's first record, in UTC.

    Returns:
        Local time minus UTC in seconds, to the nearest quarter hour; ``None`` when the name
        isn't a date and time, or isn't within ``NAME_TOLERANCE_S`` of an offset a real time
        zone has (whole hours, half hours, or :45 as in Nepal).
    """
    match = _NAME.match(name or "")
    if not match:
        return None
    try:
        year, month, day, hour, minute, second = (int(part) for part in match.groups())
        local = datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except ValueError:  # not a real date, e.g. 2026-02-30
        return None
    seconds = (local - start).total_seconds()
    offset = round(seconds / _QUARTER_HOUR_S) * _QUARTER_HOUR_S
    if abs(seconds - offset) > NAME_TOLERANCE_S:
        return None
    if not MIN_UTC_OFFSET_S <= offset <= MAX_UTC_OFFSET_S:
        return None
    if (offset // 60) % 60 not in _ZONE_MINUTES:
        return None
    return offset


def offset_in_zone(zone: str, start: datetime) -> int:
    """The offset a time zone had at a moment, daylight saving included.

    Args:
        zone: An IANA name such as ``"America/New_York"``.
        start: The moment, in UTC.

    Returns:
        Local time minus UTC in seconds.
    """
    offset = start.astimezone(ZoneInfo(zone)).utcoffset()
    return int(offset.total_seconds()) if offset is not None else 0


def choose_offset(
    device_offset: int | None,
    name: str | None,
    start: datetime,
    default_zone: str | None,
) -> tuple[int | None, OffsetSource]:
    """Pick a ride's offset from UTC, from the first source that has one.

    Args:
        device_offset: The offset from the file's own local time, if usable.
        name: The file's name (no folders), if known.
        start: The ride's first record, in UTC.
        default_zone: The library's default time zone, if set.

    Returns:
        The offset (``None`` for none) and where it came from.
    """
    if device_offset is not None:
        return device_offset, OffsetSource.DEVICE
    from_name = offset_from_name(name, start)
    if from_name is not None:
        return from_name, OffsetSource.FILE_NAME
    if default_zone:
        return offset_in_zone(default_zone, start), OffsetSource.DEFAULT
    return None, OffsetSource.NONE
