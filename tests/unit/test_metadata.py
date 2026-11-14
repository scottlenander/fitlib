"""Rules for tags and default bikes."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from fitlib.metadata import InvalidTag, default_bike, normalize_tag, slot_for
from fitlib.models import BikeDefault, BikeSlot, Source
from tests.factories import make_summary


@pytest.mark.parametrize(
    ("typed", "stored"),
    [("Z2", "z2"), ("  Long   Ride ", "long ride"), ("cobbles", "cobbles")],
)
def test_tags_are_trimmed_and_lower_cased(typed: str, stored: str):
    """Tags are stored in one form, so "Z2" and " z2 " are the same tag.

    Given: tags typed with capitals, extra spaces, or already clean.
    Expect: lower-case with single spaces and no padding.
    """
    assert normalize_tag(typed) == stored


@pytest.mark.parametrize(
    "typed", ["", "   ", "z2,race", "x" * 41], ids=["empty", "blank", "comma", "long"]
)
def test_invalid_tags_are_rejected(typed: str):
    """Empty tags, tags with commas, and very long tags are refused.

    Given: an empty tag, a blank one, "z2,race" (two tags in one), and 41 characters.
    Expect: ``InvalidTag``.
    """
    with pytest.raises(InvalidTag):
        normalize_tag(typed)


@pytest.mark.parametrize(
    ("source", "indoor", "slot"),
    [(Source.ZWIFT, True, BikeSlot.ZWIFT), (Source.GARMIN, True, BikeSlot.INDOOR),
     (Source.GARMIN, False, BikeSlot.OUTDOOR), (Source.OTHER, False, BikeSlot.OUTDOOR)],
    ids=["zwift", "garmin-indoor", "garmin-outdoor", "other-outdoor"],
)  # fmt: skip
def test_slot_for(source: Source, indoor: bool, slot: BikeSlot):
    """Rides fall into the zwift, indoor or outdoor default-bike slot.

    Given: rides from each source, indoors and out.
    Expect: Zwift rides in ``zwift``; other indoor rides in ``indoor``; the rest ``outdoor``.
    """
    assert slot_for(make_summary(source=source, indoor=indoor)) is slot


DEFAULTS = [
    BikeDefault(BikeSlot.OUTDOOR, date(2020, 1, 1), "giant"),
    BikeDefault(BikeSlot.OUTDOOR, date(2023, 4, 15), "tarmac"),
    BikeDefault(BikeSlot.OUTDOOR, date(2025, 1, 1), None),
    BikeDefault(BikeSlot.ZWIFT, date(2021, 6, 1), "kickr"),
]


@pytest.mark.parametrize(
    ("day", "source", "indoor", "expected"),
    [
        (date(2019, 12, 31), Source.GARMIN, False, None),
        (date(2021, 7, 1), Source.GARMIN, False, "giant"),
        (date(2023, 4, 15), Source.GARMIN, False, "tarmac"),
        (date(2024, 12, 31), Source.GARMIN, False, "tarmac"),
        (date(2025, 3, 1), Source.GARMIN, False, None),
        (date(2021, 7, 1), Source.ZWIFT, True, "kickr"),
        (date(2021, 7, 1), Source.GARMIN, True, None),
    ],
    ids=["before-any", "first-bike", "on-switch-day", "day-before-stop", "after-stop",
         "zwift", "no-indoor-default"],
)  # fmt: skip
def test_default_bike_follows_the_dates(day: date, source: Source, indoor: bool, expected):
    """Each ride gets the latest default for its slot on or before its local date.

    Given: outdoor defaults Giant from 2020-01-01, Tarmac from 2023-04-15, none from
    2025-01-01; Zwift default Kickr from 2021-06-01; no indoor default. Rides at noon UTC
    with no local time.
    Expect: the bike in effect for each ride's slot and day (``None`` before any entry, after
    the stop, and for indoor rides).
    """
    summary = make_summary(
        start=datetime(day.year, day.month, day.day, 12, tzinfo=UTC),
        utc_offset_s=None,
        source=source,
        indoor=indoor,
    )

    assert default_bike(DEFAULTS, summary) == expected


def test_default_bike_uses_the_local_date():
    """The ride's local date picks the default, not its UTC date.

    Given: a ride at 23:30 UTC on 14 Apr 2023 recorded at UTC+2 (01:30 on 15 Apr locally),
    with the Tarmac default starting 15 Apr.
    Expect: the Tarmac, because locally the ride was on the 15th.
    """
    summary = make_summary(start=datetime(2023, 4, 14, 23, 30, tzinfo=UTC), utc_offset_s=7200)

    assert default_bike(DEFAULTS, summary) == "tarmac"
