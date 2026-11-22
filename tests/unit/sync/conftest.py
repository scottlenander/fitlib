"""Fixtures for the sync tests: local libraries with the fixture rides, and sync folders."""

from __future__ import annotations

import shutil
from collections.abc import Generator
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pytest

from fitlib.config import Config
from fitlib.importer import Importer
from fitlib.store.factory import (
    Stores,
    latest_schema_version,
    library_blobs,
    open_remote,
    open_stores,
    restore_catalog,
    snapshot_catalog,
)
from fitlib.store.interfaces import BlobStore
from fitlib.sync.crypto import KdfParams
from fitlib.sync.engine import LocalLibrary, adopt, read_keyfile, restore, setup
from fitlib.sync.keys import MemoryKeyStore
from tests.fixtures.generate import FIT_DIR

# Small Argon2id settings so the tests run quickly; real keyfiles use the defaults.
FAST_KDF = KdfParams(memory_kib=1024, time_cost=1, parallelism=1)
PASSPHRASE = "correct horse battery"


def local(stores: Stores) -> LocalLibrary:
    """What a push reads from open stores, as the command line builds it.

    Args:
        stores: An open local library.

    Returns:
        The catalog, blobs, snapshot maker and schema version.
    """
    return LocalLibrary(
        stores.catalog, stores.blobs, partial(snapshot_catalog, stores), latest_schema_version()
    )


def restore_into(config: Config, remote: BlobStore, keystore: MemoryKeyStore) -> None:
    """Restore a sync folder's copy into an empty library, as the command line does.

    Args:
        config: The empty library.
        remote: The sync folder.
        keystore: This computer's keys; the library's key is added.
    """
    restored = restore(
        remote,
        read_keyfile(remote, PASSPHRASE),
        library_blobs(config),
        partial(restore_catalog, config),
        latest_schema_version(),
    )
    with open_stores(config) as stores:
        adopt(stores.catalog, keystore, restored)


@dataclass
class Synced:
    """A library with the fixture rides and an empty sync folder set up for it.

    Attributes:
        config: The library.
        remote: The sync folder.
        folder: The sync folder's path.
        keystore: This computer's keys.
        ids: Ride id for each imported fixture file.
    """

    config: Config
    remote: BlobStore
    folder: Path
    keystore: MemoryKeyStore
    ids: dict[str, str]


@pytest.fixture(scope="session")
def template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    """Import the fixture folder into a local library, once per session.

    Args:
        tmp_path_factory: Pytest's session temporary folders.

    Returns:
        The library folder and its ride ids by fixture file.
    """
    library = tmp_path_factory.mktemp("sync-template") / "library"
    with open_stores(Config(library=library)) as stores:
        report = Importer(stores.catalog, stores.blobs, stores.streams, workers=1).run([FIT_DIR])
    return library, dict(report.imported)


@pytest.fixture
def synced(tmp_path: Path, template: tuple[Path, dict[str, str]]) -> Generator[Synced]:
    """A copy of the fixture library, with a new sync folder set up for it.

    Args:
        tmp_path: Pytest's per-test temporary folder.
        template: The imported fixture library.

    Yields:
        The library, sync folder and keys.
    """
    library, ids = template
    config = Config(library=tmp_path / "library")
    shutil.copytree(library, config.library)
    folder = tmp_path / "sync"
    folder.mkdir()
    remote = open_remote(folder)
    keystore = MemoryKeyStore()
    with open_stores(config) as stores:
        setup(stores.catalog, remote, keystore, PASSPHRASE, FAST_KDF)
    yield Synced(config, remote, folder, keystore, ids)
