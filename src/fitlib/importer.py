"""Import .fit files into the library.

For each file: hash it and skip files already imported; decode, normalize and summarize it
(in worker processes when there are several files); then, in this process, store the original
file, the 1 Hz stream and the catalog entry. One file failing never stops the others, and
re-running an interrupted import carries on where it stopped (finished files are duplicates).
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Executor, Future, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fitlib.ingest.decoder import DecodeError, decode
from fitlib.ingest.normalize import to_frame
from fitlib.ingest.scanner import scan
from fitlib.ingest.source import is_cycling
from fitlib.ingest.summarize import METRICS_VERSION, summarize
from fitlib.models import Ride, RideSummary
from fitlib.store.interfaces import BlobStore, CatalogStore, DuplicateRide
from fitlib.store.streams import StreamStore, raw_key, to_parquet

log = logging.getLogger(__name__)

# Two recordings of the same ride: starts within this window and overlapping by this much.
OVERLAP_START_WINDOW = timedelta(minutes=2)
OVERLAP_MIN_FRACTION = 0.8


@dataclass(frozen=True)
class Analysed:
    summary: RideSummary
    stream: bytes  # zstd Parquet


@dataclass(frozen=True)
class NotARide:
    sport: str


@dataclass(frozen=True)
class Failed:
    reason: str


def analyse(data: bytes) -> Analysed | NotARide | Failed:
    """Decode and summarize one file. Runs in a worker process, so it touches no stores."""
    try:
        decoded = decode(data)
    except DecodeError as exc:
        return Failed(f"not a readable FIT file ({exc})")
    if not is_cycling(decoded):
        return NotARide(decoded.sport or "unknown")
    frame = to_frame(decoded.records)
    if frame.is_empty():
        return Failed("the file has no recorded data")
    return Analysed(summarize(decoded, frame), to_parquet(frame))


@dataclass
class ImportReport:
    imported: list[tuple[str, str]] = field(default_factory=list)  # (file, ride id)
    duplicates: list[tuple[str, str]] = field(default_factory=list)  # (file, existing ride id)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (file, reason)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (file, reason)

    @property
    def total(self) -> int:
        return len(self.imported) + len(self.duplicates) + len(self.skipped) + len(self.failed)


class _InlineExecutor(Executor):
    """Runs work immediately in this process: for one worker, and for tests."""

    def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - analyse() returns Failed instead
            future.set_exception(exc)
        return future


def overlap_fraction(a: RideSummary, b: RideSummary) -> float:
    """Shared time as a fraction of the shorter ride."""
    shared = (min(a.end, b.end) - max(a.start, b.start)).total_seconds()
    shorter = min(a.elapsed_s, b.elapsed_s)
    return max(0.0, shared) / shorter if shorter else 0.0


def default_workers() -> int:
    return max(1, min(4, os.cpu_count() or 1))


class Importer:
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
        """Import every .fit file under ``paths``. ``on_progress`` is called once per file."""
        report = ImportReport()
        seen: dict[str, str] = {}  # sha256 -> file name, within this run
        # Files being analysed, oldest first. Bounded, so memory stays flat however many
        # files there are; results are stored in file order, so overlaps resolve the same
        # way every run.
        in_flight: deque[tuple[str, bytes, str, Future]] = deque()
        max_in_flight = self._workers * 4

        def store_oldest() -> None:
            name, data, sha, future = in_flight.popleft()
            self._store(name, data, sha, future.result(), report)
            if on_progress:
                on_progress(name)

        executor: Executor = (
            ProcessPoolExecutor(self._workers) if self._workers > 1 else _InlineExecutor()
        )
        with executor:
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
    ) -> None:
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
