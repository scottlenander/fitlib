"""Blobs as files under a root directory. Keys map directly to relative paths."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fitlib.store.interfaces import BlobNotFound, validate_key


class FsBlobStore:
    """Blobs as plain files under a root folder; a key is the file's relative path.

    Args:
        root: The folder to keep blobs in. Created if missing.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        """The file a key maps to.

        Args:
            key: A blob key.

        Returns:
            The path under the root.

        Raises:
            InvalidBlobKey: The key isn't valid.
        """
        return self._root / validate_key(key)

    def put(self, key: str, data: bytes) -> None:
        """Store bytes under a key, replacing any existing blob atomically.

        Args:
            key: Where to store them.
            data: The bytes.
        """
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same folder, then rename: readers never see half a blob.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, key: str) -> bytes:
        """Read a blob.

        Args:
            key: The blob's key.

        Returns:
            The stored bytes.

        Raises:
            BlobNotFound: Nothing is stored under the key.
        """
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise BlobNotFound(key) from None

    def exists(self, key: str) -> bool:
        """Check whether a blob is stored.

        Args:
            key: The blob's key.

        Returns:
            ``True`` if something is stored under the key.
        """
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        """Remove a blob, if present.

        Args:
            key: The blob's key.
        """
        self._path(key).unlink(missing_ok=True)

    def list(self, prefix: str = "") -> list[str]:
        """List stored keys.

        Args:
            prefix: Only keys starting with this; all keys by default.

        Returns:
            The matching keys, sorted.
        """
        keys = (
            path.relative_to(self._root).as_posix()
            for path in self._root.rglob("*")
            if path.is_file() and not path.name.startswith(".tmp-")
        )
        return sorted(k for k in keys if k.startswith(prefix))
