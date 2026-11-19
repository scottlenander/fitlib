"""Watching folders for new rides while the server runs.

New or changed ``.fit`` and ``.zip`` files in a watched folder are imported once they have
stopped changing for ``STABLE_S`` seconds, so a file still being written is never read half
done. Folders are also scanned when the watcher starts (for files added while it was off) and
every ``RESCAN_S`` as a safety net; files already imported with the same size and
modification time are skipped without being read. A folder that disappears (an unplugged
Garmin, a renamed folder) is reported missing and watched again when it comes back.

Everything happens on one background thread, with its own stores, so imports never run two at
a time. File system events (from ``watchdog``) only note which files to look at.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver, ObservedWatch

from fitlib.importer import Importer, ImportReport
from fitlib.models import WatchedFile, WatchFolder, WatchOutcome
from fitlib.store.factory import Stores

log = logging.getLogger(__name__)

# How long a file must stay the same size and age before it's imported.
STABLE_S = 10.0
# How often every folder is scanned in full, in case an event was missed.
RESCAN_S = 600.0
# How often the folder list is read again (folders added from the command line) and missing
# folders are looked for.
REFRESH_S = 30.0
# How often the background thread wakes up to look at files waiting to settle.
TICK_S = 1.0

SUFFIXES = (".fit", ".zip")
# Zwift rewrites this file all through a ride; the finished ride gets its own file.
IGNORED_NAMES = ("inprogressactivity.fit",)

OpenStores = Callable[[], AbstractContextManager[Stores]]


class BadWatchFolder(ValueError):
    """A folder that can't be watched: not a full path, not a folder, or the library's own."""


class NotWatched(LookupError):
    """A folder that isn't being watched."""

    def __init__(self, path: str):
        """Name the folder in the message.

        Args:
            path: The folder asked about.
        """
        super().__init__(f"{path} isn't a watched folder")


class AlreadyWatched(ValueError):
    """A folder that's already being watched."""

    def __init__(self, path: str):
        """Name the folder in the message.

        Args:
            path: The folder asked about.
        """
        super().__init__(f"{path} is already watched")


class FolderState(StrEnum):
    """Where a watched folder stands."""

    WATCHING = "watching"
    MISSING = "missing"
    ERROR = "error"
    # The server was started with --no-watch, or this is the command line.
    STOPPED = "stopped"


@dataclass(frozen=True)
class FolderStatus:
    """A watched folder and whether it's being watched.

    Attributes:
        path: The folder's path.
        state: Watching, missing, an error, or not watched at the moment.
        message: What went wrong, for an error.
    """

    path: str
    state: FolderState
    message: str | None = None


@dataclass(frozen=True)
class FileState:
    """What says whether a file has changed.

    Attributes:
        size: Size in bytes.
        mtime_ns: Modification time, in nanoseconds since 1970.
    """

    size: int
    mtime_ns: int


@dataclass(frozen=True)
class ScanResult:
    """What a scan of the watched folders did.

    Attributes:
        files: The files imported (or tried), in the order they were found.
        still_writing: Files left for later because they changed in the last ``STABLE_S``.
    """

    files: list[WatchedFile]
    still_writing: int


# Where ride files usually land, offered as one-click folders to watch when they exist.
SUGGESTED = (
    "~/Documents/Zwift/Activities",
    "/Volumes/GARMIN/Garmin/Activities",
)


def suggested_folders(watched: set[str], allowed_root: Path | None = None) -> list[str]:
    """Usual ride folders that exist on this computer and aren't watched yet.

    Args:
        watched: The watched folders' paths.
        allowed_root: If given, only folders inside it (e2e mode).

    Returns:
        Their resolved paths, in ``SUGGESTED`` order.
    """
    found = []
    for raw in SUGGESTED:
        path = Path(raw).expanduser()
        if not path.is_dir():
            continue
        path = path.resolve()
        if str(path) in watched:
            continue
        if allowed_root is not None and not path.is_relative_to(allowed_root.resolve()):
            continue
        found.append(str(path))
    return found


def check_folder(raw: str, library: Path, allowed_root: Path | None = None) -> Path:
    """Check that a folder can be watched, and give its full path.

    Args:
        raw: The folder as typed; ``~`` is expanded.
        library: The library folder, which can't be watched (its archive holds .fit files).
        allowed_root: If given, the folder must be inside it (e2e mode keeps to the temp
            folder).

    Returns:
        The folder's absolute, resolved path.

    Raises:
        BadWatchFolder: The path isn't absolute, doesn't exist, isn't a folder, is or holds
            the library or is inside it, or is outside ``allowed_root``.
    """
    text = raw.strip()
    path = Path(text).expanduser()
    if not text or not path.is_absolute():
        raise BadWatchFolder(
            f"Give the folder's full path, e.g. ~/Documents/Zwift/Activities (got {raw!r})"
        )
    if not path.exists():
        raise BadWatchFolder(f"There's no folder at {path}")
    if not path.is_dir():
        raise BadWatchFolder(f"{path} is a file, not a folder")
    path = path.resolve()
    lib = library.expanduser().resolve()
    if path == lib or path.is_relative_to(lib) or lib.is_relative_to(path):
        raise BadWatchFolder(
            f"{path} holds fitlib's own library ({lib}), whose archive would be imported again"
        )
    if allowed_root is not None and not path.is_relative_to(allowed_root.resolve()):
        raise BadWatchFolder(f"Only folders inside {allowed_root} can be watched here")
    return path


def wanted(path: Path, folder: Path) -> bool:
    """Whether a file in a watched folder should be imported.

    Args:
        path: The file.
        folder: The watched folder it's in.

    Returns:
        ``True`` for ``.fit`` and ``.zip`` files, except Zwift's in-progress file, hidden
        files and anything in a hidden folder.
    """
    name = path.name.lower()
    if not name.endswith(SUFFIXES) or name in IGNORED_NAMES:
        return False
    try:
        parts = path.relative_to(folder).parts
    except ValueError:
        return False
    return not any(p.startswith(".") or p == "__MACOSX" for p in parts)


def candidates(folder: Path) -> Iterator[Path]:
    """The files in a watched folder that should be imported, searched recursively.

    Args:
        folder: The watched folder.

    Yields:
        Each wanted file, in name order folder by folder; hidden folders aren't entered.
    """
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__MACOSX")
        for name in sorted(files):
            path = Path(root) / name
            if wanted(path, folder):
                yield path


def file_state(path: Path) -> FileState | None:
    """Read a file's size and modification time.

    Args:
        path: The file.

    Returns:
        Its state, or ``None`` if it's gone (or can't be read).
    """
    try:
        info = path.stat()
    except OSError:
        return None
    return FileState(info.st_size, info.st_mtime_ns)


def _plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def summarize(report: ImportReport) -> tuple[WatchOutcome, str | None, str | None]:
    """Sum up what importing one file (or a zip of several) did.

    Args:
        report: The import's report.

    Returns:
        The outcome (imported if any file was, then duplicate, skipped, failed), a detail
        (the reason for one file; the counts for several) and a ride id (the first imported,
        or the one a single file duplicates).
    """
    groups = (
        (WatchOutcome.IMPORTED, report.imported, ("imported", "imported")),
        (WatchOutcome.DUPLICATE, report.duplicates, ("already in the library",) * 2),
        (WatchOutcome.SKIPPED, report.skipped, ("skipped", "skipped")),
        (WatchOutcome.FAILED, report.failed, ("couldn't be read", "couldn't be read")),
    )
    found = [(outcome, rows, words) for outcome, rows, words in groups if rows]
    if not found:
        return WatchOutcome.SKIPPED, "No .fit files inside", None
    outcome, rows, _ = found[0]
    if report.total > 1:
        detail = ", ".join(_plural(len(r), "file " + w[0], "files " + w[1]) for _, r, w in found)
    else:
        detail = None if outcome is WatchOutcome.IMPORTED else rows[0][1]
    ride_id = None
    if outcome is WatchOutcome.IMPORTED:
        ride_id = rows[0][1]
    elif outcome is WatchOutcome.DUPLICATE and report.total == 1:
        ride_id = rows[0][1] if len(rows[0][1]) == 36 else None  # an id, not "same as …"
    return outcome, detail, ride_id


def import_file(stores: Stores, path: Path, folder: str, state: FileState) -> WatchedFile:
    """Import one file from a watched folder and record what happened.

    Args:
        stores: The library's stores.
        path: The file.
        folder: The watched folder it's in.
        state: Its size and modification time, read just before.

    Returns:
        The record, also saved in the catalog.
    """
    importer = Importer(stores.catalog, stores.blobs, stores.streams, workers=1)
    try:
        report = importer.run([path])
    except FileNotFoundError:
        report = ImportReport(failed=[(path.name, "The file was removed before it was read")])
    outcome, detail, ride_id = summarize(report)
    record = WatchedFile(
        path=str(path),
        folder=folder,
        size=state.size,
        mtime_ns=state.mtime_ns,
        outcome=outcome,
        detail=detail,
        ride_id=ride_id,
        # Whole seconds, as stored, so the watcher's last import matches the stored files.
        seen_at=datetime.now(UTC).replace(microsecond=0),
    )
    stores.catalog.record_watched_file(record)
    log.info("Watched folder: %s %s", path.name, outcome.value)
    return record


def unchanged(stores: Stores, path: Path, state: FileState) -> bool:
    """Whether a file was already imported and hasn't changed since.

    Args:
        stores: The library's stores.
        path: The file.
        state: Its size and modification time now.

    Returns:
        ``True`` if its record has the same size and modification time.
    """
    seen = stores.catalog.watched_file(str(path))
    return seen is not None and (seen.size, seen.mtime_ns) == (state.size, state.mtime_ns)


def scan(
    stores: Stores,
    folders: list[str],
    stable_s: float = STABLE_S,
    now: Callable[[], float] = time.time,
    on_young: Callable[[Path, str], None] | None = None,
) -> ScanResult:
    """Import every new or changed file in some watched folders.

    Files changed in the last ``stable_s`` seconds may still be being written: they're left
    for later (handed to ``on_young``, if given).

    Args:
        stores: The library's stores.
        folders: The watched folders' paths; missing ones are passed over.
        stable_s: How long a file must have been unchanged to be imported.
        now: The time, in seconds since 1970.
        on_young: Told about each file left for later, and its folder.

    Returns:
        What was imported, and how many files were left for later.
    """
    files: list[WatchedFile] = []
    young = 0
    for folder in folders:
        root = Path(folder)
        if not root.is_dir():
            continue
        for path in candidates(root):
            state = file_state(path)
            if state is None or unchanged(stores, path, state):
                continue
            if now() - state.mtime_ns / 1e9 < stable_s:
                young += 1
                if on_young is not None:
                    on_young(path, folder)
                continue
            files.append(import_file(stores, path, folder, state))
    return ScanResult(files, young)


class _Events(FileSystemEventHandler):
    """Passes file events in one watched folder on to the watcher."""

    def __init__(self, watcher: Watcher, folder: str):
        self._watcher = watcher
        self._folder = folder

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory or event.event_type not in ("created", "modified", "moved", "closed"):
            return
        raw = event.dest_path if event.event_type == "moved" else event.src_path
        path = Path(os.fsdecode(raw))
        self._watcher.notice(path, self._folder)


@dataclass
class _Pending:
    folder: str
    state: FileState | None
    since: float


class Watcher:
    """Watches the library's watched folders and imports new rides, on a background thread.

    Args:
        open_stores: Opens the library's stores (each pass gets its own).
        observer: Makes what delivers file system events (a new one each time the watcher
            starts, as one can only run once); ``watchdog``'s for this system by default.
        clock: Seconds, for timing (monotonic).
        now: Seconds since 1970, for comparing with modification times.
        stable_s: How long a file must stay unchanged before it's imported.
        rescan_s: How often every folder is scanned in full.
        refresh_s: How often the folder list is read again and missing folders looked for.
        tick_s: How often the thread wakes to look at files waiting to settle.
    """

    def __init__(
        self,
        open_stores: OpenStores,
        observer: Callable[[], BaseObserver] = Observer,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], float] = time.time,
        stable_s: float = STABLE_S,
        rescan_s: float = RESCAN_S,
        refresh_s: float = REFRESH_S,
        tick_s: float = TICK_S,
    ) -> None:
        self._open = open_stores
        self._make_observer = observer
        self._observer = observer()
        self._started = False
        self._clock = clock
        self._now = now
        self._stable_s = stable_s
        self._rescan_s = rescan_s
        self._refresh_s = refresh_s
        self._tick_s = tick_s
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: dict[str, _Pending] = {}
        self._watches: dict[str, ObservedWatch] = {}
        self._states: dict[str, FolderStatus] = {}
        self._scan_all = True
        self._scan_folders: set[str] = set()
        self._refresh_now = True
        self._next_refresh = 0.0
        self._next_rescan = 0.0
        self._last_import: datetime | None = None

    # -- control ------------------------------------------------------------------------------

    def start(self) -> None:
        """Start watching, on a background thread; the first pass scans every folder."""
        if self._started:  # started before and stopped: begin again from scratch
            self._observer = self._make_observer()
            self._watches.clear()
            with self._lock:
                self._states.clear()
                self._scan_all = self._refresh_now = True
            self._stopping.clear()
        self._started = True
        self._observer.start()
        self._thread = threading.Thread(target=self._run, name="fitlib-watcher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        """Stop watching, after any import in progress finishes.

        Args:
            timeout: Longest to wait for the thread to finish.
        """
        self._stopping.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)
        self._observer.stop()
        if self._observer.is_alive():
            self._observer.join(timeout)

    def request_refresh(self) -> None:
        """Read the folder list again soon (a folder was added or removed)."""
        with self._lock:
            self._refresh_now = True
        self._wake.set()

    def request_scan(self, folder: str | None = None) -> None:
        """Scan soon, for files added while nothing was watching.

        Args:
            folder: One folder to scan; every folder if ``None``.
        """
        with self._lock:
            if folder is None:
                self._scan_all = True
            else:
                self._scan_folders.add(folder)
        self._wake.set()

    def notice(self, path: Path, folder: str) -> None:
        """Note a file that was created or changed, to import once it settles.

        Args:
            path: The file.
            folder: The watched folder it's in.
        """
        if not wanted(path, Path(folder)):
            return
        with self._lock:
            # Any change starts its wait again.
            self._pending[str(path)] = _Pending(folder, None, self._clock())

    # -- what it's doing ----------------------------------------------------------------------

    def status(self, path: str) -> FolderStatus:
        """Say whether a folder is being watched.

        Args:
            path: A watched folder's path.

        Returns:
            Its status; "missing" or "watching" for a folder not yet looked at.
        """
        with self._lock:
            known = self._states.get(path)
        if known is not None:
            return known
        state = FolderState.WATCHING if Path(path).is_dir() else FolderState.MISSING
        return FolderStatus(path, state)

    @property
    def waiting(self) -> int:
        """How many files are waiting to settle before they're imported."""
        with self._lock:
            return len(self._pending)

    @property
    def last_import(self) -> datetime | None:
        """When a file was last imported (UTC), if one has been since the watcher started."""
        with self._lock:
            return self._last_import

    # -- the background thread ----------------------------------------------------------------

    def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                self.step()
            except Exception:
                log.exception("Watched folders: a pass failed; trying again shortly")
            self._wake.wait(self._tick_s)
            self._wake.clear()

    def step(self) -> list[WatchedFile]:
        """Do one pass: refresh the folder list, scan if due, and import settled files.

        The library is only opened when there's something to do. Runs on the background
        thread; tests call it directly.

        Returns:
            The files imported (or tried) in this pass.
        """
        now = self._clock()
        ready = self._settled(now)
        with self._lock:
            refresh = self._refresh_now or now >= self._next_refresh
            self._refresh_now = False
            scan_due = self._scan_all or bool(self._scan_folders) or now >= self._next_rescan
        if not (refresh or scan_due or ready):
            return []
        done: list[WatchedFile] = []
        with self._open() as stores:
            if refresh:
                self._refresh(stores)
                self._next_refresh = now + self._refresh_s
            with self._lock:
                scan_all = self._scan_all or now >= self._next_rescan
                folders = set(self._scan_folders)
                self._scan_all = False
                self._scan_folders.clear()
            watched = sorted(self._watches)
            to_scan = watched if scan_all else sorted(folders & set(watched))
            if to_scan:
                result = scan(stores, to_scan, self._stable_s, self._now, self._wait_for)
                done += result.files
            if scan_all:
                self._next_rescan = now + self._rescan_s
            for path, folder, state in ready:
                if not unchanged(stores, path, state):
                    done.append(import_file(stores, path, folder, state))
        if any(f.outcome is WatchOutcome.IMPORTED for f in done):
            with self._lock:
                self._last_import = max(f.seen_at for f in done)
        return done

    def _wait_for(self, path: Path, folder: str) -> None:
        with self._lock:
            self._pending.setdefault(str(path), _Pending(folder, None, self._clock()))

    def _refresh(self, stores: Stores) -> None:
        """Watch the folders in the list, stop watching the rest, and note missing ones."""
        folders = {f.path: f for f in stores.catalog.watch_folders()}
        for path in [p for p in self._watches if p not in folders]:
            self._unwatch(path)
        with self._lock:
            for path in [p for p in self._states if p not in folders]:
                del self._states[path]
            self._pending = {k: v for k, v in self._pending.items() if v.folder in folders}
        for path in folders:
            self._attach(path)

    def _attach(self, path: str) -> None:
        if not Path(path).is_dir():
            if path in self._watches:
                self._unwatch(path)
            self._set(FolderStatus(path, FolderState.MISSING))
            return
        if path in self._watches:
            return
        try:
            self._watches[path] = self._observer.schedule(_Events(self, path), path, recursive=True)
        except OSError as exc:
            self._set(FolderStatus(path, FolderState.ERROR, str(exc)))
            return
        self._set(FolderStatus(path, FolderState.WATCHING))
        with self._lock:
            self._scan_folders.add(path)  # newly watched: catch up on what's there

    def _unwatch(self, path: str) -> None:
        watch = self._watches.pop(path, None)
        if watch is not None:
            # It may already be gone with its folder.
            with contextlib.suppress(KeyError, OSError):
                self._observer.unschedule(watch)

    def _set(self, status: FolderStatus) -> None:
        with self._lock:
            self._states[status.path] = status

    def _settled(self, now: float) -> list[tuple[Path, str, FileState]]:
        """Take the waiting files that have stopped changing.

        Args:
            now: The clock's time.

        Returns:
            Each settled file, its folder and its state, no longer waiting.
        """
        with self._lock:
            pending = dict(self._pending)
        ready: list[tuple[Path, str, FileState]] = []
        for key, item in pending.items():
            state = file_state(Path(key))
            with self._lock:
                if self._pending.get(key) is not item:
                    continue  # changed again meanwhile: its wait has started over
                if state is None:
                    del self._pending[key]  # deleted, or moved away
                elif state != item.state:
                    self._pending[key] = _Pending(item.folder, state, now)
                elif now - item.since >= self._stable_s:
                    del self._pending[key]
                    ready.append((Path(key), item.folder, state))
        return ready


def watch_folder(path: Path) -> WatchFolder:
    """A new watched folder, added now.

    Args:
        path: The folder's checked path (from ``check_folder``).

    Returns:
        The folder to store.
    """
    return WatchFolder(str(path), datetime.now(UTC))
