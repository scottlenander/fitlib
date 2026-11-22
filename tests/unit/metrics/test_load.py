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


def test_threshold_hr_carries_forward_like_the_other_values():
    """Threshold heart rate is one more value that carries forward on its own.

    Given: 1 Jan: max HR 188; 1 Mar: threshold HR 165 only.
    Expect: on 1 Apr, max HR 188 and threshold HR 165.
    """
    history = [
        AthleteEntry(date(2025, 1, 1), max_hr=188),
        AthleteEntry(date(2025, 3, 1), threshold_hr=165),
    ]

    assert load.values_on(history, date(2025, 4, 1)) == load.AthleteValues(
        max_hr=188, threshold_hr=165
    )


@pytest.mark.parametrize(
    ("birth_year", "day", "expected"),
    [(1980, date(2025, 8, 2), 159), (2000, date(2025, 1, 1), 171), (1960, date(2025, 12, 31), 146)],
    ids=["45", "25", "65"],
)
def test_threshold_hr_estimated_from_age(birth_year: int, day: date, expected: int):
    """Threshold heart rate is 90 % of the age-predicted max (Tanaka: 208 - 0.7 x age).

    Given: riders aged 45, 25 and 65 (age by the day's year).
    Expect: round(0.9 x 176.5) = 159; round(0.9 x 190.5) = 171; round(0.9 x 162.5) = 146.
    """
    assert load.estimated_threshold_hr(birth_year, day) == expected


def test_threshold_hr_needs_a_birth_year_before_the_day():
    """No year of birth, or a day before it, gives no estimate.

    Given: no birth year; then a ride dated before the birth year.
    Expect: ``None`` both times.
    """
    assert load.estimated_threshold_hr(None, date(2025, 1, 1)) is None
    assert load.estimated_threshold_hr(2026, date(2025, 1, 1)) is None


def test_hr_tss_of_an_hour_at_threshold_is_100():
    """An hour at threshold heart rate scores 100, as an hour at FTP does.

    Given: 3600 s at 160 bpm with threshold 160; then 45 min at 132 bpm with threshold 165.
    Expect: 100; then 0.75 h x (132 / 165)² x 100 = 48.
    """
    hour = load.hr_squared_seconds(((160, 3600),))
    easy = load.hr_squared_seconds(((132, 2700),))

    assert load.hr_training_stress_score(hour, 160) == pytest.approx(100)
    assert load.hr_training_stress_score(easy, 165) == pytest.approx(48)


def test_hr_tss_adds_each_seconds_share():
    """Each second adds (heart rate / threshold)², so a mixed ride sums its parts.

    Given: 30 min at 150 bpm and 30 min at 180 bpm, threshold 165.
    Expect: 0.5 x (150/165)² x 100 + 0.5 x (180/165)² x 100.
    """
    mixed = load.hr_squared_seconds(((150, 1800), (180, 1800)))

    expected = 50 * (150 / 165) ** 2 + 50 * (180 / 165) ** 2
    assert load.hr_training_stress_score(mixed, 165) == pytest.approx(expected)


def test_hr_tss_needs_heart_rate_and_a_threshold():
    """Without heart rate or a threshold, there's no heart-rate TSS.

    Given: an empty histogram; then heart rate with no threshold.
    Expect: ``None`` both times.
    """
    assert load.hr_squared_seconds(()) is None
    assert load.hr_training_stress_score(None, 165) is None
    assert load.hr_training_stress_score(1_000_000.0, None) is None


@pytest.mark.parametrize(
    ("np", "ftp", "hr_squared_s", "threshold", "expected"),
    [
        (200.0, 200.0, 160 * 160 * 3600.0, 140, (100.0, load.TssSource.POWER)),
        (None, None, 160 * 160 * 3600.0, 160, (100.0, load.TssSource.HEART_RATE)),
        (200.0, None, 160 * 160 * 3600.0, 160, (100.0, load.TssSource.HEART_RATE)),
        (None, None, None, 160, (None, None)),
        (None, None, 160 * 160 * 3600.0, None, (None, None)),
    ],
    ids=["power-first", "hr-without-power", "hr-without-ftp", "no-hr", "no-threshold"],
)
def test_ride_tss_prefers_power(np, ftp, hr_squared_s, threshold, expected):
    """TSS comes from power when it can, else from heart rate.

    Given: an hour with power at FTP and heart rate above threshold; heart rate only; power
    without an FTP; neither heart rate nor a threshold.
    Expect: power TSS 100 (not heart rate's 131); heart-rate TSS 100 twice; nothing.
    """
    tss, source = load.ride_tss(3600, np, ftp, hr_squared_s, threshold)

    assert (None if tss is None else pytest.approx(tss), source) == (
        None if expected[0] is None else pytest.approx(expected[0]),
        expected[1],
    )
