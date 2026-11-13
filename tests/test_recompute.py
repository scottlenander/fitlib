"""Recomputing rides from their archived original files."""

from __future__ import annotations

from dataclasses import replace

from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.models import RideMeta
from fitlib.recompute import Recomputer
from fitlib.store.streams import raw_key
from tests.conftest import ImportedLibrary

ZWIFT = "zwift_watopia_steady_60min.fit"


def downgrade(lib: ImportedLibrary, file_name: str) -> str:
    """Make a ride look like phase 1a left it: version 1, no training figures, with notes.

    Args:
        lib: The imported library.
        file_name: The fixture file the ride came from.

    Returns:
        The ride's id.
    """
    ride = lib.ride(file_name)
    old = replace(ride.summary, np=None, kj=None, power_curve=(), power_histogram=())
    lib.catalog.replace_summary(ride.id, old, metrics_version=1)
    # Set metadata directly: the catalog's update_meta arrives in phase 1c.
    lib.catalog._rides[ride.id] = replace(
        lib.catalog.get_ride(ride.id), meta=RideMeta(notes="keep me", tags=("z2",))
    )
    return ride.id


def recomputer(lib: ImportedLibrary) -> Recomputer:
    """Build a recomputer for a library that runs in this process.

    Args:
        lib: The imported library.

    Returns:
        The recomputer.
    """
    return Recomputer(lib.catalog, lib.blobs, lib.streams, workers=1)


def test_outdated_rides_are_found_and_brought_up_to_date(imported: ImportedLibrary):
    """Rides computed with older calculations are recomputed from their raw files.

    Given: the imported fixtures with the Zwift ride downgraded to version 1 (no NP, no
    curve) and given notes and a tag.
    Expect: it is the only outdated ride; after recompute it is at the current version with
    NP 200 W and a power curve again, and its notes, tags, id and import time are unchanged.
    """
    ride_id = downgrade(imported, ZWIFT)
    before = imported.catalog.get_ride(ride_id)
    rc = recomputer(imported)

    outdated = rc.outdated()
    report = rc.run(outdated)
    after = imported.catalog.get_ride(ride_id)

    assert outdated == [ride_id], "only the downgraded ride should be outdated"
    assert report.updated == [ride_id] and report.failed == []
    assert after.metrics_version == METRICS_VERSION
    assert after.summary.np == 200 and after.summary.power_curve != ()
    assert after.meta == before.meta, "notes and tags should survive a recompute"
    assert (after.id, after.imported_at) == (before.id, before.imported_at)
    assert rc.outdated() == [], "nothing should be outdated afterwards"


def test_recompute_replaces_the_stream(imported: ImportedLibrary):
    """A recomputed ride's stream is rewritten too.

    Given: the Zwift ride with its stream deleted.
    Expect: after recompute, the stream is back with one row per second (3600).
    """
    ride = imported.ride(ZWIFT)
    imported.streams.delete(ride.id, ride.summary.start)

    recomputer(imported).run([ride.id])

    assert imported.streams.get(ride.id, ride.summary.start).height == 3600


def test_missing_original_file_is_reported(imported: ImportedLibrary):
    """A ride whose original file is gone can't be recomputed, and the others still are.

    Given: two rides; the first one's raw file deleted.
    Expect: the first reported as failed (original missing), the second updated.
    """
    first = imported.ride(ZWIFT)
    second = imported.ride("garmin_nord_pause_10min.fit")
    imported.blobs.delete(raw_key(first.sha256))

    report = recomputer(imported).run([first.id, second.id])

    assert report.failed == [(first.id, "the original file is missing")]
    assert report.updated == [second.id]
