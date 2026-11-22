"""Zwift worlds: the names the library's World filter offers."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fitlib.metrics.zwift import WORLDS

router = APIRouter(prefix="/zwift-worlds", tags=["rides"])


class WorldOut(BaseModel):
    """A Zwift world.

    Attributes:
        slug: Its short name, for the rides list's ``world`` filter.
        name: Its name.
    """

    slug: str
    name: str


@router.get("")
def list_worlds() -> list[WorldOut]:
    """List the Zwift worlds rides can be filtered on.

    Returns:
        Every world, in Zwift's order of release.
    """
    return [WorldOut(slug=w.slug, name=w.name) for w in WORLDS]
