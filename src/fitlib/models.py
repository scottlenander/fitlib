"""Domain objects shared by every layer.

These live outside ``fitlib.store`` so ingest and metrics never depend on storage. All
measurements are SI: metres, metres per second, seconds, watts, beats and revolutions per
minute. Conversion to other units happens only when displaying them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import StrEnum

# Best efforts are kept for these durations, in seconds (1 s to 2 h).
CURVE_DURATIONS_S: tuple[int, ...] = (
    1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600, 5400, 7200,
)  # fmt: skip

type Curve = tuple[tuple[int, float], ...]
"""Best efforts as ``(duration in seconds, best average over that duration)``, shortest first."""

type Histogram = tuple[tuple[int, int], ...]
"""Time at each value as ``(value, seconds)``, lowest value first, e.g. seconds at each watt."""


class Units(StrEnum):
    """Which units figures are shown in. Stored data is always SI."""

    IMPERIAL = "imperial"
    METRIC = "metric"


class Source(StrEnum):
    """Where a ride was recorded, from the FIT file's manufacturer field."""

    ZWIFT = "zwift"
    GARMIN = "garmin"
    OTHER = "other"

    @property
    def label(self) -> str:
        """Display name of the source.

        Returns:
            The source as people write it, e.g. ``"Zwift"``.
        """
        return {"zwift": "Zwift", "garmin": "Garmin", "other": "Other"}[self.value]


@dataclass(frozen=True)
class Lap:
    """Figures for one lap of a ride (a stretch between two presses of the lap button).

    Attributes:
        index: Position of the lap in the ride, starting at 0.
        start_offset_s: Seconds from the ride's start to the lap's start.
        elapsed_s: Length of the lap in seconds, pauses included.
        distance_m: Distance covered, or ``None`` without distance or speed data.
        avg_power: Average power over riding seconds, or ``None`` without a power meter.
        max_power: Highest power, or ``None`` without a power meter.
        avg_hr: Average heart rate, or ``None`` without a heart-rate strap.
        max_hr: Highest heart rate, or ``None`` without a heart-rate strap.
    """

    index: int
    start_offset_s: int
    elapsed_s: int
    distance_m: float | None
    avg_power: float | None
    max_power: int | None
    avg_hr: float | None
    max_hr: int | None


@dataclass(frozen=True)
class GeoSummary:
    """Where an outdoor ride happened.

    Location is sensitive, so it is stored separately from the rest of the ride.

    Attributes:
        start_lat: Latitude of the first recorded position, in degrees.
        start_lon: Longitude of the first recorded position, in degrees.
        min_lat: Southern edge of the area ridden, in degrees.
        min_lon: Western edge of the area ridden, in degrees.
        max_lat: Northern edge of the area ridden, in degrees.
        max_lon: Eastern edge of the area ridden, in degrees.
    """

    start_lat: float
    start_lon: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


@dataclass(frozen=True)
class RideSummary:
    """What a ride's file says and what fitlib computed from it. Never edited by the user.

    Attributes:
        start: Time of the first record, in UTC (timezone-aware).
        utc_offset_s: Local time minus UTC in seconds, when the device recorded local time.
        source: Who recorded the ride.
        device: Readable device name, e.g. ``"Garmin Edge 540"``, if known.
        sport: FIT sport, normally ``"cycling"``.
        sub_sport: FIT sub-sport, e.g. ``"road"`` or ``"virtual_activity"``, if known.
        indoor: Whether the ride was indoors (virtual, trainer, or no GPS).
        elapsed_s: Seconds from start to finish, pauses included.
        moving_s: Seconds spent riding: not paused, and moving or pedalling.
        distance_m: Distance in metres, or ``None`` without distance or speed data.
        ascent_m: Total climbing in metres, or ``None`` without altitude data.
        avg_speed_mps: Distance divided by moving time, in metres per second.
        max_speed_mps: Highest speed, in metres per second.
        avg_power: Average power over riding seconds (zeros included), in watts.
        max_power: Highest power, in watts.
        avg_hr: Average heart rate, in beats per minute.
        max_hr: Highest heart rate, in beats per minute.
        avg_cadence: Average cadence while pedalling (zeros left out), in rpm.
        has_power: Whether any power was recorded.
        has_hr: Whether any heart rate was recorded.
        has_gps: Whether any position was recorded.
        laps: Per-lap figures, in order.
        geo: Start point and area for rides with GPS, else ``None``.
        np: Normalized Power in watts (needs at least 30 s of power), else ``None``.
        kj: Work done in kilojoules, else ``None``.
        vi: Variability index, NP divided by average power, else ``None``.
        decoupling_pct: Aerobic decoupling (Pw:HR drift from the first half to the second) in
            percent, for rides of 20 min or more with power and heart rate, else ``None``.
        power_curve: Best average power for each of ``CURVE_DURATIONS_S`` the ride lasted.
        hr_curve: Best average heart rate for the same durations.
        power_histogram: Riding seconds at each whole watt.
        hr_histogram: Riding seconds at each whole beat per minute.
    """

    start: datetime
    utc_offset_s: int | None
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
    np: float | None = None
    kj: float | None = None
    vi: float | None = None
    decoupling_pct: float | None = None
    power_curve: Curve = ()
    hr_curve: Curve = ()
    power_histogram: Histogram = ()
    hr_histogram: Histogram = ()

    @property
    def end(self) -> datetime:
        """When the ride finished.

        Returns:
            The start plus the elapsed time, in UTC.
        """
        return self.start + timedelta(seconds=self.elapsed_s)

    @property
    def local_start(self) -> datetime | None:
        """Start time as the rider's clock showed it.

        Returns:
            The start shifted by ``utc_offset_s`` (still labelled UTC), or ``None`` if the
            device didn't record local time.
        """
        if self.utc_offset_s is None:
            return None
        return self.start + timedelta(seconds=self.utc_offset_s)


@dataclass(frozen=True)
class AthleteEntry:
    """One dated change to the athlete's FTP, weight or max heart rate.

    Each value carries forward on its own until a later entry sets it again, so an entry can
    change just one of them.

    Attributes:
        effective_from: The first day (in the rider's local time) the values apply.
        ftp: Functional threshold power in watts, or ``None`` to leave it unchanged.
        weight_kg: Body weight in kilograms, or ``None`` to leave it unchanged.
        max_hr: Maximum heart rate in bpm, or ``None`` to leave it unchanged.
    """

    effective_from: date
    ftp: int | None = None
    weight_kg: float | None = None
    max_hr: int | None = None


@dataclass(frozen=True)
class RideMeta:
    """What the user adds to a ride. Everything is optional.

    Attributes:
        name: The user's name for the ride; a default name is shown when ``None``.
        notes: Free-text notes.
        rpe: Perceived effort from 1 (very easy) to 10 (maximal).
        bike_id: Id of the bike ridden, from the ``bikes`` table.
        tags: Tag names, e.g. ``("cobbles", "z2")``.
    """

    name: str | None = None
    notes: str | None = None
    rpe: int | None = None
    bike_id: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Ride:
    """A ride in the library: its summary, the user's metadata, and how it was imported.

    Attributes:
        id: Random UUID. Never derived from the file, date or location.
        sha256: Hash of the original .fit file, used to detect re-imports.
        summary: Figures from the file and computed by fitlib.
        imported_at: When the ride was imported, in UTC.
        metrics_version: Version of the calculations used for ``summary``.
        source_name: The original file name, for display only.
        meta: What the user added.
    """

    id: str
    sha256: str
    summary: RideSummary
    imported_at: datetime
    metrics_version: int
    source_name: str
    meta: RideMeta = field(default_factory=RideMeta)

    @property
    def short_id(self) -> str:
        """The first 8 characters of the id, enough to refer to a ride.

        Returns:
            The id prefix.
        """
        return self.id[:8]

    @property
    def display_name(self) -> str:
        """The user's name for the ride, or a default built from its source and date.

        Returns:
            For example ``"Zwift ride, 2 Aug 2025"``, ``"Garmin indoor ride, 19 Aug 2025"``
            or ``"Ride, 1 Sep 2025"`` when the user hasn't named it.
        """
        if self.meta.name:
            return self.meta.name
        s = self.summary
        kind = "indoor ride" if s.indoor and s.source is not Source.ZWIFT else "ride"
        prefix = kind.capitalize() if s.source is Source.OTHER else f"{s.source.label} {kind}"
        day = s.local_start or s.start
        return f"{prefix}, {day.day} {day:%b %Y}"


class SortKey(StrEnum):
    """What the ride library can be sorted by."""

    START = "start"
    DURATION = "duration"
    DISTANCE = "distance"
    POWER = "power"


@dataclass(frozen=True)
class Filters:
    """Search criteria for the ride library. ``None`` means "don't filter on this".

    Attributes:
        text: Words that must each start a word in the ride's name, notes, tags, source or
            device.
        since: Only rides starting at or after this time.
        until: Only rides starting before this time.
        source: Only rides from this source.
        indoor: Only indoor (``True``) or outdoor (``False``) rides.
        min_duration_s: Only rides with at least this much moving time, in seconds.
        max_duration_s: Only rides with at most this much moving time, in seconds.
        has_power: Only rides with (``True``) or without (``False``) power data.
    """

    text: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    source: Source | None = None
    indoor: bool | None = None
    min_duration_s: int | None = None
    max_duration_s: int | None = None
    has_power: bool | None = None


@dataclass(frozen=True)
class Page[T]:
    """One page of search results.

    Attributes:
        items: The results on this page, in order.
        total: How many results match in all, across every page.
        offset: How many results come before this page.
        limit: The most results a page can hold.
    """

    items: tuple[T, ...]
    total: int
    offset: int
    limit: int
