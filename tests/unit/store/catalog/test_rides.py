"""Catalog contract: rides.

Adding, ids, time windows, search, recompute support, routes, trend rows and deleting.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from fitlib.models import (
    Bike,
    Filters,
    RideMeta,
    SortKey,
    Source,
)
from fitlib.store.interfaces import (
    AmbiguousRideId,
    CatalogStore,
    DuplicateRide,
    RideNotFound,
)
from tests.unit.factories import DEFAULT_START, make_ride, make_summary
from tests.unit.store.catalog.helpers import at, ids


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
