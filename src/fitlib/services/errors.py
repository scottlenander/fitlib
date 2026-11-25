"""Errors the services raise for requests a person can fix.

``ServiceError`` is a bad request (the API answers 422); ``NotFound`` is something asked for
that isn't there (404). Each message is a sentence for the person, shown as it is by the web
app and the command line.
"""

from __future__ import annotations

from fitlib.store.interfaces import RideNotFound


class ServiceError(ValueError):
    """A request that can't be done as asked; the message says why."""


class NotFound(LookupError):
    """Something asked for isn't in the library; the message says what."""


class MissingRides(RideNotFound):
    """Some of several rides asked for at once aren't in the library.

    A ``RideNotFound``, so anything handling one ride not being found handles this too.

    Args:
        refs: The ids or prefixes that match no ride.

    Attributes:
        refs: The ids or prefixes that match no ride, in the order asked.
    """

    def __init__(self, refs: list[str]):
        super().__init__(*refs)
        self.refs = refs

    def __str__(self) -> str:
        """Say how many rides weren't found, readably.

        Returns:
            E.g. "2 rides are no longer in the library (they may have been deleted)".
        """
        if len(self.refs) == 1:
            return "1 ride is no longer in the library (it may have been deleted)"
        return f"{len(self.refs)} rides are no longer in the library (they may have been deleted)"


class NothingToChange(ServiceError):
    """An edit of several rides that changes nothing."""

    def __init__(self) -> None:
        """Say what to choose."""
        super().__init__("Choose an effort, a bike or tags to change.")


class WrongRideCount(ServiceError):
    """Too few or too many rides to compare."""

    def __init__(self, low: int, high: int, got: int) -> None:
        """Say how many rides are needed.

        Args:
            low: The fewest rides allowed.
            high: The most rides allowed.
            got: How many were given.
        """
        super().__init__(f"Compare {low} to {high} rides; got {got}.")


class RideTwice(ServiceError):
    """The same ride given more than once where each must be different."""

    def __init__(self) -> None:
        """Say what's wrong."""
        super().__init__("The same ride is given more than once.")


class BadSmoothing(ServiceError):
    """A smoothing window that isn't offered."""

    def __init__(self, allowed: tuple[int, ...], got: int) -> None:
        """Say which windows are offered.

        Args:
            allowed: The windows offered, in seconds.
            got: The window asked for.
        """
        super().__init__(f"Smoothing must be one of {list(allowed)} seconds; got {got}.")


class CantAlignByDistance(ServiceError):
    """Lining rides up by distance when one of them recorded none."""

    def __init__(self, name: str) -> None:
        """Name the ride without distance.

        Args:
            name: The ride's display name.
        """
        super().__init__(
            f"{name} recorded no distance, so the rides can't be lined up by it; line them up "
            "by time instead."
        )


class UnknownStreamFields(ServiceError):
    """Stream columns that don't exist."""

    def __init__(self, unknown: list[str], known: tuple[str, ...]) -> None:
        """List the unknown columns and the ones there are.

        Args:
            unknown: The columns asked for that don't exist.
            known: Every column there is.
        """
        super().__init__(f"Unknown stream fields {unknown}; expected any of {list(known)}.")


class WorldNeedsZwift(ServiceError):
    """A Zwift world filter combined with a source other than Zwift."""

    def __init__(self, source: str) -> None:
        """Say which source clashes.

        Args:
            source: The other source asked for.
        """
        super().__init__(
            f"Zwift worlds are for Zwift rides; leave out the source or choose Zwift, not {source}."
        )


class EmptyBikeName(ServiceError):
    """A bike name with nothing but spaces."""

    def __init__(self) -> None:
        """Say what's wrong."""
        super().__init__("Bike names can't be empty.")


class DefaultNotFound(NotFound):
    """No default-bike entry for a kind of ride on a date."""

    def __init__(self, slot: str, day: str) -> None:
        """Say which entry is missing.

        Args:
            slot: The kind of ride.
            day: The entry's date, ``YYYY-MM-DD``.
        """
        super().__init__(f"No {slot} default starts on {day}.")


class AthleteEntryNotFound(NotFound):
    """No athlete history entry on a date."""

    def __init__(self, day: str) -> None:
        """Say which entry is missing.

        Args:
            day: The date, ``YYYY-MM-DD``.
        """
        super().__init__(f"No athlete entry on {day}.")
