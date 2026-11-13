"""A ride's FTP-based figures: IF, TSS, W/kg and time in zones.

They are worked out when read, from the ride's stored figures and the athlete history in
effect on its date.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from fitlib.metrics import load, zones
from fitlib.models import AthleteEntry, Ride
from fitlib.store.interfaces import CatalogStore

EFTP_DURATION_S = 20 * 60


@dataclass(frozen=True)
class Training:
    """FTP-based figures for one ride.

    Attributes:
        ftp: The FTP used, in watts, or ``None`` if neither set nor estimable.
        ftp_estimated: Whether ``ftp`` is estimated from recent rides rather than set.
        weight_kg: Body weight on the ride's date, if set.
        max_hr: Max heart rate on the ride's date, if set.
        intensity_factor: NP / FTP, or ``None``.
        tss: Training Stress Score, or ``None``.
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
    intensity_factor: float | None
    tss: float | None
    watts_per_kg: float | None
    np_per_kg: float | None
    power_zones: tuple[int, ...] | None
    hr_zones: tuple[int, ...] | None


def ride_date(ride: Ride) -> date:
    """The day a ride happened, in the rider's local time when known.

    Args:
        ride: The ride.

    Returns:
        The local date, or the UTC date if the device didn't record local time.
    """
    return (ride.summary.local_start or ride.summary.start).date()


def estimated_ftp(catalog: CatalogStore, ride: Ride) -> float | None:
    """Estimate FTP for a ride from the best 20 minutes in the six weeks up to it.

    The window ends at the ride's start and includes the ride itself.

    Args:
        catalog: Where the other rides are.
        ride: The ride.

    Returns:
        0.95 × the best 20-minute power in the window, or ``None`` if there is none.
    """
    start = ride.summary.start
    best = catalog.best_effort_between(
        "power", EFTP_DURATION_S, start - timedelta(days=load.EFTP_LOOKBACK_DAYS), start
    )
    return load.estimated_ftp(best)


def training(
    catalog: CatalogStore, ride: Ride, history: Sequence[AthleteEntry] | None = None
) -> Training:
    """Work out a ride's FTP-based figures.

    The FTP, weight and max heart rate are those in effect on the ride's local date. When no
    FTP had been set by then, it is estimated from recent rides.

    Args:
        catalog: The library's catalog (for the athlete history and the FTP estimate).
        ride: The ride.
        history: The athlete history, if already loaded (saves a query per ride when
            working through a list).

    Returns:
        The ride's training figures.
    """
    if history is None:
        history = catalog.athlete_history()
    s = ride.summary
    athlete = load.values_on(history, ride_date(ride))

    ftp: float | None = athlete.ftp
    ftp_estimated = False
    if ftp is None and s.has_power:
        ftp = estimated_ftp(catalog, ride)
        ftp_estimated = ftp is not None

    power_zones = None
    if ftp and s.power_histogram:
        power_zones = zones.zone_times(s.power_histogram, ftp, zones.POWER_ZONE_BOUNDS)
    hr_zones = None
    if athlete.max_hr and s.hr_histogram:
        hr_zones = zones.zone_times(s.hr_histogram, athlete.max_hr, zones.HR_ZONE_BOUNDS)

    return Training(
        ftp=ftp,
        ftp_estimated=ftp_estimated,
        weight_kg=athlete.weight_kg,
        max_hr=athlete.max_hr,
        intensity_factor=load.intensity_factor(s.np, ftp),
        tss=load.training_stress_score(s.moving_s, s.np, ftp),
        watts_per_kg=load.watts_per_kg(s.avg_power, athlete.weight_kg),
        np_per_kg=load.watts_per_kg(s.np, athlete.weight_kg),
        power_zones=power_zones,
        hr_zones=hr_zones,
    )
