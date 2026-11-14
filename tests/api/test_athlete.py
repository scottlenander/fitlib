"""The athlete history, and how it feeds a ride's training figures."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import Api

INTERVALS = "garmin_nord_intervals_5x4.fit"  # 5 Aug 2025


def test_empty_history(client: TestClient):
    """A new library has no athlete values.

    Given: an empty library.
    Expect: no entries, and nothing in effect today.
    """
    response = client.get("/api/athlete")

    assert response.json() == {
        "history": [],
        "today": {"ftp": None, "weight_kg": None, "max_hr": None},
    }


def test_entries_carry_values_forward(client: TestClient):
    """Each value comes from the latest entry that sets it.

    Given: FTP, weight and max HR from 2025-01-01, then only a new FTP from 2025-06-01.
    Expect: both entries oldest first; today's FTP from June, weight and max HR from January.
    """
    client.put("/api/athlete/2025-06-01", json={"ftp": 260})
    client.put("/api/athlete/2025-01-01", json={"ftp": 250, "weight_kg": 72.5, "max_hr": 185})

    response = client.get("/api/athlete")

    body = response.json()
    assert [e["effective_from"] for e in body["history"]] == ["2025-01-01", "2025-06-01"]
    assert body["today"] == {"ftp": 260, "weight_kg": 72.5, "max_hr": 185}


def test_put_replaces_the_entry_on_that_date(client: TestClient):
    """Saving values on a date that already has an entry replaces it.

    Given: an entry with FTP and weight, then a second save on the same date with only FTP.
    Expect: one entry, with the new FTP and no weight.
    """
    client.put("/api/athlete/2025-01-01", json={"ftp": 250, "weight_kg": 72.5})

    saved = client.put("/api/athlete/2025-01-01", json={"ftp": 255}).json()

    history = client.get("/api/athlete").json()["history"]
    assert saved == {"effective_from": "2025-01-01", "ftp": 255, "weight_kg": None, "max_hr": None}
    assert history == [saved]


@pytest.mark.parametrize(
    "body",
    [{}, {"ftp": 0}, {"ftp": -5}, {"weight_kg": 0}, {"max_hr": 300}, {"vo2max": 60}],
    ids=["nothing", "zero-ftp", "negative-ftp", "zero-weight", "max-hr-high", "unknown-field"],
)
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
