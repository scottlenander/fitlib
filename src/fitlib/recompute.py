"""Recompute rides' figures from their archived original files.

Needed only when fitlib's own calculations change (``METRICS_VERSION``); FTP and athlete
history changes need no recompute because FTP-based figures are worked out when read.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field

from fitlib.ingest.analyse import Analysed, Failed, NotARide, analyse
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.models import Ride
from fitlib.parallel import default_workers, make_executor
from fitlib.store.interfaces import BlobNotFound, BlobStore, CatalogStore
from fitlib.store.streams import StreamStore, raw_key

log = logging.getLogger(__name__)


@dataclass
class RecomputeReport:
    """What happened to each ride in a recompute.

    Attributes:
        updated: Ids of rides recomputed.
        failed: ``(ride id, reason)`` for rides that couldn't be recomputed.
    """

    updated: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


class Recomputer:
    """Recomputes rides from their raw files with the current calculations.

    Args:
        catalog: Where the rides are.
        blobs: Where the raw files are.
        streams: Where each ride's stream is replaced.
        workers: Decoding processes; ``None`` for ``default_workers()``.
    """

    def __init__(
        self,
        catalog: CatalogStore,
        blobs: BlobStore,
        streams: StreamStore,
        workers: int | None = None,
    ) -> None:
        self._catalog = catalog
        self._blobs = blobs
        self._streams = streams
        self._workers = default_workers() if workers is None else workers

    def outdated(self) -> list[str]:
        """List rides computed with older calculations.

        Returns:
            Their ids, oldest ride first.
        """
        return self._catalog.ride_ids(below_version=METRICS_VERSION)

    def run(
        self,
        ride_ids: Iterable[str],
        on_progress: Callable[[str], None] | None = None,
    ) -> RecomputeReport:
        """Recompute the given rides, keeping their ids, import details and metadata.

        Args:
            ride_ids: Full ids of the rides to recompute.
            on_progress: Called with each ride's id once it has been handled.

        Returns:
            Which rides were updated and which failed, with reasons.
        """
        report = RecomputeReport()
        # Bounded, like the importer, so memory stays flat when recomputing every ride.
        in_flight: deque[tuple[Ride, Future]] = deque()

        def finish_oldest() -> None:
            """Wait for the oldest ride in flight and store its new figures."""
            ride, future = in_flight.popleft()
            self._store(ride, future.result(), report)
            if on_progress:
                on_progress(ride.id)

        with make_executor(self._workers) as executor:
            for ride_id in ride_ids:
                ride = self._catalog.get_ride(ride_id)
                try:
                    data = self._blobs.get(raw_key(ride.sha256))
                except BlobNotFound:
                    report.failed.append((ride_id, "the original file is missing"))
                    if on_progress:
                        on_progress(ride_id)
                    continue
                in_flight.append((ride, executor.submit(analyse, data)))
                if len(in_flight) >= self._workers * 4:
                    finish_oldest()
            while in_flight:
                finish_oldest()
        return report

    def _store(
        self, ride: Ride, result: Analysed | NotARide | Failed, report: RecomputeReport
    ) -> None:
        """Save one ride's recomputed figures and stream, or note why it failed.

        Args:
            ride: The ride as it was.
            result: What ``analyse`` made of its raw file.
            report: The recompute's report, updated with this ride's outcome.
        """
        if not isinstance(result, Analysed):
            reason = result.reason if isinstance(result, Failed) else "no longer a ride"
            report.failed.append((ride.id, reason))
            log.info("recompute failed for ride %s: %s", ride.short_id, reason)
            return
        self._streams.delete(ride.id, ride.summary.start)
        self._streams.put_bytes(ride.id, result.summary.start, result.stream)
        self._catalog.replace_summary(ride.id, result.summary, METRICS_VERSION)
        report.updated.append(ride.id)
        log.info("recomputed ride %s", ride.short_id)
