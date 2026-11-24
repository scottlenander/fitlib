"""What showing rides needs besides the rides: the athlete's values and the bikes.

Training figures depend on the FTP, weight and heart rates in effect on each ride's day, and
lists name each ride's bike. ``RideContext`` loads those once, so a list of rides doesn't
query them again for every ride.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fitlib.analysis.training import AthleteProfile, Training, athlete_profile, training
from fitlib.metrics.zwift import zwift_world
from fitlib.models import Bike, Ride
from fitlib.store.interfaces import CatalogStore


@dataclass(frozen=True)
class RideView:
    """A ride with what's shown beside it.

    Attributes:
        ride: The ride.
        figures: Its training figures (FTP, TSS, zones...), for its day.
        bike: Its bike, if it has one.
        world: The Zwift world it was ridden in, by name, for Zwift rides.
    """

    ride: Ride
    figures: Training
    bike: Bike | None
    world: str | None


class RideContext:
    """The athlete's profile and the bikes, loaded once for showing any number of rides.

    Attributes:
        catalog: The library's catalog.
        athlete: The athlete's dated values, year of birth and calibration rides.
        bikes: Every bike, by id.
    """

    def __init__(
        self, catalog: CatalogStore, athlete: AthleteProfile, bikes: dict[str, Bike]
    ) -> None:
        """Keep what's loaded.

        Args:
            catalog: The library's catalog (for estimated FTPs).
            athlete: The athlete's profile.
            bikes: Every bike, by id.
        """
        self.catalog = catalog
        self.athlete = athlete
        self.bikes = bikes

    @classmethod
    def load(cls, catalog: CatalogStore) -> RideContext:
        """Load the athlete's profile and the bikes.

        Args:
            catalog: The library's catalog.

        Returns:
            The context.
        """
        return cls(catalog, athlete_profile(catalog), {b.id: b for b in catalog.list_bikes()})

    def bike(self, bike_id: str | None) -> Bike | None:
        """Find a bike by id.

        Args:
            bike_id: The bike's id, if any.

        Returns:
            The bike, or ``None`` for no id or an id that isn't a bike.
        """
        return self.bikes.get(bike_id) if bike_id is not None else None

    def figures(self, ride: Ride) -> Training:
        """Work out a ride's training figures.

        Args:
            ride: The ride.

        Returns:
            Its figures, with the values in effect on its day.
        """
        return training(self.catalog, ride, self.athlete)

    def view(self, ride: Ride) -> RideView:
        """Gather what's shown with a ride.

        Args:
            ride: The ride.

        Returns:
            The ride with its figures, bike and Zwift world.
        """
        world = zwift_world(ride.summary)
        return RideView(
            ride=ride,
            figures=self.figures(ride),
            bike=self.bike(ride.meta.bike_id),
            world=world.name if world else None,
        )

    def views(self, rides: Iterable[Ride]) -> list[RideView]:
        """Gather what's shown with each of several rides.

        Args:
            rides: The rides.

        Returns:
            Their views, in the same order.
        """
        return [self.view(ride) for ride in rides]
