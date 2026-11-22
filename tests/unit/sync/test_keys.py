"""The keychain key store, against a stand-in keyring backend (never the real Keychain)."""

from __future__ import annotations

from collections.abc import Generator

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import NoKeyringError

from fitlib.sync.crypto import new_master_key
from fitlib.sync.keys import SERVICE, KeychainKeyStore, NoKeychain


class DictKeyring(KeyringBackend):
    """A keyring backend holding passwords in a dict."""

    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        """Read a password.

        Args:
            service: The service name.
            username: The account.

        Returns:
            The password, or ``None``.
        """
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        """Store a password.

        Args:
            service: The service name.
            username: The account.
            password: The password.
        """
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        """Remove a password.

        Args:
            service: The service name.
            username: The account.
        """
        self.passwords.pop((service, username), None)


class NoBackend(DictKeyring):
    """A keyring backend that isn't there, like Linux without a secret service."""

    def get_password(self, service: str, username: str) -> str | None:
        """Fail to read.

        Args:
            service: The service name.
            username: The account.

        Raises:
            NoKeyringError: Always.
        """
        raise NoKeyringError("No recommended backend was available")

    def set_password(self, service: str, username: str, password: str) -> None:
        """Fail to write.

        Args:
            service: The service name.
            username: The account.
            password: The password.

        Raises:
            NoKeyringError: Always.
        """
        raise NoKeyringError("No recommended backend was available")


@pytest.fixture
def backend() -> Generator[DictKeyring]:
    """Swap the keyring backend for a dict while the test runs.

    Yields:
        The stand-in backend.
    """
    previous = keyring.get_keyring()
    fake = DictKeyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(previous)


def test_key_round_trips_through_the_keychain(backend: DictKeyring):
    """A key put in the keychain comes back as the same bytes.

    Given: A random master key put for a library id.
    Expect: ``get`` returns it; it's kept under service ``fitlib`` as base64 text; another
        library id has none.
    """
    store = KeychainKeyStore()
    key = new_master_key()

    store.put("library-1", key)

    assert store.get("library-1") == key
    assert (SERVICE, "library-1") in backend.passwords
    assert key not in backend.passwords[(SERVICE, "library-1")].encode()
    assert store.get("library-2") is None


def test_missing_keychain_is_a_clear_error():
    """With no keyring backend, reads and writes raise ``NoKeychain``.

    Given: A backend that raises ``NoKeyringError``.
    Expect: ``NoKeychain`` from both ``get`` and ``put``.
    """
    previous = keyring.get_keyring()
    keyring.set_keyring(NoBackend())
    try:
        store = KeychainKeyStore()
        with pytest.raises(NoKeychain):
            store.get("library-1")
        with pytest.raises(NoKeychain):
            store.put("library-1", new_master_key())
    finally:
        keyring.set_keyring(previous)
