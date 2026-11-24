"""Watched folders: adding and removing them, their state, scanning, and the server's watcher."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Generator
from functools import partial
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api.app import create_app
from fitlib.config import Config
from fitlib.services.watching import Watcher
from fitlib.store.factory import open_stores
from tests.clients import LOCAL
from tests.fixtures.generate import FIT_DIR

ZWIFT = "2025-08-02-08-29-42.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
CORRUPT = "corrupt_truncated.fit"
LONG_AGO = 1_700_000_000


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """An empty folder to watch, outside the library.

    Returns:
        Its resolved path.
    """
    path = tmp_path / "Activities"
    path.mkdir()
    return path.resolve()


def drop(folder: Path, fixture: str, mtime: float = LONG_AGO) -> Path:
    """Copy a fixture file into a folder, settled long ago.

    Args:
        folder: Where to put it.
        fixture: The fixture's file name.
        mtime: Its modification time, in seconds since 1970.

    Returns:
        The copy.
    """
    path = folder / fixture
    shutil.copyfile(FIT_DIR / fixture, path)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home folder of the test's own, so suggestions never come from the real one.

    Returns:
        The home folder (with no Zwift folder in it).
    """
    path = tmp_path / "home"
    path.mkdir()
    monkeypatch.setenv("HOME", str(path))
    return path


def test_no_folders_at_first(client: TestClient):
    """A new library watches nothing; without a watcher, the server says so.

    Given: an empty library served without a watcher.
    Expect: no folders, no recent files, not running.
    """
    response = client.get("/api/watch")

    assert response.json() == {
        "running": False,
        "folders": [],
        "recent": [],
        "waiting": 0,
        "last_import": None,
        "suggestions": [],
    }


def test_add_list_and_remove_a_folder(client: TestClient, folder: Path):
    """A folder can be added (as typed, with a trailing slash), listed and removed.

    Given: the folder added, then listed, then removed (twice).
    Expect: 201 with its resolved path, "stopped" (no watcher); listed; 204 then 404.
    """
    added = client.post("/api/watch/folders", json={"path": f"{folder}/"})
    listed = client.get("/api/watch").json()["folders"]
    removed = client.delete("/api/watch/folders", params={"path": str(folder)})
    again = client.delete("/api/watch/folders", params={"path": str(folder)})

    assert added.status_code == 201
    expected = {"path": str(folder), "state": "stopped", "message": None, "files": 0}
    assert added.json() == expected
    assert listed == [expected]
    assert removed.status_code == 204
    assert again.status_code == 404
    assert again.json()["detail"] == f"{folder} isn't a watched folder"


@pytest.mark.parametrize(
    ("path", "status", "message"),
    [
        ("Activities", 422, "Give the folder's full path"),
        ("{tmp}/nowhere", 422, "There's no folder at"),
        ("{tmp}/library", 422, "holds fitlib's own library"),
        ("{folder}", 409, "is already watched"),
    ],
    ids=["relative", "missing", "the-library", "already-watched"],
)
def test_add_folder_refused(
    client: TestClient, config: Config, folder: Path, tmp_path: Path, path, status, message
):
    """Folders that can't be watched, or already are, are refused with a reason.

    Given: the folder already watched, then a relative path, a missing folder, the library
    or the same folder again.
    Expect: 422 or 409 saying why, and still just the one folder.
    """
    config.library.mkdir(parents=True, exist_ok=True)
    client.post("/api/watch/folders", json={"path": str(folder)})

    response = client.post(
        "/api/watch/folders", json={"path": path.format(tmp=tmp_path, folder=folder)}
    )

    assert response.status_code == status
    assert message in response.json()["detail"]
    assert len(client.get("/api/watch").json()["folders"]) == 1


def test_a_missing_folder_is_listed_as_missing(client: TestClient, folder: Path, tmp_path: Path):
    """A watched folder that's gone is listed as missing.

    Given: a watched folder renamed away.
    Expect: its state is "missing".
    """
    client.post("/api/watch/folders", json={"path": str(folder)})
    folder.rename(tmp_path / "elsewhere")

    folders = client.get("/api/watch").json()["folders"]

    assert folders[0]["state"] == "missing"


def test_scan_without_a_watcher_imports_at_once(client: TestClient, folder: Path):
    """Without a watcher, a scan imports the folders' new files before answering.

    Given: a watched folder with two rides and a broken file, scanned twice.
    Expect: 2 imported and 1 failed; then nothing new; recent files list all three, newest
    first, the rides linked to their rides; the folder counts 3 files.
    """
    client.post("/api/watch/folders", json={"path": str(folder)})
    for name in (ZWIFT, INTERVALS, CORRUPT):
        drop(folder, name)

    first = client.post("/api/watch/scan").json()
    second = client.post("/api/watch/scan").json()
    status = client.get("/api/watch").json()

    assert first == {
        "background": False,
        "imported": 2,
        "duplicates": 0,
        "skipped": 0,
        "failed": 1,
        "still_writing": 0,
    }
    assert second["imported"] == second["failed"] == 0, "nothing new the second time"
    recent = {f["name"]: f for f in status["recent"]}
    assert recent.keys() == {ZWIFT, INTERVALS, CORRUPT}
    assert recent[CORRUPT]["outcome"] == "failed" and recent[CORRUPT]["detail"]
    ride = client.get(f"/api/rides/{recent[ZWIFT]['ride_id']}").json()
    assert ride["name"] == "Zwift 2025-08-02 08:30"
    assert status["folders"][0]["files"] == 3


@pytest.fixture
def watching(config: Config) -> Generator[TestClient]:
    """A client for an app whose watcher settles files after 0.3 s.

    Args:
        config: The library to serve.

    Yields:
        The client; the watcher runs while it's open.
    """
    watcher = Watcher(partial(open_stores, config), stable_s=0.3, tick_s=0.05)
    with TestClient(create_app(config, workers=1, watcher=watcher), base_url=LOCAL) as test_client:
        yield test_client


def wait_for(client: TestClient, check, what: str) -> dict:
    """Poll the watch status until a check passes, for up to 10 seconds.

    Args:
        client: The client.
        check: Takes the status; true when done.
        what: What's waited for, for the failure message.

    Returns:
        The status that passed.
    """
    deadline = time.monotonic() + 10
    while True:
        status = client.get("/api/watch").json()
        if check(status):
            return status
        assert time.monotonic() < deadline, f"{what} should happen within 10 s"
        time.sleep(0.05)


def test_the_server_watcher_imports_what_is_there_and_what_arrives(
    watching: TestClient, folder: Path
):
    """With the watcher running, a new folder's rides are imported, then new ones too.

    Given: a folder holding a ride added while the server watches; then a second ride
    copied in; then a scan asked for.
    Expect: the folder "watching" and the first ride imported; the second imported after
    it settles; the scan runs in the background.
    """
    drop(folder, ZWIFT)

    watching.post("/api/watch/folders", json={"path": str(folder)})
    first = wait_for(watching, lambda s: len(s["recent"]) == 1, "the first ride's import")
    shutil.copyfile(FIT_DIR / INTERVALS, folder / INTERVALS)
    second = wait_for(watching, lambda s: len(s["recent"]) == 2, "the second ride's import")
    scanned = watching.post("/api/watch/scan").json()

    assert first["running"] is True
    assert first["folders"][0]["state"] == "watching"
    assert first["last_import"] is not None
    assert [f["name"] for f in second["recent"]] == [INTERVALS, ZWIFT], "newest first"
    assert watching.get("/api/rides").json()["total"] == 2
    assert scanned["background"] is True


def test_e2e_mode_keeps_watched_folders_in_the_temp_folder(tmp_path: Path, folder: Path):
    """In e2e mode, only folders inside the temp folder can be watched.

    Given: an app in e2e mode, then a temp folder and this repository's tests folder.
    Expect: the temp folder accepted; the tests folder refused.
    """
    config = Config(library=tmp_path / "library")
    app = create_app(config, workers=1, e2e_fixtures=FIT_DIR)

    with TestClient(app, base_url=LOCAL) as client:
        inside = client.post("/api/watch/folders", json={"path": str(folder)})
        outside = client.post("/api/watch/folders", json={"path": str(Path(__file__).parent)})

    assert inside.status_code == 201
    assert outside.status_code == 422
    assert "Only folders inside" in outside.json()["detail"]


def test_zwift_folder_is_suggested_until_watched(client: TestClient, home: Path):
    """Zwift's Activities folder is suggested when it exists, until it's watched.

    Given: ``~/Documents/Zwift/Activities`` in the home folder, then watched.
    Expect: suggested before, not after.
    """
    zwift = home / "Documents" / "Zwift" / "Activities"
    zwift.mkdir(parents=True)

    before = client.get("/api/watch").json()["suggestions"]
    client.post("/api/watch/folders", json={"path": before[0]})
    after = client.get("/api/watch").json()["suggestions"]

    assert before == [str(zwift.resolve())]
    assert after == []
