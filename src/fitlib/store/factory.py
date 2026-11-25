"""Build the stores a config asks for. The only place that knows which backend is in use."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fitlib.config import Config, ConfigError
from fitlib.store.interfaces import BlobStore, CatalogStore
from fitlib.store.streams import StreamStore

CATALOG_FILE = "catalog.sqlite3"
BLOBS_DIR = "blobs"


@dataclass(frozen=True)
class Stores:
    """The stores one library is made of.

    Attributes:
        catalog: Ride entries.
        blobs: Original files and streams.
        streams: Streams, on top of ``blobs``.
    """

    catalog: CatalogStore
    blobs: BlobStore
    streams: StreamStore


# The library holds where you ride: only its owner may read it.
PRIVATE_MODE = 0o700


def private_folder(folder: Path) -> None:
    """Create a library folder readable by its owner only, or make an existing one so.

    Other accounts on the computer then can't read anything inside, whatever the modes of
    the files in it.

    Args:
        folder: The library folder.
    """
    folder.mkdir(mode=PRIVATE_MODE, parents=True, exist_ok=True)
    if folder.stat().st_mode & 0o777 != PRIVATE_MODE:
        folder.chmod(PRIVATE_MODE)


@contextmanager
def open_stores(config: Config) -> Generator[Stores]:
    """Open the library a config describes, creating it if needed, and close it afterwards.

    The library folder is made readable by its owner only (see ``private_folder``).

    Args:
        config: Which library and backend to use.

    Yields:
        The library's stores.

    Raises:
        ConfigError: The config names a backend that doesn't exist.
    """
    if config.backend != "local":
        raise ConfigError(f"Unknown store backend {config.backend!r}")

    from fitlib.store.local import FsBlobStore, SqliteCatalog

    private_folder(config.library)
    catalog = SqliteCatalog(config.library / CATALOG_FILE)
    blobs = FsBlobStore(config.library / BLOBS_DIR)
    try:
        yield Stores(catalog=catalog, blobs=blobs, streams=StreamStore(blobs))
    finally:
        catalog.close()


def catalog_path(config: Config) -> Path:
    """The catalog file of a local library.

    Args:
        config: Which library.

    Returns:
        The path of its SQLite catalog (which may not exist yet).
    """
    return config.library / CATALOG_FILE


def library_has_data(config: Config) -> bool:
    """Check whether a library holds any rides or blobs, without creating it.

    Args:
        config: Which library.

    Returns:
        ``True`` if its catalog has rides or its blob folder has files.
    """
    from fitlib.store.local import FsBlobStore, SqliteCatalog

    blobs = config.library / BLOBS_DIR
    if blobs.is_dir() and FsBlobStore(blobs).list():
        return True
    if not catalog_path(config).exists():
        return False
    catalog = SqliteCatalog(catalog_path(config))
    try:
        return catalog.count() > 0
    finally:
        catalog.close()


def remove_empty_catalog(config: Config) -> None:
    """Delete a library's catalog file, which must hold no rides, so a restore can replace it.

    Args:
        config: Which library.

    Raises:
        ValueError: The library has rides or blobs.
    """
    if library_has_data(config):
        raise ValueError(f"The library at {config.library} isn't empty")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{catalog_path(config)}{suffix}").unlink(missing_ok=True)


def snapshot_catalog(stores: Stores, local_settings: frozenset[str]) -> bytes:
    """Copy a library's catalog for sync, without this computer's own data.

    Args:
        stores: The open library.
        local_settings: Keys of this computer's own settings, left out.

    Returns:
        The snapshot's bytes.

    Raises:
        ConfigError: The backend can't make snapshots.
    """
    from fitlib.store.local import SqliteCatalog

    if not isinstance(stores.catalog, SqliteCatalog):
        raise ConfigError("Only the local backend can sync")
    return stores.catalog.snapshot(local_settings)


def restore_catalog(config: Config, data: bytes) -> None:
    """Write a catalog snapshot as a library's catalog, checking it first.

    Args:
        config: Which library; it must have no catalog file yet.
        data: The snapshot.

    Raises:
        FileExistsError: The library already has a catalog.
        BadSnapshot: The snapshot is damaged or from a newer fitlib.
    """
    from fitlib.store.local.catalog import restore_snapshot

    private_folder(config.library)
    restore_snapshot(catalog_path(config), data)


def latest_schema_version() -> int:
    """The newest catalog schema this fitlib knows.

    Returns:
        Its number.
    """
    from fitlib.store.local.catalog import latest_schema_version as latest

    return latest()


def library_blobs(config: Config) -> BlobStore:
    """The blob store of a local library, without opening its catalog.

    Args:
        config: Which library.

    Returns:
        Its blobs (the folder is created if missing).
    """
    from fitlib.store.local import FsBlobStore

    private_folder(config.library)
    return FsBlobStore(config.library / BLOBS_DIR)


def open_remote(folder: Path) -> BlobStore:
    """The blob store for a sync folder.

    Args:
        folder: The sync folder; it must exist.

    Returns:
        Its blobs, one file per object.

    Raises:
        ConfigError: The folder doesn't exist.
    """
    from fitlib.store.local import FsBlobStore

    if not folder.is_dir():
        raise ConfigError(f"The sync folder {folder} doesn't exist or isn't a folder")
    return FsBlobStore(folder)
