"""Bikes, the default-bike timeline and backfill."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator

from fitlib.api.schemas.common import BikeRef
from fitlib.models import (
    Bike,
    BikeKind,
    BikeSlot,
)


class BikeOut(BaseModel):
    """A bike.

    Attributes:
        id: The bike's id.
        name: The bike's name.
        kind: Road, gravel, TT and so on, if set.
        retired: Whether the bike is retired.
    """

    id: str
    name: str
    kind: BikeKind | None
    retired: bool


def bike_out(bike: Bike) -> BikeOut:
    """Copy a bike.

    Args:
        bike: The bike.

    Returns:
        The bike for the API.
    """
    return BikeOut(id=bike.id, name=bike.name, kind=bike.kind, retired=bike.retired)


def _bike_name(value: str) -> str:
    """Tidy a bike name: runs of spaces become one, and it can't be blank.

    Args:
        value: The name as sent.

    Returns:
        The tidied name.

    Raises:
        ValueError: The name is blank.
    """
    clean = " ".join(value.split())
    if not clean:
        raise ValueError("Bike names can't be empty")
    return clean


class BikeCreate(BaseModel):
    """A new bike.

    Attributes:
        name: The bike's name; spaces are tidied and it can't be blank.
        kind: Road, gravel, TT and so on.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: BikeKind | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        """Tidy the name.

        Args:
            value: The name as sent.

        Returns:
            The tidied name.
        """
        return _bike_name(value)


class BikePatch(BaseModel):
    """Changes to a bike. Fields left out stay as they are.

    Attributes:
        name: A new name; spaces are tidied and it can't be blank.
        kind: A new kind; ``null`` clears it.
        retired: Retire (true) or bring back (false) the bike.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    kind: BikeKind | None = None
    retired: bool | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        """Tidy the name, if one was sent.

        Args:
            value: The name as sent, or ``None``.

        Returns:
            The tidied name, or ``None``.
        """
        return None if value is None else _bike_name(value)


class BikeWithTotals(BikeOut):
    """A bike and how much it has been ridden.

    Attributes:
        rides: Rides on the bike.
        distance_m: Their total distance.
        moving_s: Their total moving time.
    """

    rides: int
    distance_m: float
    moving_s: int


class DefaultOut(BaseModel):
    """One entry in the default-bike timeline.

    Attributes:
        slot: Which kind of ride: zwift, indoor or outdoor.
        effective_from: The first day the entry applies.
        bike: The default bike from that day, or ``None`` to stop defaulting.
    """

    slot: BikeSlot
    effective_from: date
    bike: BikeRef | None


class DefaultSet(BaseModel):
    """The bike to default to from a date.

    Attributes:
        bike_id: The bike, or ``null`` to stop defaulting from that date.
    """

    model_config = ConfigDict(extra="forbid")

    bike_id: str | None


class BackfillChange(BaseModel):
    """How many rides a backfill gives (or would give) one bike.

    Attributes:
        bike: The bike, or ``None`` for rides that lose their default bike.
        rides: How many rides.
    """

    bike: BikeRef | None
    rides: int


class BackfillResult(BaseModel):
    """What a backfill changed, or would change on a dry run.

    Attributes:
        dry_run: Whether nothing was saved.
        changes: Rides per bike, most first.
    """

    dry_run: bool
    changes: list[BackfillChange]
