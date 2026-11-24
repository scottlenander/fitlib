"""Bike and athlete services: names, changes, the default timeline, backfill, and today."""

from __future__ import annotations

from datetime import date

import pytest

from fitlib.metadata import KEEP
from fitlib.metrics.load import ThresholdSource
from fitlib.models import AthleteEntry, BikeDefault, BikeKind, BikeSlot
from fitlib.services import athlete, bikes
from fitlib.services.errors import AthleteEntryNotFound, DefaultNotFound, EmptyBikeName
from fitlib.store.memory import MemoryCatalog
from tests.unit.conftest import ImportedLibrary


def test_bike_names_are_tidied_and_must_not_be_empty():
    """Spaces around and inside a bike name are tidied; a blank name is refused.

    Given: A name with extra spaces, then a name of spaces.
    Expect: The tidied name is saved; ``EmptyBikeName`` for the blank one.
    """
    catalog = MemoryCatalog()

    bike = bikes.add_bike(catalog, "  Giant   Contend 1 ", BikeKind.ROAD)

    assert catalog.get_bike(bike.id).name == "Giant Contend 1"
    with pytest.raises(EmptyBikeName):
        bikes.add_bike(catalog, "   ")


def test_changing_a_bike_keeps_what_isnt_changed():
    """Only the parts of a bike given are changed.

    Given: A road bike, renamed, then retired, then its kind cleared.
    Expect: Each step keeps the other parts.
    """
    catalog = MemoryCatalog()
    bike = bikes.add_bike(catalog, "Old name", BikeKind.ROAD)

    renamed = bikes.change_bike(catalog, bike, name="New name")
    retired = bikes.change_bike(catalog, renamed, retired=True)
    no_kind = bikes.change_bike(catalog, retired, kind=None)

    assert (renamed.name, renamed.kind, renamed.retired) == ("New name", BikeKind.ROAD, False)
    assert (retired.name, retired.kind, retired.retired) == ("New name", BikeKind.ROAD, True)
    assert (no_kind.kind, bikes.change_bike(catalog, no_kind, kind=KEEP).kind) == (None, None)


def test_the_default_timeline_names_bikes_and_removing_needs_an_entry():
    """Default entries come with their bikes; removing one that isn't there is an error.

    Given: A Zwift default from 1 Aug 2025, and one that stops defaulting from 1 Sep.
    Expect: The timeline names the bike, then none; removing a 2 Aug entry is
        ``DefaultNotFound`` saying which.
    """
    catalog = MemoryCatalog()
    bike = bikes.add_bike(catalog, "Trainer bike")
    bikes.set_default(catalog, BikeDefault(BikeSlot.ZWIFT, date(2025, 8, 1), bike.id))
    bikes.set_default(catalog, BikeDefault(BikeSlot.ZWIFT, date(2025, 9, 1), None))

    timeline = bikes.default_timeline(catalog)

    assert [d.bike for d in timeline] == [bike, None]
    assert bikes.current_defaults(catalog) == {BikeSlot.ZWIFT: None}
    with pytest.raises(DefaultNotFound, match="No zwift default starts on 2025-08-02"):
        bikes.remove_default(catalog, BikeSlot.ZWIFT, date(2025, 8, 2))


def test_backfill_names_the_bikes_rides_gain(imported: ImportedLibrary):
    """Backfilling reports each bike with how many rides it would get.

    Given: The fixture library and a Zwift default bike from 2025.
    Expect: The bike gains the one Zwift ride, in a dry run and for real; a second run
        changes nothing.
    """
    bike = bikes.add_bike(imported.catalog, "Trainer bike")
    bikes.set_default(imported.catalog, BikeDefault(BikeSlot.ZWIFT, date(2025, 1, 1), bike.id))

    preview = bikes.backfill(imported.catalog, dry_run=True)
    done = bikes.backfill(imported.catalog)

    assert preview == done == [(bike, 1)]
    assert bikes.backfill(imported.catalog) == [], "Nothing should be left to change"


def test_athlete_today_gathers_history_values_and_threshold():
    """Today's athlete view has the history oldest first and the values in effect.

    Given: A 2026 entry with FTP, then a 2025 entry with weight and threshold heart rate.
    Expect: History oldest first; today's values combine both; the set threshold.
    """
    catalog = MemoryCatalog()
    catalog.set_athlete_entry(AthleteEntry(date(2026, 1, 1), ftp=250))
    catalog.set_athlete_entry(AthleteEntry(date(2025, 1, 1), weight_kg=70.0, threshold_hr=165))

    now = athlete.athlete_today(catalog, date(2026, 6, 1))

    assert [e.effective_from for e in now.history] == [date(2025, 1, 1), date(2026, 1, 1)]
    assert (now.values.ftp, now.values.weight_kg) == (250, 70.0)
    assert (now.threshold_hr, now.threshold_source) == (165, ThresholdSource.SET)


def test_removing_an_athlete_entry_needs_one():
    """Removing an entry on a day without one is an error saying which day.

    Given: An empty history.
    Expect: ``AthleteEntryNotFound`` naming the day.
    """
    with pytest.raises(AthleteEntryNotFound, match="No athlete entry on 2025-08-01"):
        athlete.remove_entry(MemoryCatalog(), date(2025, 8, 1))
