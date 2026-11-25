"""Trends over many rides."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class VolumeBucketOut(BaseModel):
    """What was ridden in one week or month.

    Attributes:
        start: The first day of the week (Monday) or month.
        rides: Number of rides.
        moving_s: Riding time.
        distance_m: Distance.
        ascent_m: Climbing.
        kj: Work in kilojoules.
        tss: Total Training Stress Score.
        rides_without_tss: Rides adding no TSS (neither from power nor heart rate).
    """

    start: date
    rides: int
    moving_s: int
    distance_m: float
    ascent_m: float
    kj: float
    tss: float
    rides_without_tss: int


class Volume(BaseModel):
    """Riding per week or month.

    Attributes:
        period: ``week`` or ``month``.
        since: First day asked for (the first bucket starts on or before it).
        until: Last day.
        buckets: One per week or month, oldest first, empty ones included.
    """

    period: Literal["week", "month"]
    since: date
    until: date
    buckets: list[VolumeBucketOut]


class FitnessDayOut(BaseModel):
    """Training load on one day.

    Attributes:
        day: The local date.
        tss: TSS ridden that day.
        fitness: Chronic training load (CTL, 42-day average) at the end of the day.
        fatigue: Acute training load (ATL, 7-day average) at the end of the day.
        form: Training stress balance (TSB): yesterday's fitness minus fatigue.
    """

    day: date
    tss: float
    fitness: float
    fatigue: float
    form: float


class FitnessOut(BaseModel):
    """Fitness, fatigue and form for each day of a range.

    Attributes:
        since: First day.
        until: Last day.
        rides_without_tss: Rides in the range that add no TSS (neither from power nor heart
            rate).
        days: One per day, oldest first.
    """

    since: date
    until: date
    rides_without_tss: int
    days: list[FitnessDayOut]


class FtpPointOut(BaseModel):
    """FTP at the end of one week or month.

    Attributes:
        day: The last day of the week or month (or of the range).
        ftp: The FTP set in the athlete history on that day, if any.
        estimated: 0.95 × the best 20 minutes in the six weeks up to that day, if any.
    """

    day: date
    ftp: int | None
    estimated: float | None


class FtpOut(BaseModel):
    """Set and estimated FTP over time.

    Attributes:
        period: ``week`` or ``month``.
        since: First day asked for.
        until: Last day.
        points: One per week or month, oldest first.
    """

    period: Literal["week", "month"]
    since: date
    until: date
    points: list[FtpPointOut]


class EfficiencyPointOut(BaseModel):
    """One ride's efficiency factor.

    Attributes:
        ride_id: The ride.
        day: Its local date.
        efficiency: Normalized Power / average heart rate, in W per bpm.
        np: Normalized Power.
        avg_hr: Average heart rate.
        decoupling_pct: Aerobic decoupling, if worked out.
        indoor: Whether it was ridden indoors.
    """

    ride_id: str
    day: date
    efficiency: float
    np: float
    avg_hr: float
    decoupling_pct: float | None
    indoor: bool


class EfficiencyOut(BaseModel):
    """Efficiency of each ride with power and heart rate lasting 20 minutes or more.

    Attributes:
        since: First day.
        until: Last day.
        points: One per ride, oldest first.
    """

    since: date
    until: date
    points: list[EfficiencyPointOut]


class CurveBestOut(BaseModel):
    """The best effort over one duration in a period.

    Attributes:
        duration_s: The duration.
        value: Best average power (W) or heart rate (bpm).
        ride_id: The ride it came from.
        start: That ride's start, UTC.
    """

    duration_s: int
    value: float
    ride_id: str
    start: datetime


class CurveOut(BaseModel):
    """Best efforts at every duration in a period.

    Attributes:
        kind: ``power`` or ``hr``.
        since: First day.
        until: Last day.
        points: One per duration, shortest first.
    """

    kind: Literal["power", "hr"]
    since: date
    until: date
    points: list[CurveBestOut]
