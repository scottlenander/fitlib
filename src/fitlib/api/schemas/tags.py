"""Tags in use."""

from __future__ import annotations

from pydantic import BaseModel


class TagCount(BaseModel):
    """A tag in use.

    Attributes:
        name: The tag.
        rides: How many rides have it.
    """

    name: str
    rides: int
