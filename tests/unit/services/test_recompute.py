"""Recomputing rides from their archived original files."""

from __future__ import annotations

import threading
from contextlib import nullcontext
from dataclasses import replace

import pytest

from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.models import OffsetSource, RideMeta
from fitlib.services import recompute as recompute_module
from fitlib.services.recompute import BackgroundRecompute, Recomputer, RecomputeState
from fitlib.store.streams import raw_key, stream_key
from tests.unit.conftest import ImportedLibrary

ZWIFT = "2025-08-02-08-29-42.fit"


def downgrade(lib: ImportedLibrary, file_name: str) -> str:
    """Make a ride look like phase 1a left it: version 1, no training figures or route, with notes.

    Args:
        lib: The imported library.
        file_name: The fixture file the ride came from.

    Returns:
        The ride's id.
    """
    ride = lib.ride(file_name)
    old = replace(ride.summary, np=None, kj=None, power_curve=(), power_histogram=())
    lib.catalog.replace_summary(ride.id, old, metrics_version=1)
    lib.catalog.update_meta(ride.id, RideMeta(notes="keep me", tags=("z2",)))
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
    curve, no route cells) and given notes and a tag.
    Expect: it is the only outdated ride; after recompute it is at the current version with
    NP 200 W, a power curve and route cells again, and its notes, tags, id and import time
    are unchanged.
    """
    ride_id = downgrade(imported, ZWIFT)
    before = imported.catalog.get_ride(ride_id)
    route_before = imported.catalog.route_cells(ride_id)
    rc = recomputer(imported)

    outdated = rc.outdated()
    report = rc.run(outdated)
    after = imported.catalog.get_ride(ride_id)

    assert route_before == frozenset(), "the downgraded ride should have no route cells"
    assert outdated == [ride_id], "only the downgraded ride should be outdated"
    assert report.updated == [ride_id] and report.failed == []
    assert after.metrics_version == METRICS_VERSION
    assert after.summary.np == 200 and after.summary.power_curve != ()
    assert imported.catalog.route_cells(ride_id), "recompute should add the route cells"
    assert after.meta == before.meta, "notes and tags should survive a recompute"
    assert (after.id, after.imported_at) == (before.id, before.imported_at)
    assert rc.outdated() == [], "nothing should be outdated afterwards"


def test_recompute_repairs_a_zwift_ride_dated_1989(imported: ImportedLibrary):
    """A Zwift ride imported before version 4 took Zwift's 1989 local time; recompute fixes it.

    Given: the Zwift ride stored at version 3 with the offset older versions worked out from
        its 1989-12-31 local time (about -35 years), so it showed as 30 Dec 1989.
    Expect: it is outdated; after recompute its time zone comes from its file name
        (2025-08-02-08-29-42, CEST: +2 h) and it is dated 2 Aug 2025.
    """
    ride = imported.ride(ZWIFT)
    broken = replace(ride.summary, utc_offset_s=-1_123_054_200)
    imported.catalog.replace_summary(ride.id, broken, metrics_version=3)
    rc = recomputer(imported)

    outdated = rc.outdated()
    rc.run(outdated)
    after = imported.catalog.get_ride(ride.id)

    assert broken.local_start is not None and broken.local_start.year == 1989
    assert outdated == [ride.id]
    assert after.summary.utc_offset_s == 2 * 3600
    assert after.summary.utc_offset_source == OffsetSource.FILE_NAME
    assert after.display_name == "Zwift 2025-08-02 08:30"


def test_recompute_gives_a_zwift_ride_its_distance(imported: ImportedLibrary):
    """A Zwift ride imported before version 5 had no distance; recompute adds it from speed.

    Given: the Zwift ride stored at version 4 with no distance (as Zwift's rare odometer
        readings left it) and a stream without distance.
    Expect: it is outdated; after recompute its distance is about 33.4 km and its stream has
        a distance every riding second.
    """
    ride = imported.ride(ZWIFT)
    imported.catalog.replace_summary(
        ride.id, replace(ride.summary, distance_m=None, avg_speed_mps=None), metrics_version=4
    )
    stream = imported.streams.get(ride.id, ride.summary.start)
    imported.streams.put(ride.id, ride.summary.start, stream.with_columns(distance=None))
    rc = recomputer(imported)

    outdated = rc.outdated()
    rc.run(outdated)
    after = imported.catalog.get_ride(ride.id)
    distance = imported.streams.get(ride.id, ride.summary.start)["distance"]

    assert outdated == [ride.id]
    assert after.summary.distance_m is not None
    assert round(after.summary.distance_m / 1000, 1) == 33.4
    assert distance.null_count() == 0, "every riding second should have a distance"


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


def test_stopping_starts_no_more_rides(imported: ImportedLibrary):
    """Once asked to stop, the recompute starts no more rides, and the rest stay outdated.

    Given: two downgraded rides; ``should_stop`` false before the first, true before the second.
    Expect: the first updated; the second not touched and still outdated.
    """
    first = downgrade(imported, ZWIFT)
    second = downgrade(imported, "garmin_nord_pause_10min.fit")
    answers = iter([False, True])
    rc = recomputer(imported)

    report = rc.run([first, second], should_stop=lambda: next(answers))

    assert report.updated == [first]
    assert rc.outdated() == [second], "the ride not started should still be outdated"


def test_a_ride_deleted_before_its_turn_is_skipped(imported: ImportedLibrary):
    """A ride deleted before the recompute reaches it is counted as gone, not as a failure.

    Given: two rides, the first deleted before the run.
    Expect: the first in ``gone`` (and reported to ``on_progress``), the second updated.
    """
    first = imported.ride(ZWIFT).id
    second = imported.ride("garmin_nord_pause_10min.fit").id
    imported.catalog.delete_rides([first], remember=False)
    handled: list[str] = []

    report = recomputer(imported).run([first, second], on_progress=handled.append)

    assert report.gone == [first]
    assert (report.updated, report.failed) == ([second], [])
    assert handled == [first, second], "progress should count the deleted ride too"


def test_a_ride_deleted_while_being_worked_out_is_skipped(imported: ImportedLibrary):
    """A ride deleted after its file was read leaves no stream behind.

    Given: two rides worked out in this process; the second deleted from the catalog as soon
    as the first has been stored (both are already read by then).
    Expect: the second in ``gone`` and its new stream removed; the first updated.
    """
    first = imported.ride(ZWIFT)
    second = imported.ride("garmin_nord_pause_10min.fit")

    def delete_second(ride_id: str) -> None:
        if ride_id == first.id:
            imported.catalog.delete_rides([second.id], remember=False)

    report = recomputer(imported).run([first.id, second.id], on_progress=delete_second)

    assert report.updated == [first.id]
    assert report.gone == [second.id]
    assert not imported.blobs.exists(stream_key(second.id, second.summary.start)), (
        "the deleted ride's new stream should be removed"
    )


class Gate:
    """Holds up the first ride's figures until released, so a test can look mid-run.

    Attributes:
        entered: Set once the first ride is being worked out.
        release: Set by the test to let it finish.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self._first = True

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Wrap ``analyse`` so its first call waits for ``release``.

        Args:
            monkeypatch: Pytest's monkeypatch fixture.
        """
        real = recompute_module.analyse

        def gated(*args, **kwargs):
            if self._first:
                self._first = False
                self.entered.set()
                assert self.release.wait(10), "the test should release the gate"
            return real(*args, **kwargs)

        monkeypatch.setattr(recompute_module, "analyse", gated)


def background(lib: ImportedLibrary) -> BackgroundRecompute:
    """Build a background recompute over a library, working out rides in its thread.

    Args:
        lib: The imported library.

    Returns:
        The background recompute, not started.
    """
    return BackgroundRecompute(lambda: nullcontext(lib.stores), workers=1)


def test_background_recompute_brings_outdated_rides_up_to_date(
    imported: ImportedLibrary, monkeypatch: pytest.MonkeyPatch
):
    """The server's background recompute updates every outdated ride and reports progress.

    Given: two downgraded rides; the first ride held up mid-run.
    Expect: progress 0 of 2 while held; once released, both rides current and no progress
    reported any more.
    """
    downgrade(imported, ZWIFT)
    downgrade(imported, "garmin_nord_pause_10min.fit")
    gate = Gate()
    gate.install(monkeypatch)
    job = background(imported)

    job.start()
    assert gate.entered.wait(10), "the first ride should be started"
    during = job.state()
    gate.release.set()
    finished = job.wait(10)

    assert during == RecomputeState(total=2, done=0)
    assert finished, "the recompute should finish"
    assert job.state() is None, "a finished recompute should report no progress"
    assert recomputer(imported).outdated() == []


def test_background_recompute_with_nothing_to_do(imported: ImportedLibrary):
    """A library with every ride current needs no recompute.

    Given: the imported fixtures, all current.
    Expect: the recompute finishes at once and never reports progress.
    """
    job = background(imported)

    job.start()

    assert job.wait(10), "the recompute should finish"
    assert job.state() is None


def test_stopping_the_background_recompute_leaves_the_rest_for_next_time(
    imported: ImportedLibrary, monkeypatch: pytest.MonkeyPatch
):
    """Stopping the server partway keeps the rides done and leaves the rest outdated.

    Given: two downgraded rides; the recompute asked to stop while the first is held up.
    Expect: the first ride current, the second still outdated.
    """
    first = downgrade(imported, ZWIFT)
    second = downgrade(imported, "garmin_nord_pause_10min.fit")
    gate = Gate()
    gate.install(monkeypatch)
    job = background(imported)

    job.start()
    assert gate.entered.wait(10), "the first ride should be started"
    job.stop(timeout=0)
    gate.release.set()

    assert job.wait(10), "the recompute should finish"
    assert recomputer(imported).outdated() == [second]
    assert imported.catalog.get_ride(first).metrics_version == METRICS_VERSION
