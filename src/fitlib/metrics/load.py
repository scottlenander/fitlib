"""FTP-based figures (IF, TSS, W/kg), the athlete's values on a date, and estimated FTP.

These are worked out when read rather than stored, so changing the athlete history takes
effect everywhere at once.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from fitlib.models import AthleteEntry

# Estimated FTP: this share of the best 20-minute power in the recent past.
EFTP_FACTOR = 0.95
EFTP_LOOKBACK_DAYS = 42


@dataclass(frozen=True)
class AthleteValues:
    """The athlete's FTP, weight and max heart rate on one day, from the history.

    Attributes:
        ftp: Watts, or ``None`` if no entry on or before the day sets it.
        weight_kg: Kilograms, or ``None`` if no entry on or before the day sets it.
        max_hr: Beats per minute, or ``None`` if no entry on or before the day sets it.
    """

    ftp: int | None = None
    weight_kg: float | None = None
    max_hr: int | None = None


def values_on(history: Iterable[AthleteEntry], day: date) -> AthleteValues:
    """Find the FTP, weight and max heart rate in effect on a day.

    Each value comes from the latest entry on or before ``day`` that sets it, so the values
    can come from different entries.

    Args:
        history: The athlete's entries, in any order.
        day: The day in question (the rider's local date).

    Returns:
        The values in effect; any never set by then are ``None``.
    """
    ftp = weight = max_hr = None
    for entry in sorted(history, key=lambda e: e.effective_from):
        if entry.effective_from > day:
            break
        ftp = entry.ftp if entry.ftp is not None else ftp
        weight = entry.weight_kg if entry.weight_kg is not None else weight
        max_hr = entry.max_hr if entry.max_hr is not None else max_hr
    return AthleteValues(ftp=ftp, weight_kg=weight, max_hr=max_hr)


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
