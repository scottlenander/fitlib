"""Watched folders and the files seen in them."""

from __future__ import annotations

import sqlite3

from fitlib.models import (
    WatchedFile,
    WatchFolder,
    WatchOutcome,
)
from fitlib.store.local.catalog.base import (
    _Base,
    _dt,
    _ts,
)


def _watched(row: sqlite3.Row) -> WatchedFile:
    """Build a watched file from its row.

    Args:
        row: A ``watch_files`` row.

    Returns:
        The watched file.
    """
    return WatchedFile(
        path=row["path"],
        folder=row["folder"],
        size=row["size"],
        mtime_ns=row["mtime_ns"],
        outcome=WatchOutcome(row["outcome"]),
        detail=row["detail"],
        ride_id=row["ride_id"],
        seen_at=_dt(row["seen_at"]),
    )


class _Watch(_Base):
    """Watched folders and the files seen in them."""

    def watch_folders(self) -> list[WatchFolder]:
        """List the watched folders.

        Returns:
            Every watched folder, by path.
        """
        with self._lock:
            rows = self._db.execute("SELECT * FROM watch_folders ORDER BY path").fetchall()
        return [WatchFolder(r["path"], _dt(r["added_at"])) for r in rows]

    def add_watch_folder(self, folder: WatchFolder) -> bool:
        """Start watching a folder.

        Args:
            folder: The folder, with its absolute path.

        Returns:
            ``False`` if it was already watched (nothing changes).
        """
        with self._tx() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO watch_folders (path, added_at) VALUES (?, ?)",
                (folder.path, _ts(folder.added_at)),
            )
        return cursor.rowcount == 1

    def remove_watch_folder(self, path: str) -> bool:
        """Stop watching a folder, forgetting the files found in it.

        Args:
            path: The folder's path, as added.

        Returns:
            ``False`` if it wasn't watched.
        """
        with self._tx() as db:
            cursor = db.execute("DELETE FROM watch_folders WHERE path = ?", (path,))
            db.execute("DELETE FROM watch_files WHERE folder = ?", (path,))
        return cursor.rowcount == 1

    def watched_file(self, path: str) -> WatchedFile | None:
        """Look up a file found in a watched folder.

        Args:
            path: The file's absolute path.

        Returns:
            What was recorded for it, or ``None`` if it has never been imported.
        """
        with self._lock:
            row = self._db.execute("SELECT * FROM watch_files WHERE path = ?", (path,)).fetchone()
        return _watched(row) if row else None

    def record_watched_file(self, file: WatchedFile) -> None:
        """Record what importing a watched file did, replacing anything recorded before.

        Args:
            file: The file, its size and modification time, and the outcome.
        """
        with self._tx() as db:
            db.execute(
                "INSERT OR REPLACE INTO watch_files "
                "(path, folder, size, mtime_ns, outcome, detail, ride_id, seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    file.path,
                    file.folder,
                    file.size,
                    file.mtime_ns,
                    file.outcome.value,
                    file.detail,
                    file.ride_id,
                    _ts(file.seen_at),
                ),
            )

    def recent_watched_files(self, limit: int = 20) -> list[WatchedFile]:
        """List the latest files from watched folders that weren't already in the library.

        Args:
            limit: The most files to list.

        Returns:
            Imported, skipped and failed files, newest first (duplicates are left out: the
            first scan of an existing folder finds hundreds).
        """
        with self._lock:
            rows = self._db.execute(
                # Within a second, the one recorded last first (a replaced row gets a new rowid).
                "SELECT * FROM watch_files WHERE outcome != 'duplicate' "
                "ORDER BY seen_at DESC, rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_watched(r) for r in rows]

    def watched_file_counts(self) -> dict[str, int]:
        """Count the files found in each watched folder.

        Returns:
            Files recorded per folder path; folders with none are left out.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT folder, COUNT(*) AS n FROM watch_files GROUP BY folder"
            ).fetchall()
        return {r["folder"]: r["n"] for r in rows}
