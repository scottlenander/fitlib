"""``GET /api/health``: whether the server is up and can read the library."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fitlib import __version__
from fitlib.api.deps import StoresDep

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """The server's status.

    Attributes:
        status: Always ``"ok"`` when the server answers.
        version: fitlib's version.
        rides: How many rides the library holds.
    """

    status: str
    version: str
    rides: int


@router.get("/health")
def health(stores: StoresDep) -> Health:
    """Report that the server is up, with the library's ride count.

    Args:
        stores: The library's stores.

    Returns:
        The server's status.
    """
    return Health(status="ok", version=__version__, rides=stores.catalog.count())
