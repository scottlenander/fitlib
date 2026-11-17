"""Reading rides: the library list, one ride's detail, and its streams."""

from __future__ import annotations

from dataclasses import replace

import pytest

from fitlib.ingest.normalize import VALUE_COLUMNS
from fitlib.store.factory import open_stores
from tests.api.conftest import Api

ZWIFT = "2025-08-02-08-29-42.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
HR_ONLY = "garmin_nord_hr_no_power.fit"
INDOOR = "garmin_indoor_no_hr.fit"
RIDE_B = "garmin_export.zip:garmin_export_ride_b.fit"


def names(api: Api, items: list[dict]) -> set[str]:
    """Name the fixture files a list of rides came from.

    Args:
        api: The client and its ride ids.
        items: Rides from a list response.

    Returns:
        The fixture file names.
    """
    by_id = {ride_id: name for name, ride_id in api.ids.items()}
    return {by_id[item["id"]] for item in items}


# -- list -------------------------------------------------------------------------------------


def test_list_returns_every_ride_newest_first(reader: Api):
    """With no filters, every ride comes back, newest first.

    Given: the 8 imported fixture rides.
    Expect: all 8, sorted by start time descending, starting with the latest export ride.
    """
    response = reader.client.get("/api/rides")

    body = response.json()
    starts = [item["start"] for item in body["items"]]
    assert response.status_code == 200
    assert body["total"] == 8
    assert starts == sorted(starts, reverse=True), "rides should be newest first"
    assert body["items"][0]["id"] == reader.ids[RIDE_B]


def test_list_pages_through_the_same_order(reader: Api):
    """Pages are consecutive slices of the full order.

    Given: a page of 3 starting at offset 3.
    Expect: the 4th to 6th rides of the full list, with the full total.
    """
    everything = reader.client.get("/api/rides").json()["items"]

    page = reader.client.get("/api/rides", params={"offset": 3, "limit": 3}).json()

    assert [i["id"] for i in page["items"]] == [i["id"] for i in everything[3:6]]
    assert (page["total"], page["offset"], page["limit"]) == (8, 3, 3)


def test_list_sorts_by_duration_ascending(reader: Api):
    """Rides can be sorted by moving time, shortest first.

    Given: ``sort=duration`` and ``desc=false``.
    Expect: moving times never decrease.
    """
    response = reader.client.get("/api/rides", params={"sort": "duration", "desc": False})

    moving = [item["moving_s"] for item in response.json()["items"]]
    assert moving == sorted(moving), "moving times should increase"


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"source": "zwift"}, {ZWIFT}),
        ({"indoor": True}, {ZWIFT, INDOOR}),
        ({"has_power": False}, {HR_ONLY}),
        ({"min_duration_s": 3600}, {ZWIFT, INTERVALS}),
        ({"since": "2025-08-16", "until": "2025-08-20"}, {HR_ONLY, INDOOR}),
        ({"source": "garmin", "indoor": True, "has_power": True}, {INDOOR}),
        ({"q": "zwift"}, {ZWIFT}),
    ],
    ids=["source", "indoor", "no-power", "min-duration", "dates", "combined", "text"],
)
def test_list_filters(reader: Api, params: dict, expected: set[str]):
    """Each filter, alone or combined, narrows the list to the matching rides.

    Given: one or more filters.
    Expect: exactly the fixture rides that match, with a matching total.
    """
    response = reader.client.get("/api/rides", params=params)

    body = response.json()
    assert names(reader, body["items"]) == expected
    assert body["total"] == len(expected)


@pytest.mark.parametrize(
    "params",
    [{"limit": 201}, {"limit": 0}, {"offset": -1}, {"min_rpe": 0}, {"sort": "speed"}],
    ids=["limit-too-big", "limit-zero", "negative-offset", "rpe-out-of-range", "bad-sort"],
)
def test_list_rejects_bad_parameters(reader: Api, params: dict):
    """Parameters out of range are refused rather than silently adjusted.

    Given: a limit above 200 or below 1, a negative offset, an RPE of 0 or an unknown sort.
    Expect: 422.
    """
    response = reader.client.get("/api/rides", params=params)

    assert response.status_code == 422


def test_list_rejects_a_bad_tag(reader: Api):
    """Tags are checked like on the command line.

    Given: a tag filter containing a comma.
    Expect: 422 with a message about the tag.
    """
    response = reader.client.get("/api/rides", params={"tag": "a,b"})

    assert response.status_code == 422
    assert "a,b" in response.json()["detail"]


def test_list_items_carry_estimated_tss(reader: Api):
    """Without an FTP set, rides with power get TSS from an estimated FTP.

    Given: the fixture library, which has no athlete history.
    Expect: every ride with power has a TSS marked estimated; the HR-only ride has none.
    """
    response = reader.client.get("/api/rides")

    items = {item["id"]: item for item in response.json()["items"]}
    hr_only = items.pop(reader.ids[HR_ONLY])
    assert hr_only["tss"] is None
    assert all(i["tss"] is not None and i["ftp_estimated"] for i in items.values()), (
        "every ride with power should have an estimated TSS"
    )


# -- detail -----------------------------------------------------------------------------------


def test_detail_by_full_id_and_by_prefix(reader: Api):
    """A ride can be fetched by its id or by the first 8 characters of it.

    Given: the Zwift ride's full id and its 8-character prefix.
    Expect: the same ride both times, named and timed as imported.
    """
    ride_id = reader.ids[ZWIFT]

    full = reader.client.get(f"/api/rides/{ride_id}").json()
    short = reader.client.get(f"/api/rides/{ride_id[:8]}").json()

    assert full == short
    assert full["id"] == ride_id
    assert full["name"] == "Zwift ride, 2 Aug 2025"
    assert (full["moving_s"], full["source"], full["indoor"]) == (3600, "zwift", True)


def test_detail_has_training_zones_and_curves(reader: Api):
    """A ride with power has its FTP-based figures, power zones and power curve.

    Given: the interval ride (an hour, with power and heart rate) and no athlete history.
    Expect: an estimated FTP with IF and TSS, 7 power zones covering the moving time, no HR
    zones (no max heart rate set) and a power curve up to 60 minutes.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[INTERVALS]}")

    ride = response.json()
    training = ride["training"]
    assert training["ftp_estimated"] and training["tss"] is not None
    assert training["intensity_factor"] is not None
    assert [z["zone"] for z in ride["power_zones"]] == [1, 2, 3, 4, 5, 6, 7]
    assert sum(z["seconds"] for z in ride["power_zones"]) == ride["moving_s"], (
        "zone times should add up to the moving time"
    )
    assert ride["hr_zones"] is None
    durations = [p["duration_s"] for p in ride["power_curve"]]
    assert durations == sorted(durations) and durations[-1] == 3600


def test_detail_without_power_has_no_power_figures(reader: Api):
    """A ride with heart rate only has no power-based figures.

    Given: the HR-only ride.
    Expect: no TSS, no power zones and an empty power curve; a heart-rate curve.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[HR_ONLY]}")

    ride = response.json()
    assert ride["training"]["tss"] is None
    assert ride["power_zones"] is None
    assert ride["power_curve"] == []
    assert ride["hr_curve"], "the HR curve should be there"


def test_detail_has_laps_location_and_empty_meta(reader: Api):
    """The detail includes laps, the start point and bounding box, and the user's metadata.

    Given: the interval ride, recorded outdoors with GPS and never edited.
    Expect: laps, a bounding box around the start point, and empty metadata.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[INTERVALS]}")

    ride = response.json()
    geo = ride["geo"]
    assert ride["laps"], "the interval ride has laps"
    assert geo["min_lat"] <= geo["start_lat"] <= geo["max_lat"]
    assert geo["min_lon"] <= geo["start_lon"] <= geo["max_lon"]
    assert ride["meta"] == {
        "name": None,
        "notes": None,
        "rpe": None,
        "bike": None,
        "bike_from_default": False,
        "tags": [],
    }


@pytest.mark.parametrize("ref", ["zzzzzzzz", "ab"], ids=["unknown", "too-short"])
def test_detail_of_unknown_ride_is_404(reader: Api, ref: str):
    """An id that matches nothing, or a prefix too short to use, is a 404.

    Given: an id matching no ride, or a 2-character prefix.
    Expect: 404 with a message.
    """
    response = reader.client.get(f"/api/rides/{ref}")

    assert response.status_code == 404
    assert response.json()["detail"]


def test_ambiguous_prefix_is_409_with_candidates(writer: Api):
    """A prefix shared by two rides is refused, listing both.

    Given: a second ride whose id starts with the same 8 characters as the Zwift ride's.
    Expect: 409 listing both full ids.
    """
    original = writer.ids[ZWIFT]
    twin = original[:8] + "-twin"
    with open_stores(writer.config) as stores:
        ride = stores.catalog.get_ride(original)
        stores.catalog.add_ride(replace(ride, id=twin, sha256="0" * 64))

    response = writer.client.get(f"/api/rides/{original[:8]}")

    assert response.status_code == 409
    assert sorted(response.json()["candidates"]) == sorted([original, twin])


# -- streams ----------------------------------------------------------------------------------


def test_streams_default_to_every_column_but_location(reader: Api):
    """By default, streams have every column except latitude and longitude.

    Given: the Zwift ride (60 minutes, 1 Hz).
    Expect: ``active`` and every value column but lat/lon, each as long as ``t``, which
    counts seconds from 0.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[ZWIFT]}/streams")

    streams = response.json()
    expected = ["active", *(c for c in VALUE_COLUMNS if c not in ("lat", "lon"))]
    assert list(streams["columns"]) == expected
    assert streams["t"][:3] == [0, 1, 2]
    assert all(len(v) == len(streams["t"]) for v in streams["columns"].values()), (
        "every column should line up with t"
    )


def test_streams_can_be_downsampled_and_narrowed(reader: Api):
    """A step and a field list cut the response down.

    Given: ``step=10`` and only the power field.
    Expect: samples 10 s apart, with only the power column.
    """
    params = {"step": 10, "fields": ["power"]}

    response = reader.client.get(f"/api/rides/{reader.ids[ZWIFT]}/streams", params=params)

    streams = response.json()
    assert streams["step"] == 10
    assert streams["t"][:3] == [0, 10, 20]
    assert list(streams["columns"]) == ["power"]


def test_location_is_sent_only_when_asked_for(reader: Api):
    """Latitude and longitude come back when requested by name.

    Given: the interval ride, recorded with GPS, and ``fields=lat&fields=lon``.
    Expect: just those two columns, with values.
    """
    params = {"fields": ["lat", "lon"]}

    response = reader.client.get(f"/api/rides/{reader.ids[INTERVALS]}/streams", params=params)

    columns = response.json()["columns"]
    assert list(columns) == ["lat", "lon"]
    assert columns["lat"][0] is not None


def test_streams_reject_unknown_fields(reader: Api):
    """Asking for a column that doesn't exist is an error naming it.

    Given: ``fields=watts``.
    Expect: 422 naming ``watts``.
    """
    params = {"fields": ["watts"]}

    response = reader.client.get(f"/api/rides/{reader.ids[ZWIFT]}/streams", params=params)

    assert response.status_code == 422
    assert "watts" in response.json()["detail"]


def test_streams_of_unknown_ride_is_404(reader: Api):
    """Streams for a ride that doesn't exist are a 404.

    Given: an unknown id.
    Expect: 404.
    """
    response = reader.client.get("/api/rides/zzzzzzzz/streams")

    assert response.status_code == 404


def test_tags_are_empty_before_any_are_added(reader: Api):
    """The tag list is empty for a library nobody has tagged.

    Given: the fixture library.
    Expect: an empty list.
    """
    response = reader.client.get("/api/tags")

    assert response.json() == []
