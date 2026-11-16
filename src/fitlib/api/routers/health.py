"""``GET /api/health``: whether the server is up and can read the library."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fitlib import __version__
from fitlib.api.deps import StoresDep
from fitlib.ingest.summarize import METRICS_VERSION

router = APIRouter(tags=["health"])


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


@router.get("/health")
def health(stores: StoresDep) -> Health:
    """Report that the server is up, with the library's ride counts.

    Args:
        stores: The library's stores.

    Returns:
        The server's status.
    """
    catalog = stores.catalog
    return Health(
        status="ok",
        version=__version__,
        rides=catalog.count(),
        outdated_rides=len(catalog.ride_ids(below_version=METRICS_VERSION)),
    )
