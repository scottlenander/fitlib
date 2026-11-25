"""The server's health and the library's state."""

from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    """The server's status.

    Attributes:
        status: Always ``"ok"`` when the server answers.
        version: fitlib's version.
        rides: How many rides the library holds.
        outdated_rides: Rides computed with older calculations; ``fitlib recompute`` brings
            them up to date.
    """

    status: str
    version: str
    rides: int
    outdated_rides: int
