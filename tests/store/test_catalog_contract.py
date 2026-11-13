"""Behaviour every ``CatalogStore`` must have. Runs against each implementation.

A new backend (e.g. a future cloud one) is added to the ``catalog`` fixture's params and must
pass this whole file unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from fitlib.models import Filters, RideMeta, SortKey, Source
from fitlib.store.interfaces import AmbiguousRideId, CatalogStore, DuplicateRide, RideNotFound
from fitlib.store.local import SqliteCatalog
from fitlib.store.memory import MemoryCatalog
from tests.factories import DEFAULT_START, make_ride


@pytest.fixture(params=["sqlite", "memory"])
def catalog(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[CatalogStore]:
    store: CatalogStore
    if request.param == "sqlite":
        store = SqliteCatalog(tmp_path / "catalog.sqlite3")
    else:
        store = MemoryCatalog()
    yield store
    store.close()


def ids(page) -> list[str]:
    return [ride.id for ride in page.items]


def at(days: int) -> datetime:
    return DEFAULT_START + timedelta(days=days)


# -- adding and reading ---------------------------------------------------------------------


def test_added_ride_reads_back_unchanged(catalog: CatalogStore):
    """A stored ride comes back exactly as it went in, including laps, location and metadata.

    Given: a ride with two laps, a GPS bounding box, a name, notes, RPE and two tags.
    Expect: ``get_ride`` returns an equal ``Ride``.
    """
    ride = make_ride(
        meta=RideMeta(name="Arenberg loop", notes="windy", rpe=7, tags=("cobbles", "z2"))
    )

    catalog.add_ride(ride)
    loaded = catalog.get_ride(ride.id)

    assert loaded == ride, "every field should survive a round trip through the catalog"


def test_ride_without_optional_data_reads_back_unchanged(catalog: CatalogStore):
    """Indoor rides with no power, HR, GPS or laps store their missing values as missing.

    Given: a ride whose optional summary fields are all ``None`` or empty.
    Expect: ``get_ride`` returns an equal ``Ride``, with no zeros standing in for missing data.
    """
    ride = make_ride(
        indoor=True, has_power=False, has_hr=False, has_gps=False, distance_m=None,
        ascent_m=None, avg_power=None, max_power=None, avg_hr=None, max_hr=None,
        avg_cadence=None, avg_speed_mps=None, max_speed_mps=None, utc_offset_s=None,
        device=None, laps=(), geo=None,
    )  # fmt: skip

    catalog.add_ride(ride)
    loaded = catalog.get_ride(ride.id)

    assert loaded == ride


def test_same_file_hash_cannot_be_added_twice(catalog: CatalogStore):
    """The catalog refuses a second ride from the same file.

    Given: a stored ride, and a new ride with a different id but the same sha256.
    Expect: ``DuplicateRide`` is raised and the catalog still holds one ride.
    """
    first = make_ride()
    second = make_ride(sha256=first.sha256)
    catalog.add_ride(first)

    with pytest.raises(DuplicateRide):
        catalog.add_ride(second)

    assert catalog.count() == 1, "the duplicate should not have been stored"


def test_unknown_ride_is_not_found(catalog: CatalogStore):
    """Asking for an id that was never stored is an error, not ``None``.

    Given: an empty catalog.
    Expect: ``get_ride`` raises ``RideNotFound``.
    """
    with pytest.raises(RideNotFound):
        catalog.get_ride("00000000-0000-0000-0000-000000000000")


def test_find_by_hash(catalog: CatalogStore):
    """Rides can be looked up by the sha256 of their original file.

    Given: one stored ride.
    Expect: its hash gives its id; an unknown hash gives ``None``.
    """
    ride = make_ride()
    catalog.add_ride(ride)

    found = catalog.find_by_hash(ride.sha256)
    missing = catalog.find_by_hash("f" * 64)

    assert found == ride.id
    assert missing is None, "an unknown hash should find nothing"


# -- ids --------------------------------------------------------------------------------------


def test_resolve_id_accepts_full_ids_and_unique_prefixes(catalog: CatalogStore):
    """Rides can be referred to by a short id prefix, like git commits.

    Given: two rides whose ids share the first four characters (``abcd``).
    Expect: the full id and a unique 5-character prefix both resolve to the right ride.
    """
    first = make_ride(id="abcd1111-0000-4000-8000-000000000001")
    second = make_ride(id="abcd2222-0000-4000-8000-000000000002")
    catalog.add_ride(first)
    catalog.add_ride(second)

    by_full_id = catalog.resolve_id(first.id)
    by_prefix = catalog.resolve_id("abcd2")

    assert by_full_id == first.id
    assert by_prefix == second.id


def test_resolve_id_rejects_ambiguous_short_and_unknown_refs(catalog: CatalogStore):
    """A reference must pick out exactly one ride.

    Given: two rides whose ids share the prefix ``abcd``.
    Expect: ``abcd`` is ambiguous (both candidates listed); a 3-character prefix and an unknown
    prefix are not found.
    """
    catalog.add_ride(make_ride(id="abcd1111-0000-4000-8000-000000000001"))
    catalog.add_ride(make_ride(id="abcd2222-0000-4000-8000-000000000002"))

    with pytest.raises(AmbiguousRideId) as ambiguous:
        catalog.resolve_id("abcd")
    with pytest.raises(RideNotFound):
        catalog.resolve_id("abc")
    with pytest.raises(RideNotFound):
        catalog.resolve_id("ffff")

    assert len(ambiguous.value.candidates) == 2, "both matching rides should be listed"


# -- time windows -----------------------------------------------------------------------------


def test_rides_starting_between_is_inclusive_and_ordered(catalog: CatalogStore):
    """The overlap check gets every ride that starts inside a time window, oldest first.

    Given: rides starting 2 min before, exactly at, 1 min after, exactly at the end of, and
    after a 4-minute window.
    Expect: the three rides from the window's start to its end (both inclusive), oldest first.
    """
    window_start = DEFAULT_START
    window_end = DEFAULT_START + timedelta(minutes=4)
    before = make_ride(start=window_start - timedelta(minutes=2))
    on_start = make_ride(start=window_start)
    inside = make_ride(start=window_start + timedelta(minutes=1))
    on_end = make_ride(start=window_end)
    after = make_ride(start=window_end + timedelta(seconds=1))
    for ride in (after, inside, before, on_end, on_start):
        catalog.add_ride(ride)

    found = catalog.rides_starting_between(window_start, window_end)

    assert [r.id for r in found] == [on_start.id, inside.id, on_end.id]


# -- search -----------------------------------------------------------------------------------


def test_search_without_filters_lists_newest_first(catalog: CatalogStore):
    """The default library view shows every ride, newest first.

    Given: three rides on consecutive days, added out of order.
    Expect: all three, newest first, with a total of 3.
    """
    rides = [make_ride(start=at(day)) for day in (1, 0, 2)]
    for ride in rides:
        catalog.add_ride(ride)

    page = catalog.search()

    assert ids(page) == [rides[2].id, rides[0].id, rides[1].id], "newest ride should be first"
    assert page.total == 3


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        (Filters(since=at(1)), ["tuesday", "wednesday"]),
        (Filters(until=at(1)), ["monday"]),
        (Filters(since=at(1), until=at(2)), ["tuesday"]),
        (Filters(source=Source.ZWIFT), ["tuesday"]),
        (Filters(indoor=True), ["tuesday"]),
        (Filters(indoor=False), ["monday", "wednesday"]),
        (Filters(min_duration_s=3000), ["monday", "tuesday"]),
        (Filters(max_duration_s=3000), ["wednesday"]),
        (Filters(has_power=False), ["wednesday"]),
    ],
    ids=["since", "until", "since-until", "source", "indoor", "outdoor", "min-duration",
         "max-duration", "no-power"],
)  # fmt: skip
def test_search_filters(catalog: CatalogStore, filters: Filters, expected: list[str]):
    """Each library filter keeps only the rides that match it.

    Given: Monday (outdoor Garmin, 60 min, power), Tuesday (Zwift, indoor, 90 min, power) and
    Wednesday (outdoor Garmin, 30 min, no power meter).
    Expect: only the named days, oldest first.
    """
    rides = {
        "monday": make_ride(start=at(0), moving_s=3600),
        "tuesday": make_ride(start=at(1), source=Source.ZWIFT, indoor=True, moving_s=5400),
        "wednesday": make_ride(start=at(2), moving_s=1800, has_power=False, avg_power=None),
    }
    for ride in rides.values():
        catalog.add_ride(ride)

    page = catalog.search(filters, descending=False)

    assert ids(page) == [rides[day].id for day in expected]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("arenberg", ["named"]),
        ("ARENB", ["named"]),
        ("headwind", ["noted"]),
        ("cobbles", ["tagged"]),
        ("zwift", ["zwift"]),
        ("edge 540", ["named", "noted", "tagged"]),
        ("arenberg headwind", []),
        ("nothing-like-this", []),
    ],
    ids=["name", "prefix-any-case", "notes", "tag", "source", "device-two-words",
         "all-words-must-match", "no-match"],
)  # fmt: skip
def test_search_text(catalog: CatalogStore, query: str, expected: list[str]):
    """Text search matches the start of words in name, notes, tags, source and device.

    Given: a named ride, a ride with notes, a tagged ride (all Garmin Edge 540) and a Zwift
    ride with no device.
    Expect: each query finds only the listed rides; every word in the query must match.
    """
    rides = {
        "named": make_ride(start=at(0), meta=RideMeta(name="Arenberg loop")),
        "noted": make_ride(start=at(1), meta=RideMeta(notes="Strong headwind home")),
        "tagged": make_ride(start=at(2), meta=RideMeta(tags=("cobbles",))),
        "zwift": make_ride(start=at(3), source=Source.ZWIFT, device=None),
    }
    for ride in rides.values():
        catalog.add_ride(ride)

    page = catalog.search(Filters(text=query), descending=False)

    assert ids(page) == [rides[name].id for name in expected]


def test_search_sorts_missing_values_last(catalog: CatalogStore):
    """Sorting by average power puts rides without a power meter last, in either direction.

    Given: rides averaging 150 W and 250 W, and one with no power data.
    Expect: 250, 150, none when descending; 150, 250, none when ascending.
    """
    low = make_ride(start=at(0), avg_power=150.0)
    high = make_ride(start=at(1), avg_power=250.0)
    none = make_ride(start=at(2), avg_power=None, has_power=False)
    for ride in (low, high, none):
        catalog.add_ride(ride)

    descending = catalog.search(sort=SortKey.POWER, descending=True)
    ascending = catalog.search(sort=SortKey.POWER, descending=False)

    assert ids(descending) == [high.id, low.id, none.id]
    assert ids(ascending) == [low.id, high.id, none.id], "missing power should still be last"


def test_search_pages_through_results(catalog: CatalogStore):
    """Results come one page at a time with the total count of matches.

    Given: five rides on consecutive days.
    Expect: offset 2, limit 2 gives the 3rd and 4th newest, and a total of 5.
    """
    rides = [make_ride(start=at(day)) for day in range(5)]
    for ride in rides:
        catalog.add_ride(ride)

    page = catalog.search(offset=2, limit=2)

    assert ids(page) == [rides[2].id, rides[1].id], "should be the 3rd and 4th newest rides"
    assert (page.total, page.offset, page.limit) == (5, 2, 2)


# -- SQLite only ------------------------------------------------------------------------------


def test_sqlite_catalog_persists_and_is_migrated(tmp_path: Path):
    """A SQLite catalog keeps its rides after being closed and reopened, at the latest schema.

    Given: a catalog file with one ride, closed and opened again.
    Expect: the ride is still there and the schema version is 1 (the initial migration).
    """
    path = tmp_path / "catalog.sqlite3"
    ride = make_ride(start=datetime(2025, 8, 2, tzinfo=UTC))
    first = SqliteCatalog(path)
    first.add_ride(ride)
    first.close()

    reopened = SqliteCatalog(path)
    loaded = reopened.get_ride(ride.id)
    version = reopened.schema_version
    reopened.close()

    assert loaded == ride, "the ride should survive closing and reopening the catalog"
    assert version == 1
