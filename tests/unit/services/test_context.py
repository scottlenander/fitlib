"""What's shown beside rides: figures, bike and Zwift world, loaded once for many rides."""

from __future__ import annotations

from collections import Counter
from typing import Any

from fitlib.analysis.training import training
from fitlib.metadata import KEEP, MetaEdit
from fitlib.models import Filters
from fitlib.services import bikes, rides
from fitlib.services.context import RideContext
from fitlib.store.factory import Stores
from tests.unit.conftest import ImportedLibrary

ZWIFT = "2025-08-02-08-29-42.fit"


class CountingCatalog:
    """A catalog that counts the calls made to it, for checking what's loaded how often.

    Attributes:
        calls: How many times each method was called.
    """

    def __init__(self, inner: Any) -> None:
        """Wrap a catalog.

        Args:
            inner: The catalog to pass calls on to.
        """
        self._inner = inner
        self.calls: Counter[str] = Counter()

    def __getattr__(self, name: str) -> Any:
        """Count a method call and pass it on.

        Args:
            name: The attribute asked for.

        Returns:
            The inner catalog's attribute; methods counted when called.
        """
        value = getattr(self._inner, name)
        if not callable(value):
            return value

        def counted(*args: Any, **kwargs: Any) -> Any:
            self.calls[name] += 1
            return value(*args, **kwargs)

        return counted


def test_figures_match_training_for_every_ride(imported: ImportedLibrary):
    """The context gives each ride the same figures as working them out alone.

    Given: The fixture library, with an FTP set for some rides and estimated for others.
    Expect: For every ride, the context's figures equal ``training()``'s.
    """
    context = RideContext.load(imported.catalog)

    for ride_id in imported.catalog.ride_ids():
        ride = imported.catalog.get_ride(ride_id)
        assert context.figures(ride) == training(imported.catalog, ride), (
            f"{ride.source_name} should have the same figures either way"
        )


def test_a_list_loads_the_athlete_and_bikes_once(imported: ImportedLibrary):
    """Listing every ride loads the athlete's profile and the bikes once, not per ride.

    Given: The fixture library behind a catalog that counts calls.
    Expect: One ``list_bikes`` and one full ``trend_rows`` (the profile's calibration rides)
        for the whole page.
    """
    counting = CountingCatalog(imported.catalog)
    stores = Stores(counting, imported.blobs, imported.streams)  # type: ignore[arg-type]

    found = rides.list_rides(stores, Filters(), limit=50)

    assert len(found.views) > 5
    assert counting.calls["list_bikes"] == 1, "The bikes should be loaded once"
    assert counting.calls["trend_rows"] == 1, "The athlete's profile should be loaded once"


def test_a_view_names_the_bike_and_the_zwift_world(imported: ImportedLibrary):
    """A ride's view carries its bike and, for Zwift rides, the world.

    Given: The Zwift fixture ride on a new bike, and an outdoor ride.
    Expect: The Zwift ride's view names the bike and Watopia; the outdoor ride has no world.
    """
    bike = bikes.add_bike(imported.catalog, "Trainer bike")
    zwift = imported.ride(ZWIFT)
    rides.edit_ride(imported.stores, zwift.id, MetaEdit(bike_id=bike.id, tags=KEEP))

    view = rides.ride_view(imported.stores, zwift.id)
    outdoor = rides.ride_view(imported.stores, imported.ride("garmin_nord_pause_10min.fit").id)

    assert (view.bike, view.world) == (bike, "Watopia")
    assert outdoor.world is None, "An outdoor ride should have no Zwift world"


def test_a_page_makes_the_same_queries_whatever_its_size(imported: ImportedLibrary):
    """Figures for more rides need no more queries: estimates come from the loaded profile.

    Given: The fixture library (no FTP set, so every ride with power estimates one), listed
        one ride to a page, then eight.
    Expect: The same catalog calls, the same number of times, for both pages.
    """

    def calls_for(limit: int) -> Counter[str]:
        counting = CountingCatalog(imported.catalog)
        stores = Stores(counting, imported.blobs, imported.streams)  # type: ignore[arg-type]
        found = rides.list_rides(stores, Filters(), limit=limit)
        assert len(found.views) == limit
        return counting.calls

    assert calls_for(1) == calls_for(8)
