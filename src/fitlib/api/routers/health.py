"""``GET /api/health``: whether the server is up and can read the library."""

from __future__ import annotations

from fastapi import APIRouter, Request

from fitlib import __version__
from fitlib.api.deps import StoresDep
from fitlib.api.schemas.health import Health, RecomputeProgress
from fitlib.ingest.summarize import METRICS_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, stores: StoresDep) -> Health:
    """Report that the server is up, with the library's ride counts.

    Args:
        request: The current request, whose app holds the background recompute and
            whether it may be stopped.
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
        recompute=RecomputeProgress.of(
            None if (job := request.app.state.recompute) is None else job.state()
        ),
        can_quit=request.app.state.can_quit,
    )
