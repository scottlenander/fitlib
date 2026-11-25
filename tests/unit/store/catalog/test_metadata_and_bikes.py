"""Catalog contract: ride metadata, bikes and default bikes.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from fitlib.models import (
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
    Box,
    Filters,
    GeoSummary,
    RideMeta,
)
from fitlib.store.interfaces import (
    AmbiguousBike,
    BikeNotFound,
    CatalogStore,
    DuplicateBike,
    RideNotFound,
)
from tests.unit.factories import DEFAULT_START, make_ride
from tests.unit.store.catalog.helpers import at, ids

GIANT = Bike(id="b1000000-0000-4000-8000-000000000001", name="Giant Contend 1", kind=BikeKind.ROAD)


GRAVEL = Bike(id="b1000000-0000-4000-8000-000000000002", name="Giant Revolt", kind=BikeKind.GRAVEL)


KICKR = Bike(id="b1000000-0000-4000-8000-000000000003", name="Kickr", kind=BikeKind.TRAINER)


def add_bikes(catalog: CatalogStore) -> None:
    """Add the three test bikes.

    Args:
        catalog: The catalog to add them to.
    """
    for bike in (KICKR, GRAVEL, GIANT):
        catalog.add_bike(bike)


def test_update_meta_replaces_metadata_and_refreshes_search(catalog: CatalogStore):
    """Editing a ride replaces its metadata and makes it findable by the new text.

    Given: a ride with notes "windy" and tag "z2"; it is edited to a name, new notes, RPE 7,
    the Giant Contend 1 and tags "cobbles" and "race".
    Expect: the new metadata (tags sorted) is stored; searching "windy" no longer finds it;
    searching "cobbles", "contend" (the bike) or the new notes does.
    """
    add_bikes(catalog)
    ride = make_ride(meta=RideMeta(notes="windy", tags=("z2",)))
    catalog.add_ride(ride)
    new = RideMeta(name="Arenberg", notes="dry cobbles", rpe=7, bike_id=GIANT.id,
                   tags=("race", "cobbles"))  # fmt: skip

    catalog.update_meta(ride.id, new)
    loaded = catalog.get_ride(ride.id)

    assert loaded.meta == RideMeta("Arenberg", "dry cobbles", 7, GIANT.id, ("cobbles", "race"))
    assert ids(catalog.search(Filters(text="windy"))) == [], "old notes should not match"
    for query in ("cobbles", "contend", "dry"):
        assert ids(catalog.search(Filters(text=query))) == [ride.id], f"should find {query!r}"


def test_update_meta_errors(catalog: CatalogStore):
    """Editing an unknown ride, or setting an unknown bike, is an error.

    Given: one ride and no bikes.
    Expect: ``RideNotFound`` for an unknown ride; ``BikeNotFound`` for an unknown bike.
    """
    ride = make_ride()
    catalog.add_ride(ride)

    with pytest.raises(RideNotFound):
        catalog.update_meta("00000000-0000-0000-0000-000000000000", RideMeta())
    with pytest.raises(BikeNotFound):
        catalog.update_meta(ride.id, RideMeta(bike_id="no-such-bike"))


def test_rides_starting_in_a_box(catalog: CatalogStore):
    """Rides can be filtered on where they start.

    Given: a ride starting in northern France (the factory's), a ride starting at
    -11.64, 166.95, and a ride without positions.
    Expect: a box around the second finds only it; a box around France only the first.
    """
    france = make_ride()
    island = make_ride(start=DEFAULT_START + timedelta(days=1),
                       geo=GeoSummary(-11.64, 166.95, -11.65, 166.94, -11.63, 166.96))  # fmt: skip
    nowhere = make_ride(start=DEFAULT_START + timedelta(days=2), geo=None, has_gps=False)
    for ride in (france, island, nowhere):
        catalog.add_ride(ride)

    near_island = catalog.search(Filters(starts_in=Box(-11.7, 166.9, -11.6, 167.0)))
    near_france = catalog.search(Filters(starts_in=Box(50.0, 3.0, 51.0, 4.0)))

    assert ids(near_island) == [island.id]
    assert ids(near_france) == [france.id]


def test_update_metas_changes_several_rides_and_their_search(catalog: CatalogStore):
    """Several rides can be edited together.

    Given: two rides with no metadata; both get RPE 6, the Giant and tag "cobbles", the
    first also a name.
    Expect: each has its new metadata; searching "cobbles" finds both.
    """
    add_bikes(catalog)
    first = make_ride()
    second = make_ride(start=DEFAULT_START + timedelta(days=1))
    for ride in (first, second):
        catalog.add_ride(ride)
    shared = RideMeta(rpe=6, bike_id=GIANT.id, tags=("cobbles",))

    catalog.update_metas({first.id: replace(shared, name="Arenberg"), second.id: shared})

    assert catalog.get_ride(first.id).meta == replace(shared, name="Arenberg")
    assert catalog.get_ride(second.id).meta == shared
    assert set(ids(catalog.search(Filters(text="cobbles")))) == {first.id, second.id}


@pytest.mark.parametrize("bad", ["ride", "bike"])
def test_update_metas_changes_nothing_when_one_fails(catalog: CatalogStore, bad: str):
    """Editing several rides is all or nothing.

    Given: two rides edited together, the second edit naming an unknown ride or bike.
    Expect: ``RideNotFound`` or ``BikeNotFound``, and the first ride unchanged.
    """
    first = make_ride()
    second = make_ride(start=DEFAULT_START + timedelta(days=1))
    for ride in (first, second):
        catalog.add_ride(ride)
    other = "00000000-0000-0000-0000-000000000000" if bad == "ride" else second.id
    other_meta = RideMeta(bike_id="no-such-bike" if bad == "bike" else None)

    with pytest.raises(RideNotFound if bad == "ride" else BikeNotFound):
        catalog.update_metas({first.id: RideMeta(rpe=3), other: other_meta})

    assert catalog.get_ride(first.id).meta == RideMeta(), "the first ride should be unchanged"


def test_bikes_are_listed_by_name_and_retired_ones_can_be_hidden(catalog: CatalogStore):
    """Bikes are listed alphabetically; retired bikes can be left out.

    Given: Kickr, Giant Revolt and Giant Contend 1 added in that order; then the Kickr
    retired.
    Expect: all three by name (Contend, Revolt, Kickr), and without the Kickr when retired
    bikes are hidden.
    """
    add_bikes(catalog)
    catalog.update_bike(replace(KICKR, retired=True))

    everything = catalog.list_bikes()
    active = catalog.list_bikes(include_retired=False)

    assert [b.name for b in everything] == ["Giant Contend 1", "Giant Revolt", "Kickr"]
    assert [b.name for b in active] == ["Giant Contend 1", "Giant Revolt"]
    assert catalog.get_bike(KICKR.id).retired


def test_bike_names_are_unique_ignoring_case(catalog: CatalogStore):
    """Two bikes can't share a name, even in different case, on add or rename.

    Given: the three test bikes; a new bike named "giant contend 1"; then the Kickr renamed
    to "GIANT REVOLT".
    Expect: ``DuplicateBike`` both times.
    """
    add_bikes(catalog)

    with pytest.raises(DuplicateBike):
        catalog.add_bike(Bike(id="b1000000-0000-4000-8000-000000000009", name="giant contend 1"))
    with pytest.raises(DuplicateBike):
        catalog.update_bike(replace(KICKR, name="GIANT REVOLT"))


@pytest.mark.parametrize(
    ("ref", "expected"),
    [("Giant Contend 1", "Giant Contend 1"), ("kickr", "Kickr"), ("giant c", "Giant Contend 1"),
     ("  KICK", "Kickr")],
    ids=["exact", "any-case", "prefix", "spaces-and-case"],
)  # fmt: skip
def test_resolve_bike_by_name_or_prefix(catalog: CatalogStore, ref: str, expected: str):
    """Bikes can be named exactly (any case) or by a unique start of the name.

    Given: Giant Contend 1, Giant Revolt and Kickr.
    Expect: each reference finds the named bike.
    """
    add_bikes(catalog)

    assert catalog.resolve_bike(ref).name == expected


def test_resolve_bike_errors(catalog: CatalogStore):
    """A bike reference must pick out exactly one bike.

    Given: Giant Contend 1, Giant Revolt and Kickr.
    Expect: "giant" is ambiguous (both Giants listed); "trek" and "" are not found.
    """
    add_bikes(catalog)

    with pytest.raises(AmbiguousBike) as ambiguous:
        catalog.resolve_bike("giant")
    with pytest.raises(BikeNotFound):
        catalog.resolve_bike("trek")
    with pytest.raises(BikeNotFound):
        catalog.resolve_bike("")

    assert ambiguous.value.candidates == ["Giant Contend 1", "Giant Revolt"]


def test_renaming_a_bike_refreshes_search(catalog: CatalogStore):
    """Rides are found by their bike's new name after a rename.

    Given: a ride on the Giant Contend 1; the bike renamed "Contend AR".
    Expect: searching "ar" finds the ride; searching "giant" doesn't.
    """
    add_bikes(catalog)
    ride = make_ride(meta=RideMeta(bike_id=GIANT.id))
    catalog.add_ride(ride)

    catalog.update_bike(replace(GIANT, name="Contend AR"))

    assert ids(catalog.search(Filters(text="ar"))) == [ride.id]
    assert ids(catalog.search(Filters(text="giant"))) == [], "the old name should not match"


def test_bike_totals_and_tag_counts(catalog: CatalogStore):
    """Totals per bike and counts per tag cover every ride.

    Given: two rides on the Giant (30 km, 1 h each; tags z2 and race / z2), one on the Kickr
    (no distance; tag z2), and one with no bike or tags.
    Expect: Giant 2 rides, 60 km, 2 h; Revolt 0; Kickr 1 ride, 0 km; tags race 1, z2 3.
    """
    add_bikes(catalog)
    catalog.add_ride(
        make_ride(start=at(0), moving_s=3600, meta=RideMeta(bike_id=GIANT.id, tags=("z2", "race")))
    )
    catalog.add_ride(
        make_ride(start=at(1), moving_s=3600, meta=RideMeta(bike_id=GIANT.id, tags=("z2",)))
    )
    catalog.add_ride(
        make_ride(start=at(2), distance_m=None, meta=RideMeta(bike_id=KICKR.id, tags=("z2",)))
    )
    catalog.add_ride(make_ride(start=at(3)))

    totals = {t.bike.name: (t.rides, t.distance_m, t.moving_s) for t in catalog.bike_totals()}
    tags = catalog.tag_counts()

    assert totals == {
        "Giant Contend 1": (2, 60_000.0, 7200),
        "Giant Revolt": (0, 0.0, 0),
        "Kickr": (1, 0.0, 3500),
    }
    assert tags == [("race", 1), ("z2", 3)]


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(tags=("z2",)), ["monday", "tuesday"]),
        (Filters(tags=("z2", "race")), ["monday"]),
        (Filters(bike_id=GIANT.id), ["monday"]),
        (Filters(has_bike=False), ["wednesday"]),
        (Filters(has_bike=True), ["monday", "tuesday"]),
        (Filters(min_rpe=6), ["monday"]),
        (Filters(max_rpe=5), ["tuesday"]),
    ],
    ids=["tag", "every-tag", "bike", "no-bike", "has-bike", "min-rpe", "max-rpe"],
)
def test_metadata_filters(catalog: CatalogStore, filters: Filters, expected: list[str]):
    """Rides can be filtered by tags (all must match), bike, having a bike, and RPE.

    Given: Monday (Giant, RPE 8, tags z2 + race), Tuesday (Kickr, RPE 4, tag z2), Wednesday
    (no bike, no RPE, no tags).
    Expect: only the named days; rides without an RPE never match an RPE filter.
    """
    add_bikes(catalog)
    rides = {
        "monday": make_ride(
            start=at(0), meta=RideMeta(rpe=8, bike_id=GIANT.id, tags=("z2", "race"))
        ),
        "tuesday": make_ride(start=at(1), meta=RideMeta(rpe=4, bike_id=KICKR.id, tags=("z2",))),
        "wednesday": make_ride(start=at(2)),
    }
    for ride in rides.values():
        catalog.add_ride(ride)

    page = catalog.search(filters, descending=False)

    assert ids(page) == [rides[day].id for day in expected]


def test_bike_default_entries(catalog: CatalogStore):
    """Default-bike entries are kept per slot and date; one can be replaced or removed.

    Given: outdoor defaults Giant from 2020-01-01 and Revolt from 2023-04-15, a Zwift default
    Kickr from 2020-01-01, an indoor "stop defaulting" entry from 2024-06-01; then the 2023
    outdoor entry replaced with the Giant, then removed.
    Expect: entries by slot then date; the replacement; and removal reported once.
    """
    add_bikes(catalog)
    entries = [
        BikeDefault(BikeSlot.OUTDOOR, date(2023, 4, 15), GRAVEL.id),
        BikeDefault(BikeSlot.ZWIFT, date(2020, 1, 1), KICKR.id),
        BikeDefault(BikeSlot.OUTDOOR, date(2020, 1, 1), GIANT.id),
        BikeDefault(BikeSlot.INDOOR, date(2024, 6, 1), None),
    ]
    for entry in entries:
        catalog.set_bike_default(entry)

    listed = catalog.bike_defaults()
    catalog.set_bike_default(BikeDefault(BikeSlot.OUTDOOR, date(2023, 4, 15), GIANT.id))
    replaced = [d for d in catalog.bike_defaults() if d.effective_from == date(2023, 4, 15)]
    removed = catalog.delete_bike_default(BikeSlot.OUTDOOR, date(2023, 4, 15))
    removed_again = catalog.delete_bike_default(BikeSlot.OUTDOOR, date(2023, 4, 15))

    assert listed == [entries[3], entries[2], entries[0], entries[1]], "by slot, then date"
    assert replaced == [BikeDefault(BikeSlot.OUTDOOR, date(2023, 4, 15), GIANT.id)]
    assert (removed, removed_again) == (True, False)
    with pytest.raises(BikeNotFound):
        catalog.set_bike_default(BikeDefault(BikeSlot.ZWIFT, date(2025, 1, 1), "no-such-bike"))


def test_bike_from_default_round_trips(catalog: CatalogStore):
    """Whether a bike came from a default is stored; without a bike it is always false.

    Given: a ride whose Giant came from a default; then its metadata replaced with no bike but
    the flag still set.
    Expect: the flag reads back true with the bike, and false once there is no bike.
    """
    add_bikes(catalog)
    ride = make_ride(meta=RideMeta(bike_id=GIANT.id, bike_from_default=True))
    catalog.add_ride(ride)

    with_bike = catalog.get_ride(ride.id).meta
    catalog.update_meta(ride.id, RideMeta(bike_from_default=True))
    without_bike = catalog.get_ride(ride.id).meta

    assert with_bike.bike_from_default
    assert not without_bike.bike_from_default, "no bike means nothing came from a default"
