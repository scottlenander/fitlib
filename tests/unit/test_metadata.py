"""Rules for tags and default bikes."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from fitlib.metadata import (
    KEEP,
    InvalidTag,
    MetaEdit,
    apply_edit,
    default_bike,
    normalize_tag,
    normalize_tags,
    slot_for,
)
from fitlib.models import BikeDefault, BikeSlot, RideMeta, Source
from tests.unit.factories import make_summary


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


def test_normalize_tags_drops_repeats():
    """Tags typed twice, in any form, are kept once.

    Given: "Z2", "race" and " z2 ".
    Expect: "z2" then "race".
    """
    assert normalize_tags(["Z2", "race", " z2 "]) == ("z2", "race")


BEFORE = RideMeta(name="Arenberg", notes="dry", rpe=5, bike_id="giant", tags=("z2", "race"),
                  bike_from_default=True)  # fmt: skip


@pytest.mark.parametrize(
    ("edit", "after"),
    [
        (MetaEdit(), BEFORE),
        (MetaEdit(rpe=8), RideMeta("Arenberg", "dry", 8, "giant", ("z2", "race"), True)),
        (MetaEdit(rpe=None, name=None), RideMeta(None, "dry", None, "giant", ("z2", "race"), True)),
        (MetaEdit(bike_id="tarmac"), RideMeta("Arenberg", "dry", 5, "tarmac", ("z2", "race"))),
        (MetaEdit(bike_id=None), RideMeta("Arenberg", "dry", 5, None, ("z2", "race"))),
        (MetaEdit(add_tags=("race", "cobbles"), remove_tags=("z2",)),
         RideMeta("Arenberg", "dry", 5, "giant", ("race", "cobbles"), True)),
        (MetaEdit(tags=("solo",), add_tags=("wet",)),
         RideMeta("Arenberg", "dry", 5, "giant", ("solo", "wet"), True)),
    ],
    ids=["nothing", "set-rpe", "clear", "set-bike", "clear-bike", "add-remove-tags",
         "replace-tags"],
)  # fmt: skip
def test_apply_edit(edit: MetaEdit, after: RideMeta):
    """An edit changes only what it names; a bike it sets or clears is the user's.

    Given: a ride with a name, notes, RPE 5, a default bike and tags "z2" and "race".
    Expect: the fields edited change, the rest stay; tags added go last without repeats;
    a bike set or cleared is no longer from the defaults.
    """
    assert apply_edit(BEFORE, edit) == after


def test_is_empty():
    """An edit that changes nothing says so; clearing a field is a change.

    Given: an edit of nothing, one clearing the RPE, one removing a tag.
    Expect: only the first is empty.
    """
    assert MetaEdit().is_empty
    assert not MetaEdit(rpe=None).is_empty
    assert not MetaEdit(remove_tags=("z2",)).is_empty
    assert MetaEdit(rpe=KEEP).is_empty
