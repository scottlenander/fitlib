"""Formatting ride figures for people."""

from __future__ import annotations

import pytest

from fitlib import display


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00"), (65, "1:05"), (3599.6, "1:00:00"), (3725, "1:02:05"), (None, "–")],
)
def test_duration(seconds, expected):
    """Durations read as m:ss under an hour and h:mm:ss above; missing values as a dash.

    Given: 0 s, 65 s, 3599.6 s (rounds up to an hour), 3725 s, and ``None``.
    Expect: ``0:00``, ``1:05``, ``1:00:00``, ``1:02:05`` and ``–``.
    """
    assert display.duration(seconds) == expected


def test_units():
    """Distances, speeds, power, heart rate and cadence get units; missing values a dash.

    Given: 32 025 m, 8.9 m/s, 186.7 W, 136.6 bpm, 86.7 rpm, and ``None``.
    Expect: rounded values with units; ``–`` for ``None``.
    """
    assert display.km(32_025) == "32.0 km"
    assert display.kmh(8.9) == "32.0 km/h"
    assert display.watts(186.7) == "187 W"
    assert display.bpm(136.6) == "137 bpm"
    assert display.rpm(86.7) == "87 rpm"
    assert display.metres(129.6) == "130 m"
    assert display.watts(None) == "–", "missing values should show as a dash"
