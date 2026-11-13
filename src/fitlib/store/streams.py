"""Per-ride streams (the 1 Hz samples) as zstd Parquet, kept in any ``BlobStore``.

Also defines where original .fit files live, so blob keys are decided in one place.
"""

from __future__ import annotations

from datetime import datetime

import polars as pl

from fitlib.parquet import from_parquet, to_parquet
from fitlib.store.interfaces import BlobStore


def raw_key(sha256: str) -> str:
    """Where an original .fit file is kept.

    Args:
        sha256: Hex sha256 of the file.

    Returns:
        ``raw/<first 2 hex characters>/<sha256>.fit``.
    """
    return f"raw/{sha256[:2]}/{sha256}.fit"


def stream_key(ride_id: str, start: datetime) -> str:
    """Where a ride's 1 Hz stream is kept.

    Args:
        ride_id: The ride's id.
        start: The ride's start, which picks the year folder.

    Returns:
        ``streams/<year>/<ride id>.parquet``.
    """
    return f"streams/{start.year:04d}/{ride_id}.parquet"


class StreamStore:
    """Per-ride 1 Hz streams as Parquet blobs, keyed by ride id and start year.

    Args:
        blobs: The blob store holding the streams.
    """

    def __init__(self, blobs: BlobStore) -> None:
        self._blobs = blobs

    def put(self, ride_id: str, start: datetime, frame: pl.DataFrame) -> None:
        """Store a ride's stream, replacing any previous one.

        Args:
            ride_id: The ride's id.
            start: The ride's start.
            frame: The ride's 1 Hz frame.
        """
        self.put_bytes(ride_id, start, to_parquet(frame))

    def put_bytes(self, ride_id: str, start: datetime, parquet: bytes) -> None:
        """Store a stream that is already Parquet (e.g. made in a worker process).

        Args:
            ride_id: The ride's id.
            start: The ride's start.
            parquet: The stream as Parquet bytes, from ``to_parquet``.
        """
        self._blobs.put(stream_key(ride_id, start), parquet)

    def get(self, ride_id: str, start: datetime) -> pl.DataFrame:
        """Load a ride's stream.

        Args:
            ride_id: The ride's id.
            start: The ride's start.

        Returns:
            The ride's 1 Hz frame.

        Raises:
            BlobNotFound: The ride has no stored stream.
        """
        return from_parquet(self._blobs.get(stream_key(ride_id, start)))

    def delete(self, ride_id: str, start: datetime) -> None:
        """Remove a ride's stream, if there is one.

        Args:
            ride_id: The ride's id.
            start: The ride's start.
        """
        self._blobs.delete(stream_key(ride_id, start))
