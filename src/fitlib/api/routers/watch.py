"""Watched folders: new rides in them are imported while the server runs.

The folders belong to this computer, so the API takes and shows full local paths. The app has
no login and listens only on this computer by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request, Response

from fitlib.api.deps import ConfigDep, StoresDep
from fitlib.api.schemas.watch import (
    FolderIn,
    ScanOut,
    WatchFolderOut,
    WatchStatus,
    _file,
)
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


def _watcher(request: Request) -> Watcher | None:
    return request.app.state.watcher


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
