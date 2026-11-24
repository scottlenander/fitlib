"""Which Zwift world a ride was in, from where it started.

Zwift records positions on Earth: some worlds sit on the real city they show (London, New
York, Paris...), the made-up ones on small Pacific islands (Watopia on Teanu, in the Solomon
Islands). Each world fits in a box of latitude and longitude, so a ride's start point gives
its world.

The boxes are from zwift-data (https://github.com/andipaetzold/zwift-data), under the MIT
License:

    Copyright (c) 2021 Andi Pätzold

    Permission is hereby granted, free of charge, to any person obtaining a copy of this
    software and associated documentation files (the "Software"), to deal in the Software
    without restriction, including without limitation the rights to use, copy, modify, merge,
    publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
    to whom the Software is furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all copies or
    substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
    INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
    PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
    FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
    OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from dataclasses import dataclass

from fitlib.models import Box, RideSummary, Source


@dataclass(frozen=True)
class World:
    """A Zwift world.

    Attributes:
        slug: Its short name, e.g. ``"makuri-islands"``.
        name: Its name, e.g. ``"Makuri Islands"``.
        box: Where its positions lie.
    """

    slug: str
    name: str
    box: Box


def _world(slug: str, name: str, corner: tuple[float, float], other: tuple[float, float]) -> World:
    """Build a world from two opposite corners of its box, in either order.

    Args:
        slug: Its short name.
        name: Its name.
        corner: One corner, (latitude, longitude).
        other: The opposite corner.

    Returns:
        The world.
    """
    (lat1, lon1), (lat2, lon2) = corner, other
    box = Box(min(lat1, lat2), min(lon1, lon2), max(lat1, lat2), max(lon1, lon2))
    return World(slug, name, box)


WORLDS: tuple[World, ...] = (
    _world("watopia", "Watopia", (-11.62597, 166.87747), (-11.74087, 167.03255)),
    _world("richmond", "Richmond", (37.5774, -77.48954), (37.5014, -77.394)),
    _world("london", "London", (51.5362, -0.1776), (51.4601, -0.0555)),
    _world("new-york", "New York", (40.817257, -74.022655), (40.587913, -73.922165)),
    _world("innsbruck", "Innsbruck", (47.2947, 11.3501), (47.2055, 11.4822)),
    _world("bologna", "Bologna", (44.5308037, 11.26261748), (44.45463821, 11.36991729102076)),
    _world("yorkshire", "Yorkshire", (54.0254, -1.632), (53.9491, -1.5022)),
    _world("crit-city", "Crit City", (-10.3657, 165.7824), (-10.4038, 165.8207)),
    _world("makuri-islands", "Makuri Islands", (-10.73746, 165.76591), (-10.85234, 165.88222)),
    _world("france", "France", (-21.64155, 166.1384), (-21.7564, 166.26125)),
    _world("paris", "Paris", (48.9058, 2.2561), (48.82945, 2.3722)),
    _world("scotland", "Scotland", (55.67595, -5.2802), (55.61845, -5.17798)),
)

_BY_SLUG = {w.slug: w for w in WORLDS}


class UnknownWorld(ValueError):
    """A Zwift world name that isn't one of ``WORLDS``."""

    def __init__(self, slug: str) -> None:
        """Say which name wasn't known, and which are.

        Args:
            slug: The name given.
        """
        names = ", ".join(w.slug for w in WORLDS)
        super().__init__(f"No Zwift world called {slug!r}. Worlds: {names}.")


def world_by_slug(slug: str) -> World:
    """Find a world by its short name.

    Args:
        slug: E.g. ``"watopia"`` (any case).

    Returns:
        The world.

    Raises:
        UnknownWorld: No world has that name.
    """
    try:
        return _BY_SLUG[slug.strip().lower()]
    except KeyError:
        raise UnknownWorld(slug) from None


def world_at(lat: float, lon: float) -> World | None:
    """Find the world whose box holds a position.

    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.

    Returns:
        The world, or ``None`` if the position is in none of them.
    """
    return next((w for w in WORLDS if w.box.contains(lat, lon)), None)


def zwift_world(summary: RideSummary) -> World | None:
    """The Zwift world a ride was in.

    Args:
        summary: The ride's summary.

    Returns:
        The world its start point is in, for Zwift rides with positions; else ``None``.
    """
    if summary.source is not Source.ZWIFT or summary.geo is None:
        return None
    return world_at(summary.geo.start_lat, summary.geo.start_lon)
