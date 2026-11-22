"""Training load (IF, TSS from power or heart rate, W/kg) and the athlete's values on a date.

Also estimated FTP and threshold heart rate.

These are worked out when read rather than stored, so changing the athlete history takes
effect everywhere at once.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from fitlib.models import AthleteEntry, Histogram

# Estimated FTP: this share of the best 20-minute power in the recent past.
EFTP_FACTOR = 0.95
EFTP_LOOKBACK_DAYS = 42
# Estimated threshold heart rate: this share of the max heart rate expected at the rider's
# age, by Tanaka's formula (208 - 0.7 x age).
TANAKA_INTERCEPT = 208.0
TANAKA_SLOPE = 0.7
THRESHOLD_SHARE_OF_MAX = 0.9
# Threshold heart rate from your own rides: heart rate per watt over rides with power and
# heart rate of at least this long, in this many days up to the day, once there are enough.
CALIBRATION_DAYS = 90
CALIBRATION_MIN_RIDES = 3
CALIBRATION_MIN_S = 20 * 60


class TssSource(StrEnum):
    """What a ride's TSS was worked out from."""

    POWER = "power"
    HEART_RATE = "hr"


class ThresholdSource(StrEnum):
    """Where a threshold heart rate came from."""

    # Set in the athlete history.
    SET = "set"
    # From your rides with power and heart rate, and the FTP on the day.
    RIDES = "rides"
    # Estimated from your age.
    AGE = "age"


@dataclass(frozen=True)
class CalibrationRide:
    """What one ride with power and heart rate adds to the heart rate per watt.

    Attributes:
        day: The ride's local date.
        power_term: Riding seconds times NP squared (W² · s).
        hr_term: Riding seconds times heart rate squared, summed (bpm² · s).
    """

    day: date
    power_term: float
    hr_term: float


def calibration_ride(
    day: date, moving_s: int, np: float | None, hr_squared_s: float | None
) -> CalibrationRide | None:
    """A ride's part in the heart rate per watt, if it can have one.

    Args:
        day: Its local date.
        moving_s: Its riding time.
        np: Its Normalized Power, if it has power.
        hr_squared_s: Its riding seconds times heart rate squared, if it has heart rate.

    Returns:
        Its terms, or ``None`` without power or heart rate, or when shorter than
        ``CALIBRATION_MIN_S``.
    """
    if not np or not hr_squared_s or moving_s < CALIBRATION_MIN_S:
        return None
    return CalibrationRide(day, moving_s * np * np, hr_squared_s)


def hr_per_watt(rides: Sequence[CalibrationRide], day: date) -> float | None:
    """Heart rate per watt of NP over recent rides, as TSS sees them.

    With it, ``FTP x hr_per_watt`` is the threshold heart rate at which a ride's heart-rate
    TSS adds up to its power TSS: power TSS is ``Σ s x NP² / FTP²`` and heart-rate TSS
    ``Σ s x HR² / threshold²`` (both / 36), so over these rides
    ``threshold = FTP x sqrt(Σ s·HR² / Σ s·NP²)``. It doesn't depend on FTP itself.

    Args:
        rides: Rides with power and heart rate, oldest first by day.
        day: The day it's for.

    Returns:
        ``sqrt(Σ hr_term / Σ power_term)`` over the rides in the ``CALIBRATION_DAYS`` days up
        to ``day`` (included), or ``None`` with fewer than ``CALIBRATION_MIN_RIDES``.
    """
    days = [r.day for r in rides]
    lo = bisect_left(days, day - timedelta(days=CALIBRATION_DAYS - 1))
    hi = bisect_right(days, day)
    window = rides[lo:hi]
    if len(window) < CALIBRATION_MIN_RIDES:
        return None
    return math.sqrt(sum(r.hr_term for r in window) / sum(r.power_term for r in window))


@dataclass(frozen=True)
class AthleteValues:
    """The athlete's FTP, weight, max and threshold heart rate on one day, from the history.

    Attributes:
        ftp: Watts, or ``None`` if no entry on or before the day sets it.
        weight_kg: Kilograms, or ``None`` if no entry on or before the day sets it.
        max_hr: Beats per minute, or ``None`` if no entry on or before the day sets it.
        threshold_hr: Beats per minute, or ``None`` if no entry on or before the day sets it.
    """

    ftp: int | None = None
    weight_kg: float | None = None
    max_hr: int | None = None
    threshold_hr: int | None = None


def values_on(history: Iterable[AthleteEntry], day: date) -> AthleteValues:
    """Find the FTP, weight, max and threshold heart rate in effect on a day.

    Each value comes from the latest entry on or before ``day`` that sets it, so the values
    can come from different entries.

    Args:
        history: The athlete's entries, in any order.
        day: The day in question (the rider's local date).

    Returns:
        The values in effect; any never set by then are ``None``.
    """
    ftp = weight = max_hr = threshold_hr = None
    for entry in sorted(history, key=lambda e: e.effective_from):
        if entry.effective_from > day:
            break
        ftp = entry.ftp if entry.ftp is not None else ftp
        weight = entry.weight_kg if entry.weight_kg is not None else weight
        max_hr = entry.max_hr if entry.max_hr is not None else max_hr
        threshold_hr = entry.threshold_hr if entry.threshold_hr is not None else threshold_hr
    return AthleteValues(ftp=ftp, weight_kg=weight, max_hr=max_hr, threshold_hr=threshold_hr)


def estimated_threshold_hr(birth_year: int | None, day: date) -> int | None:
    """Estimate threshold heart rate from the rider's age on a day.

    Args:
        birth_year: The year the rider was born.
        day: The day (its year gives the age).

    Returns:
        ``THRESHOLD_SHARE_OF_MAX`` of the age-predicted max heart rate (Tanaka:
        208 - 0.7 x age), in whole bpm; ``None`` without a birth year, or for a day before
        it.
    """
    if birth_year is None or day.year < birth_year:
        return None
    predicted_max = TANAKA_INTERCEPT - TANAKA_SLOPE * (day.year - birth_year)
    return round(THRESHOLD_SHARE_OF_MAX * predicted_max)


def hr_squared_seconds(histogram: Histogram) -> float | None:
    """Sum riding seconds times heart rate squared, the ride's part of heart-rate TSS.

    Args:
        histogram: Riding seconds at each whole bpm.

    Returns:
        The sum in bpm² · s, or ``None`` without heart rate.
    """
    return sum(seconds * bpm * bpm for bpm, seconds in histogram) or None


def hr_training_stress_score(
    hr_squared_s: float | None, threshold_hr: float | None
) -> float | None:
    """TSS from heart rate, for rides without power: an hour at threshold heart rate scores 100.

    Like power TSS with heart rate in place of Normalized Power: each riding second adds
    (heart rate / threshold heart rate)², so easy riding counts for little and riding above
    threshold for more.

    Args:
        hr_squared_s: The ride's riding seconds times heart rate squared, summed.
        threshold_hr: Threshold heart rate in bpm.

    Returns:
        ``Σ seconds × (HR / threshold)² / 3600 × 100``, or ``None`` if either is missing.
    """
    if not hr_squared_s or not threshold_hr:
        return None
    return hr_squared_s / (threshold_hr * threshold_hr) / 3600 * 100


def estimated_ftp(best_20min_power: float | None) -> float | None:
    """Estimate FTP from a recent best 20-minute effort.

    Args:
        best_20min_power: The best 20-minute average power in the lookback window, in watts.

    Returns:
        ``EFTP_FACTOR`` times that power, or ``None`` without one.
    """
    return EFTP_FACTOR * best_20min_power if best_20min_power else None


def intensity_factor(np: float | None, ftp: float | None) -> float | None:
    """How hard a ride was relative to threshold.

    Args:
        np: Normalized Power in watts.
        ftp: FTP in watts.

    Returns:
        NP divided by FTP (1.0 is an hour-long all-out effort), or ``None`` if either is
        missing.
    """
    if np is None or not ftp:
        return None
    return np / ftp


def training_stress_score(duration_s: int, np: float | None, ftp: float | None) -> float | None:
    """Training Stress Score: the training load of a ride; an hour at FTP scores 100.

    Args:
        duration_s: The ride's moving time in seconds.
        np: Normalized Power in watts.
        ftp: FTP in watts.

    Returns:
        ``duration × NP × IF / (FTP × 3600) × 100``, or ``None`` if NP or FTP is missing.
    """
    intensity = intensity_factor(np, ftp)
    if intensity is None or np is None or ftp is None:
        return None
    return duration_s * np * intensity / (ftp * 3600) * 100


def watts_per_kg(watts: float | None, weight_kg: float | None) -> float | None:
    """Power relative to body weight.

    Args:
        watts: Any power figure.
        weight_kg: Body weight in kilograms.

    Returns:
        Watts per kilogram, or ``None`` if either is missing.
    """
    if watts is None or not weight_kg:
        return None
    return watts / weight_kg


def ride_tss(
    moving_s: int,
    np: float | None,
    ftp: float | None,
    hr_squared_s: float | None,
    threshold_hr: float | None,
) -> tuple[float | None, TssSource | None]:
    """A ride's TSS: from power when it can be, else from heart rate.

    Args:
        moving_s: Riding time in seconds.
        np: Normalized Power, if the ride has power.
        ftp: FTP in watts (set or estimated).
        hr_squared_s: Riding seconds times heart rate squared, summed, if it has heart rate.
        threshold_hr: Threshold heart rate (set or estimated).

    Returns:
        The TSS and what it came from, or ``(None, None)`` when neither works.
    """
    tss = training_stress_score(moving_s, np, ftp)
    if tss is not None:
        return tss, TssSource.POWER
    tss = hr_training_stress_score(hr_squared_s, threshold_hr)
    return (tss, TssSource.HEART_RATE) if tss is not None else (None, None)
