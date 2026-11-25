"""Recompute rides' figures from their archived original files.

Needed only when fitlib's own calculations change (``METRICS_VERSION``); FTP and athlete
history changes need no recompute because FTP-based figures are worked out when read.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable, Iterable
from concurrent.futures import Future
from dataclasses import dataclass, field, replace

from fitlib.ingest.analyse import Analysed, Failed, NotARide, analyse
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.models import Ride
from fitlib.parallel import default_workers, make_executor
from fitlib.store.factory import OpenStores
from fitlib.store.interfaces import BlobNotFound, BlobStore, CatalogStore, RideNotFound
from fitlib.store.settings import DEFAULT_TIME_ZONE
from fitlib.store.streams import StreamStore, raw_key

log = logging.getLogger(__name__)


@dataclass
class RecomputeReport:
    """What happened to each ride in a recompute.

    Attributes:
        updated: Ids of rides recomputed.
        failed: ``(ride id, reason)`` for rides that couldn't be recomputed.
        gone: Ids of rides deleted while the recompute ran (from the browser app, the
            command line or by another import), so skipped.
    """

    updated: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)


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
        should_stop: Callable[[], bool] | None = None,
    ) -> RecomputeReport:
        """Recompute the given rides, keeping their ids, import details and metadata.

        Args:
            ride_ids: Full ids of the rides to recompute.
            on_progress: Called with each ride's id once it has been handled.
            should_stop: Asked before each ride is started; once it returns true, no more
                rides are started, and those already started are finished and stored.

        Returns:
            Which rides were updated and which failed, with reasons.
        """
        report = RecomputeReport()
        default_zone = DEFAULT_TIME_ZONE.get(self._catalog)
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
                if should_stop is not None and should_stop():
                    break
                try:
                    ride = self._catalog.get_ride(ride_id)
                except RideNotFound:
                    self._gone(ride_id, report)
                    if on_progress:
                        on_progress(ride_id)
                    continue
                try:
                    data = self._blobs.get(raw_key(ride.sha256))
                except BlobNotFound:
                    report.failed.append((ride_id, "the original file is missing"))
                    if on_progress:
                        on_progress(ride_id)
                    continue
                future = executor.submit(analyse, data, ride.source_name, default_zone)
                in_flight.append((ride, future))
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
        try:
            self._catalog.replace_summary(
                ride.id, result.summary, METRICS_VERSION, route=result.route
            )
        except RideNotFound:
            # Deleted while its figures were worked out: drop the stream just written.
            self._streams.delete(ride.id, result.summary.start)
            self._gone(ride.id, report)
            return
        report.updated.append(ride.id)
        log.info("recomputed ride %s", ride.short_id)

    @staticmethod
    def _gone(ride_id: str, report: RecomputeReport) -> None:
        """Note a ride deleted while the recompute ran.

        Args:
            ride_id: The ride's id.
            report: The recompute's report.
        """
        report.gone.append(ride_id)
        log.info("ride %s was deleted before it could be recomputed", ride_id[:8])


@dataclass(frozen=True)
class RecomputeState:
    """How far a background recompute has got.

    Attributes:
        total: Rides it set out to recompute.
        done: Rides handled so far, whatever happened to them. Rides that failed show up
            afterwards as still outdated.
    """

    total: int
    done: int


class BackgroundRecompute:
    """Brings rides computed with older calculations up to date, on a background thread.

    Runs once each time it's started (when the server starts), with its own stores, so the
    app can be used meanwhile. Each ride is stored as soon as it's done.

    Args:
        open_stores: Opens the library's stores.
        workers: Decoding processes; ``None`` for ``default_workers()``.
    """

    def __init__(self, open_stores: OpenStores, workers: int | None = None) -> None:
        self._open = open_stores
        self._workers = workers
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self._state: RecomputeState | None = None

    def start(self) -> None:
        """Look for outdated rides and recompute them, on a background thread."""
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="fitlib-recompute", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        """Start no more rides, and wait for those in progress to be stored.

        The rides not reached stay outdated, for the next start.

        Args:
            timeout: Longest to wait for the thread to finish.
        """
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for the recompute to finish.

        Args:
            timeout: Longest to wait; ``None`` for as long as it takes.

        Returns:
            Whether it has finished (true too if it was never started).
        """
        if self._thread is not None:
            self._thread.join(timeout)
            return not self._thread.is_alive()
        return True

    def state(self) -> RecomputeState | None:
        """Say how far the recompute has got.

        Returns:
            Its progress while it runs; ``None`` before it has found any rides to do, and
            once it has finished or stopped.
        """
        with self._lock:
            return self._state

    def _run(self) -> None:
        """Recompute every outdated ride, keeping the progress up to date."""
        try:
            with self._open() as stores:
                recomputer = Recomputer(
                    stores.catalog, stores.blobs, stores.streams, workers=self._workers
                )
                ids = recomputer.outdated()
                if not ids:
                    return
                log.info("recomputing %d ride(s) with older figures", len(ids))
                with self._lock:
                    self._state = RecomputeState(total=len(ids), done=0)

                def progress(_: str) -> None:
                    with self._lock:
                        assert self._state is not None
                        self._state = replace(self._state, done=self._state.done + 1)

                report = recomputer.run(
                    ids, on_progress=progress, should_stop=self._stopping.is_set
                )
                log.info(
                    "recompute finished: %d updated, %d failed, %d deleted meanwhile",
                    len(report.updated),
                    len(report.failed),
                    len(report.gone),
                )
        except Exception:
            log.exception("the background recompute stopped with an error")
        finally:
            with self._lock:
                self._state = None
