"""Build the stores a config asks for. The only place that knows which backend is in use."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

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


@contextmanager
def open_stores(config: Config) -> Generator[Stores]:
    """Open the library a config describes, creating it if needed, and close it afterwards.

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

    config.library.mkdir(parents=True, exist_ok=True)
    catalog = SqliteCatalog(config.library / CATALOG_FILE)
    blobs = FsBlobStore(config.library / BLOBS_DIR)
    try:
        yield Stores(catalog=catalog, blobs=blobs, streams=StreamStore(blobs))
    finally:
        catalog.close()
