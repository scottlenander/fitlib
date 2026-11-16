"""What the API sends and accepts, built from fitlib's domain objects.

Every figure is in SI units (metres, seconds, m/s, kg); the browser app formats them. Start
times are UTC; ``local_start`` is the rider's clock time with no time zone attached.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitlib.analysis.training import Training
from fitlib.metrics import zones
from fitlib.models import Bike, BikeKind, BikeSlot, Curve, GeoSummary, Lap, Ride, Source


class BikeRef(BaseModel):
    """A bike, as named on a ride.

    Attributes:
        id: The bike's id.
        name: The bike's name.
    """

    id: str
    name: str


class RideItem(BaseModel):
    """One ride in a list: enough for a library table.

    Attributes:
        id: The ride's id.
        short_id: The first 8 characters of the id.
        name: The user's name for the ride, or one built from its source and date.
        start: Start time, UTC.
        local_start: Start time on the rider's clock, if the device recorded it.
        source: Zwift, Garmin or other.
        indoor: Whether the ride was indoors.
        device: The recording device, if known.
        moving_s: Moving time.
        elapsed_s: Elapsed time.
        distance_m: Distance, if recorded.
        ascent_m: Climbing, if recorded.
        avg_power: Average power, if recorded.
        np: Normalized Power, if there was power.
        avg_hr: Average heart rate, if recorded.
        tss: Training Stress Score, if there was power and an FTP.
        ftp_estimated: Whether the TSS uses an estimated FTP.
        rpe: Perceived effort, 1-10, if set.
        bike: The ride's bike, if any.
        tags: The ride's tags.
    """

    id: str
    short_id: str
    name: str
    start: datetime
    local_start: datetime | None
    source: Source
    indoor: bool
    device: str | None
    moving_s: int
    elapsed_s: int
    distance_m: float | None
    ascent_m: float | None
    avg_power: float | None
    np: float | None
    avg_hr: float | None
    tss: float | None
    ftp_estimated: bool
    rpe: int | None
    bike: BikeRef | None
    tags: list[str]


class RidePage(BaseModel):
    """A page of rides.

    Attributes:
        items: The rides on this page.
        total: How many rides match, across all pages.
        offset: How many matching rides come before this page.
        limit: The most rides a page holds.
    """

    items: list[RideItem]
    total: int
    offset: int
    limit: int


class SimilarRide(BaseModel):
    """A ride like another one.

    Attributes:
        ride: The similar ride.
        overlap: Route matches: the share of the asked-about ride's route this ride covered.
        other_overlap: Route matches: the share of this ride's route the asked-about ride
            covered.
        same_route: Route matches: both overlaps are high enough to be the same route.
        similarity: Effort matches: 100 for an identical effort, lower as they differ.
    """

    ride: RideItem
    overlap: float | None = None
    other_overlap: float | None = None
    same_route: bool | None = None
    similarity: int | None = None


class SimilarRides(BaseModel):
    """Rides like a given one.

    Attributes:
        kind: ``route`` (on the same roads) or ``effort`` (a similar effort).
        has_route: Whether the asked-about ride has positions to match routes on.
        items: The matches: for routes, same-route ones first, then by overlap; for efforts,
            most similar first.
    """

    kind: str
    has_route: bool
    items: list[SimilarRide]


class LapOut(BaseModel):
    """One lap.

    Attributes:
        index: Position in the ride, from 0.
        start_offset_s: Seconds from the ride's start.
        elapsed_s: The lap's length.
        distance_m: Distance, if recorded.
        avg_power: Average power, if recorded.
        max_power: Highest power, if recorded.
        avg_hr: Average heart rate, if recorded.
        max_hr: Highest heart rate, if recorded.
    """

    index: int
    start_offset_s: int
    elapsed_s: int
    distance_m: float | None
    avg_power: float | None
    max_power: int | None
    avg_hr: float | None
    max_hr: int | None


class GeoOut(BaseModel):
    """Where an outdoor ride was: its start and bounding box, in degrees.

    Attributes:
        start_lat: Latitude of the first fix.
        start_lon: Longitude of the first fix.
        min_lat: Southern edge.
        min_lon: Western edge.
        max_lat: Northern edge.
        max_lon: Eastern edge.
    """

    start_lat: float
    start_lon: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float


class TrainingOut(BaseModel):
    """FTP-based figures, using the athlete values in effect on the ride's date.

    Attributes:
        ftp: The FTP used, if set or estimable.
        ftp_estimated: Whether ``ftp`` is estimated from recent rides.
        weight_kg: Body weight on the day, if set.
        max_hr: Max heart rate on the day, if set.
        intensity_factor: NP / FTP.
        tss: Training Stress Score.
        watts_per_kg: Average power per kilogram.
        np_per_kg: Normalized Power per kilogram.
    """

    ftp: float | None
    ftp_estimated: bool
    weight_kg: float | None
    max_hr: int | None
    intensity_factor: float | None
    tss: float | None
    watts_per_kg: float | None
    np_per_kg: float | None


class ZoneTime(BaseModel):
    """Time spent in one zone.

    Attributes:
        zone: Zone number, from 1.
        name: The zone's name, such as ``"Threshold"``.
        seconds: Time in the zone.
    """

    zone: int
    name: str
    seconds: int


class CurvePoint(BaseModel):
    """The best average over one duration.

    Attributes:
        duration_s: The duration.
        value: Best average power (W) or heart rate (bpm) over it.
    """

    duration_s: int
    value: float


class MetaOut(BaseModel):
    """What the user added to a ride.

    Attributes:
        name: The user's name for the ride, if set.
        notes: Free-text notes, if any.
        rpe: Perceived effort, 1-10, if set.
        bike: The ride's bike, if any.
        bike_from_default: Whether the bike came from a default rather than being set by hand.
        tags: The ride's tags.
    """

    name: str | None
    notes: str | None
    rpe: int | None
    bike: BikeRef | None
    bike_from_default: bool
    tags: list[str]


class RideDetail(RideItem):
    """Everything about one ride, for its detail page.

    Attributes:
        source_name: The file the ride was imported from (a display hint only).
        imported_at: When it was imported, UTC.
        metrics_version: Version of fitlib's calculations the figures come from.
        sport: The file's sport, e.g. ``"cycling"``.
        sub_sport: The file's sub-sport, if any.
        utc_offset_s: The rider's clock offset from UTC, if recorded.
        avg_speed_mps: Average moving speed.
        max_speed_mps: Top speed.
        max_power: Highest power.
        max_hr: Highest heart rate.
        avg_cadence: Average cadence while pedalling.
        has_power: Whether the ride recorded power.
        has_hr: Whether the ride recorded heart rate.
        has_gps: Whether the ride recorded location.
        kj: Work done, in kilojoules.
        vi: Variability index (NP / average power).
        decoupling_pct: Aerobic decoupling (Pw:HR), for rides of 20 minutes or more.
        laps: The ride's laps.
        geo: Start point and bounding box, for outdoor rides with GPS.
        training: FTP-based figures.
        power_zones: Time in each of the 7 power zones, if there was power and an FTP.
        hr_zones: Time in each of the 5 heart-rate zones, if there was heart rate and a
            max heart rate.
        power_curve: Best average power over standard durations.
        hr_curve: Best average heart rate over standard durations.
        meta: What the user added.
    """

    source_name: str
    imported_at: datetime
    metrics_version: int
    sport: str
    sub_sport: str | None
    utc_offset_s: int | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    max_power: int | None
    max_hr: int | None
    avg_cadence: float | None
    has_power: bool
    has_hr: bool
    has_gps: bool
    kj: float | None
    vi: float | None
    decoupling_pct: float | None
    laps: list[LapOut]
    geo: GeoOut | None
    training: TrainingOut
    power_zones: list[ZoneTime] | None
    hr_zones: list[ZoneTime] | None
    power_curve: list[CurvePoint]
    hr_curve: list[CurvePoint]
    meta: MetaOut


class Streams(BaseModel):
    """A ride's samples, one per second (or every ``step`` seconds), as columns.

    Attributes:
        ride_id: The ride's id.
        step: Seconds between samples.
        t: Seconds from the start, for each sample.
        columns: Each requested field's values, aligned with ``t``. ``null`` where the
            device recorded nothing.
    """

    ride_id: str
    step: int
    t: list[int]
    columns: dict[str, list[float | int | bool | None]]


class TagCount(BaseModel):
    """A tag in use.

    Attributes:
        name: The tag.
        rides: How many rides have it.
    """

    name: str
    rides: int


class BikeOut(BaseModel):
    """A bike.

    Attributes:
        id: The bike's id.
        name: The bike's name.
        kind: Road, gravel, TT and so on, if set.
        retired: Whether the bike is retired.
    """

    id: str
    name: str
    kind: BikeKind | None
    retired: bool


def bike_ref(bike_id: str | None, bikes: dict[str, Bike]) -> BikeRef | None:
    """Name a ride's bike.

    Args:
        bike_id: The ride's bike id, if any.
        bikes: Every bike, by id.

    Returns:
        The bike's id and name, or ``None`` if the ride has no bike.
    """
    if bike_id is None or bike_id not in bikes:
        return None
    return BikeRef(id=bike_id, name=bikes[bike_id].name)


def _naive(moment: datetime | None) -> datetime | None:
    """Drop a time zone label, for clock times that aren't really UTC.

    Args:
        moment: A time labelled UTC, or ``None``.

    Returns:
        The same wall-clock time with no time zone, or ``None``.
    """
    return moment.replace(tzinfo=None) if moment is not None else None


def ride_item(ride: Ride, figures: Training, bikes: dict[str, Bike]) -> RideItem:
    """Build a list entry for a ride.

    Args:
        ride: The ride.
        figures: Its FTP-based figures.
        bikes: Every bike, by id.

    Returns:
        The list entry.
    """
    s, m = ride.summary, ride.meta
    return RideItem(
        id=ride.id,
        short_id=ride.short_id,
        name=ride.display_name,
        start=s.start,
        local_start=_naive(s.local_start),
        source=s.source,
        indoor=s.indoor,
        device=s.device,
        moving_s=s.moving_s,
        elapsed_s=s.elapsed_s,
        distance_m=s.distance_m,
        ascent_m=s.ascent_m,
        avg_power=s.avg_power,
        np=s.np,
        avg_hr=s.avg_hr,
        tss=figures.tss,
        ftp_estimated=figures.ftp_estimated,
        rpe=m.rpe,
        bike=bike_ref(m.bike_id, bikes),
        tags=list(m.tags),
    )


def _zones(seconds: tuple[int, ...] | None, names: tuple[str, ...]) -> list[ZoneTime] | None:
    """Pair zone times with their names.

    Args:
        seconds: Time in each zone, or ``None``.
        names: The zones' names, in order.

    Returns:
        One entry per zone, or ``None``.
    """
    if seconds is None:
        return None
    return [
        ZoneTime(zone=i, name=name, seconds=secs)
        for i, (name, secs) in enumerate(zip(names, seconds, strict=True), start=1)
    ]


def _curve(curve: Curve) -> list[CurvePoint]:
    """Turn a stored curve into points.

    Args:
        curve: ``(duration, value)`` pairs.

    Returns:
        The same pairs as points.
    """
    return [CurvePoint(duration_s=d, value=v) for d, v in curve]


def _lap(lap: Lap) -> LapOut:
    """Copy a lap.

    Args:
        lap: The lap.

    Returns:
        The lap for the API.
    """
    return LapOut(
        index=lap.index,
        start_offset_s=lap.start_offset_s,
        elapsed_s=lap.elapsed_s,
        distance_m=lap.distance_m,
        avg_power=lap.avg_power,
        max_power=lap.max_power,
        avg_hr=lap.avg_hr,
        max_hr=lap.max_hr,
    )


def _geo(geo: GeoSummary | None) -> GeoOut | None:
    """Copy a ride's location summary.

    Args:
        geo: The location summary, if the ride had GPS.

    Returns:
        The summary for the API, or ``None``.
    """
    if geo is None:
        return None
    return GeoOut(
        start_lat=geo.start_lat,
        start_lon=geo.start_lon,
        min_lat=geo.min_lat,
        min_lon=geo.min_lon,
        max_lat=geo.max_lat,
        max_lon=geo.max_lon,
    )


def ride_detail(ride: Ride, figures: Training, bikes: dict[str, Bike]) -> RideDetail:
    """Build the full view of a ride.

    Args:
        ride: The ride.
        figures: Its FTP-based figures.
        bikes: Every bike, by id.

    Returns:
        Everything about the ride.
    """
    s, m = ride.summary, ride.meta
    return RideDetail(
        **ride_item(ride, figures, bikes).model_dump(),
        source_name=ride.source_name,
        imported_at=ride.imported_at,
        metrics_version=ride.metrics_version,
        sport=s.sport,
        sub_sport=s.sub_sport,
        utc_offset_s=s.utc_offset_s,
        avg_speed_mps=s.avg_speed_mps,
        max_speed_mps=s.max_speed_mps,
        max_power=s.max_power,
        max_hr=s.max_hr,
        avg_cadence=s.avg_cadence,
        has_power=s.has_power,
        has_hr=s.has_hr,
        has_gps=s.has_gps,
        kj=s.kj,
        vi=s.vi,
        decoupling_pct=s.decoupling_pct,
        laps=[_lap(lap) for lap in s.laps],
        geo=_geo(s.geo),
        training=TrainingOut(
            ftp=figures.ftp,
            ftp_estimated=figures.ftp_estimated,
            weight_kg=figures.weight_kg,
            max_hr=figures.max_hr,
            intensity_factor=figures.intensity_factor,
            tss=figures.tss,
            watts_per_kg=figures.watts_per_kg,
            np_per_kg=figures.np_per_kg,
        ),
        power_zones=_zones(figures.power_zones, zones.POWER_ZONE_NAMES),
        hr_zones=_zones(figures.hr_zones, zones.HR_ZONE_NAMES),
        power_curve=_curve(s.power_curve),
        hr_curve=_curve(s.hr_curve),
        meta=MetaOut(
            name=m.name,
            notes=m.notes,
            rpe=m.rpe,
            bike=bike_ref(m.bike_id, bikes),
            bike_from_default=m.bike_from_default,
            tags=list(m.tags),
        ),
    )


def bike_out(bike: Bike) -> BikeOut:
    """Copy a bike.

    Args:
        bike: The bike.

    Returns:
        The bike for the API.
    """
    return BikeOut(id=bike.id, name=bike.name, kind=bike.kind, retired=bike.retired)


# -- requests and write responses --------------------------------------------------------------


def _clean_text(value: str | None) -> str | None:
    """Trim free text; blank text means no value.

    Args:
        value: The text as sent.

    Returns:
        The trimmed text, or ``None`` if blank or not given.
    """
    if value is None:
        return None
    return value.strip() or None


class MetaPatch(BaseModel):
    """Changes to a ride's metadata. Fields left out stay as they are; ``null`` clears one.

    Attributes:
        name: The ride's name. Blank clears it.
        notes: Free-text notes. Blank clears them.
        rpe: Perceived effort, 1-10.
        bike_id: The ride's bike. Choosing one here marks it as set by hand.
        tags: The ride's full set of tags, replacing the current ones.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    notes: str | None = None
    rpe: Annotated[int | None, Field(ge=1, le=10)] = None
    bike_id: str | None = None
    tags: list[str] | None = None

    @field_validator("name", "notes")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        """Trim the name and notes; blank clears them.

        Args:
            value: The text as sent.

        Returns:
            The trimmed text, or ``None``.
        """
        return _clean_text(value)


def _bike_name(value: str) -> str:
    """Tidy a bike name: runs of spaces become one, and it can't be blank.

    Args:
        value: The name as sent.

    Returns:
        The tidied name.

    Raises:
        ValueError: The name is blank.
    """
    clean = " ".join(value.split())
    if not clean:
        raise ValueError("Bike names can't be empty")
    return clean


class BikeCreate(BaseModel):
    """A new bike.

    Attributes:
        name: The bike's name; spaces are tidied and it can't be blank.
        kind: Road, gravel, TT and so on.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: BikeKind | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        """Tidy the name.

        Args:
            value: The name as sent.

        Returns:
            The tidied name.
        """
        return _bike_name(value)


class BikePatch(BaseModel):
    """Changes to a bike. Fields left out stay as they are.

    Attributes:
        name: A new name; spaces are tidied and it can't be blank.
        kind: A new kind; ``null`` clears it.
        retired: Retire (true) or bring back (false) the bike.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    kind: BikeKind | None = None
    retired: bool | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        """Tidy the name, if one was sent.

        Args:
            value: The name as sent, or ``None``.

        Returns:
            The tidied name, or ``None``.
        """
        return None if value is None else _bike_name(value)


class BikeWithTotals(BikeOut):
    """A bike and how much it has been ridden.

    Attributes:
        rides: Rides on the bike.
        distance_m: Their total distance.
        moving_s: Their total moving time.
    """

    rides: int
    distance_m: float
    moving_s: int


class DefaultOut(BaseModel):
    """One entry in the default-bike timeline.

    Attributes:
        slot: Which kind of ride: zwift, indoor or outdoor.
        effective_from: The first day the entry applies.
        bike: The default bike from that day, or ``None`` to stop defaulting.
    """

    slot: BikeSlot
    effective_from: date
    bike: BikeRef | None


class DefaultSet(BaseModel):
    """The bike to default to from a date.

    Attributes:
        bike_id: The bike, or ``null`` to stop defaulting from that date.
    """

    model_config = ConfigDict(extra="forbid")

    bike_id: str | None


class BackfillChange(BaseModel):
    """How many rides a backfill gives (or would give) one bike.

    Attributes:
        bike: The bike, or ``None`` for rides that lose their default bike.
        rides: How many rides.
    """

    bike: BikeRef | None
    rides: int


class BackfillResult(BaseModel):
    """What a backfill changed, or would change on a dry run.

    Attributes:
        dry_run: Whether nothing was saved.
        changes: Rides per bike, most first.
    """

    dry_run: bool
    changes: list[BackfillChange]


class AthleteValuesIn(BaseModel):
    """Athlete values from a date. Values left out carry forward from earlier entries.

    Attributes:
        ftp: FTP in watts.
        weight_kg: Body weight in kilograms.
        max_hr: Max heart rate in bpm.
    """

    model_config = ConfigDict(extra="forbid")

    ftp: Annotated[int | None, Field(gt=0, le=2000)] = None
    weight_kg: Annotated[float | None, Field(gt=0, le=300)] = None
    max_hr: Annotated[int | None, Field(gt=0, le=250)] = None


class AthleteEntryOut(AthleteValuesIn):
    """One dated entry in the athlete history.

    Attributes:
        effective_from: The first day the entry applies.
    """

    effective_from: date


class Athlete(BaseModel):
    """The athlete history and the values in effect today.

    Attributes:
        history: Every entry, oldest first.
        today: FTP, weight and max heart rate in effect today, each from the latest entry
            that sets it.
    """

    history: list[AthleteEntryOut]
    today: AthleteValuesIn
