"""Watched folders: new rides in them are imported while the server runs.

The folders belong to this computer, so the API takes and shows full local paths. The app has
no login and listens only on this computer by default.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from fitlib.api.deps import ConfigDep, StoresDep
from fitlib.models import WatchedFile, WatchOutcome
from fitlib.services.watching import (
    AlreadyWatched,
    FolderState,
    NotWatched,
    Watcher,
    check_folder,
    scan,
    suggested_folders,
    watch_folder,
)
from fitlib.store.factory import Stores

router = APIRouter(prefix="/watch", tags=["watch"])

RECENT = 20


class WatchFolderOut(BaseModel):
    """A watched folder.

    Attributes:
        path: Its full path.
        state: ``watching``; ``missing`` (not there now: watched again when it's back);
            ``error`` (see ``message``); or ``stopped`` (the server isn't watching, e.g.
            started with ``--no-watch``).
        message: What went wrong, for an error.
        files: How many files have been found in it.
    """

    path: str
    state: FolderState
    message: str | None
    files: int


class WatchedFileOut(BaseModel):
    """A file found in a watched folder, and what importing it did.

    Attributes:
        path: Its full path.
        name: Its file name.
        folder: The watched folder it was in.
        outcome: ``imported``, ``duplicate``, ``skipped`` or ``failed``.
        detail: Why it was skipped or failed; for a zip, how many files had each outcome.
        ride_id: The ride it became (for a zip, the first), if imported.
        ride_deleted: The ride it became has been deleted since.
        seen_at: When it was imported, UTC.
    """

    path: str
    name: str
    folder: str
    outcome: WatchOutcome
    detail: str | None
    ride_id: str | None
    ride_deleted: bool = False
    seen_at: datetime


class WatchStatus(BaseModel):
    """The watched folders and what was found in them lately.

    Attributes:
        running: Whether the server is watching (it isn't with ``--no-watch``).
        folders: The watched folders, by path.
        recent: The latest files that weren't already in the library, newest first.
        waiting: Files waiting to stop changing before they're imported.
        last_import: When the watcher last imported a ride, if it has since the server
            started: the browser app checks this to refresh its lists.
        suggestions: Usual ride folders on this computer not watched yet (Zwift's
            Activities folder, a plugged-in Garmin), offered as one-click additions.
    """

    running: bool
    folders: list[WatchFolderOut]
    recent: list[WatchedFileOut]
    waiting: int
    last_import: datetime | None
    suggestions: list[str]


class FolderIn(BaseModel):
    """A folder to watch.

    Attributes:
        path: Its full path; ``~`` stands for your home folder.
    """

    model_config = ConfigDict(extra="forbid")

    path: str


class ScanOut(BaseModel):
    """What scanning the watched folders did.

    Attributes:
        background: The server's watcher will scan shortly (the counts are then 0); without
            one, the scan was done before answering.
        imported: Files imported.
        duplicates: Files already in the library.
        skipped: Files left out (not rides, or second recordings).
        failed: Files that couldn't be read.
        still_writing: Files changed in the last few seconds, left for later.
    """

    background: bool
    imported: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0
    still_writing: int = 0


def _watcher(request: Request) -> Watcher | None:
    return request.app.state.watcher


def _file(file: WatchedFile, rides: set[str]) -> WatchedFileOut:
    deleted = file.ride_id is not None and file.ride_id not in rides
    return WatchedFileOut(
        path=file.path,
        name=Path(file.path).name,
        folder=file.folder,
        outcome=file.outcome,
        detail=file.detail,
        ride_id=None if deleted else file.ride_id,
        ride_deleted=deleted,
        seen_at=file.seen_at,
    )


def _folder(path: str, watcher: Watcher | None, counts: dict[str, int]) -> WatchFolderOut:
    if watcher is not None:
        status = watcher.status(path)
        state, message = status.state, status.message
    else:
        state = FolderState.STOPPED if Path(path).is_dir() else FolderState.MISSING
        message = None
    return WatchFolderOut(path=path, state=state, message=message, files=counts.get(path, 0))


def _status(stores: Stores, watcher: Watcher | None, root: Path | None) -> WatchStatus:
    catalog = stores.catalog
    counts = catalog.watched_file_counts()
    folders = catalog.watch_folders()
    recent = catalog.recent_watched_files(RECENT)
    rides = set(catalog.ride_ids()) if any(f.ride_id for f in recent) else set()
    return WatchStatus(
        running=watcher is not None,
        folders=[_folder(f.path, watcher, counts) for f in folders],
        recent=[_file(f, rides) for f in recent],
        waiting=watcher.waiting if watcher is not None else 0,
        last_import=watcher.last_import if watcher is not None else None,
        suggestions=suggested_folders({f.path for f in folders}, root),
    )


@router.get("")
def get_watch(request: Request, stores: StoresDep) -> WatchStatus:
    """Show the watched folders and the latest files found in them.

    Args:
        request: The request (for the server's watcher).
        stores: The library's stores.

    Returns:
        The folders with their state, recent files, and when a ride was last imported.
    """
    return _status(stores, _watcher(request), request.app.state.watch_root)


@router.post("/folders", status_code=201)
def add_folder(
    request: Request, stores: StoresDep, config: ConfigDep, body: FolderIn
) -> WatchFolderOut:
    """Start watching a folder; what's already in it is imported shortly.

    Args:
        request: The request (for the server's watcher).
        stores: The library's stores.
        config: The config (for the library folder, which can't be watched).
        body: The folder.

    Returns:
        The folder as stored, with its state.

    Raises:
        BadWatchFolder: Not a full path to a folder, or the library's own (422).
        AlreadyWatched: The folder is already watched (409).
    """
    path = check_folder(body.path, config.library, request.app.state.watch_root)
    if not stores.catalog.add_watch_folder(watch_folder(path)):
        raise AlreadyWatched(str(path))
    watcher = _watcher(request)
    if watcher is not None:
        watcher.request_refresh()
    return _folder(str(path), watcher, {})


@router.delete("/folders", status_code=204)
def remove_folder(request: Request, stores: StoresDep, path: str) -> Response:
    """Stop watching a folder. Rides already imported from it stay in the library.

    Args:
        request: The request (for the server's watcher).
        stores: The library's stores.
        path: The folder, as listed.

    Returns:
        An empty 204 response.

    Raises:
        NotWatched: The folder isn't watched (404).
    """
    if not stores.catalog.remove_watch_folder(path):
        raise NotWatched(path)
    watcher = _watcher(request)
    if watcher is not None:
        watcher.request_refresh()
    return Response(status_code=204)


@router.post("/scan")
def scan_folders(request: Request, stores: StoresDep) -> ScanOut:
    """Look for new files in every watched folder now.

    With the server's watcher running, it scans in the background; otherwise the scan is
    done before answering.

    Args:
        request: The request (for the server's watcher).
        stores: The library's stores.

    Returns:
        Whether it runs in the background, or what the scan did.
    """
    watcher = _watcher(request)
    if watcher is not None:
        watcher.request_scan()
        return ScanOut(background=True)
    result = scan(stores, [f.path for f in stores.catalog.watch_folders()])

    def count(outcome: Literal["imported", "duplicate", "skipped", "failed"]) -> int:
        return sum(1 for f in result.files if f.outcome == outcome)

    return ScanOut(
        background=False,
        imported=count("imported"),
        duplicates=count("duplicate"),
        skipped=count("skipped"),
        failed=count("failed"),
        still_writing=result.still_writing,
    )
