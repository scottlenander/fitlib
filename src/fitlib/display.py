"""Human-readable formatting for ride figures.

Every function takes SI values (as stored) and returns text for people. Missing values
(``None``) are shown as a dash.
"""

from __future__ import annotations

from datetime import datetime

from fitlib.models import RideSummary

DASH = "–"


def duration(seconds: int | float | None) -> str:
    """Format a duration.

    Args:
        seconds: Length of time in seconds, or ``None``.

    Returns:
        ``m:ss`` under an hour and ``h:mm:ss`` from an hour up, e.g. ``"42:05"`` or
        ``"1:02:05"``; a dash for ``None``.
    """
    if seconds is None:
        return DASH
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def km(metres: float | None) -> str:
    """Format a distance in kilometres.

    Args:
        metres: Distance in metres, or ``None``.

    Returns:
        For example ``"32.0 km"``; a dash for ``None``.
    """
    return DASH if metres is None else f"{metres / 1000:.1f} km"


def metres(value: float | None) -> str:
    """Format a height or short distance in whole metres.

    Args:
        value: Distance in metres, or ``None``.

    Returns:
        For example ``"130 m"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f} m"


def kmh(mps: float | None) -> str:
    """Format a speed in kilometres per hour.

    Args:
        mps: Speed in metres per second, or ``None``.

    Returns:
        For example ``"32.0 km/h"``; a dash for ``None``.
    """
    return DASH if mps is None else f"{mps * 3.6:.1f} km/h"


def watts(value: float | None) -> str:
    """Format power in whole watts.

    Args:
        value: Power in watts, or ``None``.

    Returns:
        For example ``"187 W"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f} W"


def bpm(value: float | None) -> str:
    """Format a heart rate.

    Args:
        value: Heart rate in beats per minute, or ``None``.

    Returns:
        For example ``"137 bpm"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f} bpm"


def rpm(value: float | None) -> str:
    """Format a cadence.

    Args:
        value: Cadence in revolutions per minute, or ``None``.

    Returns:
        For example ``"87 rpm"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f} rpm"


def start_time(summary: RideSummary) -> str:
    """Format when a ride started, in the rider's local time when known.

    Args:
        summary: The ride's summary.

    Returns:
        For example ``"Tue 05 Aug 2025, 19:00"`` in local time, or the UTC time followed by
        ``" UTC"`` when the device didn't record local time.
    """
    local = summary.local_start
    if local is not None:
        return f"{local:%a %d %b %Y, %H:%M}"
    return f"{summary.start:%a %d %b %Y, %H:%M} UTC"


def date(value: datetime) -> str:
    """Format a date as ISO year-month-day.

    Args:
        value: Any datetime.

    Returns:
        For example ``"2025-08-05"``.
    """
    return f"{value:%Y-%m-%d}"
