"""SQLite catalog: WAL mode, numbered SQL migrations, FTS5 text search.

One class, ``SqliteCatalog``, made of a part per role over one connection; see ``base`` for
the connection and migrations.
"""

from __future__ import annotations

from fitlib.store.local.catalog.athlete import _Athlete
from fitlib.store.local.catalog.base import latest_schema_version, restore_snapshot
from fitlib.store.local.catalog.bikes import _Bikes
from fitlib.store.local.catalog.rides import _Rides
from fitlib.store.local.catalog.settings import _Settings
from fitlib.store.local.catalog.watch import _Watch

__all__ = ["SqliteCatalog", "latest_schema_version", "restore_snapshot"]


class SqliteCatalog(_Rides, _Bikes, _Athlete, _Settings, _Watch):
    """The catalog in a SQLite file: WAL mode, numbered migrations, FTS5 text search.

    Safe to share between threads (calls are serialized with a lock). Opening a catalog
    applies any migrations it hasn't had yet.

    Args:
        path: The database file (created if missing), or ``":memory:"``.
    """
