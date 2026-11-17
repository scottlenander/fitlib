"""The default time zone: listing zones, setting it, and the rides that follow it."""

from __future__ import annotations

from tests.api.conftest import Api

# A Wahoo ride with no local time and an undated name: 02:00 UTC on 11 Aug 2025.
NO_TIME_ZONE = "other_ride_no_time_zone.fit"
ZWIFT = "2025-08-02-08-29-42.fit"


def test_time_zones_are_listed(reader: Api):
    """The zones the default can be set to are listed, sorted.

    Given: the app.
    Expect: IANA names including New York and Paris, in order.
    """
    zones = reader.client.get("/api/settings/time-zones").json()

    assert "America/New_York" in zones and "Europe/Paris" in zones
    assert zones == sorted(zones)


def test_setting_the_default_updates_rides_without_their_own(writer: Api):
    """Rides without a time zone take the default at once; others keep theirs.

    Given: the Wahoo ride with no time zone; the Zwift ride with one from its file name.
    Expect: 1 ride updated; the Wahoo ride starts 22:00 on 10 Aug in New York (-4 h), and is
        named for that time instead of 02:00 UTC; the Zwift ride still at 08:30 (CEST);
        settings report the zone.
    """
    ride_id = writer.ids[NO_TIME_ZONE]
    before = writer.client.get(f"/api/rides/{ride_id}").json()

    response = writer.client.put("/api/settings/timezone", json={"timezone": "America/New_York"})
    after = writer.client.get(f"/api/rides/{ride_id}").json()
    zwift = writer.client.get(f"/api/rides/{writer.ids[ZWIFT]}").json()

    assert (before["local_start"], before["name"]) == (None, "Ride 2025-08-11 02:00 UTC")
    assert response.status_code == 200
    assert response.json() == {"timezone": "America/New_York", "updated": 1, "bikes_to_check": 0}
    assert (after["utc_offset_s"], after["local_start"]) == (-14400, "2025-08-10T22:00:00")
    assert after["name"] == "Ride 2025-08-10 22:00"
    assert zwift["local_start"] == "2025-08-02T08:30:00"
    assert writer.client.get("/api/settings").json()["timezone"] == "America/New_York"


def test_clearing_the_default_goes_back_to_utc(writer: Api):
    """Clearing the default leaves rides that used it with no time zone.

    Given: the Wahoo ride on the New York default.
    Expect: 1 ride updated; no local start; no zone in settings.
    """
    writer.client.put("/api/settings/timezone", json={"timezone": "America/New_York"})

    response = writer.client.put("/api/settings/timezone", json={"timezone": None})
    ride = writer.client.get(f"/api/rides/{writer.ids[NO_TIME_ZONE]}").json()

    assert response.json()["updated"] == 1
    assert ride["local_start"] is None
    assert writer.client.get("/api/settings").json()["timezone"] is None


def test_an_unknown_zone_is_refused(writer: Api):
    """A zone that isn't in the database is a 422, and nothing changes.

    Given: "Mars/Olympus_Mons".
    Expect: a 422 naming it; no default saved.
    """
    response = writer.client.put("/api/settings/timezone", json={"timezone": "Mars/Olympus_Mons"})

    assert response.status_code == 422
    assert "Mars/Olympus_Mons" in response.json()["detail"]
    assert writer.client.get("/api/settings").json()["timezone"] is None
