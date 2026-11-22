"""Similar rides: on the same roads, or with a similar effort."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fitlib.store.factory import open_stores
from tests.api.conftest import Api

INTERVALS = "garmin_nord_intervals_5x4.fit"
ZWIFT = "2025-08-02-08-29-42.fit"
INDOOR = "garmin_indoor_no_hr.fit"
HR_ONLY = "garmin_nord_hr_no_power.fit"
# Every outdoor fixture ride laps the same 5 km loop.
OTHER_OUTDOOR = {
    "garmin_nord_pause_10min.fit",
    "garmin_nord_smart_recording.fit",
    "garmin_nord_hr_no_power.fit",
    "garmin_export.zip:garmin_export_ride_a.fit",
    "garmin_export.zip:garmin_export_ride_b.fit",
}


def files(api: Api, items: list[dict]) -> list[str]:
    """Name the fixture files a list of matches came from.

    Args:
        api: The client and its ride ids.
        items: Matches from a similar-rides response.

    Returns:
        The fixture file names, in order.
    """
    by_id = {ride_id: name for name, ride_id in api.ids.items()}
    return [by_id[item["ride"]["id"]] for item in items]


def test_route_matches_are_the_other_rides_on_the_loop(reader: Api):
    """Rides on the same loop are listed as the same route, fully overlapping.

    Given: the interval ride, on the Nord loop like every other outdoor fixture ride.
    Expect: the 5 other outdoor rides, each the same route with 100 % overlap both ways; not
    the Zwift ride (Watopia) or the indoor ride (no GPS).
    """
    response = reader.client.get(f"/api/rides/{reader.ids[INTERVALS]}/similar")

    body = response.json()
    assert response.status_code == 200
    assert (body["kind"], body["has_route"]) == ("route", True)
    assert set(files(reader, body["items"])) == OTHER_OUTDOOR
    for item in body["items"]:
        assert (item["overlap"], item["other_overlap"], item["same_route"]) == (1.0, 1.0, True)
        assert item["similarity"] is None


def test_route_matches_come_with_list_figures(reader: Api):
    """Each match carries the same figures as the library list, for showing in a table.

    Given: the interval ride's route matches.
    Expect: each has a name, start, moving time and a TSS (none with neither power nor heart
    rate).
    """
    response = reader.client.get(f"/api/rides/{reader.ids[INTERVALS]}/similar")

    for item in response.json()["items"]:
        ride = item["ride"]
        assert ride["name"] and ride["start"] and ride["moving_s"] > 0
        assert (ride["tss"] is None) == (ride["avg_power"] is None and ride["avg_hr"] is None)


@pytest.mark.parametrize(
    ("file", "has_route"), [(ZWIFT, True), (INDOOR, False)], ids=["zwift", "indoor"]
)
def test_rides_with_no_other_ride_on_their_route(reader: Api, file: str, has_route: bool):
    """A ride alone on its route, or without GPS, has no route matches.

    Given: the Zwift ride (the only ride in Watopia) and the indoor ride (no GPS).
    Expect: no matches; ``has_route`` says whether the ride had positions to match on.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[file]}/similar")

    assert response.json() == {"kind": "route", "has_route": has_route, "items": []}


def test_partly_shared_route(writer: Api):
    """A ride covering part of another's route is listed as partly shared.

    Given: a copy of the interval ride whose route is only the cells north of the loop's
    centre (about half the loop).
    Expect: from the interval ride, the copy covers about half its route and is not the
    same route; the copy's route is fully covered by the interval ride.
    """
    original = writer.ids[INTERVALS]
    with open_stores(writer.config) as stores:
        ride = stores.catalog.get_ride(original)
        cells = stores.catalog.route_cells(original)
        north = frozenset(sorted(cells)[len(cells) // 2 :])
        copy = replace(ride, id="half-loop-copy", sha256="1" * 64)
        stores.catalog.add_ride(copy, route=north)

    response = writer.client.get(f"/api/rides/{original}/similar")

    [half] = [i for i in response.json()["items"] if i["ride"]["id"] == "half-loop-copy"]
    assert 0.3 <= half["overlap"] < 0.7, f"about half the loop, got {half['overlap']}"
    assert half["other_overlap"] == 1.0
    assert half["same_route"] is False


def test_effort_matches_rank_the_closest_effort_first(reader: Api):
    """Effort matches list rides with power, most similar first.

    Given: the 25-minute export ride at 175 W (steady).
    Expect: only rides with power; the 30-minute ride at 180 W first (closer in both length
    and power than the 20-minute ride at 160 W); similarities from 100 down; no route
    figures.
    """
    response = reader.client.get(
        f"/api/rides/{reader.ids['garmin_export.zip:garmin_export_ride_b.fit']}/similar",
        params={"kind": "effort"},
    )

    items = response.json()["items"]
    similarities = [i["similarity"] for i in items]
    assert files(reader, items)[:2] == [
        "garmin_nord_smart_recording.fit",
        "garmin_export.zip:garmin_export_ride_a.fit",
    ]
    assert HR_ONLY not in files(reader, items), "HR-only rides are matched separately"
    assert similarities == sorted(similarities, reverse=True)
    assert all(0 <= s <= 100 for s in similarities)
    assert all(i["overlap"] is None for i in items)


def test_effort_matches_for_a_heart_rate_only_ride(reader: Api):
    """A ride with heart rate only is matched with other heart-rate-only rides.

    Given: the HR-only ride, the only one of its kind in the fixtures.
    Expect: no matches.
    """
    response = reader.client.get(
        f"/api/rides/{reader.ids[HR_ONLY]}/similar", params={"kind": "effort"}
    )

    assert response.json()["items"] == []


@pytest.mark.parametrize(
    ("ref", "params", "status"),
    [
        ("zzzzzzzz", {}, 404),
        (None, {"kind": "colour"}, 422),
        (None, {"limit": 0}, 422),
        (None, {"limit": 51}, 422),
    ],
    ids=["unknown-ride", "bad-kind", "limit-zero", "limit-too-big"],
)
def test_similar_rejects_bad_requests(reader: Api, ref: str | None, params: dict, status: int):
    """Unknown rides, kinds and limits outside 1-50 are refused.

    Given: an unknown ride, or a real one with a bad kind or limit.
    Expect: 404 or 422.
    """
    path = f"/api/rides/{ref or reader.ids[INTERVALS]}/similar"

    response = reader.client.get(path, params=params)

    assert response.status_code == status


def test_health_counts_outdated_rides(writer: Api):
    """The health check says how many rides need recomputing.

    Given: the fixture library with one ride marked as computed by version 1.
    Expect: 1 outdated ride.
    """
    with open_stores(writer.config) as stores:
        ride = stores.catalog.get_ride(writer.ids[ZWIFT])
        stores.catalog.replace_summary(ride.id, ride.summary, metrics_version=1)

    response = writer.client.get("/api/health")

    assert response.json()["outdated_rides"] == 1
