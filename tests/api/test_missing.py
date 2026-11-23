"""Several rides asked for at once when some are gone: every missing one is listed."""

from __future__ import annotations

from tests.api.conftest import Api

OUTDOOR = "garmin_nord_intervals_5x4.fit"
HR_ONLY = "garmin_nord_hr_no_power.fit"
ZWIFT = "2025-08-02-08-29-42.fit"
GONE = ["ffffffff", "eeeeeeee"]


def test_compare_lists_every_missing_ride(writer: Api):
    """Comparing with rides that aren't there names all of them.

    Given: Two real rides and one deleted, plus an id that never existed.
    Expect: 404 saying how many are gone, with ``missing`` listing both, in order.
    """
    deleted = writer.ids[ZWIFT]
    writer.client.delete(f"/api/rides/{deleted}")
    ids = [writer.ids[OUTDOOR], deleted, writer.ids[HR_ONLY], GONE[0]]

    response = writer.client.get("/api/compare", params={"ids": ids})

    assert response.status_code == 404
    body = response.json()
    assert body["missing"] == [deleted, GONE[0]]
    assert body["detail"] == "2 rides are no longer in the library (they may have been deleted)"


def test_bulk_edit_with_missing_rides_changes_nothing(writer: Api):
    """A bulk edit naming rides that are gone lists them and edits none.

    Given: One real ride and two unknown ids, with an effort to set.
    Expect: 404 listing the two; the real ride's effort unchanged.
    """
    real = writer.ids[OUTDOOR]

    response = writer.client.post("/api/rides/bulk-meta", json={"ids": [real, *GONE], "rpe": 7})

    assert response.status_code == 404
    assert response.json()["missing"] == GONE
    assert writer.client.get(f"/api/rides/{real}").json()["meta"]["rpe"] is None


def test_bulk_delete_with_a_missing_ride_deletes_nothing(writer: Api):
    """A bulk delete naming a ride that's gone lists it and deletes none.

    Given: One real ride and one unknown id.
    Expect: 404 saying one ride is gone, with ``missing``; the real ride still there.
    """
    real = writer.ids[OUTDOOR]

    response = writer.client.post("/api/rides/bulk-delete", json={"ids": [real, GONE[0]]})

    assert response.status_code == 404
    assert response.json() == {
        "detail": "1 ride is no longer in the library (it may have been deleted)",
        "missing": [GONE[0]],
    }
    assert writer.client.get(f"/api/rides/{real}").status_code == 200
