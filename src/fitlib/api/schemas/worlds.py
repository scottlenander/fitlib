"""Zwift worlds."""

from __future__ import annotations

from pydantic import BaseModel


class WorldOut(BaseModel):
    """A Zwift world.

    Attributes:
        slug: Its short name, for the rides list's ``world`` filter.
        name: Its name.
    """

    slug: str
    name: str
