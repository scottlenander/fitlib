"""Watched folders: their state, the files seen in them, and scans."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from fitlib.models import WatchedFile, WatchOutcome
from fitlib.services.watching import (
    FolderState,
)


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
