"""Ride services: finding, listing, samples, matching, editing and deleting."""

from __future__ import annotations

import pytest

from fitlib.metadata import KEEP, MetaEdit
from fitlib.metrics.zwift import UnknownWorld
from fitlib.models import Filters, Source
from fitlib.services import rides
from fitlib.services.errors import (
    MissingRides,
    NothingToChange,
    UnknownStreamFields,
    WorldNeedsZwift,
)
from tests.unit.conftest import ImportedLibrary

ZWIFT = "2025-08-02-08-29-42.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"
PAUSE = "garmin_nord_pause_10min.fit"
GONE = "00000000-0000-4000-8000-0000000000aa"
ALSO_GONE = "00000000-0000-4000-8000-0000000000bb"


def test_find_rides_lists_every_missing_ride(imported: ImportedLibrary):
    """Asking for several rides reports every one that isn't there, in order.

    Given: Two ids of rides that don't exist around one that does.
    Expect: ``MissingRides`` naming both missing ids, in the order asked.
    """
    with pytest.raises(MissingRides) as caught:
        rides.find_rides(imported.catalog, [GONE, imported.ride(ZWIFT).id, ALSO_GONE])

    assert caught.value.refs == [GONE, ALSO_GONE]


def test_list_narrows_to_a_zwift_world(imported: ImportedLibrary):
    """A world narrows the list to Zwift rides ridden there.

    Given: The fixture library and the world ``watopia``.
    Expect: Only the Zwift fixture ride, with Watopia on its view.
    """
    found = rides.list_rides(imported.stores, Filters(), world="watopia")

    assert [v.ride.source_name for v in found.views] == [ZWIFT]
    assert found.views[0].world == "Watopia"


def test_a_world_with_another_source_or_an_unknown_world_is_refused(imported: ImportedLibrary):
    """A world only goes with Zwift rides, and must be a world.

    Given: Watopia with the Garmin source, and a world that doesn't exist.
    Expect: ``WorldNeedsZwift`` naming the source; ``UnknownWorld``.
    """
    with pytest.raises(WorldNeedsZwift, match="not garmin"):
        rides.list_rides(imported.stores, Filters(source=Source.GARMIN), world="watopia")
    with pytest.raises(UnknownWorld):
        rides.list_rides(imported.stores, Filters(), world="atlantis")


def test_samples_default_to_every_column_but_positions(imported: ImportedLibrary):
    """Samples come back in the columns asked for, else every column but lat and lon.

    Given: A ride, asked for no columns, then for power and positions (power twice).
    Expect: The default has no lat or lon; the request gives t, power, lat, lon in that order.
    """
    ride_id = imported.ride(PAUSE).id

    _, every = rides.ride_streams(imported.stores, ride_id)
    _, chosen = rides.ride_streams(imported.stores, ride_id, ["power", "lat", "lon", "power"])

    assert "lat" not in every.columns and "lon" not in every.columns, (
        "Positions should only be sent when asked for"
    )
    assert chosen.columns == ["t", "power", "lat", "lon"]


def test_unknown_sample_columns_are_refused(imported: ImportedLibrary):
    """Columns that don't exist are named in the error.

    Given: A request for power and ``watts``.
    Expect: ``UnknownStreamFields`` naming ``watts``.
    """
    with pytest.raises(UnknownStreamFields, match="'watts'"):
        rides.ride_streams(imported.stores, imported.ride(PAUSE).id, ["power", "watts"])


def test_similar_routes_and_efforts_come_with_figures(imported: ImportedLibrary):
    """Matches carry each ride's view, and the numbers for their kind of match.

    Given: An outdoor ride on the fixture loop.
    Expect: Route matches have overlaps and no similarity, and the ride has a route; effort
        matches have a similarity and no overlaps.
    """
    ride_id = imported.ride(INTERVALS).id

    by_route = rides.similar(imported.stores, ride_id, "route")
    by_effort = rides.similar(imported.stores, ride_id, "effort")

    assert by_route.has_route
    assert by_route.matches, "Other rides on the fixture loop should match by route"
    assert all(m.overlap is not None and m.similarity is None for m in by_route.matches)
    assert by_effort.matches, "Other rides should match by effort"
    assert all(m.similarity is not None and m.overlap is None for m in by_effort.matches)


def test_route_progress_includes_the_ride_itself(imported: ImportedLibrary):
    """A route's progress lists the ride asked about with the others, oldest first.

    Given: An outdoor ride on the fixture loop.
    Expect: The ride is among the views, which are oldest first.
    """
    ride = imported.ride(INTERVALS)

    progress = rides.route_progress(imported.stores, ride.id)

    starts = [v.ride.summary.start for v in progress.views]
    assert ride.id in {v.ride.id for v in progress.views}
    assert starts == sorted(starts)


def test_editing_several_rides_changes_each_once(imported: ImportedLibrary):
    """A ride named twice is edited once, and comes back once.

    Given: Two rides, the first named twice, given a tag.
    Expect: Two rides back, both tagged.
    """
    first, second = imported.ride(ZWIFT).id, imported.ride(PAUSE).id

    edited = rides.edit_rides(
        imported.stores, [first, second, first], MetaEdit(add_tags=("hills",))
    )

    assert [r.id for r in edited] == [first, second]
    assert all(r.meta.tags == ("hills",) for r in edited)


def test_an_edit_of_several_rides_needs_a_change(imported: ImportedLibrary):
    """An edit that changes nothing is refused before looking at the rides.

    Given: An edit that keeps everything.
    Expect: ``NothingToChange``.
    """
    with pytest.raises(NothingToChange):
        rides.edit_rides(imported.stores, [GONE], MetaEdit(rpe=KEEP))


def test_an_edit_with_a_missing_ride_changes_nothing(imported: ImportedLibrary):
    """All the rides change, or none.

    Given: An effort for one ride that exists and one that doesn't.
    Expect: ``MissingRides``; the ride that exists still has no effort.
    """
    ride_id = imported.ride(ZWIFT).id

    with pytest.raises(MissingRides):
        rides.edit_rides(imported.stores, [ride_id, GONE], MetaEdit(rpe=7))

    assert imported.catalog.get_ride(ride_id).meta.rpe is None, "Nothing should have changed"


def test_deleting_with_a_missing_ride_deletes_nothing(imported: ImportedLibrary):
    """All the rides are deleted, or none.

    Given: A ride that exists and one that doesn't.
    Expect: ``MissingRides``; the ride that exists is still there.
    """
    ride_id = imported.ride(ZWIFT).id

    with pytest.raises(MissingRides):
        rides.delete_rides(imported.stores, [ride_id, GONE])

    assert imported.catalog.get_ride(ride_id), "Nothing should have been deleted"


def test_a_ride_named_twice_is_deleted_once(imported: ImportedLibrary):
    """Deleting the same ride twice in one request deletes it once.

    Given: One ride's id given twice.
    Expect: One ride deleted.
    """
    ride_id = imported.ride(ZWIFT).id

    deleted = rides.delete_rides(imported.stores, [ride_id, ride_id])

    assert [r.id for r in deleted] == [ride_id]
