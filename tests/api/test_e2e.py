"""The ``/e2e`` test shortcuts: only in e2e mode, and only over a throwaway library."""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.api.routers.e2e import UnsafeLibrary
from fitlib.config import Config
from tests.fixtures.generate import FIT_DIR

PAUSE = "garmin_nord_pause_10min.fit"
ZWIFT = "2025-08-02-08-29-42.fit"
IMPORTED_RIDES = 8


@pytest.fixture
def e2e(config: Config) -> Generator[TestClient]:
    """A client for an app in e2e mode over an empty temporary library.

    Args:
        config: The library to serve, inside pytest's temporary folder.

    Yields:
        The client; closed after the test.
    """
    with TestClient(create_app(config, workers=1, e2e_fixtures=FIT_DIR)) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/e2e/rides"),
        ("POST", "/e2e/reset"),
        ("POST", f"/e2e/import/{PAUSE}"),
        ("POST", "/e2e/rides/abcd/delete"),
    ],
)
def test_shortcuts_are_absent_outside_e2e_mode(client: TestClient, method: str, path: str):
    """Without e2e mode the shortcuts don't exist at all.

    Given: an app started normally.
    Expect: 404 for each shortcut, and the library still empty.
    """
    response = client.request(method, path)

    assert response.status_code == 404
    assert client.get("/api/health").json()["rides"] == 0


def test_reset_imports_the_fixtures_and_lists_their_ids(e2e: TestClient):
    """Reset fills an empty library with the fixture rides.

    Given: an e2e app over an empty library.
    Expect: reset returns 8 ride ids by file name, matching ``/e2e/rides`` and the
    library's ride count.
    """
    ids = e2e.post("/e2e/reset").json()

    assert len(ids) == IMPORTED_RIDES
    assert ids == e2e.get("/e2e/rides").json()
    assert e2e.get("/api/health").json()["rides"] == IMPORTED_RIDES
    assert e2e.get(f"/api/rides/{ids[ZWIFT]}").status_code == 200


def test_reset_throws_away_edits_and_added_rides(e2e: TestClient):
    """A second reset starts again from just the fixtures.

    Given: a reset library with a bike added and a ride tagged, then another reset.
    Expect: no bikes, no tags, and 8 rides with new ids.
    """
    first = e2e.post("/e2e/reset").json()
    e2e.post("/api/bikes", json={"name": "Giant Contend 1"})
    e2e.patch(f"/api/rides/{first[ZWIFT]}/meta", json={"tags": ["base"]})

    second = e2e.post("/e2e/reset").json()

    assert e2e.get("/api/bikes").json() == []
    assert e2e.get("/api/tags").json() == []
    assert len(second) == IMPORTED_RIDES
    assert second[ZWIFT] != first[ZWIFT], "rides should be imported afresh"


def test_reset_meta_returns_a_ride_to_how_it_was_imported(e2e: TestClient):
    """Undoing a ride's edits clears them and gives back its default bike.

    Given: a Zwift default bike, the Zwift ride imported, then renamed, tagged, rated and
    moved to another bike.
    Expect: after reset-meta, no name, notes, effort or tags, and the default bike again.
    """
    ride_id = e2e.post("/e2e/reset").json()[ZWIFT]
    default = e2e.post("/api/bikes", json={"name": "Giant Contend 1"}).json()
    other = e2e.post("/api/bikes", json={"name": "Scott Addict"}).json()
    e2e.put("/api/bikes/defaults/zwift/2000-01-01", json={"bike_id": default["id"]})
    edits = {"name": "x", "notes": "y", "rpe": 5, "tags": ["t"], "bike_id": other["id"]}
    e2e.patch(f"/api/rides/{ride_id}/meta", json=edits)

    response = e2e.post(f"/e2e/rides/{ride_id}/reset-meta")

    meta = e2e.get(f"/api/rides/{ride_id}").json()["meta"]
    assert response.status_code == 204
    assert meta == {
        "name": None,
        "notes": None,
        "rpe": None,
        "bike": {"id": default["id"], "name": "Giant Contend 1"},
        "bike_from_default": True,
        "tags": [],
    }


def test_delete_ride_lets_it_be_imported_again(e2e: TestClient):
    """A deleted ride is gone, with its files, so importing it again adds it afresh.

    Given: the fixtures imported, then one ride deleted.
    Expect: 204; the ride is a 404 and the count drops by one; importing the same file
    again imports it (not "already in library") under a new id.
    """
    ids = e2e.post("/e2e/reset").json()

    response = e2e.post(f"/e2e/rides/{ids[PAUSE]}/delete")
    after = e2e.get("/api/health").json()["rides"]
    again = e2e.post(f"/e2e/import/{PAUSE}").json()

    assert response.status_code == 204
    assert e2e.get(f"/api/rides/{ids[PAUSE]}").status_code == 404
    assert after == IMPORTED_RIDES - 1
    assert [o["file"] for o in again["imported"]] == [PAUSE], "should import, not dedupe"
    assert again["imported"][0]["detail"] != ids[PAUSE]


def test_import_one_fixture(e2e: TestClient):
    """One fixture can be imported into the library on its own.

    Given: an empty library.
    Expect: the fixture imported, and the library holding just that ride.
    """
    response = e2e.post(f"/e2e/import/{PAUSE}")

    assert [o["file"] for o in response.json()["imported"]] == [PAUSE]
    assert list(e2e.get("/e2e/rides").json()) == [PAUSE]


@pytest.mark.parametrize("name", ["missing.fit", "..%2Fspecs.py"], ids=["missing", "escape"])
def test_import_only_takes_files_from_the_fixture_folder(e2e: TestClient, name: str):
    """Only files in the fixture folder can be imported.

    Given: a fixture name that doesn't exist, or one climbing out of the folder.
    Expect: 404.
    """
    response = e2e.post(f"/e2e/import/{name}")

    assert response.status_code == 404


def test_shortcuts_stay_out_of_the_api_description(e2e: TestClient):
    """The shortcuts aren't part of the documented API.

    Given: an e2e app.
    Expect: no ``/e2e`` paths in ``/openapi.json``.
    """
    response = e2e.get("/openapi.json")

    assert not [p for p in response.json()["paths"] if p.startswith("/e2e")]


@pytest.mark.parametrize(
    "library",
    [Path.home() / ".fitlib" / "library", Path(tempfile.gettempdir())],
    ids=["home-library", "temp-folder-itself"],
)
def test_e2e_mode_refuses_libraries_outside_the_temp_folder(library: Path):
    """E2E mode can wipe its library, so it refuses any library that might be real.

    Given: the default library under the home folder, or the temp folder itself.
    Expect: building the app fails with ``UnsafeLibrary``.
    """
    with pytest.raises(UnsafeLibrary):
        create_app(Config(library=library), e2e_fixtures=FIT_DIR)
