"""Human-readable formatting for ride figures."""

from __future__ import annotations

from datetime import datetime

from fitlib.models import RideSummary

DASH = "–"


def duration(seconds: int | float | None) -> str:
    """``3725`` -> ``1:02:05``; under an hour -> ``42:05``."""
    if seconds is None:
        return DASH
    total = round(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def km(metres: float | None) -> str:
    return DASH if metres is None else f"{metres / 1000:.1f} km"


def metres(value: float | None) -> str:
    return DASH if value is None else f"{value:.0f} m"


def kmh(mps: float | None) -> str:
    return DASH if mps is None else f"{mps * 3.6:.1f} km/h"


def watts(value: float | None) -> str:
    return DASH if value is None else f"{value:.0f} W"


def bpm(value: float | None) -> str:
    return DASH if value is None else f"{value:.0f} bpm"


def rpm(value: float | None) -> str:
    return DASH if value is None else f"{value:.0f} rpm"


def start_time(summary: RideSummary) -> str:
    """Local time when the device recorded it, else UTC (marked)."""
    local = summary.local_start
    if local is not None:
        return f"{local:%a %d %b %Y, %H:%M}"
    return f"{summary.start:%a %d %b %Y, %H:%M} UTC"


def date(value: datetime) -> str:
    return f"{value:%Y-%m-%d}"
