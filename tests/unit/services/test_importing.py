"""Importing the fixture folder end to end into in-memory (and SQLite) stores."""

from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from fitlib.models import Bike, BikeDefault, BikeSlot, OffsetSource, Ride, Source
from fitlib.services.importing import Importer, ImportReport, overlap_fraction
from fitlib.store.interfaces import BlobStore, CatalogStore
from fitlib.store.local import FsBlobStore, SqliteCatalog
from fitlib.store.memory import MemoryBlobStore, MemoryCatalog
from fitlib.store.settings import DEFAULT_TIME_ZONE
from fitlib.store.streams import StreamStore, raw_key
from tests.fixtures.generate import FIT_DIR
from tests.fixtures.specs import RIDES, ride
from tests.unit.factories import make_summary

IMPORTED = sorted(
    f"{s.zip_name}.zip:{s.fit_name}" if s.zip_name else s.fit_name
    for s in RIDES
    if s.sport == "cycling" and s.name != "zwift_watopia_steady_60min_head_unit"
)
NOW = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)


@dataclass
class Library:
    """A set of stores to import into.

    Attributes:
        catalog: The rides.
        blobs: Original files and streams.
        streams: Streams, on top of ``blobs``.
    """

    catalog: CatalogStore
    blobs: BlobStore
    streams: StreamStore

    def importer(self, workers: int = 1) -> Importer:
        """Build an importer for these stores, with a fixed clock.

        Args:
            workers: Decoding processes; 1 runs everything in this process.

        Returns:
            The importer.
        """
        return Importer(self.catalog, self.blobs, self.streams, workers=workers, clock=lambda: NOW)

    def ride_from(self, file_name: str, report: ImportReport) -> Ride:
        """Look up the ride an import created from a file.

        Args:
            file_name: The file's display name in the report.
            report: The import's report.

        Returns:
            The ride, loaded from the catalog.
        """
        ride_id = dict(report.imported)[file_name]
        return self.catalog.get_ride(ride_id)


@pytest.fixture
def library() -> Library:
    """Provide empty in-memory stores.

    Returns:
        The stores.
    """
    blobs = MemoryBlobStore()
    return Library(MemoryCatalog(), blobs, StreamStore(blobs))


def test_importing_the_fixture_folder(library: Library):
    """Every kind of file in the folder gets the right outcome.

    Given: the fixture folder (8 importable rides incl. two in a zip, a byte-identical copy,
    a run, a second recording of the Zwift ride, and a truncated file).
    Expect: the 9 rides imported; the copy a duplicate; the run and the second recording
    skipped with reasons; the truncated file failed with a reason.
    """
    report = library.importer().run([FIT_DIR])
    zwift_id = dict(report.imported)["2025-08-02-08-29-42.fit"]

    assert sorted(name for name, _ in report.imported) == IMPORTED
    assert report.duplicates == [
        ("garmin_nord_intervals_5x4_copy.fit", "same file as garmin_nord_intervals_5x4.fit")
    ]
    assert report.skipped == [
        ("garmin_nord_run_20min.fit", "not a ride (running)"),
        ("zwift_watopia_steady_60min_head_unit.fit", f"overlaps ride {zwift_id[:8]}"),
    ], "the run and the second recording of the Zwift ride should be skipped"
    assert [name for name, _ in report.failed] == ["corrupt_truncated.fit"]
    assert "not a readable FIT file" in report.failed[0][1]
    assert library.catalog.count() == 9


def test_reimporting_imports_nothing(library: Library):
    """Running the same import again is safe: files already imported are duplicates.

    Given: the fixture folder imported once.
    Expect: a second run imports 0 rides; the 9 rides and the copy are duplicates; the
    catalog still holds 9 rides.
    """
    library.importer().run([FIT_DIR])

    again = library.importer().run([FIT_DIR])

    assert again.imported == [], "nothing should be imported twice"
    assert len(again.duplicates) == 10, "9 imported rides plus the byte-identical copy"
    assert library.catalog.count() == 9


def test_raw_files_and_streams_are_stored(library: Library):
    """Each imported ride keeps its original file and its 1 Hz stream.

    Given: the fixture folder imported.
    Expect: a raw blob per imported ride plus one for the skipped second recording (archived
    so nothing is lost); a stream per imported ride whose length is the ride's elapsed time.
    """
    report = library.importer().run([FIT_DIR])
    rides = [library.catalog.get_ride(ride_id) for _, ride_id in report.imported]

    raw = library.blobs.list("raw/")
    streams = library.blobs.list("streams/")

    assert len(raw) == 10, "9 imported rides + the archived overlapping recording"
    assert all(library.blobs.exists(raw_key(r.sha256)) for r in rides)
    assert len(streams) == 9
    for r in rides:
        frame = library.streams.get(r.id, r.summary.start)
        assert frame.height == r.summary.elapsed_s, f"stream length for {r.source_name}"


def test_imported_rides_are_summarised(library: Library):
    """Imported rides carry their summary, source, device, name and import details.

    Given: the fixture folder imported at a fixed clock time.
    Expect: the Zwift ride: Zwift, indoor, 1 h at 200 W, default name; the paused Garmin ride:
    outdoor, local time CEST, 40 min elapsed and 30 min moving; the zipped ride named after
    its member file.
    """
    report = library.importer().run([FIT_DIR])

    zwift = library.ride_from("2025-08-02-08-29-42.fit", report)
    paused = library.ride_from("garmin_nord_pause_10min.fit", report)
    zipped = library.ride_from("garmin_export.zip:garmin_export_ride_a.fit", report)

    assert (zwift.summary.source, zwift.summary.indoor) == (Source.ZWIFT, True)
    assert (zwift.summary.moving_s, zwift.summary.avg_power) == (3600, 200)
    assert zwift.display_name == "Zwift 2025-08-02 08:30"
    assert zwift.imported_at == NOW
    assert paused.summary.device == "Garmin Edge 540"
    assert paused.summary.utc_offset_s == 7200, "Garmin rides record local time (CEST)"
    assert (paused.summary.elapsed_s, paused.summary.moving_s) == (2400, 1800)
    assert zipped.source_name == "garmin_export_ride_a.fit", "zip members keep their own name"


def test_progress_is_reported_once_per_file(library: Library):
    """The progress callback fires once for every file found, whatever its outcome.

    Given: the fixture folder (12 files including the two zip members).
    Expect: 12 calls, one per file name.
    """
    seen: list[str] = []

    report = library.importer().run([FIT_DIR], on_progress=seen.append)

    assert sorted(seen) == sorted(
        [n for n, _ in report.imported]
        + [n for n, _ in report.duplicates]
        + [n for n, _ in report.skipped]
        + [n for n, _ in report.failed]
    )
    assert len(seen) == 13


def test_process_pool_gives_the_same_result(library: Library):
    """Decoding in several processes changes nothing about the outcome.

    Given: the fixture folder imported with 2 worker processes.
    Expect: the same imported, duplicate, skipped and failed files as with one worker.
    """
    inline = Library(MemoryCatalog(), blobs := MemoryBlobStore(), StreamStore(blobs))
    expected = inline.importer(workers=1).run([FIT_DIR])

    pooled = library.importer(workers=2).run([FIT_DIR])

    assert [n for n, _ in pooled.imported] == [n for n, _ in expected.imported]
    assert pooled.duplicates == expected.duplicates
    assert [n for n, _ in pooled.skipped] == [n for n, _ in expected.skipped]
    assert pooled.failed == expected.failed


def test_first_recording_of_a_ride_is_kept(tmp_path: Path, library: Library):
    """When two files record the same ride, whichever is imported first stays in the library.

    Given: the Garmin head-unit recording imported on its own first, then the Zwift ride
    (same ride, starting 30 s earlier).
    Expect: the Garmin recording is kept and the Zwift file is skipped as overlapping it.
    """
    garmin = library.importer().run([FIT_DIR / "zwift_watopia_steady_60min_head_unit.fit"])
    garmin_id = garmin.imported[0][1]

    zwift = library.importer().run([FIT_DIR / "2025-08-02-08-29-42.fit"])

    assert zwift.imported == []
    assert zwift.skipped == [("2025-08-02-08-29-42.fit", f"overlaps ride {garmin_id[:8]}")]


@pytest.mark.parametrize(
    ("offset_s", "length_s", "expected"),
    [(30, 3600, 3570 / 3600), (0, 1800, 1.0), (3600, 3600, 0.0), (-60, 600, 540 / 600)],
    ids=["30s-later", "inside", "back-to-back", "earlier-and-shorter"],
)
def test_overlap_fraction(offset_s: int, length_s: int, expected: float):
    """Overlap is the shared time as a fraction of the shorter ride.

    Given: a 1-hour ride and a second ride starting ``offset_s`` later, lasting ``length_s``.
    Expect: shared seconds / the shorter ride's length.
    """
    first = make_summary(elapsed_s=3600)
    second = make_summary(start=first.start + timedelta(seconds=offset_s), elapsed_s=length_s)

    assert overlap_fraction(first, second) == pytest.approx(expected)


def test_failed_catalog_write_leaves_no_stream(library: Library):
    """If the catalog can't store a ride, its stream is removed again.

    Given: a catalog whose ``add_ride`` raises, and one fixture file to import.
    Expect: the error propagates and no stream blob is left behind.
    """

    class BrokenCatalog(MemoryCatalog):
        """A catalog whose writes always fail, to test clean-up after a failed write."""

        def add_ride(self, ride, route=frozenset()):
            """Fail as a full disk would.

            Args:
                ride: The ride that would have been stored.
                route: Its route fingerprint.

            Raises:
                RuntimeError: Always.
            """
            raise RuntimeError("disk full")

    broken = Library(BrokenCatalog(), library.blobs, library.streams)

    with pytest.raises(RuntimeError, match="disk full"):
        broken.importer().run([FIT_DIR / "garmin_nord_pause_10min.fit"])

    assert library.blobs.list("streams/") == [], "the orphaned stream should be deleted"


def test_import_into_sqlite_and_files(tmp_path: Path):
    """The real local backend imports the same way and keeps everything on disk.

    Given: a SQLite catalog and filesystem blobs in a temp library; the two zipped rides.
    Expect: both imported, readable after reopening the catalog, with their files on disk.
    """
    blobs = FsBlobStore(tmp_path / "blobs")
    catalog = SqliteCatalog(tmp_path / "catalog.sqlite3")
    report = Importer(catalog, blobs, StreamStore(blobs), workers=1).run(
        [FIT_DIR / "garmin_export.zip"]
    )
    catalog.close()

    reopened = SqliteCatalog(tmp_path / "catalog.sqlite3")
    count = reopened.count()
    reopened.close()

    assert len(report.imported) == 2
    assert count == 2, "rides should still be there after reopening"
    assert len(list((tmp_path / "blobs" / "streams").rglob("*.parquet"))) == 2


def test_logs_never_contain_coordinates(library: Library, caplog: pytest.LogCaptureFixture):
    """Location is sensitive, so import logging never prints coordinates.

    Given: the fixture folder imported with logging at INFO (outdoor rides loop near
    50.39°N 3.41°E, Zwift near -11.64°, 166.95°).
    Expect: log lines for every file, none containing those coordinates.
    """
    caplog.set_level(logging.INFO, logger="fitlib")
    centres = {ride("garmin_nord_pause_10min").loop, ride("zwift_watopia_steady_60min").loop}

    library.importer().run([FIT_DIR])

    text = caplog.text
    assert "imported:" in text, "imports should be logged"
    for loop in centres:
        for value in (loop.center_lat, loop.center_lon):
            assert f"{value:.2f}" not in text, f"coordinate {value:.2f} should not be logged"


def test_unreadable_files_do_not_stop_the_import(tmp_path: Path, library: Library):
    """One bad file is reported and the rest still import.

    Given: a folder with an empty .fit file, a text file renamed .fit, and one good ride.
    Expect: the good ride imported; both bad files failed.
    """
    (tmp_path / "a_empty.fit").write_bytes(b"")
    (tmp_path / "b_text.fit").write_text("not a fit file")
    shutil.copy(FIT_DIR / "garmin_nord_pause_10min.fit", tmp_path / "c_good.fit")

    report = library.importer().run([tmp_path])

    assert [n for n, _ in report.imported] == ["c_good.fit"]
    assert [n for n, _ in report.failed] == ["a_empty.fit", "b_text.fit"]


def test_new_rides_get_the_dated_default_bike(library: Library):
    """Imported rides get the default bike for their kind and local date.

    Given: outdoor defaults Giant from 1 Jan and Tarmac from 10 Aug 2025, a Zwift default
    Kickr, and no indoor default; then the fixture folder imported.
    Expect: the 5 Aug outdoor ride on the Giant, the 12 Aug one on the Tarmac, the Zwift ride
    on the Kickr, and the Garmin indoor ride with no bike.
    """
    bikes = {name: Bike(id=f"b100000{i}-0000-4000-8000-000000000000", name=name)
             for i, name in enumerate(("Giant", "Tarmac", "Kickr"))}  # fmt: skip
    for bike in bikes.values():
        library.catalog.add_bike(bike)
    for slot, day, name in ((BikeSlot.OUTDOOR, date(2025, 1, 1), "Giant"),
                            (BikeSlot.OUTDOOR, date(2025, 8, 10), "Tarmac"),
                            (BikeSlot.ZWIFT, date(2025, 1, 1), "Kickr")):  # fmt: skip
        library.catalog.set_bike_default(BikeDefault(slot, day, bikes[name].id))

    report = library.importer().run([FIT_DIR])

    def bike_of(file_name: str) -> str | None:
        """Name of the bike the ride from ``file_name`` got, if any."""
        meta = library.ride_from(file_name, report).meta
        assert meta.bike_from_default or meta.bike_id is None, "import bikes come from defaults"
        return library.catalog.get_bike(meta.bike_id).name if meta.bike_id else None

    assert bike_of("garmin_nord_intervals_5x4.fit") == "Giant"
    assert bike_of("garmin_nord_smart_recording.fit") == "Tarmac"
    assert bike_of("2025-08-02-08-29-42.fit") == "Kickr"
    assert bike_of("garmin_indoor_no_hr.fit") is None, "there is no indoor default"


def test_imported_rides_get_route_fingerprints(library: Library):
    """Rides with positions are stored with their route cells; indoor rides without any.

    Given: the fixture folder imported.
    Expect: the Nord interval ride and the Zwift ride have cells (Zwift files carry Watopia's
    coordinates); the indoor ride without GPS has none.
    """
    report = library.importer().run([FIT_DIR])
    ids = dict(report.imported)

    nord = library.catalog.route_cells(ids["garmin_nord_intervals_5x4.fit"])
    zwift = library.catalog.route_cells(ids["2025-08-02-08-29-42.fit"])
    indoor = library.catalog.route_cells(ids["garmin_indoor_no_hr.fit"])

    assert nord and zwift, "rides with positions should have route cells"
    assert not nord & zwift, "the two loops are on opposite sides of the world"
    assert indoor == frozenset()


# -- time zones -------------------------------------------------------------------------------

ZWIFT_FILE = "2025-08-02-08-29-42.fit"


def test_a_zwift_ride_takes_its_time_zone_from_its_file_name(library: Library):
    """Zwift's 1989 local time is ignored and its file name, the local start, is used.

    Given: the Zwift fixture, named 2025-08-02-08-29-42.fit and starting 06:30:00 UTC.
    Expect: +2 h (CEST), from the file name; its file name stored as written.
    """
    report = library.importer().run([FIT_DIR / ZWIFT_FILE])
    zwift = library.ride_from(ZWIFT_FILE, report)

    assert zwift.summary.utc_offset_s == 2 * 3600
    assert zwift.summary.utc_offset_source == OffsetSource.FILE_NAME
    assert zwift.source_name == ZWIFT_FILE


def test_a_renamed_file_uses_the_default_time_zone(library: Library, tmp_path: Path):
    """Without a local time or a dated name, the library's default time zone is used.

    Given: the Zwift fixture copied as "morning ride.fit", with the default set to New York.
    Expect: New York's summer offset, -4 h, from the default.
    """
    renamed = tmp_path / "morning ride.fit"
    shutil.copy(FIT_DIR / ZWIFT_FILE, renamed)
    DEFAULT_TIME_ZONE.set(library.catalog, "America/New_York")

    report = library.importer().run([renamed])
    zwift = library.ride_from("morning ride.fit", report)

    assert zwift.summary.utc_offset_s == -4 * 3600
    assert zwift.summary.utc_offset_source == OffsetSource.DEFAULT


def test_a_file_in_a_zip_is_named_without_the_zip(library: Library, tmp_path: Path):
    """A dated file inside a zip is matched by its own name.

    Given: the Zwift fixture inside "export.zip" under a "rides/" folder.
    Expect: +2 h from its name; stored as just its file name.
    """
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.write(FIT_DIR / ZWIFT_FILE, f"rides/{ZWIFT_FILE}")

    report = library.importer().run([archive])
    [(_, ride_id)] = report.imported
    ride = library.catalog.get_ride(ride_id)

    assert ride.summary.utc_offset_s == 2 * 3600
    assert ride.source_name == ZWIFT_FILE
