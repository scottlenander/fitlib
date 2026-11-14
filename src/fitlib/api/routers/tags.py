"""``GET /api/tags``: the tags in use."""

from __future__ import annotations

from fastapi import APIRouter

from fitlib.api.deps import StoresDep
from fitlib.api.schemas import TagCount

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("")
def list_tags(stores: StoresDep) -> list[TagCount]:
    """List every tag in use with how many rides have it.

    Args:
        stores: The library's stores.

    Returns:
        The tags, as the catalog orders them.
    """
    return [TagCount(name=name, rides=rides) for name, rides in stores.catalog.tag_counts()]
