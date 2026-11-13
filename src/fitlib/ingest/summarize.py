"""Combine a decoded file and its 1 Hz frame into a ``RideSummary``."""

from __future__ import annotations

import polars as pl

from fitlib.ingest.decoder import DecodedActivity
from fitlib.ingest.source import detect_source, device_name, is_indoor
from fitlib.metrics import basic, curves, hr, power, zones
from fitlib.models import RideSummary

# Bump when any computed figure changes, so `recompute` knows which rides are out of date.
METRICS_VERSION = 2


def summarize(decoded: DecodedActivity, frame: pl.DataFrame) -> RideSummary:
    """Combine what the file says with figures computed from its samples.

    Args:
        decoded: The decoded file.
        frame: The ride's 1 Hz frame from ``to_frame``. Must have at least one row.

    Returns:
        The ride's summary.
    """
    has_gps = basic.has_data(frame, "lat")
    avg_power = basic.avg_power(frame)
    np = power.normalized_power(frame)
    return RideSummary(
        start=frame["timestamp"][0],
        utc_offset_s=decoded.utc_offset_s,
        source=detect_source(decoded),
        device=device_name(decoded),
        sport=decoded.sport or "cycling",
        sub_sport=decoded.sub_sport,
        indoor=is_indoor(decoded, has_gps),
        elapsed_s=basic.elapsed_s(frame),
        moving_s=basic.moving_s(frame),
        distance_m=basic.distance_m(frame),
        ascent_m=basic.ascent_m(frame),
        avg_speed_mps=basic.avg_speed_mps(frame),
        max_speed_mps=basic.max_speed_mps(frame),
        avg_power=avg_power,
        max_power=basic.max_power(frame),
        avg_hr=basic.avg_hr(frame),
        max_hr=basic.max_hr(frame),
        avg_cadence=basic.avg_cadence(frame),
        has_power=basic.has_data(frame, "power"),
        has_hr=basic.has_data(frame, "heart_rate"),
        has_gps=has_gps,
        laps=basic.laps(frame, [lap.start for lap in decoded.laps]),
        geo=basic.geo(frame),
        np=np,
        kj=power.kilojoules(frame),
        vi=power.variability_index(np, avg_power),
        decoupling_pct=hr.decoupling_pct(frame),
        power_curve=curves.best_averages(frame, "power"),
        hr_curve=curves.best_averages(frame, "heart_rate"),
        power_histogram=zones.histogram(frame, "power"),
        hr_histogram=zones.histogram(frame, "heart_rate"),
    )
