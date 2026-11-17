"""Bikes, the default-bike timeline, and backfilling defaults onto rides."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import Api

ZWIFT = "2025-08-02-08-29-42.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
OUTDOOR_RIDES = 7  # every fixture ride except the Zwift ride and the Garmin indoor ride


def add_bike(client: TestClient, name: str, kind: str | None = None) -> dict:
    """Add a bike through the API.

    Args:
        client: The test client.
        name: The bike's name.
        kind: The bike's kind, if any.

    Returns:
        The new bike as returned.
    """
    response = client.post("/api/bikes", json={"name": name, "kind": kind})
    assert response.status_code == 201, response.text
    return response.json()


def test_add_and_list_bikes_with_totals(writer: Api):
    """New bikes are listed, sorted by name, with what they've been ridden.

    Given: two bikes, one of them on the Zwift ride.
    Expect: both listed by name with their kind; the one used has 1 ride and an hour.
    """
    scott = add_bike(writer.client, "Scott  Addict", "road")
    giant = add_bike(writer.client, "Giant Contend 1")
    writer.client.patch(f"/api/rides/{writer.ids[ZWIFT]}/meta", json={"bike_id": giant["id"]})

    bikes = writer.client.get("/api/bikes").json()

    assert scott["name"] == "Scott Addict", "runs of spaces in names should be tidied"
    assert [(b["name"], b["kind"], b["rides"]) for b in bikes] == [
        ("Giant Contend 1", None, 1),
        ("Scott Addict", "road", 0),
    ]
    assert bikes[0]["moving_s"] == 3600


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"name": "giant contend 1"}, 409),
        ({"name": "   "}, 422),
        ({"name": "Trek", "kind": "unicycle"}, 422),
    ],
    ids=["duplicate-name", "blank-name", "unknown-kind"],
)
def test_add_bike_rejects_bad_bikes(client: TestClient, body: dict, status: int):
    """Names must be new (ignoring case) and not blank; kinds must be known.

    Given: an existing bike, then a bike with the same name in lower case, a blank name or
    an unknown kind.
    Expect: the error status, and still only one bike.
    """
    add_bike(client, "Giant Contend 1")

    response = client.post("/api/bikes", json=body)

    assert response.status_code == status
    assert len(client.get("/api/bikes").json()) == 1
    if status == 409:
        assert response.json()["detail"] == "There is already a bike called 'giant contend 1'"


def test_rename_retire_and_bring_back(client: TestClient):
    """A bike can be renamed, given a kind, retired and brought back.

    Given: a bike, then a rename with a kind, then retiring it, then bringing it back.
    Expect: each change is returned; retired bikes drop out of the list of active bikes.
    """
    bike = add_bike(client, "Old name")
    url = f"/api/bikes/{bike['id']}"

    renamed = client.patch(url, json={"name": "New name", "kind": "gravel"}).json()
    retired = client.patch(url, json={"retired": True}).json()
    active = client.get("/api/bikes", params={"include_retired": False}).json()
    back = client.patch(url, json={"retired": False}).json()

    assert (renamed["name"], renamed["kind"], renamed["retired"]) == ("New name", "gravel", False)
    assert retired["retired"] and retired["name"] == "New name", "retiring keeps the name"
    assert active == []
    assert not back["retired"]


@pytest.mark.parametrize(
    ("bike_id", "body", "status"),
    [("missing", {"name": "x"}, 404), (None, {"name": "Taken"}, 409)],
    ids=["unknown-bike", "name-taken"],
)
def test_update_bike_errors(client: TestClient, bike_id: str | None, body: dict, status: int):
    """Updating a missing bike, or renaming to a taken name, is refused.

    Given: bikes ``Taken`` and ``Mine``, then a patch to an unknown id or renaming ``Mine``
    to ``Taken``.
    Expect: 404 or 409.
    """
    add_bike(client, "Taken")
    mine = add_bike(client, "Mine")

    response = client.patch(f"/api/bikes/{bike_id or mine['id']}", json=body)

    assert response.status_code == status


def test_default_timeline_set_clear_and_remove(client: TestClient):
    """Default-bike entries can be set, set to no bike, listed and removed.

    Given: a bike as the outdoor default from 2025-01-01, no outdoor default from
    2025-06-01, then removing the June entry.
    Expect: both entries listed in date order, then just the first; removing it again is a
    404.
    """
    bike = add_bike(client, "Scott Addict")

    client.put("/api/bikes/defaults/outdoor/2025-01-01", json={"bike_id": bike["id"]})
    client.put("/api/bikes/defaults/outdoor/2025-06-01", json={"bike_id": None})
    both = client.get("/api/bikes/defaults").json()
    removed = client.delete("/api/bikes/defaults/outdoor/2025-06-01")
    after = client.get("/api/bikes/defaults").json()
    again = client.delete("/api/bikes/defaults/outdoor/2025-06-01")

    assert both == [
        {
            "slot": "outdoor",
            "effective_from": "2025-01-01",
            "bike": {"id": bike["id"], "name": "Scott Addict"},
        },
        {"slot": "outdoor", "effective_from": "2025-06-01", "bike": None},
    ]
    assert removed.status_code == 204
    assert after == both[:1]
    assert again.status_code == 404


@pytest.mark.parametrize(
    ("path", "body", "status"),
    [
        ("/api/bikes/defaults/outdoor/2025-01-01", {"bike_id": "missing"}, 404),
        ("/api/bikes/defaults/mtb/2025-01-01", {"bike_id": None}, 422),
        ("/api/bikes/defaults/outdoor/someday", {"bike_id": None}, 422),
    ],
    ids=["unknown-bike", "unknown-slot", "bad-date"],
)
def test_set_default_errors(client: TestClient, path: str, body: dict, status: int):
    """Defaults need a real bike, a known slot and a valid date.

    Given: an unknown bike, slot or date.
    Expect: 404 or 422.
    """
    response = client.put(path, json=body)

    assert response.status_code == status


def test_backfill_dry_run_then_apply_keeps_hand_set_bikes(writer: Api):
    """Backfill gives rides their default bike, but never overrides one set by hand.

    Given: a Zwift default and an outdoor default from 2000, and the interval ride given
    the Zwift bike by hand.
    Expect: the dry run reports the changes and saves nothing; the real run gives the Zwift
    ride the Zwift bike and the other outdoor rides the outdoor bike, leaving the interval
    ride on its hand-set bike.
    """
    giant = add_bike(writer.client, "Giant Contend 1")
    scott = add_bike(writer.client, "Scott Addict")
    put = writer.client.put
    put("/api/bikes/defaults/zwift/2000-01-01", json={"bike_id": giant["id"]})
    put("/api/bikes/defaults/outdoor/2000-01-01", json={"bike_id": scott["id"]})
    writer.client.patch(f"/api/rides/{writer.ids[INTERVALS]}/meta", json={"bike_id": giant["id"]})
    expected = [
        {"bike": {"id": scott["id"], "name": "Scott Addict"}, "rides": OUTDOOR_RIDES - 1},
        {"bike": {"id": giant["id"], "name": "Giant Contend 1"}, "rides": 1},
    ]

    dry = writer.client.post("/api/bikes/backfill", params={"dry_run": True}).json()
    totals_after_dry = {b["name"]: b["rides"] for b in writer.client.get("/api/bikes").json()}
    real = writer.client.post("/api/bikes/backfill").json()
    zwift = writer.client.get(f"/api/rides/{writer.ids[ZWIFT]}").json()["meta"]
    intervals = writer.client.get(f"/api/rides/{writer.ids[INTERVALS]}").json()["meta"]

    assert dry == {"dry_run": True, "changes": expected}
    assert totals_after_dry == {"Giant Contend 1": 1, "Scott Addict": 0}, "dry run saves nothing"
    assert real == {"dry_run": False, "changes": expected}
    assert (zwift["bike"]["name"], zwift["bike_from_default"]) == ("Giant Contend 1", True)
    assert (intervals["bike"]["name"], intervals["bike_from_default"]) == ("Giant Contend 1", False)
