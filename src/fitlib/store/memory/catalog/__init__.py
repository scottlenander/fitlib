"""In-memory catalog, for tests: plain dicts, with the same behaviour as SQLite.

One class, ``MemoryCatalog``, made of a part per role over shared state; see ``base``.
"""

from __future__ import annotations

from fitlib.store.memory.catalog.athlete import _Athlete
from fitlib.store.memory.catalog.bikes import _Bikes
from fitlib.store.memory.catalog.rides import _Rides
from fitlib.store.memory.catalog.settings import _Settings
from fitlib.store.memory.catalog.watch import _Watch

__all__ = ["MemoryCatalog"]


class MemoryCatalog(_Rides, _Bikes, _Athlete, _Settings, _Watch):
    """Rides in a dict, for tests. Passes the same contract tests as ``SqliteCatalog``."""
