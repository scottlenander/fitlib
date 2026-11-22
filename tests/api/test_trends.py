"""Trends: volume, fitness, FTP, efficiency and best efforts by period; route progress."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from tests.api.conftest import Api

ZWIFT = "2025-08-02-08-29-42.fit"  # 2 Aug, 60 min at 200 W: TSS 100 × (200/190)² on its own eFTP
INTERVALS = "garmin_nord_intervals_5x4.fit"
INDOOR = "garmin_indoor_no_hr.fit"
AUGUST = {"since": "2025-08-01", "until": "2025-08-31"}
# Every outdoor Garmin ride laps the Nord loop, by date.
NORD_LOOP = [
    INTERVALS,  # 5 Aug
    "garmin_nord_pause_10min.fit",  # 9 Aug
    "garmin_nord_smart_recording.fit",  # 12 Aug
    "garmin_nord_hr_no_power.fit",  # 16 Aug
    "garmin_export.zip:garmin_export_ride_a.fit",  # 23 Aug
    "garmin_export.zip:garmin_export_ride_b.fit",  # 24 Aug
]


def ride_items(api: Api) -> list[dict]:
    """List every ride in the library.

    Args:
        api: The client.

    Returns:
        The list entries.
    """
    return api.client.get("/api/rides", params={"limit": 200}).json()["items"]


def test_span_is_the_first_and_latest_ride(reader: Api):
    """The span covers the fixture rides' local dates.

    Given: the fixture rides, 2 to 24 Aug 2025.
    Expect: first 2 Aug, last 24 Aug.
    """
    response = reader.client.get("/api/trends/span")

    assert response.json() == {"first": "2025-08-02", "last": "2025-08-24"}


def test_weekly_volume(reader: Api):
    """August's rides are added up per week, Monday to Sunday.

    Given: the 9 fixture rides, and August 2025 (from Fri 1 Aug).
    Expect: weeks from Mon 28 Jul to Mon 25 Aug with 1, 2, 3, 3 and 0 rides; times add up to
    the rides' moving times; the 2 rides without power have no TSS.
    """
    response = reader.client.get("/api/trends/volume", params=AUGUST)

    body = response.json()
    buckets = body["buckets"]
    assert response.status_code == 200
    assert (body["period"], body["since"], body["until"]) == ("week", "2025-08-01", "2025-08-31")
    assert [(b["start"], b["rides"]) for b in buckets] == [
        ("2025-07-28", 1),
        ("2025-08-04", 2),
        ("2025-08-11", 3),
        ("2025-08-18", 3),
        ("2025-08-25", 0),
    ]
    items = ride_items(reader)
    assert sum(b["moving_s"] for b in buckets) == sum(i["moving_s"] for i in items)
    assert sum(b["tss"] for b in buckets) == pytest.approx(sum(i["tss"] or 0 for i in items)), (
        "trend TSS should add up the rides' TSS"
    )
    assert sum(b["rides_without_tss"] for b in buckets) == 1, (
        "only the ride with neither power nor heart rate should be without TSS"
    )


def test_monthly_volume_defaults_to_twelve_months(reader: Api):
    """By month, the default range is this month and the 11 before it.

    Given: ``period=month`` and no dates; then August 2025 only.
    Expect: 12 buckets ending this month; August holds all 9 rides.
    """
    default = reader.client.get("/api/trends/volume", params={"period": "month"}).json()
    august = reader.client.get("/api/trends/volume", params={"period": "month", **AUGUST}).json()

    today = date.today()
    assert len(default["buckets"]) == 12
    assert default["buckets"][-1]["start"] == today.replace(day=1).isoformat()
    assert [(b["start"], b["rides"]) for b in august["buckets"]] == [("2025-08-01", 9)]


@pytest.mark.parametrize(
    ("path", "days"),
    [("volume", 84), ("fitness", 90), ("ftp", 365), ("efficiency", 365), ("curve", 42)],
)
def test_default_ranges_end_today(reader: Api, path: str, days: int):
    """Left out, the range ends today and goes back a span suited to each view.

    Given: no dates.
    Expect: ``until`` is today and ``since`` the right number of days before, inclusive.
    """
    body = reader.client.get(f"/api/trends/{path}").json()

    today = date.today()
    assert (body["since"], body["until"]) == (
        (today - timedelta(days=days - 1)).isoformat(),
        today.isoformat(),
    )


@pytest.mark.parametrize("path", ["volume", "fitness", "ftp", "efficiency", "curve"])
def test_since_after_until_is_refused(reader: Api, path: str):
    """A range that ends before it starts is an error.

    Given: since 31 Aug, until 1 Aug.
    Expect: 422 naming both dates.
    """
    params = {"since": "2025-08-31", "until": "2025-08-01"}

    response = reader.client.get(f"/api/trends/{path}", params=params)

    assert response.status_code == 422
    assert "2025-08-31" in response.json()["detail"]


def test_fitness(reader: Api):
    """Each day of August has fitness, fatigue and form; the Zwift ride starts them off.

    Given: August 2025; the first ride is the Zwift ride on 2 Aug.
    Expect: 31 days; 1 Aug all zero; 2 Aug with the Zwift ride's TSS, fitness TSS/42 and
    fatigue TSS/7; the 1 ride with neither power nor heart rate counted.
    """
    response = reader.client.get("/api/trends/fitness", params=AUGUST)

    body = response.json()
    days = body["days"]
    tss = 100 * (200 / 190) ** 2
    assert len(days) == 31
    assert days[0] == {"day": "2025-08-01", "tss": 0, "fitness": 0, "fatigue": 0, "form": 0}
    assert days[1]["tss"] == pytest.approx(tss)
    assert days[1]["fitness"] == pytest.approx(tss / 42)
    assert days[1]["fatigue"] == pytest.approx(tss / 7)
    assert body["rides_without_tss"] == 1


def test_ftp_by_month_and_after_setting_one(writer: Api):
    """FTP over time shows the set FTP and the estimate from the best 20 minutes.

    Given: no FTP at first, then FTP 250 W from 10 Aug; months July and August.
    Expect: July has neither; August's estimate is 0.95 × the best 20 minutes of the month,
    with no set FTP at first and 250 W afterwards.
    """
    params = {"period": "month", "since": "2025-07-01", "until": "2025-08-31"}
    curve = writer.client.get("/api/trends/curve", params=AUGUST).json()["points"]
    best_20 = next(p["value"] for p in curve if p["duration_s"] == 1200)

    before = writer.client.get("/api/trends/ftp", params=params).json()["points"]
    writer.client.put("/api/athlete/2025-08-10", json={"ftp": 250})
    after = writer.client.get("/api/trends/ftp", params=params).json()["points"]

    assert before[0] == {"day": "2025-07-31", "ftp": None, "estimated": None}
    assert before[1]["day"] == "2025-08-31"
    assert before[1]["estimated"] == pytest.approx(0.95 * best_20)
    assert (before[1]["ftp"], after[1]["ftp"]) == (None, 250)


def test_efficiency_lists_rides_with_power_and_heart_rate(reader: Api):
    """Efficiency has a point for each ride with power and heart rate of 20 minutes or more.

    Given: August's rides.
    Expect: exactly those rides, each with NP / average HR.
    """
    response = reader.client.get("/api/trends/efficiency", params=AUGUST)

    points = response.json()["points"]
    expected = {
        i["id"]: i["np"] / i["avg_hr"]
        for i in ride_items(reader)
        if i["np"] and i["avg_hr"] and i["moving_s"] >= 1200
    }
    assert {p["ride_id"]: p["efficiency"] for p in points} == pytest.approx(expected)
    assert len(points) > 1, "several fixture rides have power and heart rate"


def test_power_curve_comes_from_the_best_ride(reader: Api):
    """Each duration's best is the highest among the rides, with the ride it came from.

    Given: August's rides and their own best efforts.
    Expect: every duration any ride has, each best equal to the highest ride's, from that
    ride.
    """
    points = reader.client.get("/api/trends/curve", params=AUGUST).json()["points"]

    best: dict[int, tuple[float, set[str]]] = {}
    for ride_id in reader.ids.values():
        curve = reader.client.get(f"/api/rides/{ride_id}").json()["power_curve"]
        for p in curve:
            value, ids = best.get(p["duration_s"], (0.0, set()))
            if p["value"] > value:
                best[p["duration_s"]] = (p["value"], {ride_id})
            elif p["value"] == value:
                ids.add(ride_id)
    assert [p["duration_s"] for p in points] == sorted(best)
    for p in points:
        value, ids = best[p["duration_s"]]
        assert p["value"] == pytest.approx(value)
        assert p["ride_id"] in ids, f"the {p['duration_s']} s best should name its ride"


def test_heart_rate_curve_outside_the_rides_is_empty(reader: Api):
    """A period with no rides has no best efforts.

    Given: heart rate in July 2025, before the fixture rides.
    Expect: no points.
    """
    params = {"kind": "hr", "since": "2025-07-01", "until": "2025-07-31"}

    response = reader.client.get("/api/trends/curve", params=params)

    assert response.json() == {
        "kind": "hr",
        "since": "2025-07-01",
        "until": "2025-07-31",
        "points": [],
    }


@pytest.mark.parametrize("file", [INTERVALS, NORD_LOOP[-1]], ids=["first", "last"])
def test_route_progress_lists_the_loop_oldest_first(reader: Api, file: str):
    """Route progress lists every ride on the loop, the asked-about one included.

    Given: one of the 6 rides on the Nord loop.
    Expect: all 6, oldest first, as list entries.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[file]}/route-progress")

    body = response.json()
    by_id = {ride_id: name for name, ride_id in reader.ids.items()}
    assert body["has_route"] is True
    assert [by_id[i["id"]] for i in body["items"]] == NORD_LOOP
    assert body["items"][0]["moving_s"] > 0


@pytest.mark.parametrize(
    ("file", "has_route"), [(ZWIFT, True), (INDOOR, False)], ids=["zwift", "indoor"]
)
def test_route_progress_of_a_ride_alone_on_its_route(reader: Api, file: str, has_route: bool):
    """A ride with no other ride on its route, or without positions, lists only itself.

    Given: the Zwift ride (alone in Watopia) or the indoor ride (no GPS).
    Expect: only that ride; ``has_route`` says whether it had positions.
    """
    response = reader.client.get(f"/api/rides/{reader.ids[file]}/route-progress")

    body = response.json()
    assert body["has_route"] is has_route
    assert [i["id"] for i in body["items"]] == [reader.ids[file]]


def test_route_progress_of_an_unknown_ride_is_404(reader: Api):
    """Route progress for a ride that doesn't exist is a 404.

    Given: an unknown id.
    Expect: 404.
    """
    response = reader.client.get("/api/rides/zzzzzzzz/route-progress")

    assert response.status_code == 404
