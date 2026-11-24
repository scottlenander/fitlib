"""Deleting rides, and importing their files again afterwards."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fitlib.importer import Importer
from fitlib.services.deleting import delete_rides
from fitlib.store.interfaces import RideNotFound
from fitlib.store.streams import raw_key
from tests.fixtures.generate import FIT_DIR
from tests.unit.conftest import ImportedLibrary

RIDE = "garmin_nord_intervals_5x4.fit"
OTHER = "garmin_indoor_no_hr.fit"
ZIPPED = "garmin_export.zip:garmin_export_ride_a.fit"


def importer(lib: ImportedLibrary) -> Importer:
    """An importer over the library's stores, in this process.

    Args:
        lib: The library.

    Returns:
        The importer.
    """
    return Importer(lib.catalog, lib.blobs, lib.streams, workers=1)


def test_delete_removes_the_ride_its_stream_and_its_file(imported: ImportedLibrary):
    """Deleting a ride removes its entry, stream and original file; other rides stay.

    Given: The fixture library, with one ride deleted.
    Expect: The ride is returned; it's gone from the catalog; its stream and raw file are
        gone; another ride's stream and file are still there.
    """
    ride, other = imported.ride(RIDE), imported.ride(OTHER)
    count = imported.catalog.count()

    (removed,) = delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id])

    assert removed.id == ride.id
    assert imported.catalog.count() == count - 1
    with pytest.raises(RideNotFound):
        imported.catalog.get_ride(ride.id)
    assert not imported.blobs.exists(raw_key(ride.sha256))
    assert not any(ride.id in k for k in imported.blobs.list()), "should remove its stream"
    assert imported.blobs.exists(raw_key(other.sha256))
    assert imported.streams.get(other.id, other.summary.start).height > 0


def test_unknown_ride_deletes_nothing(imported: ImportedLibrary):
    """An unknown id among several leaves every ride, stream and file in place.

    Given: A real ride and an unknown id.
    Expect: ``RideNotFound``, and the same rides and blobs as before.
    """
    ride = imported.ride(RIDE)
    blobs = imported.blobs.list()
    count = imported.catalog.count()

    with pytest.raises(RideNotFound):
        delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id, "no-such-ride"])

    assert imported.catalog.count() == count
    assert imported.blobs.list() == blobs


def test_importing_a_deleted_ride_again_skips_it(imported: ImportedLibrary):
    """A deleted ride's file is skipped on import, with when it was deleted.

    Given: A ride deleted, then its file imported again.
    Expect: Nothing imported; the file listed as deleted, with today's date; the ride still
        gone.
    """
    ride = imported.ride(RIDE)
    delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id])

    report = importer(imported).run([FIT_DIR / RIDE])

    today = datetime.now(UTC).date()
    assert report.imported == []
    assert report.deleted == [(RIDE, f"You deleted this ride on {today:%Y-%m-%d}")]
    assert imported.catalog.find_by_hash(ride.sha256) is None


def test_include_deleted_brings_a_ride_back_for_good(imported: ImportedLibrary):
    """``include_deleted`` brings the ride back; later imports treat it as normal again.

    Given: A ride deleted, imported with ``include_deleted``, then imported again normally.
    Expect: The first import adds it (with a new id and its stream and file); the second
        finds it a duplicate.
    """
    ride = imported.ride(RIDE)
    delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id])

    back = importer(imported).run([FIT_DIR / RIDE], include_deleted=True)
    again = importer(imported).run([FIT_DIR / RIDE])

    ((_, new_id),) = back.imported
    assert new_id != ride.id
    assert imported.blobs.exists(raw_key(ride.sha256))
    assert [name for name, _ in again.duplicates] == [RIDE]
    assert again.deleted == []


def test_deleted_ride_inside_a_zip_is_skipped(imported: ImportedLibrary):
    """A deleted ride is skipped when its file comes back inside a zip (a Garmin export).

    Given: One of the zip's rides deleted, then the zip imported again.
    Expect: That ride listed as deleted; the zip's other ride a duplicate.
    """
    ride = imported.ride(ZIPPED)
    delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id])

    report = importer(imported).run([FIT_DIR / "garmin_export.zip"])

    assert [name for name, _ in report.deleted] == [ZIPPED]
    assert len(report.duplicates) == 1
    assert report.total == 2


def test_test_set_up_delete_leaves_the_ride_importable(imported: ImportedLibrary):
    """Deleting without remembering (test set-up) lets the file import as new.

    Given: A ride deleted with ``remember=False``, then its file imported.
    Expect: Imported again, nothing listed as deleted.
    """
    ride = imported.ride(RIDE)
    delete_rides(imported.catalog, imported.blobs, imported.streams, [ride.id], remember=False)

    report = importer(imported).run([FIT_DIR / RIDE])

    assert [name for name, _ in report.imported] == [RIDE]
    assert report.deleted == []
