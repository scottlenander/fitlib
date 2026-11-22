"""Training load (IF, TSS from power or heart rate, W/kg) and the athlete's values on a date.

Also estimated FTP and threshold heart rate.

These are worked out when read rather than stored, so changing the athlete history takes
effect everywhere at once.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
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


class TssSource(StrEnum):
    """What a ride's TSS was worked out from."""

    POWER = "power"
    HEART_RATE = "hr"


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
