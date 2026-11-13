"""Import .fit files into the library.

For each file: hash it and skip files already imported; decode, normalize and summarize it
(in worker processes when there are several files); then, in this process, store the original
file, the 1 Hz stream and the catalog entry. One file failing never stops the others, and
re-running an interrupted import carries on where it stopped (finished files are duplicates).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fitlib.ingest.analyse import Analysed, Failed, NotARide, analyse
from fitlib.ingest.scanner import scan
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.metadata import default_bike
from fitlib.models import BikeDefault, Ride, RideMeta, RideSummary
from fitlib.parallel import default_workers, make_executor
from fitlib.store.interfaces import BlobStore, CatalogStore, DuplicateRide
from fitlib.store.streams import StreamStore, raw_key

log = logging.getLogger(__name__)

# Two recordings of the same ride: starts within this window and overlapping by this much.
OVERLAP_START_WINDOW = timedelta(minutes=2)
OVERLAP_MIN_FRACTION = 0.8


@dataclass
class ImportReport:
    """What happened to each file in an import.

    Every entry is ``(file name, detail)``. Zipped files are named ``<zip>:<member>``.

    Attributes:
        imported: Files added to the library; detail is the new ride's id.
        duplicates: Files already in the library; detail is the existing ride's id, or which
            earlier file in the same import had identical bytes.
        skipped: Files left out on purpose; detail is the reason (not a ride, or overlaps a
            ride already in the library).
        failed: Files that couldn't be read; detail is the reason.
    """

    imported: list[tuple[str, str]] = field(default_factory=list)
    duplicates: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """How many files the import looked at.

        Returns:
            The number of entries across all four lists.
        """
        return len(self.imported) + len(self.duplicates) + len(self.skipped) + len(self.failed)


def overlap_fraction(a: RideSummary, b: RideSummary) -> float:
    """How much two rides overlap in time.

    Args:
        a: One ride.
        b: The other ride.

    Returns:
        The time both were in progress, as a fraction of the shorter ride's elapsed time:
        0.0 for no overlap, 1.0 when the shorter ride lies entirely within the longer one.
    """
    shared = (min(a.end, b.end) - max(a.start, b.start)).total_seconds()
    shorter = min(a.elapsed_s, b.elapsed_s)
    return max(0.0, shared) / shorter if shorter else 0.0


class Importer:
    """Imports .fit files into a library's stores.

    Args:
        catalog: Where ride entries go.
        blobs: Where original files go.
        streams: Where each ride's 1 Hz samples go.
        workers: Decoding processes; ``None`` for ``default_workers()``. With 1, everything
            runs in this process.
        clock: Returns the current time, used for ``imported_at``. Replaceable in tests.
    """

    def __init__(
        self,
        catalog: CatalogStore,
        blobs: BlobStore,
        streams: StreamStore,
        workers: int | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._catalog = catalog
        self._blobs = blobs
        self._streams = streams
        self._workers = default_workers() if workers is None else workers
        self._clock = clock

    def run(
        self,
        paths: Iterable[Path],
        on_progress: Callable[[str], None] | None = None,
    ) -> ImportReport:
        """Import every .fit file under ``paths``.

        One bad file never stops the others. Files already imported are recognised by their
        hash, so running the same import again (or resuming one) is safe.

        Args:
            paths: Folders (searched recursively), .fit files and .zip archives.
            on_progress: Called with each file's name once it has been handled.

        Returns:
            What happened to every file.

        Raises:
            FileNotFoundError: A path doesn't exist. Raised before anything is imported.
        """
        report = ImportReport()
        defaults = self._catalog.bike_defaults()
        seen: dict[str, str] = {}  # sha256 -> file name, within this run
        # Files being analysed, oldest first. Bounded, so memory stays flat however many
        # files there are; results are stored in file order, so overlaps resolve the same
        # way every run.
        in_flight: deque[tuple[str, bytes, str, Future]] = deque()
        max_in_flight = self._workers * 4

        def store_oldest() -> None:
            """Wait for the oldest file in flight and store its result."""
            name, data, sha, future = in_flight.popleft()
            self._store(name, data, sha, future.result(), report, defaults)
            if on_progress:
                on_progress(name)

        with make_executor(self._workers) as executor:
            for source in scan(paths):
                data = source.read()
                sha = hashlib.sha256(data).hexdigest()
                if self._is_duplicate(source.name, sha, seen, report):
                    if on_progress:
                        on_progress(source.name)
                    continue
                seen[sha] = source.name
                in_flight.append((source.name, data, sha, executor.submit(analyse, data)))
                if len(in_flight) >= max_in_flight:
                    store_oldest()
            while in_flight:
                store_oldest()
        return report

    def _is_duplicate(
        self, name: str, sha: str, seen: dict[str, str], report: ImportReport
    ) -> bool:
        """Check whether a file was imported before, or already seen in this run.

        Records the duplicate in ``report`` when it is one.

        Args:
            name: The file's display name.
            sha: The file's sha256.
            seen: Hashes of files already queued in this run, mapped to their names.
            report: The import's report.

        Returns:
            ``True`` if the file should not be imported again.
        """
        existing = self._catalog.find_by_hash(sha)
        if existing is not None:
            report.duplicates.append((name, existing))
            log.info("duplicate: %s is already ride %s", name, existing[:8])
            return True
        if sha in seen:
            report.duplicates.append((name, f"same file as {seen[sha]}"))
            log.info("duplicate: %s is the same file as %s", name, seen[sha])
            return True
        return False

    def _overlapping(self, summary: RideSummary) -> Ride | None:
        """Find a ride already in the library that records the same ride as ``summary``.

        Args:
            summary: The new ride's summary.

        Returns:
            The first ride starting within ``OVERLAP_START_WINDOW`` of it and overlapping by
            more than ``OVERLAP_MIN_FRACTION``, or ``None``.
        """
        candidates = self._catalog.rides_starting_between(
            summary.start - OVERLAP_START_WINDOW, summary.start + OVERLAP_START_WINDOW
        )
        return next(
            (r for r in candidates if overlap_fraction(r.summary, summary) > OVERLAP_MIN_FRACTION),
            None,
        )

    def _store(
        self,
        name: str,
        data: bytes,
        sha: str,
        result: Analysed | NotARide | Failed,
        report: ImportReport,
        defaults: list[BikeDefault],
    ) -> None:
        """Record one analysed file: store it as a ride, or note why not.

        Args:
            name: The file's display name.
            data: The file's bytes, archived as the raw file.
            sha: The file's sha256.
            result: What ``analyse`` made of it.
            report: The import's report, updated with this file's outcome.
            defaults: The dated default bikes, used to set the new ride's bike.

        Raises:
            Exception: Anything the catalog raises other than ``DuplicateRide``, after the
                ride's stream has been removed again.
        """
        match result:
            case Failed(reason):
                report.failed.append((name, reason))
                log.info("failed: %s: %s", name, reason)
                return
            case NotARide(sport):
                report.skipped.append((name, f"not a ride ({sport})"))
                log.info("skipped: %s is not a ride (%s)", name, sport)
                return

        assert isinstance(result, Analysed)
        if (other := self._overlapping(result.summary)) is not None:
            # Keep the ride already in the library; archive this file so nothing is lost.
            self._blobs.put(raw_key(sha), data)
            report.skipped.append((name, f"overlaps ride {other.short_id}"))
            log.info("skipped: %s overlaps ride %s", name, other.short_id)
            return

        ride = Ride(
            id=str(uuid.uuid4()),
            sha256=sha,
            summary=result.summary,
            imported_at=self._clock(),
            metrics_version=METRICS_VERSION,
            source_name=Path(name.split(":")[-1]).name,
            meta=RideMeta(bike_id=default_bike(defaults, result.summary)),
        )
        self._blobs.put(raw_key(sha), data)
        self._streams.put_bytes(ride.id, ride.summary.start, result.stream)
        try:
            self._catalog.add_ride(ride)
        except DuplicateRide:
            # Another import added the same file meanwhile; its blobs are identical.
            self._streams.delete(ride.id, ride.summary.start)
            report.duplicates.append((name, self._catalog.find_by_hash(sha) or "unknown"))
            return
        except BaseException:
            self._streams.delete(ride.id, ride.summary.start)
            raise
        report.imported.append((name, ride.id))
        log.info("imported: %s as ride %s", name, ride.short_id)
