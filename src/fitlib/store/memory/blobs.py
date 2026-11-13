"""In-memory blob store for tests. Behaves exactly like the filesystem store."""

from __future__ import annotations

from fitlib.store.interfaces import BlobNotFound, validate_key


class MemoryBlobStore:
    """Blobs in a dict, for tests. Behaves like ``FsBlobStore``."""

    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        """Store bytes under a key, replacing any existing blob atomically.

        Args:
            key: Where to store them.
            data: The bytes.
        """
        self._blobs[validate_key(key)] = bytes(data)

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
            return self._blobs[validate_key(key)]
        except KeyError:
            raise BlobNotFound(key) from None

    def exists(self, key: str) -> bool:
        """Check whether a blob is stored.

        Args:
            key: The blob's key.

        Returns:
            ``True`` if something is stored under the key.
        """
        return validate_key(key) in self._blobs

    def delete(self, key: str) -> None:
        """Remove a blob, if present.

        Args:
            key: The blob's key.
        """
        self._blobs.pop(validate_key(key), None)

    def list(self, prefix: str = "") -> list[str]:
        """List stored keys.

        Args:
            prefix: Only keys starting with this; all keys by default.

        Returns:
            The matching keys, sorted.
        """
        return sorted(k for k in self._blobs if k.startswith(prefix))
