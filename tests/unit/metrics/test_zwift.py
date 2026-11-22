"""Which Zwift world a ride was in, from its start point."""

from __future__ import annotations

import pytest

from fitlib.metrics.zwift import WORLDS, UnknownWorld, world_at, world_by_slug, zwift_world
from fitlib.models import GeoSummary, Source
from tests.unit.factories import make_summary

WATOPIA_START = GeoSummary(-11.64, 166.95, -11.65, 166.94, -11.63, 166.96)


@pytest.mark.parametrize("world", WORLDS, ids=[w.slug for w in WORLDS])
def test_each_world_holds_its_centre_and_corners(world):
    """A world's centre and corners are in that world and no other.

    Given: each world's box.
    Expect: its centre and its four corners (edges count) found as that world.
    """
    b = world.box
    centre = ((b.min_lat + b.max_lat) / 2, (b.min_lon + b.max_lon) / 2)
    corners = [(b.min_lat, b.min_lon), (b.min_lat, b.max_lon), (b.max_lat, b.min_lon),
               (b.max_lat, b.max_lon)]  # fmt: skip

    for lat, lon in [centre, *corners]:
        assert world_at(lat, lon) == world, f"({lat}, {lon}) should be in {world.name}"


def test_no_two_worlds_overlap():
    """No position can be in two worlds.

    Given: every pair of world boxes.
    Expect: none overlap.
    """
    for i, a in enumerate(WORLDS):
        for b in WORLDS[i + 1 :]:
            apart = (a.box.max_lat < b.box.min_lat or b.box.max_lat < a.box.min_lat
                     or a.box.max_lon < b.box.min_lon or b.box.max_lon < a.box.min_lon)  # fmt: skip
            assert apart, f"{a.name} and {b.name} should not overlap"


@pytest.mark.parametrize(
    ("lat", "lon"),
    [(50.3967, 3.4153), (0.0, 0.0), (-11.6, 166.95), (51.5, -0.18)],
    ids=["nord", "null-island", "just-north-of-watopia", "just-west-of-london"],
)
def test_positions_outside_every_world(lat: float, lon: float):
    """Real rides elsewhere, and positions just outside a box, are in no world.

    Given: the fixture's loop in northern France, 0°/0°, and points just outside Watopia and
    London.
    Expect: no world.
    """
    assert world_at(lat, lon) is None


def test_a_zwift_ride_in_watopia():
    """A Zwift ride starting in Watopia is in Watopia.

    Given: a Zwift ride starting at -11.64, 166.95.
    Expect: Watopia.
    """
    summary = make_summary(source=Source.ZWIFT, indoor=True, geo=WATOPIA_START)

    world = zwift_world(summary)

    assert world is not None and world.name == "Watopia"


@pytest.mark.parametrize(
    ("source", "geo"),
    [(Source.GARMIN, WATOPIA_START), (Source.ZWIFT, None)],
    ids=["not-zwift", "no-positions"],
)
def test_only_zwift_rides_with_positions_have_a_world(source: Source, geo):
    """Other sources, and Zwift rides without positions, have no world.

    Given: a Garmin ride starting in Watopia's box; a Zwift ride without positions.
    Expect: no world for either.
    """
    assert zwift_world(make_summary(source=source, geo=geo)) is None


def test_worlds_by_slug():
    """Worlds are found by their short name, in any case; unknown names are refused.

    Given: "Makuri-Islands", then "atlantis".
    Expect: Makuri Islands; then ``UnknownWorld`` listing the worlds.
    """
    assert world_by_slug("Makuri-Islands").name == "Makuri Islands"
    with pytest.raises(UnknownWorld, match="watopia"):
        world_by_slug("atlantis")
