"""The athlete history, and how it feeds a ride's training figures."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import Api

INTERVALS = "garmin_nord_intervals_5x4.fit"  # 5 Aug 2025
HR_ONLY = "garmin_nord_hr_no_power.fit"  # 16 Aug 2025, 45 min at 132 bpm, no power


def test_empty_history(client: TestClient):
    """A new library has no athlete values.

    Given: an empty library.
    Expect: no entries, nothing in effect today, no year of birth and so no estimate.
    """
    response = client.get("/api/athlete")

    assert response.json() == {
        "history": [],
        "today": {"ftp": None, "weight_kg": None, "max_hr": None, "threshold_hr": None},
        "birth_year": None,
        "estimated_threshold_hr": None,
        "threshold_hr_today": None,
        "threshold_hr_source_today": None,
    }


def test_entries_carry_values_forward(client: TestClient):
    """Each value comes from the latest entry that sets it.

    Given: FTP, weight, max and threshold HR from 2025-01-01, then only a new FTP from
    2025-06-01.
    Expect: both entries oldest first; today's FTP from June, the rest from January.
    """
    client.put("/api/athlete/2025-06-01", json={"ftp": 260})
    client.put(
        "/api/athlete/2025-01-01",
        json={"ftp": 250, "weight_kg": 72.5, "max_hr": 185, "threshold_hr": 165},
    )

    response = client.get("/api/athlete")

    body = response.json()
    assert [e["effective_from"] for e in body["history"]] == ["2025-01-01", "2025-06-01"]
    assert body["today"] == {"ftp": 260, "weight_kg": 72.5, "max_hr": 185, "threshold_hr": 165}


def test_put_replaces_the_entry_on_that_date(client: TestClient):
    """Saving values on a date that already has an entry replaces it.

    Given: an entry with FTP and weight, then a second save on the same date with only FTP.
    Expect: one entry, with the new FTP and no weight.
    """
    client.put("/api/athlete/2025-01-01", json={"ftp": 250, "weight_kg": 72.5})

    saved = client.put("/api/athlete/2025-01-01", json={"ftp": 255}).json()

    history = client.get("/api/athlete").json()["history"]
    assert saved == {
        "effective_from": "2025-01-01",
        "ftp": 255,
        "weight_kg": None,
        "max_hr": None,
        "threshold_hr": None,
    }
    assert history == [saved]


@pytest.mark.parametrize(
    "body",
    [{}, {"ftp": 0}, {"ftp": -5}, {"weight_kg": 0}, {"max_hr": 300}, {"threshold_hr": 0},
     {"vo2max": 60}],
    ids=["nothing", "zero-ftp", "negative-ftp", "zero-weight", "max-hr-high", "zero-threshold",
         "unknown-field"],
)  # fmt: skip
def test_put_rejects_missing_or_impossible_values(client: TestClient, body: dict):
    """An entry needs at least one plausible value.

    Given: no values, a zero or negative value, a max HR of 300 or an unknown field.
    Expect: 422, and the history still empty.
    """
    response = client.put("/api/athlete/2025-01-01", json=body)

    assert response.status_code == 422
    assert client.get("/api/athlete").json()["history"] == []


def test_delete_entry(client: TestClient):
    """An entry can be removed; removing a missing one is a 404.

    Given: one entry, deleted twice.
    Expect: 204, then 404, and an empty history.
    """
    client.put("/api/athlete/2025-01-01", json={"ftp": 250})

    first = client.delete("/api/athlete/2025-01-01")
    second = client.delete("/api/athlete/2025-01-01")

    assert (first.status_code, second.status_code) == (204, 404)
    assert client.get("/api/athlete").json()["history"] == []


def test_ride_figures_use_the_ftp_in_effect_on_the_ride_date(writer: Api):
    """A set FTP replaces the estimate for rides on or after its date only.

    Given: FTP 250 and max HR 190 from 2025-08-01, and FTP 300 from the day after the
    interval ride.
    Expect: the interval ride (5 Aug 2025) uses FTP 250, not estimated, and has HR zones.
    """
    writer.client.put("/api/athlete/2025-08-01", json={"ftp": 250, "max_hr": 190})
    writer.client.put("/api/athlete/2025-08-06", json={"ftp": 300})

    ride = writer.client.get(f"/api/rides/{writer.ids[INTERVALS]}").json()

    training = ride["training"]
    assert (training["ftp"], training["ftp_estimated"]) == (250, False)
    assert training["intensity_factor"] == pytest.approx(ride["np"] / 250)
    assert len(ride["hr_zones"]) == 5, "max HR is set, so HR zones should be there"
    assert date.fromisoformat(ride["start"][:10]) < date(2025, 8, 6)


def test_year_of_birth_gives_an_estimated_threshold(client: TestClient):
    """A year of birth gives today's estimated threshold heart rate; it can be cleared.

    Given: born 1980, then cleared.
    Expect: the year and round(0.9 x (208 - 0.7 x age)) today; then neither.
    """
    age = date.today().year - 1980

    saved = client.put("/api/athlete/birth-year", json={"birth_year": 1980}).json()
    cleared = client.put("/api/athlete/birth-year", json={"birth_year": None}).json()

    assert saved["birth_year"] == 1980
    assert saved["estimated_threshold_hr"] == round(0.9 * (208 - 0.7 * age))
    assert (cleared["birth_year"], cleared["estimated_threshold_hr"]) == (None, None)


@pytest.mark.parametrize(
    "year", [1899, date.today().year + 1, "x"], ids=["early", "future", "text"]
)
def test_impossible_years_of_birth_are_refused(client: TestClient, year):
    """Years before 1900, in the future or not numbers are refused.

    Given: 1899, next year, and "x".
    Expect: 422, and still no year of birth.
    """
    response = client.put("/api/athlete/birth-year", json={"birth_year": year})

    assert response.status_code == 422
    assert client.get("/api/athlete").json()["birth_year"] is None


def test_a_ride_without_power_gets_tss_from_heart_rate(writer: Api):
    """Rides without power get a heart-rate TSS, marked as such, in detail and in the list.

    Given: threshold HR 165 from 2025-08-01; the 16 Aug ride with heart rate only.
    Expect: TSS 48 from heart rate, threshold 165 not estimated; the library row the same.
    """
    writer.client.put("/api/athlete/2025-08-01", json={"threshold_hr": 165})

    ride = writer.client.get(f"/api/rides/{writer.ids[HR_ONLY]}").json()
    items = writer.client.get("/api/rides", params={"limit": 200}).json()["items"]

    training = ride["training"]
    assert training["tss"] == pytest.approx(48)
    assert training["tss_source"] == "hr"
    assert (training["threshold_hr"], training["threshold_hr_estimated"]) == (165, False)
    row = next(r for r in items if r["id"] == writer.ids[HR_ONLY])
    assert (row["tss"], row["tss_source"], row["threshold_hr_estimated"]) == (
        pytest.approx(48),
        "hr",
        False,
    )


def test_your_rides_give_the_threshold_before_your_age(writer: Api):
    """Without a set threshold, rides with power and heart rate give one, ahead of the age.

    Given: born 1980; the fixture rides with power and heart rate from 2 to 12 Aug 2025, and
    the 16 Aug ride without power.
    Expect: that ride's threshold 145 bpm from your rides, and its TSS from it; today (no
    rides in the last 90 days), the threshold from age.
    """
    writer.client.put("/api/athlete/birth-year", json={"birth_year": 1980})

    training = writer.client.get(f"/api/rides/{writer.ids[HR_ONLY]}").json()["training"]
    athlete = writer.client.get("/api/athlete").json()

    assert (training["threshold_hr"], training["threshold_hr_source"]) == (145, "rides")
    assert training["tss"] == pytest.approx(75 * (132 / 145) ** 2)
    age = date.today().year - 1980
    assert (athlete["threshold_hr_today"], athlete["threshold_hr_source_today"]) == (
        round(0.9 * (208 - 0.7 * age)),
        "age",
    )
