"""The catalog fixture: each backend in turn, empty.

A new backend (e.g. a future cloud one) is added to the fixture's params and must pass every
contract test in this folder unchanged.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from fitlib.store.interfaces import (
    CatalogStore,
)
from fitlib.store.local import SqliteCatalog
from fitlib.store.memory import MemoryCatalog


@pytest.fixture(params=["sqlite", "memory"])
def catalog(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[CatalogStore]:
    """Provide each catalog implementation in turn, empty, and close it afterwards.

    Args:
        request: Pytest request; its param picks the implementation.
        tmp_path: Folder for the SQLite file.

    Yields:
        A SQLite or in-memory catalog.
    """
    store: CatalogStore
    if request.param == "sqlite":
        store = SqliteCatalog(tmp_path / "catalog.sqlite3")
    else:
        store = MemoryCatalog()
    yield store
    store.close()
