"""Aerobic decoupling (Pw:HR)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics.hr import decoupling_pct
from tests.fixtures.generate import committed_bytes


def ride_with(power: int, hr_first: int, hr_second: int, minutes: int = 40):
    """Steady power with heart rate stepping up halfway through."""
    start = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)
    seconds = minutes * 60
    return to_frame(
        [
            {
                "timestamp": start + timedelta(seconds=i),
                "power": power,
                "heart_rate": hr_first if i < seconds // 2 else hr_second,
            }
            for i in range(seconds)
        ]
    )


def test_drifting_heart_rate_shows_as_decoupling():
    """Heart rate rising at the same power is positive decoupling.

    Given: 40 min at 200 W, heart rate 140 bpm in the first half and 150 bpm in the second.
    Expect: (200/140 - 200/150) / (200/140) = 1 - 140/150 = 6.67 %.
    """
    frame = ride_with(power=200, hr_first=140, hr_second=150)

    assert decoupling_pct(frame) == pytest.approx((1 - 140 / 150) * 100)


def test_steady_ride_has_no_decoupling():
    """Constant power and heart rate means no drift.

    Given: the steady Zwift ride (200 W, 140 bpm throughout).
    Expect: 0 %.
    """
    frame = to_frame(decode(committed_bytes("zwift_watopia_steady_60min")).records)

    assert decoupling_pct(frame) == pytest.approx(0)


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("garmin_nord_hr_no_power", "no power meter"),
        ("garmin_indoor_no_hr", "no heart-rate strap"),
    ],
)
def test_decoupling_needs_power_and_heart_rate(name: str, why: str):
    """Decoupling compares power with heart rate, so it needs both.

    Given: a ride with no power meter, and one with no heart-rate strap.
    Expect: ``None``.
    """
    frame = to_frame(decode(committed_bytes(name)).records)

    assert decoupling_pct(frame) is None, why


def test_decoupling_needs_twenty_minutes():
    """Short rides are too short for decoupling to mean anything.

    Given: 19 minutes with drifting heart rate.
    Expect: ``None``.
    """
    frame = ride_with(power=200, hr_first=140, hr_second=150, minutes=19)

    assert decoupling_pct(frame) is None
