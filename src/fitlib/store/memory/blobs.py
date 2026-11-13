from __future__ import annotations

from fitlib.store.interfaces import BlobNotFound, validate_key


class MemoryBlobStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._blobs[validate_key(key)] = bytes(data)

    def get(self, key: str) -> bytes:
        try:
            return self._blobs[validate_key(key)]
        except KeyError:
            raise BlobNotFound(key) from None

    def exists(self, key: str) -> bool:
        return validate_key(key) in self._blobs

    def delete(self, key: str) -> None:
        self._blobs.pop(validate_key(key), None)

    def list(self, prefix: str = "") -> list[str]:
        return sorted(k for k in self._blobs if k.startswith(prefix))
