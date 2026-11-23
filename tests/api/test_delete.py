"""Deleting rides through the API, and uploading their files again."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fitlib.store.factory import open_stores
from fitlib.watcher import watch_folder
from tests.api.conftest import Api
from tests.fixtures.generate import FIT_DIR

RIDE = "garmin_nord_intervals_5x4.fit"
OTHER = "garmin_indoor_no_hr.fit"
EXTRA = FIT_DIR.parent / "extra" / "garmin_arras_hr_only.fit"


def upload(api: Api, name: str, include_deleted: bool = False) -> dict:
    """Upload one fixture file.

    Args:
        api: The client.
        name: The fixture's file name.
        include_deleted: Ask to import it even if its ride was deleted.

    Returns:
        The import result.
    """
    response = api.client.post(
        "/api/imports",
        params={"include_deleted": include_deleted},
        files=[("files", (name, (FIT_DIR / name).read_bytes()))],
    )
    assert response.status_code == 200, response.text
    return response.json()


def total(api: Api) -> int:
    """Count the library's rides.

    Args:
        api: The client.

    Returns:
        The number of rides.
    """
    return api.client.get("/api/rides").json()["total"]


def test_delete_one_ride(writer: Api):
    """DELETE removes the ride; it's then a 404 and the library has one ride fewer.

    Given: The fixture library, with one ride deleted by an id prefix.
    Expect: ``{"deleted": 1}``; the ride 404s; the total drops by one.
    """
    ride_id = writer.ids[RIDE]
    before = total(writer)

    response = writer.client.delete(f"/api/rides/{ride_id[:8]}")

    assert response.status_code == 200
    assert response.json() == {"deleted": 1}
    assert writer.client.get(f"/api/rides/{ride_id}").status_code == 404
    assert total(writer) == before - 1


def test_delete_unknown_ride(writer: Api):
    """Deleting a ride that isn't there is a 404.

    Given: An id that matches no ride.
    Expect: 404, nothing deleted.
    """
    before = total(writer)

    response = writer.client.delete("/api/rides/ffffffff")

    assert response.status_code == 404
    assert total(writer) == before


def test_bulk_delete(writer: Api):
    """Several rides go at once; a ride named twice counts once.

    Given: Two rides, one named twice.
    Expect: ``{"deleted": 2}`` and both gone.
    """
    ids = [writer.ids[RIDE], writer.ids[OTHER], writer.ids[RIDE]]
    before = total(writer)

    response = writer.client.post("/api/rides/bulk-delete", json={"ids": ids})

    assert response.json() == {"deleted": 2}
    assert total(writer) == before - 2


def test_bulk_delete_with_an_unknown_ride_deletes_nothing(writer: Api):
    """One unknown ride stops the whole delete.

    Given: A real ride and an unknown id.
    Expect: 404, and the real ride still there.
    """
    response = writer.client.post(
        "/api/rides/bulk-delete", json={"ids": [writer.ids[RIDE], "ffffffff"]}
    )

    assert response.status_code == 404
    assert writer.client.get(f"/api/rides/{writer.ids[RIDE]}").status_code == 200


def test_bulk_delete_needs_one_to_500_rides(writer: Api):
    """The list of rides can't be empty or longer than 500.

    Given: No ids; 501 ids.
    Expect: 422 for both.
    """
    empty = writer.client.post("/api/rides/bulk-delete", json={"ids": []})
    many = writer.client.post("/api/rides/bulk-delete", json={"ids": ["abcd"] * 501})

    assert (empty.status_code, many.status_code) == (422, 422)


def test_uploading_a_deleted_ride_again(writer: Api):
    """A deleted ride's file is listed as deleted on upload, and comes back when asked.

    Given: A ride deleted, its file uploaded, then uploaded with ``include_deleted``.
    Expect: The first upload imports nothing and lists the file as deleted; the second
        imports it.
    """
    writer.client.delete(f"/api/rides/{writer.ids[RIDE]}")

    skipped = upload(writer, RIDE)
    back = upload(writer, RIDE, include_deleted=True)

    assert skipped["imported"] == []
    assert [f["file"] for f in skipped["deleted"]] == [RIDE]
    assert skipped["deleted"][0]["detail"].startswith("You deleted this ride on ")
    assert [f["file"] for f in back["imported"]] == [RIDE]
    assert back["deleted"] == []


def test_recent_watched_file_of_a_deleted_ride(writer: Api, tmp_path: Path):
    """A watched-folder import whose ride was deleted since says so instead of linking to it.

    Given: A watched folder with a new ride imported from it, then that ride deleted.
    Expect: Before, the recent file links to the ride; after, it has no ride id and
        ``ride_deleted`` is true.
    """
    folder = tmp_path / "watched"
    folder.mkdir()
    copy = folder / EXTRA.name
    copy.write_bytes(EXTRA.read_bytes())
    # Written a minute ago, so the scan doesn't wait for it to settle.
    old = time.time() - 60
    os.utime(copy, (old, old))
    with open_stores(writer.config) as stores:
        stores.catalog.add_watch_folder(watch_folder(folder))
    writer.client.post("/api/watch/scan")
    (before,) = writer.client.get("/api/watch").json()["recent"]

    writer.client.delete(f"/api/rides/{before['ride_id']}")
    (after,) = writer.client.get("/api/watch").json()["recent"]

    assert before["ride_id"] is not None and before["ride_deleted"] is False
    assert (after["ride_id"], after["ride_deleted"]) == (None, True)


def test_deleted_ride_error_is_readable(writer: Api):
    """Asking for a deleted ride says so in words, not just its id.

    Given: A ride deleted, then deleted again.
    Expect: 404 with "No ride matches '<id>' (it may have been deleted)".
    """
    ride_id = writer.ids[RIDE]
    writer.client.delete(f"/api/rides/{ride_id}")

    response = writer.client.delete(f"/api/rides/{ride_id}")

    assert response.status_code == 404
    assert response.json()["detail"] == f"No ride matches '{ride_id}' (it may have been deleted)"
