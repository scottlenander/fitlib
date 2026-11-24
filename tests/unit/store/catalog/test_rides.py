"""Behaviour every ``CatalogStore`` must have. Runs against each implementation.

A new backend (e.g. a future cloud one) is added to the ``catalog`` fixture's params and must
pass this whole file unchanged.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from importlib import resources
from pathlib import Path

import pytest

from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
    Box,
    Filters,
    GeoSummary,
    OffsetSource,
    RideMeta,
    SortKey,
    Source,
    WatchedFile,
    WatchFolder,
    WatchOutcome,
)
from fitlib.store.interfaces import (
    AmbiguousBike,
    AmbiguousRideId,
    AthleteCatalog,
    BikeCatalog,
    BikeNotFound,
    CatalogStore,
    DuplicateBike,
    DuplicateRide,
    RideCatalog,
    RideNotFound,
    SettingsStore,
    WatchState,
)
from fitlib.store.local import SqliteCatalog
from fitlib.store.memory import MemoryCatalog
from tests.unit.factories import DEFAULT_START, make_ride, make_summary


@pytest.fixture(params=["sqlite", "memory"])
def catalog(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[CatalogStore]:
    """Provide each catalog implementation in turn, empty, and close it afterwards.

    Args:
        request: Pytest request; its param picks the implementation.
        tmp_path: Folder for the SQLite file.

    Yields:
        A SQLite or in-memory catalog.
    """
    store: CatalogStore
    if request.param == "sqlite":
        store = SqliteCatalog(tmp_path / "catalog.sqlite3")
    else:
        store = MemoryCatalog()
    yield store
    store.close()


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


def test_every_backend_plays_every_role(catalog: CatalogStore):
    """Each backend has every role's methods, so it can be passed wherever one is needed.

    Given: The catalog backend under test.
    Expect: It is a ``RideCatalog``, ``BikeCatalog``, ``AthleteCatalog``, ``SettingsStore``,
        ``WatchState`` and the whole ``CatalogStore``.
    """
    roles = (RideCatalog, BikeCatalog, AthleteCatalog, SettingsStore, WatchState, CatalogStore)

    missing = [role.__name__ for role in roles if not isinstance(catalog, role)]

    assert missing == [], f"{type(catalog).__name__} should play every role"


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


# -- recompute support ----------------------------------------------------------------------


def test_replace_summary_keeps_identity_and_metadata(catalog: CatalogStore):
    """Recomputing a ride replaces its figures but nothing the user or the import set.

    Given: a ride at metrics version 1 with a name, notes and tags; a new summary with
    different power, curves and a single lap.
    Expect: the new summary and version 2; the same id, hash, import time and metadata; text
    search still finds it by its notes.
    """
    ride = make_ride(meta=RideMeta(name="Arenberg loop", notes="windy", tags=("cobbles",)))
    catalog.add_ride(replace(ride, metrics_version=1))
    new_summary = make_summary(
        avg_power=230.0, np=240.0, power_curve=((60, 400.0),), laps=(ride.summary.laps[0],)
    )

    catalog.replace_summary(ride.id, new_summary, metrics_version=2)
    loaded = catalog.get_ride(ride.id)

    assert loaded.summary == new_summary
    assert loaded.metrics_version == 2
    assert (loaded.id, loaded.sha256, loaded.imported_at) == (
        ride.id,
        ride.sha256,
        ride.imported_at,
    )
    assert loaded.meta == ride.meta, "the user's metadata should be untouched"
    assert ids(catalog.search(Filters(text="windy"))) == [ride.id], "still found by its notes"


def test_delete_ride_removes_it_everywhere(catalog: CatalogStore):
    """A deleted ride is gone from lookups, search, counts and totals; others stay.

    Given: two rides on a bike, one with notes and tags, and the tagged one deleted.
    Expect: the deleted ride returned as it was; it can't be loaded or found by id, hash or
    notes; its tag no longer counts; the bike counts one ride; the other ride is untouched.
    """
    bike = Bike(id="b1", name="Giant Contend 1")
    catalog.add_bike(bike)
    gone = make_ride(meta=RideMeta(notes="windy", tags=("cobbles",), bike_id="b1"))
    kept = make_ride(start=at(1), meta=RideMeta(bike_id="b1"))
    catalog.add_ride(gone)
    catalog.add_ride(kept)

    (removed,) = catalog.delete_rides([gone.id])

    assert removed.id == gone.id and removed.meta.notes == "windy"
    with pytest.raises(RideNotFound):
        catalog.get_ride(gone.id)
    assert catalog.find_by_hash(gone.sha256) is None
    assert ids(catalog.search(Filters(text="windy"))) == [], "search should forget it"
    assert catalog.tag_counts() == []
    assert [(t.bike.id, t.rides) for t in catalog.bike_totals()] == [("b1", 1)]
    assert ids(catalog.search()) == [kept.id]


def test_delete_unknown_ride(catalog: CatalogStore):
    """Deleting a ride that doesn't exist is an error.

    Given: an empty catalog.
    Expect: ``RideNotFound``.
    """
    with pytest.raises(RideNotFound):
        catalog.delete_rides(["00000000-0000-0000-0000-000000000000"])


def test_delete_rides_is_all_or_nothing(catalog: CatalogStore):
    """Deleting several rides removes all of them, or none if one is unknown.

    Given: three rides; then two of them plus an unknown id; then the two (one named twice).
    Expect: the unknown id raises ``RideNotFound`` with all three still there; the second
        call removes exactly the two and returns them once each.
    """
    rides = [make_ride(start=at(i)) for i in range(3)]
    for ride in rides:
        catalog.add_ride(ride)

    with pytest.raises(RideNotFound):
        catalog.delete_rides([rides[0].id, "00000000-0000-0000-0000-000000000000"])
    assert catalog.count() == 3, "should delete nothing when one id is unknown"
    removed = catalog.delete_rides([rides[0].id, rides[1].id, rides[0].id])

    assert [r.id for r in removed] == [rides[0].id, rides[1].id]
    assert ids(catalog.search()) == [rides[2].id]


def test_deleted_files_are_remembered_until_added_again(catalog: CatalogStore):
    """A deleted ride's file is remembered, unless asked not to, and forgotten on re-adding.

    Given: two rides deleted, one remembered and one not; then the remembered one added again.
    Expect: the remembered file's name and a deletion time; nothing for the other; nothing
        once the ride is back.
    """
    kept_record = make_ride(start=at(0))
    no_record = make_ride(start=at(1))
    catalog.add_ride(kept_record)
    catalog.add_ride(no_record)
    before = datetime.now(UTC).replace(microsecond=0)

    catalog.delete_rides([kept_record.id])
    catalog.delete_rides([no_record.id], remember=False)
    record = catalog.deleted_file(kept_record.sha256)

    assert record is not None
    assert (record.sha256, record.name) == (kept_record.sha256, kept_record.source_name)
    assert record.deleted_at >= before
    assert catalog.deleted_file(no_record.sha256) is None
    catalog.add_ride(kept_record)
    assert catalog.deleted_file(kept_record.sha256) is None, "re-adding should forget it"


# -- route fingerprints -----------------------------------------------------------------------


def test_route_cells_round_trip_and_rides_without_one(catalog: CatalogStore):
    """A ride's route cells are stored with it; rides added without any have none.

    Given: a ride added with three cells and one added without a route.
    Expect: the three cells back for the first; an empty set for the second.
    """
    with_route, without = make_ride(), make_ride(start=at(1))
    cells = frozenset({"u0fqtqw", "u0fqtqx", "u0fqtqy"})

    catalog.add_ride(with_route, route=cells)
    catalog.add_ride(without)

    assert catalog.route_cells(with_route.id) == cells
    assert catalog.route_cells(without.id) == frozenset()


def test_route_candidates_rank_rides_by_shared_cells(catalog: CatalogStore):
    """Rides sharing the most cells with a ride come first; rides sharing none are left out.

    Given: a ride with 4 cells, others sharing 3, 1 and 0 of them, and a limit of 5.
    Expect: the rides sharing 3 then 1 (not the ride itself, nor the one sharing none); with
    a limit of 1, only the first.
    """
    mine = make_ride()
    most, some, none = make_ride(start=at(1)), make_ride(start=at(2)), make_ride(start=at(3))
    catalog.add_ride(mine, route=frozenset({"a000000", "a000001", "a000002", "a000003"}))
    catalog.add_ride(most, route=frozenset({"a000000", "a000001", "a000002", "zzzzzzz"}))
    catalog.add_ride(some, route=frozenset({"a000003"}))
    catalog.add_ride(none, route=frozenset({"bbbbbbb"}))

    ranked = catalog.route_candidates(mine.id, limit=5)
    first = catalog.route_candidates(mine.id, limit=1)

    assert ranked == [(most.id, 3), (some.id, 1)]
    assert first == [(most.id, 3)]


def test_replacing_a_summary_replaces_the_route_and_deleting_drops_it(catalog: CatalogStore):
    """Recompute replaces a ride's cells; a deleted ride is no longer a candidate.

    Given: two rides sharing a cell; the second recomputed with different cells, then the
    first recomputed back to sharing and the second deleted.
    Expect: after the first recompute the rides share nothing; after deleting, no candidates.
    """
    first, second = make_ride(), make_ride(start=at(1))
    catalog.add_ride(first, route=frozenset({"c000000"}))
    catalog.add_ride(second, route=frozenset({"c000000"}))

    catalog.replace_summary(second.id, second.summary, 3, route=frozenset({"d000000"}))
    after_recompute = catalog.route_candidates(first.id)
    catalog.replace_summary(second.id, second.summary, 3, route=frozenset({"c000000"}))
    catalog.delete_rides([second.id])
    after_delete = catalog.route_candidates(first.id)

    assert after_recompute == []
    assert after_delete == []


def test_route_lookups_of_unknown_ride(catalog: CatalogStore):
    """Asking for a missing ride's route is an error.

    Given: an empty catalog.
    Expect: ``RideNotFound`` from both lookups.
    """
    with pytest.raises(RideNotFound):
        catalog.route_cells("missing")
    with pytest.raises(RideNotFound):
        catalog.route_candidates("missing")


def test_replace_summary_of_unknown_ride(catalog: CatalogStore):
    """Recomputing a ride that doesn't exist is an error.

    Given: an empty catalog.
    Expect: ``RideNotFound``.
    """
    with pytest.raises(RideNotFound):
        catalog.replace_summary("00000000-0000-0000-0000-000000000000", make_summary(), 2)


def test_ride_ids_by_metrics_version(catalog: CatalogStore):
    """Rides computed with older calculations can be found for recompute.

    Given: rides at metrics versions 1, 2 and 1, on consecutive days.
    Expect: all three oldest first; only the version-1 rides below version 2.
    """
    rides = [make_ride(start=at(day), metrics_version=v) for day, v in ((0, 1), (1, 2), (2, 1))]
    for ride in rides:
        catalog.add_ride(ride)

    everything = catalog.ride_ids()
    outdated = catalog.ride_ids(below_version=2)

    assert everything == [r.id for r in rides]
    assert outdated == [rides[0].id, rides[2].id], "only version-1 rides need recomputing"


def test_trend_rows(catalog: CatalogStore):
    """Trend rows carry each ride's light figures, oldest first, inside the window.

    Given: a ride with power on day 0, a heart-rate-only indoor ride on day 1 with no time
    zone, and a ride on day 5.
    Expect: all three with no bounds; days 0-1 with bounds; the first row's figures match its
    summary, and the second has no power figures and the UTC date.
    """
    first = make_ride(start=at(0))
    hr_only = make_ride(
        start=at(1),
        utc_offset_s=None,
        indoor=True,
        has_power=False,
        np=None,
        kj=None,
        power_curve=(),
    )
    later = make_ride(start=at(5))
    for ride in (later, hr_only, first):
        catalog.add_ride(ride)

    everything = catalog.trend_rows(None, None)
    window = catalog.trend_rows(at(0), at(1))

    assert [r.id for r in everything] == [first.id, hr_only.id, later.id]
    assert [r.id for r in window] == [first.id, hr_only.id]
    row = window[0]
    s = first.summary
    assert (row.start, row.utc_offset_s, row.source, row.indoor) == (s.start, 7200, s.source, False)
    assert (row.moving_s, row.distance_m, row.ascent_m) == (3500, 30_000.0, 250.0)
    assert (row.kj, row.np, row.avg_hr, row.decoupling_pct) == (720.0, 215.0, 142.0, 3.2)
    assert row.best_20min_power == 250.0
    assert row.local_date == date(2025, 8, 2)
    assert (window[1].np, window[1].kj, window[1].best_20min_power) == (None, None, None)
    assert window[1].indoor
    # 120² x 600 s + 140² x 1800 s + 160² x 1100 s + 171² x 1 s, from the factory's histogram.
    assert window[1].hr_squared_s == 72_109_241, "heart rate squared, summed over the ride"


def test_trend_rows_without_heart_rate(catalog: CatalogStore):
    """A ride without heart rate has nothing to give heart-rate TSS.

    Given: a ride with an empty heart-rate histogram.
    Expect: its trend row's ``hr_squared_s`` is ``None``.
    """
    catalog.add_ride(make_ride(hr_histogram=()))

    assert catalog.trend_rows(None, None)[0].hr_squared_s is None


def test_best_curve_between(catalog: CatalogStore):
    """Each duration's best in a window comes with the ride it came from.

    Given: ride A (day 0) best at 5 s and tied at 1 min, ride B (day 3) best at 1 min (tie)
    and 20 min, ride C (day 60) better at everything but outside the window.
    Expect: 5 s from A, 1 min from A (the earlier of the tie), 20 min from B; HR comes from
    the HR curves.
    """
    a = make_ride(start=at(0), power_curve=((5, 900.0), (60, 400.0)), hr_curve=((5, 170.0),))
    b = make_ride(start=at(3), power_curve=((5, 800.0), (60, 400.0), (1200, 260.0)), hr_curve=())
    c = make_ride(start=at(60), power_curve=((5, 999.0), (60, 999.0), (1200, 999.0)))
    for ride in (c, b, a):
        catalog.add_ride(ride)

    power = catalog.best_curve_between("power", at(0), at(42))
    hr = catalog.best_curve_between("hr", at(0), at(42))

    assert [(p.duration_s, p.value, p.ride_id) for p in power] == [
        (5, 900.0, a.id),
        (60, 400.0, a.id),
        (1200, 260.0, b.id),
    ], "ties should go to the earlier ride"
    assert power[2].start == b.summary.start
    assert [(h.duration_s, h.value, h.ride_id) for h in hr] == [(5, 170.0, a.id)]


def test_athlete_history_entries(catalog: CatalogStore):
    """Athlete history entries are kept by date, oldest first; a date can be replaced or removed.

    Given: entries for 1 Mar (FTP 250) and 1 Jan (FTP 240, 72 kg, max HR 188, threshold HR
    165), then a new 1 Mar entry (FTP 255), then 1 Jan removed.
    Expect: after each step, the entries in date order with the latest values.
    """
    january = AthleteEntry(date(2025, 1, 1), ftp=240, weight_kg=72.0, max_hr=188, threshold_hr=165)
    march = AthleteEntry(date(2025, 3, 1), ftp=250)
    catalog.set_athlete_entry(march)
    catalog.set_athlete_entry(january)

    both = catalog.athlete_history()
    catalog.set_athlete_entry(AthleteEntry(date(2025, 3, 1), ftp=255))
    replaced = catalog.athlete_history()
    removed = catalog.delete_athlete_entry(date(2025, 1, 1))
    removed_again = catalog.delete_athlete_entry(date(2025, 1, 1))

    assert both == [january, march], "entries should come back oldest first"
    assert replaced == [january, AthleteEntry(date(2025, 3, 1), ftp=255)]
    assert (removed, removed_again) == (True, False), "removing twice finds nothing the 2nd time"
    assert catalog.athlete_history() == [AthleteEntry(date(2025, 3, 1), ftp=255)]


# -- metadata, bikes and default bikes -------------------------------------------------------

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


# -- watched folders --------------------------------------------------------------------------


def watched(path: str, outcome: WatchOutcome, minute: int, folder: str = "/rides") -> WatchedFile:
    """A file found in a watched folder.

    Args:
        path: The file's path.
        outcome: What importing it did.
        minute: When it was imported: minutes after 2 Aug 2025 06:30 UTC.
        folder: The watched folder it was in.

    Returns:
        The record.
    """
    return WatchedFile(
        path=path,
        folder=folder,
        size=1000,
        mtime_ns=1_754_000_000_000_000_000,
        outcome=outcome,
        detail=None if outcome is WatchOutcome.IMPORTED else "why",
        ride_id="r1" if outcome is WatchOutcome.IMPORTED else None,
        seen_at=DEFAULT_START + timedelta(minutes=minute),
    )


def test_watch_folders_are_added_listed_and_removed(catalog: CatalogStore):
    """Watched folders are kept by path; adding one twice or removing a stranger does nothing.

    Given: two folders added (one twice), then one removed (twice).
    Expect: both listed by path; the second add and second remove report ``False``.
    """
    zwift = WatchFolder("/Users/me/Documents/Zwift/Activities", DEFAULT_START)
    garmin = WatchFolder("/Volumes/GARMIN/Garmin/Activities", DEFAULT_START)

    added = [catalog.add_watch_folder(f) for f in (zwift, garmin, zwift)]
    both = catalog.watch_folders()
    removed = [catalog.remove_watch_folder(garmin.path) for _ in range(2)]

    assert added == [True, True, False], "adding a watched folder again should change nothing"
    assert both == [zwift, garmin], "folders should be listed by path"
    assert removed == [True, False]
    assert catalog.watch_folders() == [zwift]


def test_watched_files_are_recorded_replaced_and_listed(catalog: CatalogStore):
    """A file's latest record replaces the last; recent files leave out duplicates.

    Given: a file that failed, then imported after it changed; a duplicate; a skipped file;
    a file in another folder.
    Expect: the file's record is the import; recent files are newest first without the
    duplicate; counts per folder include every file.
    """
    catalog.add_watch_folder(WatchFolder("/rides", DEFAULT_START))
    catalog.record_watched_file(watched("/rides/a.fit", WatchOutcome.FAILED, 0))
    imported = replace(watched("/rides/a.fit", WatchOutcome.IMPORTED, 5), size=2000)
    catalog.record_watched_file(imported)
    catalog.record_watched_file(watched("/rides/b.fit", WatchOutcome.DUPLICATE, 6))
    skipped = watched("/rides/c.fit", WatchOutcome.SKIPPED, 7)
    catalog.record_watched_file(skipped)
    other = watched("/other/d.fit", WatchOutcome.IMPORTED, 1, folder="/other")
    catalog.record_watched_file(other)

    assert catalog.watched_file("/rides/a.fit") == imported, "the latest record should win"
    assert catalog.watched_file("/rides/zzz.fit") is None
    assert catalog.recent_watched_files() == [skipped, imported, other]
    assert catalog.recent_watched_files(limit=1) == [skipped]
    assert catalog.watched_file_counts() == {"/rides": 3, "/other": 1}


def test_recent_files_in_the_same_second_are_latest_first(catalog: CatalogStore):
    """Files recorded in the same second are listed in the order recorded, latest first.

    Given: three files imported at the same time, recorded b, a, c; then b recorded again.
    Expect: b, c, a.
    """
    for name in ("b", "a", "c", "b"):
        catalog.record_watched_file(watched(f"/rides/{name}.fit", WatchOutcome.IMPORTED, 0))

    recent = catalog.recent_watched_files()

    assert [Path(f.path).stem for f in recent] == ["b", "c", "a"]


def test_removing_a_folder_forgets_its_files(catalog: CatalogStore):
    """Files found in a folder are forgotten when it's no longer watched.

    Given: files recorded in two folders, then one folder removed.
    Expect: only the other folder's file is left.
    """
    for folder in ("/rides", "/other"):
        catalog.add_watch_folder(WatchFolder(folder, DEFAULT_START))
        catalog.record_watched_file(
            watched(f"{folder}/a.fit", WatchOutcome.IMPORTED, 0, folder=folder)
        )

    catalog.remove_watch_folder("/rides")

    assert catalog.watched_file("/rides/a.fit") is None
    assert catalog.watched_file_counts() == {"/other": 1}


# -- SQLite only ------------------------------------------------------------------------------


def test_sqlite_catalog_persists_and_is_migrated(tmp_path: Path):
    """A SQLite catalog keeps its rides after being closed and reopened, at the latest schema.

    Given: a catalog file with one ride, closed and opened again.
    Expect: the ride is still there and the schema version is 7 (the latest migration).
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
    assert version == 8


def test_new_library_opened_twice_at_once(tmp_path: Path):
    """Two connections opening a new library at the same moment both get the full schema.

    Given: eight threads opening the same new catalog file together (as the server's watcher
    and a request can).
    Expect: every one opens at the latest schema, with no error.
    """
    path = tmp_path / "catalog.sqlite3"
    start = threading.Barrier(8)
    versions: list[int] = []
    errors: list[BaseException] = []

    def open_it() -> None:
        start.wait()
        try:
            catalog = SqliteCatalog(path)
            versions.append(catalog.schema_version)
            catalog.close()
        except BaseException as exc:  # reported below
            errors.append(exc)

    threads = [threading.Thread(target=open_it) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert versions == [8] * 8


def test_phase_1a_database_is_upgraded(tmp_path: Path):
    """A library created before training metrics is upgraded in place when opened.

    Given: a catalog file built with only the initial migration (as phase 1a left it) holding
    one ride.
    Expect: opening it applies migrations 2 to 6; the ride is still there with no training
    figures, so ``recompute`` can fill them in.
    """
    path = tmp_path / "catalog.sqlite3"
    initial = (
        resources.files("fitlib.store.local") / "migrations" / "0001_initial.sql"
    ).read_text()
    db = sqlite3.connect(path)
    db.executescript(f"{initial}\nPRAGMA user_version = 1;")
    db.execute(
        "INSERT INTO rides (id, sha256, source_name, imported_at, metrics_version, start_ts, "
        "source, sport, indoor, elapsed_s, moving_s, has_power, has_hr, has_gps) "
        "VALUES ('abcd1111-0000-4000-8000-000000000001', 'x', 'a.fit', 0, 1, 0, 'zwift', "
        "'cycling', 1, 60, 60, 1, 1, 0)"
    )
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    ride = catalog.get_ride("abcd1111-0000-4000-8000-000000000001")
    version = catalog.schema_version
    catalog.close()

    assert version == 8
    assert ride.metrics_version == 1, "the old ride should be marked for recompute"
    assert ride.summary.np is None and ride.summary.power_curve == ()


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


# -- settings and time zones ------------------------------------------------------------------


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


def test_athlete_entries_survive_the_threshold_hr_upgrade(tmp_path: Path):
    """Upgrading adds threshold heart rate without touching existing athlete entries.

    Given: a catalog at schema version 6 with an athlete entry (FTP 250, max HR 188).
    Expect: after opening it, the entry is unchanged with no threshold heart rate, and one
        can be saved.
    """
    path = tmp_path / "catalog.sqlite3"
    folder = resources.files("fitlib.store.local") / "migrations"
    scripts = sorted(
        (entry.name, entry.read_text()) for entry in folder.iterdir() if entry.name < "0007"
    )
    db = sqlite3.connect(path)
    for _, script in scripts:
        db.executescript(script)
    db.execute("PRAGMA user_version = 6")
    db.execute("INSERT INTO athlete_history VALUES ('2025-01-01', 250, NULL, 188)")
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    before = catalog.athlete_history()
    catalog.set_athlete_entry(AthleteEntry(date(2025, 2, 1), threshold_hr=165))
    after = catalog.athlete_history()
    catalog.close()

    assert before == [AthleteEntry(date(2025, 1, 1), ftp=250, max_hr=188)]
    assert after[1] == AthleteEntry(date(2025, 2, 1), threshold_hr=165)


def test_existing_rides_keep_their_time_zone_as_from_their_file(tmp_path: Path):
    """Upgrading marks where each existing ride's time zone came from.

    Given: a catalog at schema version 4 with one ride that has an offset (only ever from its
        file then) and one without.
    Expect: after opening it, the first is marked as from its file and the second as none,
        and there's no default time zone yet.
    """
    path = tmp_path / "catalog.sqlite3"
    folder = resources.files("fitlib.store.local") / "migrations"
    scripts = sorted(
        (entry.name, entry.read_text()) for entry in folder.iterdir() if entry.name < "0005"
    )
    db = sqlite3.connect(path)
    for _, script in scripts:
        db.executescript(script)
    db.execute("PRAGMA user_version = 4")
    for ride_id, offset in (
        ("abcd1111-0000-4000-8000-000000000001", 7200),
        ("abcd2222-0000-4000-8000-000000000002", None),
    ):
        db.execute(
            "INSERT INTO rides (id, sha256, source_name, imported_at, metrics_version, start_ts, "
            "utc_offset_s, source, sport, indoor, elapsed_s, moving_s, has_power, has_hr, "
            "has_gps) VALUES (?, ?, 'a.fit', 0, 5, 0, ?, 'garmin', 'cycling', 0, 60, 60, 1, 1, 0)",
            (ride_id, ride_id, offset),
        )
    db.commit()
    db.close()

    catalog = SqliteCatalog(path)
    sources = [
        catalog.get_ride(ride_id).summary.utc_offset_source
        for ride_id in (
            "abcd1111-0000-4000-8000-000000000001",
            "abcd2222-0000-4000-8000-000000000002",
        )
    ]
    zone = catalog.get_setting("default_time_zone")
    catalog.close()

    assert sources == [OffsetSource.DEVICE, OffsetSource.NONE]
    assert zone is None
