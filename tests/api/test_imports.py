"""Importing uploaded files, and the settings the browser app reads."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fitlib.api import create_app
from fitlib.config import Config
from fitlib.models import Units
from tests.clients import LOCAL
from tests.fixtures.generate import FIT_DIR
from tests.fixtures.specs import ride

PAUSE = "garmin_nord_pause_10min.fit"
ZWIFT = "2025-08-02-08-29-42.fit"


def upload(client: TestClient, *files: tuple[str, bytes]) -> dict:
    """Upload files to the import endpoint.

    Args:
        client: The test client.
        *files: ``(file name, contents)`` for each upload.

    Returns:
        The import result.
    """
    response = client.post("/api/imports", files=[("files", (name, data)) for name, data in files])
    assert response.status_code == 200, response.text
    return response.json()


def fixture(name: str) -> tuple[str, bytes]:
    """Read a committed fixture file for uploading.

    Args:
        name: The fixture's file name.

    Returns:
        The name and the file's bytes.
    """
    return name, (FIT_DIR / name).read_bytes()


def files(outcomes: list[dict]) -> list[str]:
    """Name the files in a list of outcomes.

    Args:
        outcomes: One list from an import result.

    Returns:
        The file names, in order.
    """
    return [o["file"] for o in outcomes]


def test_uploaded_ride_is_imported_and_can_be_fetched(client: TestClient):
    """An uploaded .fit file becomes a ride in the library.

    Given: an empty library and one ride uploaded.
    Expect: the file reported as imported with the new ride's id, which can be fetched;
    the library now has 1 ride.
    """
    result = upload(client, fixture(PAUSE))

    [imported] = result["imported"]
    ride_response = client.get(f"/api/rides/{imported['detail']}")
    assert imported["file"] == PAUSE
    assert ride_response.status_code == 200
    assert client.get("/api/health").json()["rides"] == 1


def test_zip_members_are_imported(client: TestClient):
    """Every ride inside an uploaded zip is imported.

    Given: the fixture Garmin export zip, holding two rides.
    Expect: both imported, named ``<zip>:<member>``.
    """
    result = upload(client, fixture("garmin_export.zip"))

    assert files(result["imported"]) == [
        "garmin_export.zip:garmin_export_ride_a.fit",
        "garmin_export.zip:garmin_export_ride_b.fit",
    ]


def test_duplicates_are_recognised_within_and_across_uploads(client: TestClient):
    """The same file is only imported once, whether repeated in one upload or uploaded later.

    Given: one ride uploaded twice in one request, then again in a second request.
    Expect: first request imports one and reports one duplicate; the second reports a
    duplicate of the existing ride; the library has 1 ride.
    """
    first = upload(client, fixture(PAUSE), fixture(PAUSE))
    second = upload(client, fixture(PAUSE))

    ride_id = first["imported"][0]["detail"]
    assert (len(first["imported"]), len(first["duplicates"])) == (1, 1)
    assert second["imported"] == []
    assert ride_id in second["duplicates"][0]["detail"], "should name the existing ride"
    assert client.get("/api/health").json()["rides"] == 1


def test_bad_files_are_reported_and_the_rest_still_import(client: TestClient):
    """Unreadable files, non-rides and other file types are reported; good files import.

    Given: a truncated .fit file, a run, a text file and a good ride in one upload.
    Expect: the ride imported; the run skipped; the truncated and text files failed with
    reasons.
    """
    result = upload(
        client,
        fixture("corrupt_truncated.fit"),
        fixture("garmin_nord_run_20min.fit"),
        ("notes.txt", b"not a ride"),
        fixture(PAUSE),
    )

    failed = {o["file"]: o["detail"] for o in result["failed"]}
    assert files(result["imported"]) == [PAUSE]
    assert files(result["skipped"]) == ["garmin_nord_run_20min.fit"]
    assert set(failed) == {"corrupt_truncated.fit", "notes.txt"}
    assert failed["notes.txt"] == "not a .fit or .zip file"


def test_upload_names_cannot_escape_the_upload_folder(client: TestClient):
    """A file name with folders in it is reduced to its base name.

    Given: a good ride uploaded as ``../../escaped.fit`` (uploads are written two levels
    below the system temp folder).
    Expect: imported under the name ``escaped.fit``, with nothing written to the temp
    folder or the one above it.
    """
    _, data = fixture(PAUSE)

    result = upload(client, ("../../escaped.fit", data))

    assert files(result["imported"]) == ["escaped.fit"]
    temp = Path(tempfile.gettempdir())
    assert not (temp / "escaped.fit").exists() and not (temp.parent / "escaped.fit").exists()


def test_uploads_get_the_default_bike(client: TestClient):
    """Uploaded rides get the default bike for their kind and date, like CLI imports.

    Given: a Zwift default bike from 2000, then the Zwift ride uploaded.
    Expect: the ride has the bike, marked as coming from the default.
    """
    bike = client.post("/api/bikes", json={"name": "Giant Contend 1"}).json()
    client.put("/api/bikes/defaults/zwift/2000-01-01", json={"bike_id": bike["id"]})

    result = upload(client, fixture(ZWIFT))

    meta = client.get(f"/api/rides/{result['imported'][0]['detail']}").json()["meta"]
    assert (meta["bike"]["id"], meta["bike_from_default"]) == (bike["id"], True)


def test_upload_needs_files(client: TestClient):
    """An import request with no files is refused.

    Given: a POST with no files.
    Expect: 422.
    """
    response = client.post("/api/imports")

    assert response.status_code == 422


def test_import_logs_never_contain_coordinates(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    """Location is sensitive, so importing through the API never logs coordinates.

    Given: an outdoor ride near 50.39°N 3.41°E and the Zwift ride near -11.64°, 166.95°,
    uploaded with fitlib logging at INFO.
    Expect: the import is logged, without those coordinates.
    """
    caplog.set_level(logging.INFO, logger="fitlib")
    loops = {ride("garmin_nord_pause_10min").loop, ride("zwift_watopia_steady_60min").loop}

    upload(client, fixture(PAUSE), fixture(ZWIFT))

    text = caplog.text
    assert "imported:" in text, "imports should be logged"
    for loop in loops:
        for value in (loop.center_lat, loop.center_lon):
            assert f"{value:.2f}" not in text, f"coordinate {value:.2f} should not be logged"


@pytest.mark.parametrize("units", [Units.IMPERIAL, Units.METRIC])
def test_settings_report_the_configured_units(tmp_path: Path, units: Units):
    """The browser app learns the default units and library folder from the config.

    Given: a config with imperial or metric units, and a new library.
    Expect: those units, the library folder, and no default time zone.
    """
    config = Config(library=tmp_path / "library", units=units)

    with TestClient(create_app(config, workers=1), base_url=LOCAL) as client:
        response = client.get("/api/settings")

    assert response.json() == {
        "units": units.value,
        "library": str(tmp_path / "library"),
        "timezone": None,
    }
