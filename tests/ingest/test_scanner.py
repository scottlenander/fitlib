"""Finding .fit files in folders, as single files, and inside .zip archives."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fitlib.ingest.scanner import scan
from tests.fixtures.generate import FIT_DIR


def names(paths: list[Path]) -> list[str]:
    return [source.name for source in scan(paths)]


def test_scans_the_fixture_folder_including_zip_members():
    """Every .fit file in a folder is found, and .zip archives are opened.

    Given: the fixture folder: 10 standalone .fit files and a .zip holding two rides.
    Expect: 12 sources in path order, the zipped ones named ``<zip>:<member>``.
    """
    found = names([FIT_DIR])

    assert len(found) == 12
    assert found == sorted(found), "sources should come in a stable, sorted order"
    assert "garmin_export.zip:garmin_export_ride_a.fit" in found
    assert "garmin_export.zip:garmin_export_ride_b.fit" in found


def test_reads_return_the_file_bytes():
    """Each source reads the bytes of its file, whether standalone or zipped.

    Given: a standalone fixture and the zipped one.
    Expect: the standalone bytes equal the file on disk; the zipped bytes are a FIT file
    (``.FIT`` signature at byte 8).
    """
    sources = {s.name: s for s in scan([FIT_DIR])}

    standalone = sources["zwift_watopia_steady_60min.fit"].read()
    zipped = sources["garmin_export.zip:garmin_export_ride_a.fit"].read()

    assert standalone == (FIT_DIR / "zwift_watopia_steady_60min.fit").read_bytes()
    assert zipped[8:12] == b".FIT", "a zip member should read as a FIT file"


def test_skips_hidden_and_non_fit_files(tmp_path: Path):
    """Only .fit and .zip files count; hidden files, hidden folders and macOS zip junk don't.

    Given: a folder with a .FIT (upper case), a .txt, a hidden .fit, a .fit in a hidden folder,
    and a zip containing a ride plus a ``__MACOSX`` copy.
    Expect: just the upper-case .fit and the real zip member.
    """
    (tmp_path / "ride.FIT").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / ".hidden.fit").write_bytes(b"x")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "inside.fit").write_bytes(b"x")
    with zipfile.ZipFile(tmp_path / "export.zip", "w") as archive:
        archive.writestr("rides/a.fit", b"x")
        archive.writestr("__MACOSX/rides/._a.fit", b"x")

    found = names([tmp_path])

    assert found == ["export.zip:rides/a.fit", "ride.FIT"]


def test_accepts_files_directly(tmp_path: Path):
    """A .fit file can be named on its own instead of a folder.

    Given: one fixture file path.
    Expect: exactly that file.
    """
    path = FIT_DIR / "garmin_nord_pause_10min.fit"

    found = names([path])

    assert found == ["garmin_nord_pause_10min.fit"]


def test_missing_path_fails_before_scanning(tmp_path: Path):
    """A typo in a path is reported straight away, not after importing the other paths.

    Given: the fixture folder and a path that doesn't exist.
    Expect: ``FileNotFoundError`` before any source is produced.
    """
    sources = scan([FIT_DIR, tmp_path / "missing"])

    with pytest.raises(FileNotFoundError):
        next(sources)
