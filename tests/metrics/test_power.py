"""Normalized Power, work, variability and best efforts, checked against the fixture specs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import cache
from statistics import mean

import polars as pl
import pytest

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics import power
from fitlib.metrics.curves import best_at, best_averages
from fitlib.models import CURVE_DURATIONS_S
from tests.fixtures.generate import committed_bytes
from tests.fixtures.specs import ride


@cache
def frame_for(name: str) -> pl.DataFrame:
    """Decode and normalize a committed fixture ride (cached, as frames are read-only here).

    Args:
        name: The ride spec's name.

    Returns:
        The ride's 1 Hz frame.
    """
    return to_frame(decode(committed_bytes(name)).records)


def synthetic(powers: list[int | None]) -> pl.DataFrame:
    """Build a frame with one record per second at the given powers, from 06:30 UTC.

    Args:
        powers: Watts per second; ``None`` for no reading.

    Returns:
        The 1 Hz frame.
    """
    start = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)
    return to_frame(
        [{"timestamp": start + timedelta(seconds=i), "power": p} for i, p in enumerate(powers)]
    )


def reference_np(powers: list[int]) -> float:
    """Work out Normalized Power the slow, obvious way, to check the polars version against.

    Args:
        powers: Watts per second, with no pauses.

    Returns:
        The 4th root of the mean 4th power of the 30-second rolling averages.
    """
    rolling = [mean(powers[i - 29 : i + 1]) for i in range(29, len(powers))]
    return mean(p**4 for p in rolling) ** 0.25


def test_steady_ride_np_equals_average_power():
    """At a constant power, NP is that power and VI is 1.

    Given: the Zwift ride, 60 min at a steady 200 W.
    Expect: NP 200 W, 720 kJ (200 W × 3600 s), VI 1.00.
    """
    frame = frame_for("zwift_watopia_steady_60min")

    np = power.normalized_power(frame)

    assert np == pytest.approx(200)
    assert power.kilojoules(frame) == pytest.approx(720)
    assert power.variability_index(np, 200) == pytest.approx(1.0)


def test_interval_ride_np_matches_a_reference_calculation():
    """NP over intervals matches a plain, step-by-step calculation of the same formula.

    Given: the interval ride (warm-up, 5 × 4 min at 300 W with 4 min at 120 W, cool-down).
    Expect: NP equal to the reference (30 s rolling average, 4th power, mean, 4th root), well
    above the 186.7 W average; kJ is the sum of the spec's watts.
    """
    spec = ride("garmin_nord_intervals_5x4")
    frame = frame_for(spec.name)

    np = power.normalized_power(frame)

    assert np == pytest.approx(reference_np(spec.powers()), rel=1e-9)
    assert np > mean(spec.powers()) + 30, "surges should push NP well above the average"
    assert power.kilojoules(frame) == pytest.approx(sum(spec.powers()) / 1000)


def test_np_needs_power_and_thirty_seconds():
    """NP needs a power meter and at least one 30-second window.

    Given: 29 seconds at 200 W; and a ride without a power meter.
    Expect: ``None`` for both; kJ ``None`` without power.
    """
    short = synthetic([200] * 29)
    no_power = frame_for("garmin_nord_hr_no_power")

    assert power.normalized_power(short) is None, "under 30 s there is no NP"
    assert power.normalized_power(no_power) is None
    assert power.kilojoules(no_power) is None


def test_variability_index_needs_both_figures():
    """VI is NP over average power, and missing without either (or with 0 W average).

    Given: NP 230 W with average 187 W; then missing NP; then a 0 W average.
    Expect: 1.23; ``None``; ``None``.
    """
    assert power.variability_index(230, 187) == pytest.approx(230 / 187)
    assert power.variability_index(None, 187) is None
    assert power.variability_index(230, 0) is None, "a 0 W average would divide by zero"


def test_steady_ride_curve_is_flat_up_to_its_length():
    """A steady ride's best effort is the same power at every duration it lasted.

    Given: the 60-minute steady Zwift ride at 200 W.
    Expect: 200 W for every curve duration up to 60 min; nothing for 90 or 120 min.
    """
    curve = best_averages(frame_for("zwift_watopia_steady_60min"), "power")

    assert [d for d, _ in curve] == [d for d in CURVE_DURATIONS_S if d <= 3600]
    assert all(value == pytest.approx(200) for _, value in curve)


def test_interval_ride_best_efforts():
    """Best efforts over intervals can be worked out from the spec.

    Given: the interval ride; each 4-min 300 W effort is preceded by 150 W (warm-up) or
    120 W (rest).
    Expect: 300 W up to 4 min; best 5 min = (240 s × 300 + 60 s × 150) / 300 = 270 W;
    best 20 min = 3 work + 2 rest blocks = (720 × 300 + 480 × 120) / 1200 = 228 W.
    """
    curve = best_averages(frame_for("garmin_nord_intervals_5x4"), "power")

    assert best_at(curve, 60) == pytest.approx(300)
    assert best_at(curve, 300) == pytest.approx(270)
    assert best_at(curve, 1200) == pytest.approx(228)


def test_best_efforts_never_span_a_pause():
    """A best effort must be continuous riding.

    Given: the paused ride: 15 min riding, a 10-min pause, 15 min riding, all at 190 W.
    Expect: efforts up to 10 min at 190 W; none for 20 min or longer, which would have to
    cross the pause.
    """
    curve = best_averages(frame_for("garmin_nord_pause_10min"), "power")

    assert best_at(curve, 600) == pytest.approx(190)
    assert best_at(curve, 1200) is None, "20 minutes would have to span the pause"


def test_curve_of_a_missing_channel_is_empty():
    """No power meter means no power curve.

    Given: the ride without a power meter.
    Expect: an empty curve.
    """
    curve = best_averages(frame_for("garmin_nord_hr_no_power"), "power")

    assert curve == ()
