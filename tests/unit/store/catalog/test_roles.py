"""Catalog contract: every catalog backend plays every role.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from fitlib.store.interfaces import (
    AthleteCatalog,
    BikeCatalog,
    CatalogStore,
    RideCatalog,
    SettingsStore,
    WatchState,
)


def test_every_backend_plays_every_role(catalog: CatalogStore):
    """Each backend has every role's methods, so it can be passed wherever one is needed.

    Given: The catalog backend under test.
    Expect: It is a ``RideCatalog``, ``BikeCatalog``, ``AthleteCatalog``, ``SettingsStore``,
        ``WatchState`` and the whole ``CatalogStore``.
    """
    roles = (RideCatalog, BikeCatalog, AthleteCatalog, SettingsStore, WatchState, CatalogStore)

    missing = [role.__name__ for role in roles if not isinstance(catalog, role)]

    assert missing == [], f"{type(catalog).__name__} should play every role"
