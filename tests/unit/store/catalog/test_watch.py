"""Catalog contract: watched folders and the files seen in them.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from fitlib.models import (
    WatchedFile,
    WatchFolder,
    WatchOutcome,
)
from fitlib.store.interfaces import (
    CatalogStore,
)
from tests.unit.factories import DEFAULT_START


def watched(path: str, outcome: WatchOutcome, minute: int, folder: str = "/rides") -> WatchedFile:
    """A file found in a watched folder.

    Args:
        path: The file's path.
        outcome: What importing it did.
        minute: When it was imported: minutes after 2 Aug 2025 06:30 UTC.
        folder: The watched folder it was in.

    Returns:
        The record.
    """
    return WatchedFile(
        path=path,
        folder=folder,
        size=1000,
        mtime_ns=1_754_000_000_000_000_000,
        outcome=outcome,
        detail=None if outcome is WatchOutcome.IMPORTED else "why",
        ride_id="r1" if outcome is WatchOutcome.IMPORTED else None,
        seen_at=DEFAULT_START + timedelta(minutes=minute),
    )


def test_watch_folders_are_added_listed_and_removed(catalog: CatalogStore):
    """Watched folders are kept by path; adding one twice or removing a stranger does nothing.

    Given: two folders added (one twice), then one removed (twice).
    Expect: both listed by path; the second add and second remove report ``False``.
    """
    zwift = WatchFolder("/Users/me/Documents/Zwift/Activities", DEFAULT_START)
    garmin = WatchFolder("/Volumes/GARMIN/Garmin/Activities", DEFAULT_START)

    added = [catalog.add_watch_folder(f) for f in (zwift, garmin, zwift)]
    both = catalog.watch_folders()
    removed = [catalog.remove_watch_folder(garmin.path) for _ in range(2)]

    assert added == [True, True, False], "adding a watched folder again should change nothing"
    assert both == [zwift, garmin], "folders should be listed by path"
    assert removed == [True, False]
    assert catalog.watch_folders() == [zwift]


def test_watched_files_are_recorded_replaced_and_listed(catalog: CatalogStore):
    """A file's latest record replaces the last; recent files leave out duplicates.

    Given: a file that failed, then imported after it changed; a duplicate; a skipped file;
    a file in another folder.
    Expect: the file's record is the import; recent files are newest first without the
    duplicate; counts per folder include every file.
    """
    catalog.add_watch_folder(WatchFolder("/rides", DEFAULT_START))
    catalog.record_watched_file(watched("/rides/a.fit", WatchOutcome.FAILED, 0))
    imported = replace(watched("/rides/a.fit", WatchOutcome.IMPORTED, 5), size=2000)
    catalog.record_watched_file(imported)
    catalog.record_watched_file(watched("/rides/b.fit", WatchOutcome.DUPLICATE, 6))
    skipped = watched("/rides/c.fit", WatchOutcome.SKIPPED, 7)
    catalog.record_watched_file(skipped)
    other = watched("/other/d.fit", WatchOutcome.IMPORTED, 1, folder="/other")
    catalog.record_watched_file(other)

    assert catalog.watched_file("/rides/a.fit") == imported, "the latest record should win"
    assert catalog.watched_file("/rides/zzz.fit") is None
    assert catalog.recent_watched_files() == [skipped, imported, other]
    assert catalog.recent_watched_files(limit=1) == [skipped]
    assert catalog.watched_file_counts() == {"/rides": 3, "/other": 1}


def test_recent_files_in_the_same_second_are_latest_first(catalog: CatalogStore):
    """Files recorded in the same second are listed in the order recorded, latest first.

    Given: three files imported at the same time, recorded b, a, c; then b recorded again.
    Expect: b, c, a.
    """
    for name in ("b", "a", "c", "b"):
        catalog.record_watched_file(watched(f"/rides/{name}.fit", WatchOutcome.IMPORTED, 0))

    recent = catalog.recent_watched_files()

    assert [Path(f.path).stem for f in recent] == ["b", "c", "a"]


def test_removing_a_folder_forgets_its_files(catalog: CatalogStore):
    """Files found in a folder are forgotten when it's no longer watched.

    Given: files recorded in two folders, then one folder removed.
    Expect: only the other folder's file is left.
    """
    for folder in ("/rides", "/other"):
        catalog.add_watch_folder(WatchFolder(folder, DEFAULT_START))
        catalog.record_watched_file(
            watched(f"{folder}/a.fit", WatchOutcome.IMPORTED, 0, folder=folder)
        )

    catalog.remove_watch_folder("/rides")

    assert catalog.watched_file("/rides/a.fit") is None
    assert catalog.watched_file_counts() == {"/other": 1}
