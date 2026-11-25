"""Rides: the library list and one ride's detail.

Also its streams, map, similar rides and route progress, and editing and deleting rides.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fitlib.api.schemas.common import BikeRef, bike_ref
from fitlib.metadata import MAX_BULK_RIDES
from fitlib.metrics import zones
from fitlib.metrics.load import ThresholdSource, TssSource
from fitlib.metrics.track import Track
from fitlib.models import (
    Curve,
    GeoSummary,
    Lap,
    OffsetSource,
    Source,
)
from fitlib.services.context import RideView


class RideItem(BaseModel):
    """One ride in a list: enough for a library table.

    Attributes:
        id: The ride's id.
        short_id: The first 8 characters of the id.
        name: The user's name for the ride, or one built from its source and date.
        start: Start time, UTC.
        local_start: Start time on the rider's clock, if the device recorded it.
        time_zone_source: Where ``local_start``'s time zone came from: ``device`` (the
            file's own local time), ``file_name`` (e.g. Zwift's), ``default`` (the library's
            default time zone) or ``none`` (shown in UTC).
        source: Zwift, Garmin or other.
        zwift_world: For Zwift rides, the world ridden in (e.g. "Watopia"), from where the
            ride started; ``null`` if unknown or not Zwift.
        indoor: Whether the ride was indoors.
        device: The recording device, if known.
        moving_s: Moving time.
        elapsed_s: Elapsed time.
        distance_m: Distance, if recorded.
        ascent_m: Climbing, if recorded.
        avg_power: Average power, if recorded.
        np: Normalized Power, if there was power.
        avg_hr: Average heart rate, if recorded.
        tss: Training Stress Score: from power and an FTP, else from heart rate and a
            threshold heart rate.
        tss_source: ``"power"`` or ``"hr"`` (heart rate), or ``null`` without a TSS.
        ftp_estimated: Whether the TSS uses an estimated FTP.
        threshold_hr_estimated: Whether a heart-rate TSS uses a threshold heart rate worked
            out (from your rides or your age) rather than set.
        rpe: Perceived effort, 1-10, if set.
        bike: The ride's bike, if any.
        tags: The ride's tags.
    """

    id: str
    short_id: str
    name: str
    start: datetime
    local_start: datetime | None
    time_zone_source: OffsetSource
    source: Source
    zwift_world: str | None
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
    tss_source: TssSource | None
    ftp_estimated: bool
    threshold_hr_estimated: bool
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
    """Training figures, using the athlete values in effect on the ride's date.

    Attributes:
        ftp: The FTP used, if set or estimable.
        ftp_estimated: Whether ``ftp`` is estimated from recent rides.
        weight_kg: Body weight on the day, if set.
        max_hr: Max heart rate on the day, if set.
        threshold_hr: Threshold heart rate on the day, set or estimated from age.
        threshold_hr_estimated: Whether ``threshold_hr`` is worked out rather than set.
        threshold_hr_source: ``"set"``, ``"rides"`` (your rides with power and heart rate,
            and the day's FTP) or ``"age"``; ``null`` without a threshold.
        intensity_factor: NP / FTP.
        tss: Training Stress Score.
        tss_source: ``"power"`` or ``"hr"`` (heart rate, for rides without power TSS).
        watts_per_kg: Average power per kilogram.
        np_per_kg: Normalized Power per kilogram.
    """

    ftp: float | None
    ftp_estimated: bool
    weight_kg: float | None
    max_hr: int | None
    threshold_hr: int | None
    threshold_hr_estimated: bool
    threshold_hr_source: ThresholdSource | None
    intensity_factor: float | None
    tss: float | None
    tss_source: TssSource | None
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


def _naive(moment: datetime | None) -> datetime | None:
    """Drop a time zone label, for clock times that aren't really UTC.

    Args:
        moment: A time labelled UTC, or ``None``.

    Returns:
        The same wall-clock time with no time zone, or ``None``.
    """
    return moment.replace(tzinfo=None) if moment is not None else None


def ride_item(view: RideView) -> RideItem:
    """Build a list entry for a ride.

    Args:
        view: The ride with its figures and bike.

    Returns:
        The list entry.
    """
    ride, figures = view.ride, view.figures
    s, m = ride.summary, ride.meta
    return RideItem(
        id=ride.id,
        short_id=ride.short_id,
        name=ride.display_name,
        start=s.start,
        local_start=_naive(s.local_start),
        time_zone_source=s.utc_offset_source,
        source=s.source,
        zwift_world=view.world,
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
        tss_source=figures.tss_source,
        ftp_estimated=figures.ftp_estimated,
        threshold_hr_estimated=figures.threshold_hr_estimated,
        rpe=m.rpe,
        bike=bike_ref(view.bike),
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


def ride_detail(view: RideView) -> RideDetail:
    """Build the full view of a ride.

    Args:
        view: The ride with its figures and bike.

    Returns:
        Everything about the ride.
    """
    ride, figures = view.ride, view.figures
    s, m = ride.summary, ride.meta
    return RideDetail(
        **ride_item(view).model_dump(),
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
            threshold_hr=figures.threshold_hr,
            threshold_hr_estimated=figures.threshold_hr_estimated,
            threshold_hr_source=figures.threshold_hr_source,
            intensity_factor=figures.intensity_factor,
            tss=figures.tss,
            tss_source=figures.tss_source,
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
            bike=bike_ref(view.bike),
            bike_from_default=m.bike_from_default,
            tags=list(m.tags),
        ),
    )


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


class BulkMetaPatch(BaseModel):
    """The same change to several rides' effort, bike and tags.

    Fields left out stay as they are; ``null`` clears the effort or the bike.

    Attributes:
        ids: The rides, by id or unique prefix.
        rpe: Perceived effort, 1-10.
        bike_id: The rides' bike. Choosing or clearing one here marks it as set by hand.
        add_tags: Tags to add to each ride.
        remove_tags: Tags to take off each ride.
    """

    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[str], Field(min_length=1, max_length=MAX_BULK_RIDES)]
    rpe: Annotated[int | None, Field(ge=1, le=10)] = None
    bike_id: str | None = None
    add_tags: list[str] = []
    remove_tags: list[str] = []


class BulkDelete(BaseModel):
    """Rides to delete together.

    Attributes:
        ids: The rides, by id or unique prefix.
    """

    model_config = ConfigDict(extra="forbid")

    ids: Annotated[list[str], Field(min_length=1, max_length=MAX_BULK_RIDES)]


class DeleteResult(BaseModel):
    """What a delete did.

    Attributes:
        deleted: How many rides were deleted (each once, however often it was named).
    """

    deleted: int


class BulkMetaResult(BaseModel):
    """What a change to several rides did.

    Attributes:
        updated: How many rides were changed.
    """

    updated: int


class MapPoint(BaseModel):
    """One point of a ride's route on the map.

    Attributes:
        t: Seconds from the start, to match the Ride Stats charts.
        lat: Latitude, degrees.
        lon: Longitude, degrees.
        distance_m: Distance ridden by then, if recorded.
    """

    t: int
    lat: float
    lon: float
    distance_m: float | None


class RideMap(BaseModel):
    """A ride's route for a map, simplified to at most a couple of thousand points.

    Attributes:
        ride_id: The ride's id.
        points: The route, in order; empty for rides without positions.
        bounds: ``[south, west, north, east]`` around the route, if it has one.
        start_finish_m: How far apart the first and last positions are.
        zwift_world: For Zwift rides, the world: their positions are Zwift's, not real
            places, so they go on a plain background.
    """

    ride_id: str
    points: list[MapPoint]
    bounds: list[float] | None
    start_finish_m: float | None
    zwift_world: str | None


def ride_map(ride_id: str, track: Track | None, world: str | None) -> RideMap:
    """Build a ride's map from its simplified track.

    Args:
        ride_id: The ride's id.
        track: Its track, or ``None`` without positions.
        world: Its Zwift world's name, if any.

    Returns:
        The map's data.
    """
    if track is None:
        return RideMap(
            ride_id=ride_id, points=[], bounds=None, start_finish_m=None, zwift_world=world
        )
    return RideMap(
        ride_id=ride_id,
        points=[
            MapPoint(t=p.t, lat=p.lat, lon=p.lon, distance_m=p.distance_m) for p in track.points
        ],
        bounds=list(track.bounds),
        start_finish_m=track.start_finish_m,
        zwift_world=world,
    )


class RouteProgress(BaseModel):
    """Every ride on the same route as a given one, to see progress over time.

    Attributes:
        has_route: Whether the asked-about ride has positions to match routes on.
        items: The same-route rides, the asked-about one included, oldest first.
    """

    has_route: bool
    items: list[RideItem]
