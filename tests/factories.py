"""Builders for domain objects in tests. Every field has a plain default; override what matters."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from fitlib.models import GeoSummary, Lap, Ride, RideMeta, RideSummary, Source

DEFAULT_START = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)
IMPORTED_AT = datetime(2025, 9, 1, 12, 0, tzinfo=UTC)


def make_summary(**overrides) -> RideSummary:
    summary = RideSummary(
        start=DEFAULT_START,
        utc_offset_s=7200,
        source=Source.GARMIN,
        device="Garmin Edge 540",
        sport="cycling",
        sub_sport="road",
        indoor=False,
        elapsed_s=3600,
        moving_s=3500,
        distance_m=30_000.0,
        ascent_m=250.0,
        avg_speed_mps=8.57,
        max_speed_mps=14.2,
        avg_power=200.0,
        max_power=650,
        avg_hr=142.0,
        max_hr=171,
        avg_cadence=88.0,
        has_power=True,
        has_hr=True,
        has_gps=True,
        laps=(
            Lap(0, 0, 1800, 15_000.0, 190.0, 600, 138.0, 165),
            Lap(1, 1800, 1800, 15_000.0, 210.0, 650, 146.0, 171),
        ),
        geo=GeoSummary(50.39, 3.41, 50.38, 3.40, 50.41, 3.43),
        np=215.0,
        kj=720.0,
        vi=1.075,
        decoupling_pct=3.2,
        power_curve=((1, 650.0), (60, 380.0), (300, 290.0), (1200, 250.0), (3600, 205.0)),
        hr_curve=((1, 171.0), (60, 168.0), (300, 162.0), (1200, 155.0), (3600, 142.0)),
        power_histogram=((0, 120), (150, 900), (200, 1500), (250, 900), (650, 1)),
        hr_histogram=((120, 600), (140, 1800), (160, 1100), (171, 1)),
    )
    return replace(summary, **overrides)


def make_ride(*, meta: RideMeta | None = None, **overrides) -> Ride:
    """A ride with a fresh id and hash. Summary fields can be overridden directly."""
    summary_fields = {
        k: overrides.pop(k) for k in list(overrides) if k in RideSummary.__dataclass_fields__
    }
    ride = Ride(
        id=str(uuid.uuid4()),
        sha256=uuid.uuid4().hex * 2,
        summary=make_summary(**summary_fields),
        imported_at=IMPORTED_AT,
        metrics_version=1,
        source_name="ride.fit",
        meta=meta or RideMeta(),
    )
    return replace(ride, **overrides)
