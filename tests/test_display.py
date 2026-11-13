"""Formatting ride figures for people."""

from __future__ import annotations

import pytest

from fitlib import display
from fitlib.models import Units


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


@pytest.mark.parametrize(
    ("units", "expected"),
    [
        (Units.IMPERIAL, ("19.9 mi", "19.9 mph", "427 ft", "165.0 lb")),
        (Units.METRIC, ("32.0 km", "32.0 km/h", "130 m", "74.8 kg")),
    ],
    ids=["imperial", "metric"],
)
def test_distance_speed_height_and_weight_follow_the_units(units: Units, expected: tuple):
    """Distance, speed, height and weight are converted from SI to the chosen units.

    Given: 32 025 m, 8.9 m/s, 130 m and 74.84 kg.
    Expect: miles, mph, feet and pounds for imperial; km, km/h, metres and kg for metric.
    """
    shown = (
        display.distance(32_025, units),
        display.speed(8.9, units),
        display.elevation(130, units),
        display.weight(74.84, units),
    )

    assert shown == expected


def test_weight_typed_in_pounds_is_stored_in_kilograms():
    """Weight entered in display units is converted to kilograms for storage.

    Given: 165 typed with imperial units, and 75 with metric units.
    Expect: 74.84 kg, and 75 kg unchanged.
    """
    assert display.kg_from(165, Units.IMPERIAL) == pytest.approx(74.843, abs=1e-3)
    assert display.kg_from(75, Units.METRIC) == 75


def test_power_heart_rate_and_training_figures():
    """Figures that don't depend on units get their usual format; missing values a dash.

    Given: 186.7 W, 136.6 bpm, 86.7 rpm, 672.4 kJ, IF 0.8, TSS 64.4, 2.4 W/kg, decoupling
    3.21 % and -0.4 %, and ``None``.
    Expect: rounded values with units, signs on percentages, ``–`` for ``None``.
    """
    assert display.watts(186.7) == "187 W"
    assert display.bpm(136.6) == "137 bpm"
    assert display.rpm(86.7) == "87 rpm"
    assert display.kilojoules(672.4) == "672 kJ"
    assert display.ratio(0.8) == "0.80"
    assert display.tss(64.4) == "64"
    assert display.watts_per_kg(2.4) == "2.40 W/kg"
    assert display.signed_percent(3.21) == "+3.2 %"
    assert display.signed_percent(-0.4) == "-0.4 %", "negative decoupling keeps its sign"
    assert display.watts(None) == "–", "missing values should show as a dash"
    assert display.distance(None, Units.IMPERIAL) == "–"
