"""Human-readable formatting for ride figures.

Every function takes SI values (as stored) and returns text for people, converting distance,
speed, height and weight to the requested units. Missing values (``None``) are shown as a dash.
"""

from __future__ import annotations

from datetime import datetime

from fitlib.models import RideSummary, Units

DASH = "–"
METRES_PER_MILE = 1609.344
FEET_PER_METRE = 3.28084
POUNDS_PER_KG = 2.20462


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


def distance(metres: float | None, units: Units) -> str:
    """Format a distance.

    Args:
        metres: Distance in metres, or ``None``.
        units: Miles for imperial, kilometres for metric.

    Returns:
        For example ``"19.9 mi"`` or ``"32.0 km"``; a dash for ``None``.
    """
    if metres is None:
        return DASH
    if units is Units.IMPERIAL:
        return f"{metres / METRES_PER_MILE:.1f} mi"
    return f"{metres / 1000:.1f} km"


def speed(mps: float | None, units: Units) -> str:
    """Format a speed.

    Args:
        mps: Speed in metres per second, or ``None``.
        units: Miles per hour for imperial, kilometres per hour for metric.

    Returns:
        For example ``"19.9 mph"`` or ``"32.0 km/h"``; a dash for ``None``.
    """
    if mps is None:
        return DASH
    if units is Units.IMPERIAL:
        return f"{mps * 3600 / METRES_PER_MILE:.1f} mph"
    return f"{mps * 3.6:.1f} km/h"


def elevation(metres: float | None, units: Units) -> str:
    """Format a height, such as climbing.

    Args:
        metres: Height in metres, or ``None``.
        units: Feet for imperial, metres for metric.

    Returns:
        For example ``"427 ft"`` or ``"130 m"``; a dash for ``None``.
    """
    if metres is None:
        return DASH
    if units is Units.IMPERIAL:
        return f"{metres * FEET_PER_METRE:.0f} ft"
    return f"{metres:.0f} m"


def weight(kg: float | None, units: Units) -> str:
    """Format body weight.

    Args:
        kg: Weight in kilograms, or ``None``.
        units: Pounds for imperial, kilograms for metric.

    Returns:
        For example ``"165.0 lb"`` or ``"74.8 kg"``; a dash for ``None``.
    """
    if kg is None:
        return DASH
    if units is Units.IMPERIAL:
        return f"{kg * POUNDS_PER_KG:.1f} lb"
    return f"{kg:.1f} kg"


def kg_from(value: float, units: Units) -> float:
    """Convert a weight typed in display units to kilograms for storage.

    Args:
        value: The weight as typed.
        units: Pounds for imperial, kilograms for metric.

    Returns:
        Kilograms.
    """
    return value / POUNDS_PER_KG if units is Units.IMPERIAL else value


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


def kilojoules(value: float | None) -> str:
    """Format work done.

    Args:
        value: Kilojoules, or ``None``.

    Returns:
        For example ``"720 kJ"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f} kJ"


def ratio(value: float | None) -> str:
    """Format a ratio such as IF or VI with two decimals.

    Args:
        value: The ratio, or ``None``.

    Returns:
        For example ``"0.80"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.2f}"


def tss(value: float | None) -> str:
    """Format a Training Stress Score as a whole number.

    Args:
        value: The score, or ``None``.

    Returns:
        For example ``"64"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.0f}"


def watts_per_kg(value: float | None) -> str:
    """Format power per kilogram.

    Args:
        value: Watts per kilogram, or ``None``.

    Returns:
        For example ``"2.67 W/kg"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:.2f} W/kg"


def signed_percent(value: float | None) -> str:
    """Format a percentage with its sign, such as decoupling.

    Args:
        value: Percent, or ``None``.

    Returns:
        For example ``"+3.2 %"`` or ``"-0.4 %"``; a dash for ``None``.
    """
    return DASH if value is None else f"{value:+.1f} %"


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
