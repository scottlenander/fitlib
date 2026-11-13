"""Shared fixtures."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fitlib.importer import Importer, ImportReport
from fitlib.models import Ride
from fitlib.store.memory import MemoryBlobStore, MemoryCatalog
from fitlib.store.streams import StreamStore
from tests.fixtures.generate import FIT_DIR


@dataclass
class ImportedLibrary:
    """In-memory stores with the fixture folder imported.

    Attributes:
        catalog: The rides.
        blobs: Original files and streams.
        streams: Streams, on top of ``blobs``.
        report: What the import did with each fixture file.
    """

    catalog: MemoryCatalog
    blobs: MemoryBlobStore
    streams: StreamStore
    report: ImportReport

    def ride(self, file_name: str) -> Ride:
        """Look up the ride imported from a fixture file.

        Args:
            file_name: The fixture's file name, e.g. ``"zwift_watopia_steady_60min.fit"``.

        Returns:
            The ride, loaded from the catalog.
        """
        return self.catalog.get_ride(dict(self.report.imported)[file_name])


@pytest.fixture
def imported() -> ImportedLibrary:
    """Import the whole fixture folder into fresh in-memory stores, in this process.

    Returns:
        The stores and the import report.
    """
    catalog, blobs = MemoryCatalog(), MemoryBlobStore()
    streams = StreamStore(blobs)
    report = Importer(catalog, blobs, streams, workers=1).run([FIT_DIR])
    return ImportedLibrary(catalog, blobs, streams, report)
