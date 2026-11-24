"""SQLite catalog: WAL mode, numbered SQL migrations, FTS5 text search."""

from fitlib.store.local.catalog.rides import (
    SqliteCatalog,
    latest_schema_version,
    restore_snapshot,
)

__all__ = ["SqliteCatalog", "latest_schema_version", "restore_snapshot"]
