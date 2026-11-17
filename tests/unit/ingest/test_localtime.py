"""Working out a ride's time zone from its file name or the library's default."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitlib.ingest.localtime import (
    UnknownTimeZone,
    check_zone,
    choose_offset,
    offset_from_name,
    offset_in_zone,
    time_zones,
)
from fitlib.models import OffsetSource

HOUR = 3600
# A real Zwift ride: named 07:23:09 on the PC, first record at 11:23:27 UTC.
ZWIFT_START = datetime(2026, 4, 29, 11, 23, 27, tzinfo=UTC)


@pytest.mark.parametrize(
    ("name", "start", "expected"),
    [
        ("2026-04-29-07-23-09.fit", ZWIFT_START, -4 * HOUR),
        ("2026-01-15-07-23-09.fit", datetime(2026, 1, 15, 12, 23, 27, tzinfo=UTC), -5 * HOUR),
        ("2025-08-02-08-29-42.fit", datetime(2025, 8, 2, 6, 30, tzinfo=UTC), 2 * HOUR),
        ("2026-04-29-17-08-27.fit", ZWIFT_START, 5 * HOUR + 45 * 60),
        ("2026-04-30-01-23-09.fit", ZWIFT_START, 14 * HOUR),
        ("2026-04-28-23-23-09.fit", ZWIFT_START, -12 * HOUR),
        ("2026-04-29-07-23-09 (1).fit", ZWIFT_START, -4 * HOUR),
        ("2026-04-29-07-23-09.FIT", ZWIFT_START, -4 * HOUR),
    ],
    ids=[
        "us-eastern-summer",
        "us-eastern-winter",
        "cest",
        "nepal",
        "plus-14h",
        "minus-12h",
        "copy-suffix",
        "upper-case",
    ],
)
def test_offset_from_a_name_that_is_the_local_start(name: str, start: datetime, expected: int):
    """A file named after its local start time gives the rider's time zone.

    Given: names a little before the first record in real time zones, as Zwift writes them.
    Expect: the offset, to the nearest quarter hour.
    """
    assert offset_from_name(name, start) == expected


@pytest.mark.parametrize(
    "name",
    [
        "2026-04-29-07-30-57.fit",
        "2026-04-29-07-38-27.fit",
        "2026-04-30-03-23-09.fit",
        "2026-02-30-07-23-09.fit",
        "garmin_export_ride_a.fit",
        "20260429072309.fit",
        "2026-04-29-07-23-09-1.fit.bak",
        None,
    ],
    ids=[
        "7-min-from-any-zone",
        "minus-3h45-no-such-zone",
        "beyond-plus-14h",
        "not-a-date",
        "no-date",
        "no-separators",
        "not-a-fit",
        "no-name",
    ],
)
def test_names_that_are_not_the_local_start_give_nothing(name: str | None):
    """Names that aren't a plausible local start time are ignored.

    Given: a name 7.5 minutes off any time zone (a renamed file, or a wrong clock), one giving
        -3:45 (no zone has it), one beyond +14 h, an impossible date, names without a date,
        and no name.
    Expect: no offset.
    """
    assert offset_from_name(name, ZWIFT_START) is None


def test_offset_in_a_zone_follows_daylight_saving():
    """A default zone gives each ride the offset in force on its date.

    Given: New York in January and in July.
    Expect: -5 h in winter and -4 h in summer.
    """
    winter = offset_in_zone("America/New_York", datetime(2026, 1, 15, 12, tzinfo=UTC))
    summer = offset_in_zone("America/New_York", datetime(2026, 7, 15, 12, tzinfo=UTC))

    assert (winter, summer) == (-5 * HOUR, -4 * HOUR)


@pytest.mark.parametrize(
    ("device", "name", "zone", "expected"),
    [
        (2 * HOUR, "2026-04-29-07-23-09.fit", "Asia/Tokyo", (2 * HOUR, OffsetSource.DEVICE)),
        (None, "2026-04-29-07-23-09.fit", "Asia/Tokyo", (-4 * HOUR, OffsetSource.FILE_NAME)),
        (None, "renamed.fit", "Asia/Tokyo", (9 * HOUR, OffsetSource.DEFAULT)),
        (None, "renamed.fit", None, (None, OffsetSource.NONE)),
    ],
    ids=["file-first", "then-name", "then-default", "else-none"],
)
def test_the_first_source_with_a_time_zone_wins(device, name, zone, expected):
    """The file's own local time beats its name, which beats the default, which beats UTC.

    Given: each source present or missing in turn.
    Expect: the offset from the first that has one, and which it was.
    """
    assert choose_offset(device, name, ZWIFT_START, zone) == expected


def test_time_zone_names_are_checked():
    """Only names from the time zone database are accepted.

    Given: a real zone, a made-up one and a path-like one.
    Expect: the real one back; UnknownTimeZone for the others; the list includes it.
    """
    assert check_zone("America/New_York") == "America/New_York"
    assert "America/New_York" in time_zones()
    for bad in ("Mars/Olympus_Mons", "../etc/passwd"):
        with pytest.raises(UnknownTimeZone):
            check_zone(bad)
