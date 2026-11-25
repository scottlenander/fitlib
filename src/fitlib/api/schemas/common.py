"""Models more than one resource uses."""

from __future__ import annotations

from pydantic import BaseModel

from fitlib.models import (
    Bike,
)


class BikeRef(BaseModel):
    """A bike, as named on a ride.

    Attributes:
        id: The bike's id.
        name: The bike's name.
    """

    id: str
    name: str


def bike_ref(bike: Bike | None) -> BikeRef | None:
    """Name a ride's bike.

    Args:
        bike: The bike, if the ride has one.

    Returns:
        The bike's id and name, or ``None``.
    """
    return BikeRef(id=bike.id, name=bike.name) if bike is not None else None
