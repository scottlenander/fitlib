"""Backfilling default bikes onto rides already in the library."""

from __future__ import annotations

from datetime import date

from fitlib.analysis.bikes import backfill_bikes
from fitlib.models import Bike, BikeDefault, BikeSlot, Filters, RideMeta
from tests.conftest import ImportedLibrary

GIANT = Bike(id="b1000000-0000-4000-8000-000000000001", name="Giant Contend 1")
TARMAC = Bike(id="b1000000-0000-4000-8000-000000000002", name="Tarmac SL7")
KICKR = Bike(id="b1000000-0000-4000-8000-000000000003", name="Kickr")


def set_up_bikes(lib: ImportedLibrary) -> None:
    """Add three bikes and dated defaults: outdoor Giant then Tarmac from 10 Aug; Zwift Kickr.

    Args:
        lib: The imported library (rides 2-24 Aug 2025).
    """
    for bike in (GIANT, TARMAC, KICKR):
        lib.catalog.add_bike(bike)
    lib.catalog.set_bike_default(BikeDefault(BikeSlot.OUTDOOR, date(2025, 1, 1), GIANT.id))
    lib.catalog.set_bike_default(BikeDefault(BikeSlot.OUTDOOR, date(2025, 8, 10), TARMAC.id))
    lib.catalog.set_bike_default(BikeDefault(BikeSlot.ZWIFT, date(2025, 1, 1), KICKR.id))


def test_backfill_follows_the_dated_defaults(imported: ImportedLibrary):
    """Rides without a bike get the default for their kind and date.

    Given: the imported fixtures (no bikes yet): outdoor rides on 5 and 9 Aug and on 12, 16,
    23 and 24 Aug; a Zwift ride on 2 Aug; a Garmin indoor ride with no indoor default.
    Expect: Giant on 2 rides, Tarmac on 4, Kickr on 1; the indoor ride stays without a bike.
    """
    set_up_bikes(imported)

    assigned = backfill_bikes(imported.catalog)

    assert dict(assigned) == {GIANT.id: 2, TARMAC.id: 4, KICKR.id: 1}
    without = imported.catalog.search(Filters(has_bike=False)).items
    assert [r.source_name for r in without] == ["garmin_indoor_no_hr.fit"], (
        "only the indoor ride, which has no default, should be left without a bike"
    )


def test_backfill_never_overwrites_a_bike_set_by_hand(imported: ImportedLibrary):
    """A bike chosen by the user stays, even if the default would differ.

    Given: the 5 Aug outdoor ride set by hand to the Tarmac (the default then is the Giant).
    Expect: the Giant is backfilled on 1 ride, not 2; the 5 Aug ride keeps the Tarmac.
    """
    set_up_bikes(imported)
    ride = imported.ride("garmin_nord_intervals_5x4.fit")
    imported.catalog.update_meta(ride.id, RideMeta(bike_id=TARMAC.id))

    assigned = backfill_bikes(imported.catalog)

    assert assigned[GIANT.id] == 1
    assert imported.catalog.get_ride(ride.id).meta.bike_id == TARMAC.id


def test_dry_run_changes_nothing_and_repeat_finds_nothing(imported: ImportedLibrary):
    """A dry run only counts; running twice changes nothing the second time.

    Given: the defaults; a dry run, then a real run, then another real run.
    Expect: the dry run reports 7 rides and leaves 8 without a bike; the second real run
    assigns nothing.
    """
    set_up_bikes(imported)

    planned = backfill_bikes(imported.catalog, dry_run=True)
    untouched = imported.catalog.search(Filters(has_bike=False)).total
    backfill_bikes(imported.catalog)
    again = backfill_bikes(imported.catalog)

    assert sum(planned.values()) == 7
    assert untouched == 8, "a dry run should not change any ride"
    assert not again, "nothing should be left to backfill"


def test_backfill_without_defaults_does_nothing(imported: ImportedLibrary):
    """With no defaults set, there is nothing to backfill.

    Given: the imported fixtures and no default bikes.
    Expect: an empty result.
    """
    assert not backfill_bikes(imported.catalog)
