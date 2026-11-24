"""Watching folders for new rides: which folders and files, scanning, settling, and the thread."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fitlib.models import WatchFolder, WatchOutcome
from fitlib.services.importing import ImportReport
from fitlib.services.watching import (
    BadWatchFolder,
    FolderState,
    Watcher,
    check_folder,
    scan,
    summarize,
    wanted,
)
from fitlib.store.factory import Stores
from fitlib.store.memory import MemoryBlobStore, MemoryCatalog
from fitlib.store.streams import StreamStore
from tests.fixtures.generate import FIT_DIR

ZWIFT = "2025-08-02-08-29-42.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
RUN = "garmin_nord_run_20min.fit"
CORRUPT = "corrupt_truncated.fit"
EXPORT_ZIP = "garmin_export.zip"
LONG_AGO = 1_700_000_000  # Nov 2023: well settled
RIDE_ID = "0b4a1f3e-5c6d-4e7f-8a9b-0c1d2e3f4a5b"


def stores() -> Stores:
    """Fresh in-memory stores.

    Returns:
        The stores.
    """
    blobs = MemoryBlobStore()
    return Stores(MemoryCatalog(), blobs, StreamStore(blobs))


def drop(folder: Path, fixture: str, name: str | None = None, mtime: float = LONG_AGO) -> Path:
    """Copy a fixture file into a folder, with a given modification time.

    Args:
        folder: Where to put it.
        fixture: The fixture's file name.
        name: The copy's name; the fixture's by default.
        mtime: Its modification time, in seconds since 1970.

    Returns:
        The copy.
    """
    path = folder / (name or fixture)
    shutil.copyfile(FIT_DIR / fixture, path)
    os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """An empty folder to watch.

    Returns:
        Its resolved path.
    """
    path = tmp_path / "Activities"
    path.mkdir()
    return path.resolve()


# -- which folders --------------------------------------------------------------------------


def test_check_folder_expands_home_and_resolves(tmp_path: Path, monkeypatch, folder: Path):
    """A folder given from home (``~``) is expanded to its full path.

    Given: HOME set to the temp folder and ``~/Activities``.
    Expect: the folder's resolved absolute path.
    """
    monkeypatch.setenv("HOME", str(tmp_path))

    checked = check_folder("~/Activities ", tmp_path / "library")

    assert checked == folder


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("Activities", "Give the folder's full path"),
        ("{tmp}/nowhere", "There's no folder at"),
        ("{tmp}/notes.txt", "is a file, not a folder"),
        ("{tmp}/library", "holds fitlib's own library"),
        ("{tmp}/library/raw", "holds fitlib's own library"),
        ("{tmp}", "holds fitlib's own library"),
    ],
    ids=["relative", "missing", "a-file", "the-library", "inside-library", "holds-library"],
)
def test_check_folder_refuses(tmp_path: Path, raw: str, message: str):
    """Folders that can't be watched are refused with a reason.

    Given: a relative path, a missing folder, a file, the library, a folder inside it, or a
    folder holding it.
    Expect: ``BadWatchFolder`` saying why.
    """
    (tmp_path / "library" / "raw").mkdir(parents=True)
    (tmp_path / "notes.txt").write_text("not a folder")

    with pytest.raises(BadWatchFolder, match=message):
        check_folder(raw.format(tmp=tmp_path), tmp_path / "library")


def test_check_folder_keeps_inside_an_allowed_root(tmp_path: Path, folder: Path):
    """In e2e mode, only folders inside the allowed root can be watched.

    Given: an allowed root, then a folder inside it and one outside.
    Expect: the inside one accepted; the outside one refused.
    """
    root = tmp_path / "e2e"
    inside = root / "watched"
    inside.mkdir(parents=True)

    assert check_folder(str(inside), tmp_path / "library", root) == inside.resolve()
    with pytest.raises(BadWatchFolder, match="Only folders inside"):
        check_folder(str(folder), tmp_path / "library", root)


# -- which files ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("2026-11-15-07-23-09.fit", True),
        ("RIDE.FIT", True),
        ("export.zip", True),
        ("sub/2026-11-15-07-23-09.fit", True),
        ("inProgressActivity.fit", False),
        ("INPROGRESSACTIVITY.FIT", False),
        ("notes.txt", False),
        (".2026-11-15.fit", False),
        (".hidden/ride.fit", False),
        ("__MACOSX/ride.fit", False),
    ],
)
def test_wanted_files(folder: Path, name: str, expected: bool):
    """Only .fit and .zip files are wanted; not Zwift's in-progress file or hidden files.

    Given: a file name inside the watched folder.
    Expect: whether it's imported.
    """
    assert wanted(folder / name, folder) is expected


# -- what an import did ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (ImportReport(imported=[("a.fit", RIDE_ID)]), (WatchOutcome.IMPORTED, None, RIDE_ID)),
        (
            ImportReport(duplicates=[("a.fit", RIDE_ID)]),
            (WatchOutcome.DUPLICATE, RIDE_ID, RIDE_ID),
        ),
        (
            ImportReport(skipped=[("a.fit", "Not a ride: running")]),
            (WatchOutcome.SKIPPED, "Not a ride: running", None),
        ),
        (
            ImportReport(failed=[("a.fit", "Truncated")]),
            (WatchOutcome.FAILED, "Truncated", None),
        ),
        (
            ImportReport(
                imported=[("z:a.fit", RIDE_ID), ("z:b.fit", "other")],
                duplicates=[("z:c.fit", "same as z:a.fit")],
            ),
            (
                WatchOutcome.IMPORTED,
                "2 files imported, 1 file already in the library",
                RIDE_ID,
            ),
        ),
        (ImportReport(), (WatchOutcome.SKIPPED, "No .fit files inside", None)),
        (
            ImportReport(deleted=[("a.fit", "You deleted this ride on 2026-11-23")]),
            (WatchOutcome.SKIPPED, "You deleted this ride on 2026-11-23", None),
        ),
        (
            ImportReport(
                imported=[("z:a.fit", RIDE_ID)],
                deleted=[("z:b.fit", "You deleted this ride on 2026-11-23")],
            ),
            (WatchOutcome.IMPORTED, "1 file imported, 1 file you deleted", RIDE_ID),
        ),
    ],
    ids=[
        "imported",
        "duplicate",
        "skipped",
        "failed",
        "zip",
        "empty-zip",
        "deleted",
        "zip-deleted",
    ],
)
def test_summarize(report: ImportReport, expected: tuple):
    """One file's outcome is its own; a zip's is the best of its files, with counts.

    Given: an import report for one file or a zip.
    Expect: the outcome, detail and ride id recorded.
    """
    assert summarize(report) == expected


# -- scanning -------------------------------------------------------------------------------


def test_scan_imports_new_files_once(folder: Path):
    """A scan imports each new file and records it; a second scan reads nothing again.

    Given: two rides, a run, a broken file, Zwift's in-progress file and a zip of two rides.
    Expect: the rides and zip imported, the run skipped, the broken file failed, the
    in-progress file ignored; then nothing on a second scan.
    """
    s = stores()
    for name in (ZWIFT, INTERVALS, RUN, CORRUPT, EXPORT_ZIP):
        drop(folder, name)
    drop(folder, ZWIFT, "inProgressActivity.fit")

    first = scan(s, [str(folder)])
    again = scan(s, [str(folder)])

    outcomes = {Path(f.path).name: f.outcome for f in first.files}
    assert outcomes == {
        ZWIFT: WatchOutcome.IMPORTED,
        INTERVALS: WatchOutcome.IMPORTED,
        RUN: WatchOutcome.SKIPPED,
        CORRUPT: WatchOutcome.FAILED,
        EXPORT_ZIP: WatchOutcome.IMPORTED,
    }
    assert s.catalog.count() == 4
    assert again.files == [], "unchanged files should not be read again"
    zwift = s.catalog.watched_file(str(folder / ZWIFT))
    assert zwift is not None and zwift.ride_id is not None
    assert s.catalog.get_ride(zwift.ride_id).source_name == ZWIFT


def test_scan_retries_a_failed_file_once_it_changes(folder: Path):
    """A file that failed is tried again only after it changes.

    Given: a broken file scanned, then scanned again, then replaced by a whole ride.
    Expect: failed; nothing; then imported.
    """
    s = stores()
    path = drop(folder, CORRUPT, "ride.fit")

    failed = scan(s, [str(folder)])
    unchanged = scan(s, [str(folder)])
    drop(folder, INTERVALS, "ride.fit", mtime=LONG_AGO + 60)
    fixed = scan(s, [str(folder)])

    assert [f.outcome for f in failed.files] == [WatchOutcome.FAILED]
    assert unchanged.files == []
    assert [f.outcome for f in fixed.files] == [WatchOutcome.IMPORTED]
    recorded = s.catalog.watched_file(str(path))
    assert recorded is not None and recorded.outcome is WatchOutcome.IMPORTED


def test_scan_leaves_files_still_being_written(folder: Path):
    """A file changed in the last 10 seconds is left for later.

    Given: a ride written 3 seconds ago and one long ago, and a missing folder.
    Expect: only the old one imported; the new one counted and handed on; nothing recorded
    for it.
    """
    s = stores()
    now = time.time()
    young = drop(folder, ZWIFT, mtime=now - 3)
    drop(folder, INTERVALS)
    later: list[Path] = []

    result = scan(
        s, [str(folder), "/no/such/folder"], now=lambda: now, on_young=lambda p, _: later.append(p)
    )

    assert [Path(f.path).name for f in result.files] == [INTERVALS]
    assert (result.still_writing, later) == (1, [young])
    assert s.catalog.watched_file(str(young)) is None


# -- the watcher, step by step --------------------------------------------------------------


class FakeObserver:
    """Stands in for watchdog's observer: records which folders are watched."""

    def __init__(self) -> None:
        self.watched: dict[str, object] = {}
        self.started = self.stopped = False

    def schedule(self, handler, path: str, recursive: bool = False):
        """Watch a folder.

        Returns:
            A token for the watch.
        """
        watch = object()
        self.watched[path] = watch
        return watch

    def unschedule(self, watch) -> None:
        """Stop a watch."""
        self.watched = {p: w for p, w in self.watched.items() if w is not watch}

    def start(self) -> None:
        """Start delivering events."""
        self.started = True

    def stop(self) -> None:
        """Stop delivering events."""
        self.stopped = True

    def is_alive(self) -> bool:
        """Whether its thread runs.

        Returns:
            Never: it has none.
        """
        return False


class Clock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        """Read the clock.

        Returns:
            The time set by the test.
        """
        return self.now


class Harness:
    """A watcher over in-memory stores, with a fake observer and clock, counting opens."""

    def __init__(self, folder: Path) -> None:
        self.stores = stores()
        self.opens = 0
        self.observer = FakeObserver()
        self.clock = Clock()
        self.folder = folder
        self.stores.catalog.add_watch_folder(WatchFolder(str(folder), datetime.now(UTC)))
        self.watcher = Watcher(
            self.open,
            observer=lambda: self.observer,  # type: ignore[arg-type,return-value]
            clock=self.clock,
            now=lambda: LONG_AGO + 3600,
            stable_s=10,
            rescan_s=600,
            refresh_s=30,
        )

    @contextmanager
    def open(self) -> Iterator[Stores]:
        """Open the stores, counting each time.

        Yields:
            The same in-memory stores.
        """
        self.opens += 1
        yield self.stores

    def at(self, seconds: float) -> list[str]:
        """Move the clock on and do one pass.

        Args:
            seconds: Seconds after the start.

        Returns:
            The names of the files imported (or tried) in the pass.
        """
        self.clock.now = 1000.0 + seconds
        return [Path(f.path).name for f in self.watcher.step()]


def test_first_pass_watches_folders_and_catches_up(folder: Path):
    """The first pass starts watching each folder and imports what's already there.

    Given: a watched folder holding a ride.
    Expect: the folder watched, the ride imported, and the time of the import kept.
    """
    drop(folder, ZWIFT)
    h = Harness(folder)

    imported = h.at(0)

    assert imported == [ZWIFT]
    assert list(h.observer.watched) == [str(folder)]
    assert h.watcher.status(str(folder)).state is FolderState.WATCHING
    assert h.watcher.last_import is not None


def test_a_new_file_is_imported_once_it_settles(folder: Path):
    """A file is imported once it has stopped changing for 10 seconds.

    Given: a watched folder; a file noticed at 5 s, still growing at 8 s, then unchanged.
    Expect: nothing until 18 s (10 s after it last changed), then the ride.
    """
    h = Harness(folder)
    h.at(0)
    path = drop(folder, INTERVALS, mtime=LONG_AGO + 3500)

    h.watcher.notice(path, str(folder))
    first_look = h.at(5)
    with path.open("ab") as f:
        f.write(b"\0")  # still being written
    still_growing = h.at(8)
    too_soon = h.at(17)
    settled = h.at(18)

    assert (first_look, still_growing, too_soon) == ([], [], [])
    assert settled == [INTERVALS]
    assert h.watcher.waiting == 0


def test_idle_passes_leave_the_library_closed(folder: Path):
    """Passes with nothing to do don't open the library.

    Given: a first pass, then passes every second for 20 s with nothing new.
    Expect: the library opened only for the first pass.
    """
    h = Harness(folder)
    h.at(0)

    for second in range(1, 21):
        h.at(second)

    assert h.opens == 1


def test_ignored_and_removed_files(folder: Path):
    """Unwanted files are never waited for; a file deleted while settling is forgotten.

    Given: Zwift's in-progress file noticed; a ride noticed then deleted.
    Expect: nothing waiting after the next passes, and nothing imported.
    """
    h = Harness(folder)
    h.at(0)
    progress = drop(folder, ZWIFT, "inProgressActivity.fit")
    ride = drop(folder, INTERVALS)

    h.watcher.notice(progress, str(folder))
    h.watcher.notice(ride, str(folder))
    ride.unlink()
    passes = [h.at(1), h.at(20)]

    assert passes == [[], []]
    assert h.watcher.waiting == 0


def test_a_missing_folder_is_watched_again_when_it_comes_back(folder: Path, tmp_path: Path):
    """A folder that disappears is reported missing and watched again when it's back.

    Given: a watched folder that's moved away, then moved back with a ride in it.
    Expect: missing and unwatched after the next refresh; then watching, with the ride
    imported, after the one after.
    """
    h = Harness(folder)
    h.at(0)
    away = tmp_path / "away"

    folder.rename(away)
    h.at(30)
    missing = h.watcher.status(str(folder)).state
    unwatched = dict(h.observer.watched)
    away.rename(folder)
    drop(folder, ZWIFT)
    back = h.at(60)

    assert missing is FolderState.MISSING
    assert unwatched == {}
    assert back == [ZWIFT]
    assert h.watcher.status(str(folder)).state is FolderState.WATCHING


def test_folders_added_and_removed_are_picked_up(folder: Path, tmp_path: Path):
    """Asking for a refresh picks up folders added or removed since.

    Given: a second folder (holding a ride) added, then the first removed.
    Expect: the second watched and its ride imported at once; then only the second watched.
    """
    h = Harness(folder)
    h.at(0)
    second = tmp_path / "Garmin"
    second.mkdir()
    drop(second, INTERVALS)

    h.stores.catalog.add_watch_folder(WatchFolder(str(second), datetime.now(UTC)))
    h.watcher.request_refresh()
    added = h.at(1)
    h.stores.catalog.remove_watch_folder(str(folder))
    h.watcher.request_refresh()
    h.at(2)

    assert added == [INTERVALS]
    assert list(h.observer.watched) == [str(second)]


def test_scan_on_request_and_every_ten_minutes(folder: Path):
    """Folders are scanned again when asked, and 10 minutes after the last full scan.

    Given: a ride dropped in without an event and a scan asked for at 1 s; another ride
    dropped in.
    Expect: the first imported on request; the second not at 600 s, but at 601 s, 10 minutes
    after the requested scan.
    """
    h = Harness(folder)
    h.at(0)

    drop(folder, ZWIFT)
    h.watcher.request_scan()
    on_request = h.at(1)
    drop(folder, INTERVALS)
    before = h.at(600)
    rescan = h.at(601)

    assert (on_request, before, rescan) == ([ZWIFT], [], [INTERVALS])


# -- the real thing -------------------------------------------------------------------------


def test_watcher_imports_a_file_dropped_into_a_folder(folder: Path):
    """With the real file watcher, a file copied in is imported soon after it settles.

    Given: a running watcher (settling after 0.3 s) over a watched folder, and a ride copied
    in.
    Expect: the ride in the library within 10 seconds; the watcher stops cleanly.
    """
    s = stores()
    s.catalog.add_watch_folder(WatchFolder(str(folder), datetime.now(UTC)))

    @contextmanager
    def open_stores() -> Iterator[Stores]:
        yield s

    watcher = Watcher(open_stores, stable_s=0.3, tick_s=0.05)
    watcher.start()
    try:
        deadline = time.monotonic() + 10
        while watcher.status(str(folder)).state is not FolderState.WATCHING:
            assert time.monotonic() < deadline, "the folder should be watched"
            time.sleep(0.05)
        time.sleep(0.2)  # let the first pass finish before the file arrives
        shutil.copyfile(FIT_DIR / ZWIFT, folder / ZWIFT)
        while s.catalog.count() == 0:
            assert time.monotonic() < deadline, "the ride should be imported"
            time.sleep(0.05)
    finally:
        watcher.stop()

    recorded = s.catalog.watched_file(str(folder / ZWIFT))
    assert recorded is not None and recorded.outcome is WatchOutcome.IMPORTED


def test_watcher_can_be_started_again_after_stopping(folder: Path):
    """A stopped watcher can be started again (as when the app's lifespan runs twice).

    Given: a real watcher started and stopped, then started again with a ride copied in.
    Expect: the ride imported the second time round.
    """
    s = stores()
    s.catalog.add_watch_folder(WatchFolder(str(folder), datetime.now(UTC)))

    @contextmanager
    def open_stores() -> Iterator[Stores]:
        yield s

    watcher = Watcher(open_stores, stable_s=0.3, tick_s=0.05)
    watcher.start()
    watcher.stop()
    drop(folder, ZWIFT)
    watcher.start()
    try:
        deadline = time.monotonic() + 10
        while s.catalog.count() == 0:
            assert time.monotonic() < deadline, "the ride should be imported after a restart"
            time.sleep(0.05)
    finally:
        watcher.stop()
