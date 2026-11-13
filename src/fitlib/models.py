"""Domain objects shared by every layer.

These live outside ``fitlib.store`` so ingest and metrics never depend on storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class Source(StrEnum):
    ZWIFT = "zwift"
    GARMIN = "garmin"
    OTHER = "other"

    @property
    def label(self) -> str:
        return {"zwift": "Zwift", "garmin": "Garmin", "other": "Other"}[self.value]


@dataclass(frozen=True)
class Lap:
    index: int
    start_offset_s: int  # seconds from the ride's start
    elapsed_s: int
    distance_m: float | None
    avg_power: float | None
    max_power: int | None
    avg_hr: float | None
    max_hr: int | None


@dataclass(frozen=True)
class GeoSummary:
    """Where an outdoor ride happened. Stored separately from the ride (location is sensitive)."""

    start_lat: float
    start_lon: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


@dataclass(frozen=True)
class RideSummary:
    """What a ride's file says and what fitlib computed from it. Never edited by the user."""

    start: datetime  # UTC, timezone-aware
    utc_offset_s: int | None  # local time = start + offset, when the device recorded it
    source: Source
    device: str | None
    sport: str
    sub_sport: str | None
    indoor: bool
    elapsed_s: int
    moving_s: int
    distance_m: float | None
    ascent_m: float | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    avg_power: float | None
    max_power: int | None
    avg_hr: float | None
    max_hr: int | None
    avg_cadence: float | None
    has_power: bool
    has_hr: bool
    has_gps: bool
    laps: tuple[Lap, ...] = ()
    geo: GeoSummary | None = None

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.elapsed_s)

    @property
    def local_start(self) -> datetime | None:
        if self.utc_offset_s is None:
            return None
        return self.start + timedelta(seconds=self.utc_offset_s)


@dataclass(frozen=True)
class RideMeta:
    """What the user adds to a ride. All optional."""

    name: str | None = None
    notes: str | None = None
    rpe: int | None = None  # perceived effort, 1-10
    bike_id: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ride:
    id: str  # random UUID, never derived from the file, date or location
    sha256: str  # of the original .fit file, for dedupe
    summary: RideSummary
    imported_at: datetime
    metrics_version: int
    source_name: str  # original file name, for display only
    meta: RideMeta = field(default_factory=RideMeta)

    @property
    def short_id(self) -> str:
        return self.id[:8]

    @property
    def display_name(self) -> str:
        if self.meta.name:
            return self.meta.name
        # e.g. "Zwift ride, 2 Aug 2025", "Garmin indoor ride, 19 Aug 2025", "Ride, 1 Sep 2025"
        s = self.summary
        kind = "indoor ride" if s.indoor and s.source is not Source.ZWIFT else "ride"
        prefix = kind.capitalize() if s.source is Source.OTHER else f"{s.source.label} {kind}"
        day = s.local_start or s.start
        return f"{prefix}, {day.day} {day:%b %Y}"


class SortKey(StrEnum):
    START = "start"
    DURATION = "duration"
    DISTANCE = "distance"
    POWER = "power"


@dataclass(frozen=True)
class Filters:
    """Search criteria for the ride library. ``None`` means "don't filter on this"."""

    text: str | None = None  # words matched against name, notes, tags, source and device
    since: datetime | None = None  # start >= since
    until: datetime | None = None  # start < until
    source: Source | None = None
    indoor: bool | None = None
    min_duration_s: int | None = None
    max_duration_s: int | None = None
    has_power: bool | None = None


@dataclass(frozen=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    offset: int
    limit: int
