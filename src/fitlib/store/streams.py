"""Per-ride streams (the 1 Hz samples) as zstd Parquet, kept in any ``BlobStore``.

Also defines where original .fit files live, so blob keys are decided in one place.
"""

from __future__ import annotations

import io
from datetime import datetime

import polars as pl

from fitlib.store.interfaces import BlobStore


def raw_key(sha256: str) -> str:
    return f"raw/{sha256[:2]}/{sha256}.fit"


def stream_key(ride_id: str, start: datetime) -> str:
    return f"streams/{start.year:04d}/{ride_id}.parquet"


def to_parquet(frame: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.write_parquet(buffer, compression="zstd")
    return buffer.getvalue()


def from_parquet(data: bytes) -> pl.DataFrame:
    return pl.read_parquet(io.BytesIO(data))


class StreamStore:
    def __init__(self, blobs: BlobStore) -> None:
        self._blobs = blobs

    def put(self, ride_id: str, start: datetime, frame: pl.DataFrame) -> None:
        self.put_bytes(ride_id, start, to_parquet(frame))

    def put_bytes(self, ride_id: str, start: datetime, parquet: bytes) -> None:
        self._blobs.put(stream_key(ride_id, start), parquet)

    def get(self, ride_id: str, start: datetime) -> pl.DataFrame:
        return from_parquet(self._blobs.get(stream_key(ride_id, start)))

    def delete(self, ride_id: str, start: datetime) -> None:
        self._blobs.delete(stream_key(ride_id, start))
