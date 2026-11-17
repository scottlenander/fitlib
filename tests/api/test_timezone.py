"""The default time zone: listing zones, setting it, and the rides that follow it."""

from __future__ import annotations

from fitlib.models import OffsetSource
from fitlib.store.factory import open_stores
from tests.api.conftest import Api

INDOOR = "garmin_indoor_no_hr.fit"  # 19 Aug 2025, starts 18:30 UTC
ZWIFT = "2025-08-02-08-29-42.fit"


def without_time_zone(api: Api, file_name: str) -> str:
    """Make a ride look as if its file had no time zone.

    Args:
        api: The client and its ride ids.
        file_name: The fixture file the ride came from.

    Returns:
        The ride's id.
    """
    ride_id = api.ids[file_name]
    with open_stores(api.config) as stores:
        stores.catalog.set_utc_offsets({ride_id: (None, OffsetSource.NONE)})
    return ride_id


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

    Given: the indoor ride with no time zone; the Zwift ride with one from its file name.
    Expect: 1 ride updated; the indoor ride starts 14:30 New York time (-4 h); the Zwift ride
        still at 08:30 (CEST); settings report the zone.
    """
    indoor = without_time_zone(writer, INDOOR)

    response = writer.client.put("/api/settings/timezone", json={"timezone": "America/New_York"})
    ride = writer.client.get(f"/api/rides/{indoor}").json()
    zwift = writer.client.get(f"/api/rides/{writer.ids[ZWIFT]}").json()

    assert response.status_code == 200
    assert response.json() == {"timezone": "America/New_York", "updated": 1, "bikes_to_check": 0}
    assert (ride["utc_offset_s"], ride["local_start"]) == (-14400, "2025-08-19T14:30:00")
    assert zwift["local_start"] == "2025-08-02T08:30:00"
    assert writer.client.get("/api/settings").json()["timezone"] == "America/New_York"


def test_clearing_the_default_goes_back_to_utc(writer: Api):
    """Clearing the default leaves rides that used it with no time zone.

    Given: the indoor ride on the New York default.
    Expect: 1 ride updated; no local start; no zone in settings.
    """
    indoor = without_time_zone(writer, INDOOR)
    writer.client.put("/api/settings/timezone", json={"timezone": "America/New_York"})

    response = writer.client.put("/api/settings/timezone", json={"timezone": None})
    ride = writer.client.get(f"/api/rides/{indoor}").json()

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
