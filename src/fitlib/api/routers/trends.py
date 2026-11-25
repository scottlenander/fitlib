"""Trends over many rides: volume, fitness, FTP, efficiency and best efforts by period.

Date ranges are the rider's local dates, inclusive at both ends. Left out, ``until`` is today
and ``since`` goes back a span that suits each view.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter

from fitlib.analysis import trends
from fitlib.analysis.trends import Period, View, resolve_range
from fitlib.api.deps import StoresDep
from fitlib.api.schemas.trends import (
    CurveBestOut,
    CurveOut,
    EfficiencyOut,
    EfficiencyPointOut,
    FitnessDayOut,
    FitnessOut,
    FtpOut,
    FtpPointOut,
    Span,
    Volume,
    VolumeBucketOut,
)

router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/span")
def get_span(stores: StoresDep) -> Span:
    """Find the first and latest ride dates.

    Args:
        stores: The library's stores.

    Returns:
        Their local dates, or nulls for an empty library.
    """
    days = [r.local_date for r in stores.catalog.trend_rows(None, None)]
    return Span(first=min(days, default=None), last=max(days, default=None))


@router.get("/volume")
def get_volume(
    stores: StoresDep,
    period: Literal["week", "month"] = "week",
    since: date | None = None,
    until: date | None = None,
) -> Volume:
    """Add up rides, time, distance, climbing, work and TSS per week or month.

    Args:
        stores: The library's stores.
        period: ``week`` (Monday to Sunday) or ``month``.
        since: First day; by default 12 weeks or 12 months back. The first bucket is widened
            back to the start of its week or month.
        until: Last day; today by default.

    Returns:
        One bucket per week or month, empty ones included.
    """
    since, until = resolve_range(View.VOLUME, since, until, Period(period))
    buckets = trends.volume(stores.catalog, Period(period), since, until)
    return Volume(
        period=period,
        since=since,
        until=until,
        buckets=[VolumeBucketOut(**asdict(b)) for b in buckets],
    )


@router.get("/fitness")
def get_fitness(
    stores: StoresDep, since: date | None = None, until: date | None = None
) -> FitnessOut:
    """Work out fitness (CTL), fatigue (ATL) and form (TSB) for each day.

    Args:
        stores: The library's stores.
        since: First day; 90 days back by default.
        until: Last day; today by default.

    Returns:
        One entry per day, and how many rides added no TSS.
    """
    since, until = resolve_range(View.FITNESS, since, until)
    result = trends.fitness(stores.catalog, since, until)
    return FitnessOut(
        since=since,
        until=until,
        rides_without_tss=result.rides_without_tss,
        days=[FitnessDayOut(**asdict(d)) for d in result.days],
    )


@router.get("/ftp")
def get_ftp(
    stores: StoresDep,
    period: Literal["week", "month"] = "week",
    since: date | None = None,
    until: date | None = None,
) -> FtpOut:
    """Track set and estimated FTP at the end of each week or month.

    Args:
        stores: The library's stores.
        period: ``week`` or ``month``.
        since: First day; a year back by default.
        until: Last day; today by default.

    Returns:
        One point per week or month.
    """
    since, until = resolve_range(View.FTP, since, until)
    points = trends.ftp_history(stores.catalog, Period(period), since, until)
    return FtpOut(
        period=period,
        since=since,
        until=until,
        points=[FtpPointOut(**asdict(p)) for p in points],
    )


@router.get("/efficiency")
def get_efficiency(
    stores: StoresDep, since: date | None = None, until: date | None = None
) -> EfficiencyOut:
    """List the efficiency factor (NP / average heart rate) of each ride.

    Only rides with power and heart rate lasting 20 minutes or more are included.

    Args:
        stores: The library's stores.
        since: First day; a year back by default.
        until: Last day; today by default.

    Returns:
        One point per ride, oldest first.
    """
    since, until = resolve_range(View.EFFICIENCY, since, until)
    points = trends.efficiency(stores.catalog, since, until)
    return EfficiencyOut(
        since=since, until=until, points=[EfficiencyPointOut(**asdict(p)) for p in points]
    )


@router.get("/curve")
def get_curve(
    stores: StoresDep,
    kind: Literal["power", "hr"] = "power",
    since: date | None = None,
    until: date | None = None,
) -> CurveOut:
    """Find the best power or heart rate at every duration in a period.

    Args:
        stores: The library's stores.
        kind: ``power`` or ``hr``.
        since: First day; 42 days back by default.
        until: Last day; today by default.

    Returns:
        One point per duration, each with the ride it came from.
    """
    since, until = resolve_range(View.CURVE, since, until)
    points = trends.best_curve(stores.catalog, kind, since, until)
    return CurveOut(
        kind=kind, since=since, until=until, points=[CurveBestOut(**asdict(p)) for p in points]
    )
