"""IF, TSS, W/kg, estimated FTP, and the athlete's values on a date."""

from __future__ import annotations

from datetime import date

import pytest

from fitlib.metrics import load
from fitlib.models import AthleteEntry


def test_tss_of_an_hour_at_ftp_is_100():
    """TSS is defined so an hour at FTP scores 100.

    Given: 3600 s with NP equal to FTP (250 W); then 3600 s at NP 200 W with FTP 250 W.
    Expect: IF 1.0 and TSS 100; then IF 0.80 and TSS 64.
    """
    assert load.intensity_factor(250, 250) == pytest.approx(1.0)
    assert load.training_stress_score(3600, 250, 250) == pytest.approx(100)
    assert load.intensity_factor(200, 250) == pytest.approx(0.8)
    assert load.training_stress_score(3600, 200, 250) == pytest.approx(64)


def test_training_figures_need_their_inputs():
    """Without NP, FTP or weight, the figures that need them are missing.

    Given: no NP; no FTP; no weight.
    Expect: ``None`` for IF, TSS and W/kg respectively.
    """
    assert load.intensity_factor(None, 250) is None
    assert load.training_stress_score(3600, 200, None) is None
    assert load.watts_per_kg(200, None) is None
    assert load.watts_per_kg(200, 80) == pytest.approx(2.5)


def test_estimated_ftp_is_95_percent_of_best_20_minutes():
    """Estimated FTP is 95 % of the best 20-minute power.

    Given: a best 20 minutes of 228 W; then no 20-minute effort.
    Expect: 216.6 W; then ``None``.
    """
    assert load.estimated_ftp(228) == pytest.approx(216.6)
    assert load.estimated_ftp(None) is None


def test_values_on_a_date_carry_forward_separately():
    """Each value comes from the latest entry on or before the date that sets it.

    Given: 1 Jan: FTP 240, 72 kg, max HR 188; 1 Mar: FTP 250 only; 1 Jun: 70 kg only.
    Expect: 31 Dec: nothing set; 1 Jan-28 Feb: the January values; 1 Mar: FTP 250 with
    January's weight and HR; 1 Jul: FTP 250, 70 kg, max HR 188.
    """
    history = [
        AthleteEntry(date(2025, 6, 1), weight_kg=70.0),
        AthleteEntry(date(2025, 1, 1), ftp=240, weight_kg=72.0, max_hr=188),
        AthleteEntry(date(2025, 3, 1), ftp=250),
    ]

    before = load.values_on(history, date(2024, 12, 31))
    february = load.values_on(history, date(2025, 2, 28))
    march = load.values_on(history, date(2025, 3, 1))
    july = load.values_on(history, date(2025, 7, 1))

    assert before == load.AthleteValues(), "nothing was set before the first entry"
    assert february == load.AthleteValues(ftp=240, weight_kg=72.0, max_hr=188)
    assert march == load.AthleteValues(ftp=250, weight_kg=72.0, max_hr=188), (
        "a new FTP should keep the earlier weight and max HR"
    )
    assert july == load.AthleteValues(ftp=250, weight_kg=70.0, max_hr=188)
