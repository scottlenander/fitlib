"""Catalog contract: the athlete history.

Every test runs against each backend (see conftest), except in test_sqlite.
"""

from __future__ import annotations

from datetime import date

from fitlib.models import (
    AthleteEntry,
)
from fitlib.store.interfaces import (
    CatalogStore,
)


def test_athlete_history_entries(catalog: CatalogStore):
    """Athlete history entries are kept by date, oldest first; a date can be replaced or removed.

    Given: entries for 1 Mar (FTP 250) and 1 Jan (FTP 240, 72 kg, max HR 188, threshold HR
    165), then a new 1 Mar entry (FTP 255), then 1 Jan removed.
    Expect: after each step, the entries in date order with the latest values.
    """
    january = AthleteEntry(date(2025, 1, 1), ftp=240, weight_kg=72.0, max_hr=188, threshold_hr=165)
    march = AthleteEntry(date(2025, 3, 1), ftp=250)
    catalog.set_athlete_entry(march)
    catalog.set_athlete_entry(january)

    both = catalog.athlete_history()
    catalog.set_athlete_entry(AthleteEntry(date(2025, 3, 1), ftp=255))
    replaced = catalog.athlete_history()
    removed = catalog.delete_athlete_entry(date(2025, 1, 1))
    removed_again = catalog.delete_athlete_entry(date(2025, 1, 1))

    assert both == [january, march], "entries should come back oldest first"
    assert replaced == [january, AthleteEntry(date(2025, 3, 1), ftp=255)]
    assert (removed, removed_again) == (True, False), "removing twice finds nothing the 2nd time"
    assert catalog.athlete_history() == [AthleteEntry(date(2025, 3, 1), ftp=255)]
