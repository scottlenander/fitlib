"""Frames to and from zstd-compressed Parquet bytes."""

from __future__ import annotations

import io

import polars as pl


def to_parquet(frame: pl.DataFrame) -> bytes:
    """Serialize a frame as zstd-compressed Parquet.

    Args:
        frame: Any frame.

    Returns:
        The Parquet file's bytes.
    """
    buffer = io.BytesIO()
    frame.write_parquet(buffer, compression="zstd")
    return buffer.getvalue()


def from_parquet(data: bytes) -> pl.DataFrame:
    """Read a frame from Parquet bytes.

    Args:
        data: A Parquet file's bytes.

    Returns:
        The frame, with its original column types.
    """
    return pl.read_parquet(io.BytesIO(data))
