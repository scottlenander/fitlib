"""A ride's route for the map."""

from __future__ import annotations

from tests.api.conftest import Api

OUTDOOR = "garmin_nord_intervals_5x4.fit"
ZWIFT = "2025-08-02-08-29-42.fit"
INDOOR = "garmin_indoor_no_hr.fit"


def test_outdoor_ride_map(reader: Api):
    """An outdoor ride's map is its simplified route, in order, inside its bounds.

    Given: The interval ride (laps of the Nord loop near Roubaix).
    Expect: Tens to hundreds of points starting at 0 s, times and distances rising, every
        point inside the bounds, which lie near 50.4°N 3.4°E; no Zwift world.
    """
    body = reader.client.get(f"/api/rides/{reader.ids[OUTDOOR]}/map").json()

    points = body["points"]
    south, west, north, east = body["bounds"]
    assert body["ride_id"] == reader.ids[OUTDOOR]
    assert 10 < len(points) < 2_000
    assert points[0]["t"] == 0
    assert [p["t"] for p in points] == sorted(p["t"] for p in points)
    assert all(south <= p["lat"] <= north and west <= p["lon"] <= east for p in points)
    assert 50.3 < south < north < 50.5 and 3.3 < west < east < 3.5
    assert body["start_finish_m"] >= 0
    assert body["zwift_world"] is None


def test_zwift_ride_map_names_its_world(reader: Api):
    """A Zwift ride's map has its route and names the world, whose positions aren't real.

    Given: The Zwift fixture ride, in Watopia.
    Expect: Points, and ``zwift_world`` "Watopia".
    """
    body = reader.client.get(f"/api/rides/{reader.ids[ZWIFT]}/map").json()

    assert len(body["points"]) > 10
    assert body["zwift_world"] == "Watopia"


def test_ride_without_positions_has_an_empty_map(reader: Api):
    """An indoor ride without GPS has no route.

    Given: The indoor fixture ride.
    Expect: 200 with no points and no bounds.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[INDOOR]}/map")

    assert response.status_code == 200
    body = response.json()
    assert (body["points"], body["bounds"], body["start_finish_m"]) == ([], None, None)


def test_map_of_unknown_ride(reader: Api):
    """Asking for a missing ride's map is a 404.

    Given: An id that matches no ride.
    Expect: 404.
    """
    assert reader.client.get("/api/rides/ffffffff/map").status_code == 404
