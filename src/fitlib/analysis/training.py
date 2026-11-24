"""A ride's training figures: IF, TSS (from power, else heart rate), W/kg and time in zones.

They are worked out when read, from the ride's stored figures, the athlete history in
effect on its date and the rider's year of birth.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from fitlib.metrics import load, zones
from fitlib.metrics.load import CalibrationRide, ThresholdSource, TssSource
from fitlib.models import AthleteEntry, Ride, TrendRow
from fitlib.store.interfaces import CatalogStore

BIRTH_YEAR_KEY = "birth_year"
EARLIEST_BIRTH_YEAR = 1900


class BadBirthYear(ValueError):
    """A year of birth that can't be right (before 1900 or in the future)."""


@dataclass(frozen=True)
class EffortHistory:
    """Each ride's best 20 minutes of power by its start, for estimating FTP without a query.

    Attributes:
        starts: Ride starts with a best 20 minutes, oldest first.
        best: Each one's best 20-minute power, in watts, in the same order.
    """

    starts: tuple[datetime, ...] = ()
    best: tuple[float, ...] = ()

    @classmethod
    def from_rows(cls, rows: Iterable[TrendRow]) -> EffortHistory:
        """Collect the rides' best 20 minutes.

        Args:
            rows: Rides' trend rows, in any order.

        Returns:
            The history, with rides lacking a best 20 minutes left out.
        """
        pairs = sorted(
            (row.start, row.best_20min_power) for row in rows if row.best_20min_power is not None
        )
        return cls(tuple(p[0] for p in pairs), tuple(p[1] for p in pairs))

    def estimated_ftp(self, at: datetime) -> float | None:
        """Estimate FTP at a moment from the best 20 minutes in the six weeks up to it.

        The window takes in rides starting from ``EFTP_LOOKBACK_DAYS`` before ``at`` up to and
        including ``at`` itself, so a ride's own effort counts towards its estimate.

        Args:
            at: The moment, e.g. a ride's start.

        Returns:
            ``EFTP_FACTOR`` × the best 20 minutes in the window, or ``None`` if there is none.
        """
        lo = bisect_left(self.starts, at - timedelta(days=load.EFTP_LOOKBACK_DAYS))
        hi = bisect_right(self.starts, at)
        return load.estimated_ftp(max(self.best[lo:hi], default=None))


@dataclass(frozen=True)
class AthleteProfile:
    """Everything about the athlete that training figures use.

    Attributes:
        history: The dated FTP, weight, max and threshold heart rate entries.
        birth_year: The year the rider was born, for estimating threshold heart rate.
        calibration: Rides with power and heart rate, oldest first, for the threshold heart
            rate from your rides.
        efforts: Every ride's best 20 minutes, for estimated FTPs.
    """

    history: tuple[AthleteEntry, ...] = ()
    birth_year: int | None = None
    calibration: tuple[CalibrationRide, ...] = ()
    efforts: EffortHistory = EffortHistory()


def athlete_profile(catalog: CatalogStore) -> AthleteProfile:
    """Read the athlete history, year of birth, and what estimates come from.

    One pass over every ride's trend row gives the calibration rides and the best efforts
    for estimated FTPs, so working out figures for any number of rides needs no more queries.

    Args:
        catalog: The library's catalog.

    Returns:
        The profile (load it once when working through many rides).
    """
    year = catalog.get_setting(BIRTH_YEAR_KEY)
    rows = catalog.trend_rows(None, None)
    rides = (
        load.calibration_ride(row.local_date, row.moving_s, row.np, row.hr_squared_s)
        for row in rows
    )
    calibration = sorted((r for r in rides if r is not None), key=lambda r: r.day)
    return AthleteProfile(
        tuple(catalog.athlete_history()),
        int(year) if year else None,
        tuple(calibration),
        EffortHistory.from_rows(rows),
    )


def set_birth_year(catalog: CatalogStore, year: int | None, today: date | None = None) -> None:
    """Set or clear the rider's year of birth.

    Args:
        catalog: The library's catalog.
        year: The year, or ``None`` to clear it.
        today: Today's date (for tests); the real one by default.

    Raises:
        BadBirthYear: Before 1900 or after this year; nothing changes.
    """
    this_year = (today or date.today()).year
    if year is not None and not EARLIEST_BIRTH_YEAR <= year <= this_year:
        raise BadBirthYear(f"Give a year of birth from {EARLIEST_BIRTH_YEAR} to {this_year}.")
    catalog.set_setting(BIRTH_YEAR_KEY, str(year) if year is not None else None)


def threshold_hr_on(
    athlete: AthleteProfile, day: date, ftp: float | None
) -> tuple[int | None, ThresholdSource | None]:
    """The threshold heart rate for a day, and where it came from.

    The one set in the history; else from your rides: the FTP on the day times your heart
    rate per watt over recent rides with power and heart rate; else estimated from age.

    Args:
        athlete: The athlete's profile.
        day: The rider's local date.
        ftp: The FTP on that day (set or estimated), if any.

    Returns:
        The threshold heart rate in whole bpm and its source, or ``(None, None)``.
    """
    set_value = load.values_on(athlete.history, day).threshold_hr
    if set_value is not None:
        return set_value, ThresholdSource.SET
    per_watt = load.hr_per_watt(athlete.calibration, day)
    if ftp and per_watt:
        return round(ftp * per_watt), ThresholdSource.RIDES
    estimate = load.estimated_threshold_hr(athlete.birth_year, day)
    return (estimate, ThresholdSource.AGE) if estimate is not None else (None, None)


def threshold_today(
    athlete: AthleteProfile, today: date | None = None
) -> tuple[int | None, ThresholdSource | None]:
    """Today's threshold heart rate and where it comes from, as a ride today would use it.

    Args:
        athlete: The athlete's profile.
        today: The day (for tests); the real date by default.

    Returns:
        The threshold heart rate and its source, or ``(None, None)``.
    """
    day = today or date.today()
    ftp: float | None = load.values_on(athlete.history, day).ftp
    if ftp is None:
        ftp = athlete.efforts.estimated_ftp(
            datetime.combine(day + timedelta(days=1), time(), tzinfo=UTC)
        )
    return threshold_hr_on(athlete, day, ftp)


@dataclass(frozen=True)
class Training:
    """Training figures for one ride.

    Attributes:
        ftp: The FTP used, in watts, or ``None`` if neither set nor estimable.
        ftp_estimated: Whether ``ftp`` is estimated from recent rides rather than set.
        weight_kg: Body weight on the ride's date, if set.
        max_hr: Max heart rate on the ride's date, if set.
        threshold_hr: Threshold heart rate on the ride's date, set, from your rides or from
            your age; used for TSS when the ride has no power TSS.
        threshold_hr_source: Where ``threshold_hr`` came from, or ``None`` without one.
        intensity_factor: NP / FTP, or ``None``.
        tss: Training Stress Score, or ``None``.
        tss_source: Whether ``tss`` came from power or heart rate, or ``None`` without one.
        watts_per_kg: Average power per kilogram, or ``None``.
        np_per_kg: Normalized Power per kilogram, or ``None``.
        power_zones: Seconds in each of the 7 power zones, or ``None`` without power or FTP.
        hr_zones: Seconds in each of the 5 heart-rate zones, or ``None`` without heart rate
            or max heart rate.
    """

    ftp: float | None
    ftp_estimated: bool
    weight_kg: float | None
    max_hr: int | None
    threshold_hr: int | None
    threshold_hr_source: ThresholdSource | None
    intensity_factor: float | None
    tss: float | None
    tss_source: TssSource | None
    watts_per_kg: float | None
    np_per_kg: float | None
    power_zones: tuple[int, ...] | None
    hr_zones: tuple[int, ...] | None

    @property
    def threshold_hr_estimated(self) -> bool:
        """Whether the threshold heart rate is worked out (from rides or age), not set."""
        return self.threshold_hr_source in (ThresholdSource.RIDES, ThresholdSource.AGE)


def ride_date(ride: Ride) -> date:
    """The day a ride happened, in the rider's local time when known.

    Args:
        ride: The ride.

    Returns:
        The local date, or the UTC date if the device didn't record local time.
    """
    return (ride.summary.local_start or ride.summary.start).date()


def training(catalog: CatalogStore, ride: Ride, athlete: AthleteProfile | None = None) -> Training:
    """Work out a ride's training figures.

    The FTP, weight, max and threshold heart rate are those in effect on the ride's local
    date. When no FTP had been set by then, it is estimated from recent rides; when no
    threshold heart rate had, it comes from your rides with power and heart rate, or else
    your age. TSS comes from power when the ride has
    power and an FTP, else from heart rate.

    Args:
        catalog: The library's catalog (for the athlete's profile, if not given).
        ride: The ride.
        athlete: The athlete's profile, if already loaded (saves queries per ride when
            working through a list).

    Returns:
        The ride's training figures.
    """
    if athlete is None:
        athlete = athlete_profile(catalog)
    s = ride.summary
    day = ride_date(ride)
    values = load.values_on(athlete.history, day)

    ftp: float | None = values.ftp
    ftp_estimated = False
    if ftp is None and s.has_power:
        ftp = athlete.efforts.estimated_ftp(s.start)
        ftp_estimated = ftp is not None

    power_zones = None
    if ftp and s.power_histogram:
        power_zones = zones.zone_times(s.power_histogram, ftp, zones.POWER_ZONE_BOUNDS)
    hr_zones = None
    if values.max_hr and s.hr_histogram:
        hr_zones = zones.zone_times(s.hr_histogram, values.max_hr, zones.HR_ZONE_BOUNDS)
    # A ride without power still has an FTP on its day, for the threshold from your rides.
    day_ftp = ftp
    if day_ftp is None and athlete.calibration and load.hr_per_watt(athlete.calibration, day):
        day_ftp = athlete.efforts.estimated_ftp(s.start)
    threshold_hr, threshold_source = threshold_hr_on(athlete, day, day_ftp)
    tss, source = load.ride_tss(
        s.moving_s, s.np, ftp, load.hr_squared_seconds(s.hr_histogram), threshold_hr
    )

    return Training(
        ftp=ftp,
        ftp_estimated=ftp_estimated,
        weight_kg=values.weight_kg,
        max_hr=values.max_hr,
        threshold_hr=threshold_hr,
        threshold_hr_source=threshold_source,
        intensity_factor=load.intensity_factor(s.np, ftp),
        tss=tss,
        tss_source=source,
        watts_per_kg=load.watts_per_kg(s.avg_power, values.weight_kg),
        np_per_kg=load.watts_per_kg(s.np, values.weight_kg),
        power_zones=power_zones,
        hr_zones=hr_zones,
    )
