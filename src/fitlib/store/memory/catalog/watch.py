"""Watched folders and the files seen in them."""

from __future__ import annotations

from fitlib.models import (
    WatchedFile,
    WatchFolder,
    WatchOutcome,
)
from fitlib.store.memory.catalog.base import _Base


class _Watch(_Base):
    """Watched folders and the files seen in them."""

    def watch_folders(self) -> list[WatchFolder]:
        """List the watched folders.

        Returns:
            Every watched folder, by path.
        """
        return [self._watch_folders[p] for p in sorted(self._watch_folders)]

    def add_watch_folder(self, folder: WatchFolder) -> bool:
        """Start watching a folder.

        Args:
            folder: The folder, with its absolute path.

        Returns:
            ``False`` if it was already watched (nothing changes).
        """
        if folder.path in self._watch_folders:
            return False
        self._watch_folders[folder.path] = folder
        return True

    def remove_watch_folder(self, path: str) -> bool:
        """Stop watching a folder, forgetting the files found in it.

        Args:
            path: The folder's path, as added.

        Returns:
            ``False`` if it wasn't watched.
        """
        if self._watch_folders.pop(path, None) is None:
            return False
        self._watched = {k: v for k, v in self._watched.items() if v.folder != path}
        return True

    def watched_file(self, path: str) -> WatchedFile | None:
        """Look up a file found in a watched folder.

        Args:
            path: The file's absolute path.

        Returns:
            What was recorded for it, or ``None`` if it has never been imported.
        """
        return self._watched.get(path)

    def record_watched_file(self, file: WatchedFile) -> None:
        """Record what importing a watched file did, replacing anything recorded before.

        Args:
            file: The file, its size and modification time, and the outcome.
        """
        self._watched.pop(file.path, None)  # to the end: recorded last
        self._watched[file.path] = file

    def recent_watched_files(self, limit: int = 20) -> list[WatchedFile]:
        """List the latest files from watched folders that weren't already in the library.

        Args:
            limit: The most files to list.

        Returns:
            Imported, skipped and failed files, newest first (duplicates are left out: the
            first scan of an existing folder finds hundreds).
        """
        # Latest recorded first, then newest first (the sort keeps that order for ties).
        files = [
            f for f in reversed(self._watched.values()) if f.outcome is not WatchOutcome.DUPLICATE
        ]
        files.sort(key=lambda f: f.seen_at, reverse=True)
        return files[:limit]

    def watched_file_counts(self) -> dict[str, int]:
        """Count the files found in each watched folder.

        Returns:
            Files recorded per folder path; folders with none are left out.
        """
        counts: dict[str, int] = {}
        for file in self._watched.values():
            counts[file.folder] = counts.get(file.folder, 0) + 1
        return counts
