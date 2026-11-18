"""Trends over many rides: volume, fitness, FTP, efficiency and best efforts by period.

Date ranges are the rider's local dates, inclusive at both ends. Left out, ``until`` is today
and ``since`` goes back a span that suits each view.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from fitlib.analysis import trends
from fitlib.analysis.trends import Period
from fitlib.api.deps import StoresDep
from fitlib.api.schemas import (
    CurveBestOut,
    CurveOut,
    EfficiencyOut,
    EfficiencyPointOut,
    FitnessDayOut,
    FitnessOut,
    FtpOut,
    FtpPointOut,
    Volume,
    VolumeBucketOut,
)

router = APIRouter(prefix="/trends", tags=["trends"])

DEFAULT_WEEKS = 12
DEFAULT_MONTHS = 12
DEFAULT_FITNESS_DAYS = 90
DEFAULT_YEAR_DAYS = 365
DEFAULT_CURVE_DAYS = 42


class Span(BaseModel):
    """The local dates of the first and latest rides, for an "all time" range.

    Attributes:
        first: The first ride's local date, or ``null`` for an empty library.
        last: The latest ride's local date, or ``null``.
    """

    first: date | None
    last: date | None


def date_range(since: date | None, until: date | None, default_days: int) -> tuple[date, date]:
    """Fill in a date range's missing ends and check it.

    Args:
        since: First day asked for, if any.
        until: Last day asked for, if any.
        default_days: How many days the range covers when ``since`` is left out.

    Returns:
        The first and last days.

    Raises:
        HTTPException: 422 if ``since`` is after ``until``.
    """
    until = until or date.today()
    since = since or until - timedelta(days=default_days - 1)
    if since > until:
        raise HTTPException(
            status_code=422, detail=f"since ({since}) must not be after until ({until})"
        )
    return since, until


def _months_back(day: date, months: int) -> date:
    """The 1st of the month a number of months before a day's month.

    Args:
        day: Any date.
        months: How many months back.

    Returns:
        The date.
    """
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


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
    if since is None and period == "month":
        since = _months_back(until or date.today(), DEFAULT_MONTHS - 1)
    since, until = date_range(since, until, DEFAULT_WEEKS * 7)
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
    since, until = date_range(since, until, DEFAULT_FITNESS_DAYS)
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
    since, until = date_range(since, until, DEFAULT_YEAR_DAYS)
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
    since, until = date_range(since, until, DEFAULT_YEAR_DAYS)
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
    since, until = date_range(since, until, DEFAULT_CURVE_DAYS)
    points = trends.best_curve(stores.catalog, kind, since, until)
    return CurveOut(
        kind=kind, since=since, until=until, points=[CurveBestOut(**asdict(p)) for p in points]
    )
