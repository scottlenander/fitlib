"""Bikes, their totals, and the dated default-bike timeline."""

from __future__ import annotations

from datetime import date

from fitlib.models import (
    Bike,
    BikeDefault,
    BikeSlot,
    BikeTotals,
)
from fitlib.store.interfaces import (
    BikeNotFound,
    DuplicateBike,
    match_bike,
)
from fitlib.store.memory.catalog.base import _Base


class _Bikes(_Base):
    """Bikes, their totals, and the dated default-bike timeline."""

    def _check_name_free(self, bike: Bike) -> None:
        """Make sure no other bike has this bike's name.

        Args:
            bike: The bike being added or changed.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        for other in self._bikes.values():
            if other.id != bike.id and other.name.casefold() == bike.name.casefold():
                raise DuplicateBike(bike.name)

    def add_bike(self, bike: Bike) -> None:
        """Add a bike.

        Args:
            bike: The bike.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        self._check_name_free(bike)
        self._bikes[bike.id] = bike

    def update_bike(self, bike: Bike) -> None:
        """Change a bike's name, kind or retired flag.

        Args:
            bike: The bike with its new values, matched by id.

        Raises:
            BikeNotFound: No bike has this id.
            DuplicateBike: Another bike has the new name (ignoring case).
        """
        self.get_bike(bike.id)
        self._check_name_free(bike)
        self._bikes[bike.id] = bike

    def get_bike(self, bike_id: str) -> Bike:
        """Load one bike.

        Args:
            bike_id: The bike's id.

        Returns:
            The bike.

        Raises:
            BikeNotFound: No bike has this id.
        """
        try:
            return self._bikes[bike_id]
        except KeyError:
            raise BikeNotFound(bike_id) from None

    def list_bikes(self, include_retired: bool = True) -> list[Bike]:
        """List bikes, sorted by name (ignoring case).

        Args:
            include_retired: Include retired bikes.

        Returns:
            The bikes.
        """
        bikes = [b for b in self._bikes.values() if include_retired or not b.retired]
        return sorted(bikes, key=lambda b: b.name.casefold())

    def resolve_bike(self, ref: str) -> Bike:
        """Find a bike by name: an exact match ignoring case, else a unique prefix.

        Args:
            ref: A bike name or the start of one.

        Returns:
            The one matching bike.

        Raises:
            BikeNotFound: No bike matches.
            AmbiguousBike: The prefix matches several bikes.
        """
        return match_bike(list(self._bikes.values()), ref)

    def bike_totals(self) -> list[BikeTotals]:
        """Add up rides, distance and riding time for every bike.

        Returns:
            One entry per bike, sorted by name (ignoring case).
        """
        totals = []
        for bike in self.list_bikes():
            rides = [r for r in self._rides.values() if r.meta.bike_id == bike.id]
            totals.append(
                BikeTotals(
                    bike=bike,
                    rides=len(rides),
                    distance_m=sum(r.summary.distance_m or 0.0 for r in rides),
                    moving_s=sum(r.summary.moving_s for r in rides),
                )
            )
        return totals

    def bike_defaults(self) -> list[BikeDefault]:
        """List the dated default-bike entries.

        Returns:
            Every entry, by slot then date.
        """
        return [self._bike_defaults[k] for k in sorted(self._bike_defaults)]

    def set_bike_default(self, entry: BikeDefault) -> None:
        """Add a default-bike entry, replacing any for the same slot and date.

        Args:
            entry: The entry.

        Raises:
            BikeNotFound: ``entry.bike_id`` isn't a bike.
        """
        if entry.bike_id is not None:
            self.get_bike(entry.bike_id)
        self._bike_defaults[(entry.slot, entry.effective_from)] = entry

    def delete_bike_default(self, slot: BikeSlot, effective_from: date) -> bool:
        """Remove the default-bike entry for a slot and date.

        Args:
            slot: The entry's slot.
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        return self._bike_defaults.pop((slot, effective_from), None) is not None
