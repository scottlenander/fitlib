"""Trends over many rides: volume, fitness and fatigue, FTP, efficiency, best efforts, routes.

Everything comes from the per-ride figures in the catalog (``trend_rows``), never from streams,
so a few thousand rides take one query. Rides are placed on their local date; date ranges are
local dates, inclusive at both ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum

from fitlib.analysis.similar import similar_routes
from fitlib.analysis.training import AthleteProfile, athlete_profile, threshold_hr_on
from fitlib.metrics import load
from fitlib.metrics.load import TssSource
from fitlib.models import CurveBest, Ride, TrendRow
from fitlib.store.interfaces import CatalogStore, RideCatalog

# Fitness (CTL) and fatigue (ATL): exponentially weighted averages of daily TSS over these.
FITNESS_DAYS = 42
FATIGUE_DAYS = 7

# Efficiency is only worth plotting for rides long enough for heart rate to settle.
EFFICIENCY_MIN_MOVING_S = 20 * 60

# How many rides sharing the most cells are scored when listing a route's history.
ROUTE_PROGRESS_CANDIDATES = 500

# Local times lie between UTC-12 and UTC+14, so a local date range covers these UTC margins.
_EARLIEST_OFFSET = timedelta(hours=-12)
_LATEST_OFFSET = timedelta(hours=14)


class Period(StrEnum):
    """How volume and FTP are grouped."""

    WEEK = "week"
    MONTH = "month"


class View(StrEnum):
    """The kinds of trend, each with its own default date range."""

    VOLUME = "volume"
    FITNESS = "fitness"
    FTP = "ftp"
    EFFICIENCY = "efficiency"
    CURVE = "curve"


# How far back each view goes when no start date is given (monthly volume: 12 months).
DEFAULT_DAYS = {
    View.VOLUME: 12 * 7,
    View.FITNESS: 90,
    View.FTP: 365,
    View.EFFICIENCY: 365,
    View.CURVE: 42,
}
DEFAULT_MONTHS = 12


class BadRange(ValueError):
    """A date range that ends before it starts."""

    def __init__(self, since: date, until: date):
        """Name both dates in the message.

        Args:
            since: The first day asked for.
            until: The last day asked for.
        """
        super().__init__(f"since ({since}) must not be after until ({until})")


@dataclass(frozen=True)
class RideLoad:
    """One ride with its training stress worked out as on the ride page.

    Attributes:
        row: The ride's trend figures.
        ftp: The FTP used for its TSS, or ``None``.
        ftp_estimated: Whether ``ftp`` was estimated from recent rides.
        tss: Training Stress Score, or ``None`` (no power TSS, and no heart rate or no
            threshold heart rate to compare with).
        tss_source: Whether ``tss`` came from power or heart rate.
    """

    row: TrendRow
    ftp: float | None
    ftp_estimated: bool
    tss: float | None
    tss_source: TssSource | None = None


@dataclass(frozen=True)
class VolumeBucket:
    """What was ridden in one week or month.

    Attributes:
        start: The first day of the week (Monday) or month.
        rides: Number of rides.
        moving_s: Riding time in seconds.
        distance_m: Distance in metres.
        ascent_m: Climbing in metres.
        kj: Work in kilojoules.
        tss: Total Training Stress Score.
        rides_without_tss: Rides that add no TSS (no power TSS and no heart-rate TSS).
    """

    start: date
    rides: int = 0
    moving_s: int = 0
    distance_m: float = 0.0
    ascent_m: float = 0.0
    kj: float = 0.0
    tss: float = 0.0
    rides_without_tss: int = 0


@dataclass(frozen=True)
class FitnessDay:
    """Training load on one day.

    Attributes:
        day: The local date.
        tss: TSS ridden that day.
        fitness: Chronic training load (CTL) at the end of the day.
        fatigue: Acute training load (ATL) at the end of the day.
        form: Training stress balance (TSB): yesterday's fitness minus fatigue, i.e. how fresh
            the rider was going into the day.
    """

    day: date
    tss: float
    fitness: float
    fatigue: float
    form: float


@dataclass(frozen=True)
class Fitness:
    """Fitness, fatigue and form for each day of a range.

    Attributes:
        days: One entry per day, oldest first.
        rides_without_tss: Rides in the range that add no TSS (neither from power nor heart
            rate).
    """

    days: list[FitnessDay]
    rides_without_tss: int


@dataclass(frozen=True)
class FtpPoint:
    """FTP at the end of one week or month.

    Attributes:
        day: The last day of the week or month (or of the range, if earlier).
        ftp: The FTP set in the athlete history on that day, if any.
        estimated: ``EFTP_FACTOR`` × the best 20 minutes in the six weeks up to that day, if
            any ride in them had one.
    """

    day: date
    ftp: int | None
    estimated: float | None


@dataclass(frozen=True)
class EfficiencyPoint:
    """How much power one ride got for its heart rate.

    Attributes:
        ride_id: The ride.
        day: Its local date.
        efficiency: Efficiency factor: Normalized Power / average heart rate (W per bpm).
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


def utc_bounds(since: date | None, until: date | None) -> tuple[datetime | None, datetime | None]:
    """Widen a local date range into UTC times that surely contain its rides.

    Args:
        since: First local date, or ``None``.
        until: Last local date, or ``None``.

    Returns:
        The earliest and latest UTC start a ride in the range could have.
    """
    start = end = None
    if since is not None:
        start = datetime.combine(since, time(), UTC) - _LATEST_OFFSET
    if until is not None:
        end = datetime.combine(until + timedelta(days=1), time(), UTC) - _EARLIEST_OFFSET
    return start, end


def months_back(day: date, months: int) -> date:
    """The 1st of the month a number of months before a day's month.

    Args:
        day: Any date.
        months: How many months back.

    Returns:
        The date.
    """
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def resolve_range(
    view: View,
    since: date | None,
    until: date | None,
    period: Period = Period.WEEK,
    today: date | None = None,
) -> tuple[date, date]:
    """Fill in a date range's missing ends with the view's defaults, and check it.

    Args:
        view: Which trend the range is for.
        since: First day asked for, if any.
        until: Last day asked for, if any.
        period: For volume, whether it's by week or month.
        today: Today's date; the computer's by default.

    Returns:
        The first and last days. ``until`` defaults to today; ``since`` to
        ``DEFAULT_DAYS[view]`` days before it (inclusive), or for monthly volume the 1st of the
        month ``DEFAULT_MONTHS - 1`` months before.

    Raises:
        BadRange: ``since`` is after ``until``.
    """
    until = until or today or date.today()
    if since is None:
        if view is View.VOLUME and period is Period.MONTH:
            since = months_back(until, DEFAULT_MONTHS - 1)
        else:
            since = until - timedelta(days=DEFAULT_DAYS[view] - 1)
    if since > until:
        raise BadRange(since, until)
    return since, until


def _in_range(day: date, since: date | None, until: date | None) -> bool:
    return (since is None or day >= since) and (until is None or day <= until)


def period_start(day: date, period: Period) -> date:
    """The first day of the week (Monday) or month a day falls in.

    Args:
        day: Any date.
        period: Week or month.

    Returns:
        The Monday on or before ``day``, or the 1st of its month.
    """
    if period is Period.WEEK:
        return day - timedelta(days=day.weekday())
    return day.replace(day=1)


def next_period(start: date, period: Period) -> date:
    """The first day of the following week or month.

    Args:
        start: The first day of a week or month.
        period: Week or month.

    Returns:
        Seven days on, or the 1st of the next month.
    """
    if period is Period.WEEK:
        return start + timedelta(days=7)
    return (start.replace(day=28) + timedelta(days=4)).replace(day=1)


def ride_loads(
    catalog: CatalogStore,
    since: date | None,
    until: date | None,
    athlete: AthleteProfile | None = None,
) -> list[RideLoad]:
    """Work out TSS for every ride in a local date range, as the ride page does.

    The FTP is the one set in the athlete history on the ride's date, or else estimated from
    the six weeks before the ride. Rides without power TSS use heart rate, with the
    threshold heart rate set on that date or estimated from the rider's age.

    Args:
        catalog: The library's catalog.
        since: First local date, or ``None`` for the first ride.
        until: Last local date, or ``None`` for the latest ride.
        athlete: The athlete's profile, if already loaded.

    Returns:
        The rides in the range, oldest first.
    """
    if athlete is None:
        athlete = athlete_profile(catalog)
    loads = []
    for row in catalog.trend_rows(*utc_bounds(since, until)):
        if not _in_range(row.local_date, since, until):
            continue
        estimate = athlete.efforts.estimated_ftp(row.start)
        ftp: float | None = load.values_on(athlete.history, row.local_date).ftp
        estimated = False
        if ftp is None and row.np is not None:
            ftp, estimated = estimate, estimate is not None
        day_ftp = ftp if ftp is not None else estimate
        threshold_hr, _ = threshold_hr_on(athlete, row.local_date, day_ftp)
        tss, source = load.ride_tss(row.moving_s, row.np, ftp, row.hr_squared_s, threshold_hr)
        loads.append(RideLoad(row, ftp, estimated, tss, source))
    return loads


def volume(catalog: CatalogStore, period: Period, since: date, until: date) -> list[VolumeBucket]:
    """Add up riding per week or month.

    The range is widened to whole weeks or months at the start, so the first bucket is
    complete. Weeks or months with no rides are included, as zeros.

    Args:
        catalog: The library's catalog.
        period: Week or month.
        since: First local date.
        until: Last local date.

    Returns:
        One bucket per week or month, oldest first.
    """
    first = period_start(since, period)
    buckets: dict[date, dict[str, float]] = {}
    day = first
    while day <= until:
        buckets[day] = {"rides": 0, "moving_s": 0, "distance_m": 0.0, "ascent_m": 0.0}
        buckets[day] |= {"kj": 0.0, "tss": 0.0, "rides_without_tss": 0}
        day = next_period(day, period)
    for ride in ride_loads(catalog, first, until):
        row = ride.row
        b = buckets[period_start(row.local_date, period)]
        b["rides"] += 1
        b["moving_s"] += row.moving_s
        b["distance_m"] += row.distance_m or 0.0
        b["ascent_m"] += row.ascent_m or 0.0
        b["kj"] += row.kj or 0.0
        if ride.tss is None:
            b["rides_without_tss"] += 1
        else:
            b["tss"] += ride.tss
    return [
        VolumeBucket(
            start=start,
            rides=int(b["rides"]),
            moving_s=int(b["moving_s"]),
            distance_m=b["distance_m"],
            ascent_m=b["ascent_m"],
            kj=b["kj"],
            tss=b["tss"],
            rides_without_tss=int(b["rides_without_tss"]),
        )
        for start, b in buckets.items()
    ]


def fitness(catalog: CatalogStore, since: date, until: date) -> Fitness:
    """Work out fitness, fatigue and form for each day of a range.

    They are built up day by day from the very first ride in the library, so the values on a
    day don't depend on the range asked for. Rides without TSS count as 0.

    Args:
        catalog: The library's catalog.
        since: First local date.
        until: Last local date.

    Returns:
        One entry per day from ``since`` to ``until``.
    """
    loads = ride_loads(catalog, None, until)
    daily: dict[date, float] = {}
    for ride in loads:
        daily[ride.row.local_date] = daily.get(ride.row.local_date, 0.0) + (ride.tss or 0.0)
    day = min([since, *daily])
    ctl = atl = 0.0
    days = []
    while day <= until:
        tss = daily.get(day, 0.0)
        form = ctl - atl
        ctl += (tss - ctl) / FITNESS_DAYS
        atl += (tss - atl) / FATIGUE_DAYS
        if day >= since:
            days.append(FitnessDay(day, tss, ctl, atl, form))
        day += timedelta(days=1)
    without = sum(1 for r in loads if r.tss is None and r.row.local_date >= since)
    return Fitness(days, without)


def ftp_history(catalog: CatalogStore, period: Period, since: date, until: date) -> list[FtpPoint]:
    """Track set and estimated FTP at the end of each week or month.

    Args:
        catalog: The library's catalog.
        period: Week or month.
        since: First local date.
        until: Last local date.

    Returns:
        One point per week or month, at its last day (or ``until``, for the last), oldest first.
    """
    history = catalog.athlete_history()
    lookback = timedelta(days=load.EFTP_LOOKBACK_DAYS)
    rows = [
        r
        for r in catalog.trend_rows(*utc_bounds(since - lookback, until))
        if r.best_20min_power is not None
    ]
    points = []
    start = period_start(since, period)
    while start <= until:
        day = min(next_period(start, period) - timedelta(days=1), until)
        best = max(
            (
                r.best_20min_power
                for r in rows
                if day - lookback < r.local_date <= day and r.best_20min_power is not None
            ),
            default=None,
        )
        points.append(FtpPoint(day, load.values_on(history, day).ftp, load.estimated_ftp(best)))
        start = next_period(start, period)
    return points


def efficiency(catalog: RideCatalog, since: date, until: date) -> list[EfficiencyPoint]:
    """List each ride's efficiency factor (Normalized Power per heartbeat per minute).

    Only rides with power and heart rate, at least ``EFFICIENCY_MIN_MOVING_S`` long, count.

    Args:
        catalog: The library's catalog.
        since: First local date.
        until: Last local date.

    Returns:
        One point per ride, oldest first.
    """
    return [
        EfficiencyPoint(
            ride_id=r.id,
            day=r.local_date,
            efficiency=r.np / r.avg_hr,
            np=r.np,
            avg_hr=r.avg_hr,
            decoupling_pct=r.decoupling_pct,
            indoor=r.indoor,
        )
        for r in catalog.trend_rows(*utc_bounds(since, until))
        if _in_range(r.local_date, since, until)
        and r.np
        and r.avg_hr
        and r.moving_s >= EFFICIENCY_MIN_MOVING_S
    ]


def best_curve(catalog: RideCatalog, kind: str, since: date, until: date) -> list[CurveBest]:
    """Find the best effort at each duration among rides in a local date range.

    Args:
        catalog: The library's catalog.
        kind: ``"power"`` or ``"hr"``.
        since: First local date.
        until: Last local date.

    Returns:
        One entry per duration, shortest first, each with the ride it came from.
    """
    inside = [
        r.start
        for r in catalog.trend_rows(*utc_bounds(since, until))
        if _in_range(r.local_date, since, until)
    ]
    if not inside:
        return []
    # The first and last rides inside the range, so rides just outside it by local date are
    # left out.
    return catalog.best_curve_between(kind, inside[0], inside[-1])


def route_progress(catalog: RideCatalog, ride: Ride) -> list[Ride]:
    """List every ride on the same route as this one, including it, oldest first.

    Args:
        catalog: The library's catalog.
        ride: The ride.

    Returns:
        The rides; just this ride when it has no positions or nothing else matches.
    """
    matches = similar_routes(
        catalog, ride, limit=ROUTE_PROGRESS_CANDIDATES, candidates=ROUTE_PROGRESS_CANDIDATES
    )
    rides = [ride, *(m.ride for m in matches if m.same_route)]
    return sorted(rides, key=lambda r: (r.summary.start, r.id))
