"""Turn one .fit file's bytes into a ride summary and stream, ready to store.

Runs in worker processes during import and recompute, so it touches no stores and returns
plain, picklable values.
"""

from __future__ import annotations

from dataclasses import dataclass

from fitlib.ingest.decoder import DecodeError, decode
from fitlib.ingest.normalize import to_frame
from fitlib.ingest.source import is_cycling
from fitlib.ingest.summarize import summarize
from fitlib.models import RideSummary
from fitlib.parquet import to_parquet


@dataclass(frozen=True)
class Analysed:
    """A file that decoded into a ride.

    Attributes:
        summary: The ride's figures.
        stream: The ride's 1 Hz samples as zstd Parquet bytes.
    """

    summary: RideSummary
    stream: bytes


@dataclass(frozen=True)
class NotARide:
    """A file that decoded but records another sport.

    Attributes:
        sport: The FIT sport, e.g. ``"running"``.
    """

    sport: str


@dataclass(frozen=True)
class Failed:
    """A file that couldn't be imported.

    Attributes:
        reason: Why, for the user.
    """

    reason: str


def analyse(data: bytes) -> Analysed | NotARide | Failed:
    """Decode, normalize and summarize one file.

    Runs in a worker process, so it touches no stores and returns plain, picklable values.

    Args:
        data: The .fit file's bytes.

    Returns:
        The ride's summary and stream; or that it isn't a ride; or why it failed (unreadable,
        or no records).
    """
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
