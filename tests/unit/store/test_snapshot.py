"""Catalog snapshots for sync, and writing one back as a library's catalog."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fitlib.config import Config
from fitlib.services.watching import watch_folder
from fitlib.store.factory import (
    catalog_path,
    library_has_data,
    open_stores,
    remove_empty_catalog,
    restore_catalog,
    snapshot_catalog,
)
from fitlib.store.interfaces import BadSnapshot
from fitlib.store.local.catalog import latest_schema_version
from fitlib.store.settings import (
    DEFAULT_TIME_ZONE,
    LIBRARY_ID,
    MACHINE_LOCAL,
    SYNC_DEVICE,
    SYNC_GENERATION,
    SYNC_REMOTE,
)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    """An empty library in a temporary folder.

    Args:
        tmp_path: Pytest's per-test temporary folder.

    Returns:
        Its config.
    """
    return Config(library=tmp_path / "library")


def test_snapshot_leaves_out_this_computers_data(config: Config, tmp_path: Path):
    """A snapshot keeps library settings but not watched folders or this computer's settings.

    Given: A library with a default time zone, a library id, every machine-local sync setting
        and a watched folder, snapshotted and restored elsewhere.
    Expect: The time zone and library id are there; the sync settings and watched folder
        aren't.
    """
    with open_stores(config) as stores:
        DEFAULT_TIME_ZONE.set(stores.catalog, "Europe/Paris")
        LIBRARY_ID.set(stores.catalog, "a-library")
        SYNC_REMOTE.set(stores.catalog, "/Volumes/Backup")
        SYNC_GENERATION.set(stores.catalog, 4)
        SYNC_DEVICE.set(stores.catalog, "this-computer")
        stores.catalog.add_watch_folder(watch_folder(tmp_path / "watched"))
        data = snapshot_catalog(stores, MACHINE_LOCAL)
    copy = Config(library=tmp_path / "copy")

    restore_catalog(copy, data)

    with open_stores(copy) as stores:
        catalog = stores.catalog
        assert DEFAULT_TIME_ZONE.get(catalog) == "Europe/Paris"
        assert LIBRARY_ID.get(catalog) == "a-library", "The library id should travel with it"
        local = [SYNC_REMOTE.get(catalog), SYNC_GENERATION.get(catalog), SYNC_DEVICE.get(catalog)]
        assert local == [None, None, None], "This computer's sync settings should stay here"
        assert catalog.watch_folders() == []


def test_unchanged_catalog_gives_the_same_snapshot(config: Config):
    """Writes to left-out settings don't change the snapshot's bytes.

    Given: Two snapshots with a sync setting written between them.
    Expect: Identical bytes, so a push can skip the catalog.
    """
    with open_stores(config) as stores:
        first = snapshot_catalog(stores, MACHINE_LOCAL)
        stores.catalog.set_setting("sync_generation", "4")
        second = snapshot_catalog(stores, MACHINE_LOCAL)

    assert first == second


def test_snapshot_is_a_plain_sqlite_file(config: Config, tmp_path: Path):
    """A snapshot is a sound SQLite database at the current schema, not in WAL mode.

    Given: A snapshot written to a file.
    Expect: Integrity check ok, rollback journal mode, newest schema version.
    """
    with open_stores(config) as stores:
        path = tmp_path / "snap.sqlite3"
        path.write_bytes(snapshot_catalog(stores, MACHINE_LOCAL))
    db = sqlite3.connect(path)

    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert db.execute("PRAGMA user_version").fetchone()[0] == latest_schema_version()
    db.close()


def test_restore_refuses_damaged_data(config: Config):
    """Bytes that aren't a SQLite database are refused, leaving no catalog.

    Given: Random-looking bytes.
    Expect: ``BadSnapshot``, and no catalog file or temp file left.
    """
    with pytest.raises(BadSnapshot):
        restore_catalog(config, b"not a database" * 100)

    assert not catalog_path(config).exists()
    assert list(config.library.iterdir()) == [], "should clean up its temp file"


def test_restore_refuses_a_newer_schema(config: Config, tmp_path: Path):
    """A catalog from a newer fitlib is refused.

    Given: A snapshot whose ``user_version`` is past the newest migration.
    Expect: ``BadSnapshot`` naming a newer fitlib.
    """
    with open_stores(Config(library=tmp_path / "source")) as stores:
        data = snapshot_catalog(stores, MACHINE_LOCAL)
    path = tmp_path / "newer.sqlite3"
    path.write_bytes(data)
    db = sqlite3.connect(path)
    db.execute(f"PRAGMA user_version = {latest_schema_version() + 1}")
    db.close()

    with pytest.raises(BadSnapshot, match="newer"):
        restore_catalog(config, path.read_bytes())


def test_restore_never_replaces_a_catalog(config: Config):
    """Restoring over an existing catalog is refused.

    Given: A library that already has a catalog.
    Expect: ``FileExistsError``.
    """
    with open_stores(config) as stores:
        data = snapshot_catalog(stores, MACHINE_LOCAL)

    with pytest.raises(FileExistsError):
        restore_catalog(config, data)


def test_empty_library_catalog_can_be_removed(config: Config):
    """An empty library's catalog can make way for a restore; one with data can't.

    Given: A library opened once (empty), then one with a blob.
    Expect: The empty one has no data and its catalog is removed; with a blob,
        ``library_has_data`` is true and removal raises ``ValueError``.
    """
    with open_stores(config):
        pass
    assert library_has_data(config) is False
    remove_empty_catalog(config)
    assert not catalog_path(config).exists()

    with open_stores(config) as stores:
        stores.blobs.put("raw/ab/ab.fit", b"x")
    assert library_has_data(config) is True
    with pytest.raises(ValueError, match="isn't empty"):
        remove_empty_catalog(config)
