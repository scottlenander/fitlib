"""Combine a decoded file and its 1 Hz frame into a ``RideSummary``."""

from __future__ import annotations

import polars as pl

from fitlib.ingest.decoder import DecodedActivity
from fitlib.ingest.localtime import choose_offset
from fitlib.ingest.source import detect_source, device_name, is_indoor
from fitlib.metrics import basic, curves, hr, power, zones
from fitlib.models import RideSummary

# Bump when any computed figure changes, so `recompute` knows which rides are out of date.
# 3: route fingerprints.
# 4: local time ignored when it isn't real (Zwift writes 1989-12-31), fixing ride dates.
# 5: distance added up from speed when the odometer is on few records (Zwift).
# 6: time zone from the file name (Zwift) or the library's default time zone; default
#    names with the start time (recompute re-indexes them for search).
METRICS_VERSION = 6


def summarize(
    decoded: DecodedActivity,
    frame: pl.DataFrame,
    name: str | None = None,
    default_zone: str | None = None,
) -> RideSummary:
    """Combine what the file says with figures computed from its samples.

    Args:
        decoded: The decoded file.
        frame: The ride's 1 Hz frame from ``to_frame``. Must have at least one row.
        name: The file's name (no folders), for a time zone when the file has none.
        default_zone: The library's default time zone, for when neither has one.

    Returns:
        The ride's summary.
    """
    start = frame["timestamp"][0]
    utc_offset_s, utc_offset_source = choose_offset(decoded.utc_offset_s, name, start, default_zone)
    has_gps = basic.has_data(frame, "lat")
    avg_power = basic.avg_power(frame)
    np = power.normalized_power(frame)
    return RideSummary(
        start=start,
        utc_offset_s=utc_offset_s,
        utc_offset_source=utc_offset_source,
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
