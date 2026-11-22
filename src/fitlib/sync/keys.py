"""Where each library's master key is kept on this computer: the macOS Keychain.

Behind a small protocol so tests (and CI, which has no Keychain) use an in-memory one.
"""

from __future__ import annotations

import base64
from typing import Protocol

from fitlib.sync.crypto import SyncError

SERVICE = "fitlib"


class NoKeychain(SyncError):
    """This computer has no keychain fitlib can use."""


class KeyStore(Protocol):
    """Master keys by library id."""

    def get(self, library_id: str) -> bytes | None:
        """Read a library's master key.

        Args:
            library_id: The library's id.

        Returns:
            The key, or ``None`` if this computer doesn't have it.
        """
        ...

    def put(self, library_id: str, key: bytes) -> None:
        """Keep a library's master key, replacing any kept before.

        Args:
            library_id: The library's id.
            key: The master key.
        """
        ...


class MemoryKeyStore:
    """Master keys in a dict, for tests."""

    def __init__(self) -> None:
        self.keys: dict[str, bytes] = {}

    def get(self, library_id: str) -> bytes | None:
        """Read a library's master key.

        Args:
            library_id: The library's id.

        Returns:
            The key, or ``None``.
        """
        return self.keys.get(library_id)

    def put(self, library_id: str, key: bytes) -> None:
        """Keep a library's master key.

        Args:
            library_id: The library's id.
            key: The master key.
        """
        self.keys[library_id] = key


class KeychainKeyStore:
    """Master keys in the system keychain (the macOS Keychain), via ``keyring``.

    Each is a generic password: service ``fitlib``, account the library id, value the key in
    base64.
    """

    def get(self, library_id: str) -> bytes | None:
        """Read a library's master key from the keychain.

        Args:
            library_id: The library's id.

        Returns:
            The key, or ``None`` if the keychain has none for this library.

        Raises:
            NoKeychain: There's no keychain to read.
        """
        import keyring
        from keyring.errors import KeyringError

        try:
            value = keyring.get_password(SERVICE, library_id)
        except KeyringError as exc:
            raise NoKeychain(f"Can't read the keychain: {exc}") from exc
        return base64.b64decode(value) if value else None

    def put(self, library_id: str, key: bytes) -> None:
        """Keep a library's master key in the keychain.

        Args:
            library_id: The library's id.
            key: The master key.

        Raises:
            NoKeychain: There's no keychain to write to.
        """
        import keyring
        from keyring.errors import KeyringError

        try:
            keyring.set_password(SERVICE, library_id, base64.b64encode(key).decode())
        except KeyringError as exc:
            raise NoKeychain(f"Can't save the key in the keychain: {exc}") from exc
