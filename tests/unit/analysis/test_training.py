"""Training figures for imported rides: set or estimated FTP, and heart-rate TSS."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from fitlib.analysis.training import (
    AthleteProfile,
    BadBirthYear,
    EffortHistory,
    athlete_profile,
    set_birth_year,
    threshold_today,
    training,
)
from fitlib.metrics.load import ThresholdSource, TssSource
from fitlib.models import AthleteEntry
from fitlib.store.memory import MemoryCatalog
from tests.unit.conftest import ImportedLibrary
from tests.unit.factories import make_ride

ZWIFT = "2025-08-02-08-29-42.fit"  # 2 Aug, 60 min at 200 W
SMART = "garmin_nord_smart_recording.fit"  # 12 Aug, 30 min at 180 W
NO_POWER = "garmin_nord_hr_no_power.fit"  # 16 Aug, no power meter
INTERVALS = "garmin_nord_intervals_5x4.fit"  # 5 Aug


def test_set_ftp_gives_if_tss_zones_and_w_per_kg(imported: ImportedLibrary):
    """A ride after an FTP entry uses that FTP, weight and max heart rate.

    Given: FTP 250 W, 75 kg and max HR 190 from 10 Aug; the 12 Aug ride, 30 min at 180 W and
    135 bpm.
    Expect: FTP 250 (not estimated), IF 0.72, TSS 0.5 h × 0.72² × 100 = 25.9, 2.40 W/kg, all
    1800 s in power Z2 (72 %) and HR Z3 (71 %).
    """
    imported.catalog.set_athlete_entry(
        AthleteEntry(date(2025, 8, 10), ftp=250, weight_kg=75.0, max_hr=190)
    )

    figures = training(imported.catalog, imported.ride(SMART))

    assert (figures.ftp, figures.ftp_estimated) == (250, False)
    assert figures.intensity_factor == pytest.approx(0.72)
    assert figures.tss == pytest.approx(25.92)
    assert figures.watts_per_kg == pytest.approx(180 / 75)
    assert figures.power_zones == (0, 1800, 0, 0, 0, 0, 0)
    assert figures.hr_zones == (0, 0, 1800, 0, 0)


def test_rides_before_any_ftp_use_an_estimate(imported: ImportedLibrary):
    """Before the first FTP entry, FTP is estimated from the best 20 minutes in six weeks.

    Given: the first FTP entry on 10 Aug; the 2 Aug Zwift ride (60 min at 200 W), the only
    ride in the six weeks up to it.
    Expect: estimated FTP 0.95 × 200 = 190 W, IF 200/190, TSS 100 × (200/190)² = 110.8; no
    weight, so no W/kg; no max HR, so no HR zones.
    """
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 10), ftp=250))

    figures = training(imported.catalog, imported.ride(ZWIFT))

    assert figures.ftp == pytest.approx(190)
    assert figures.ftp_estimated, "the FTP should be marked as estimated"
    assert figures.tss == pytest.approx(100 * (200 / 190) ** 2)
    assert figures.watts_per_kg is None, "no weight set"
    assert figures.hr_zones is None, "no max heart rate set"


def test_estimate_uses_the_best_ride_in_the_window(imported: ImportedLibrary):
    """The estimate takes the best 20 minutes from any ride in the window, not just this one.

    Given: no athlete history; the 5 Aug interval ride (best 20 min 228 W) after the 2 Aug
    Zwift ride (best 20 min 200 W).
    Expect: estimated FTP 0.95 × 228 = 216.6 W for the interval ride.
    """
    figures = training(imported.catalog, imported.ride(INTERVALS))

    assert figures.ftp == pytest.approx(0.95 * 228)


def test_ride_without_power_has_no_power_figures(imported: ImportedLibrary):
    """Without a power meter there is no FTP to apply, but heart-rate zones still work.

    Given: FTP 250 and max HR 190 from 1 Aug, and nothing to give a threshold heart rate (none
    set, no year of birth, no rides to work one out from); the 16 Aug ride with heart rate but
    no power.
    Expect: no IF, TSS or power zones; HR zones for all 2700 s.
    """
    entry = AthleteEntry(date(2025, 8, 1), ftp=250, max_hr=190)

    figures = training(imported.catalog, imported.ride(NO_POWER), AthleteProfile((entry,)))

    assert (figures.intensity_factor, figures.tss, figures.power_zones) == (None, None, None)
    assert (figures.tss_source, figures.threshold_hr) == (None, None)
    assert figures.hr_zones is not None and sum(figures.hr_zones) == 2700


def test_changing_ftp_applies_without_recomputing(imported: ImportedLibrary):
    """FTP changes take effect at once, because FTP-based figures are worked out when read.

    Given: the 12 Aug ride, first with FTP 250 from 10 Aug, then with that entry changed to
    FTP 200.
    Expect: TSS 25.9 then 0.5 × 0.9² × 100 = 40.5, with no recompute in between.
    """
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 10), ftp=250))
    before = training(imported.catalog, imported.ride(SMART)).tss

    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 10), ftp=200))
    after = training(imported.catalog, imported.ride(SMART)).tss

    assert before == pytest.approx(25.92)
    assert after == pytest.approx(40.5), "the new FTP should apply immediately"


def test_ride_without_power_gets_tss_from_heart_rate(imported: ImportedLibrary):
    """A ride without power gets its TSS from heart rate and the threshold heart rate.

    Given: threshold HR 165 from 1 Aug; the 16 Aug ride, 45 min at 132 bpm, no power.
    Expect: TSS 0.75 h x (132 / 165)² x 100 = 48, from heart rate, threshold not estimated;
    still no IF.
    """
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 1), threshold_hr=165))

    figures = training(imported.catalog, imported.ride(NO_POWER))

    assert figures.tss == pytest.approx(48)
    assert figures.tss_source is TssSource.HEART_RATE
    assert (figures.threshold_hr, figures.threshold_hr_estimated) == (165, False)
    assert figures.intensity_factor is None, "IF is a power figure"


def test_threshold_hr_is_estimated_from_age(imported: ImportedLibrary):
    """With no threshold heart rate set, it's estimated from the rider's age.

    Given: born 1980 (45 in 2025), no athlete history and no rides to work a threshold out
    from; the 16 Aug ride at 132 bpm for 45 min.
    Expect: threshold 159 bpm, from age; TSS 0.75 x (132 / 159)² x 100.
    """
    figures = training(imported.catalog, imported.ride(NO_POWER), AthleteProfile(birth_year=1980))

    assert (figures.threshold_hr, figures.threshold_hr_source) == (159, ThresholdSource.AGE)
    assert figures.tss == pytest.approx(75 * (132 / 159) ** 2)


def test_a_set_threshold_hr_wins_over_the_age_estimate(imported: ImportedLibrary):
    """A threshold heart rate set in the history is used rather than the estimate.

    Given: born 1980 and threshold HR 165 from 1 Aug.
    Expect: threshold 165, not estimated.
    """
    set_birth_year(imported.catalog, 1980)
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 1), threshold_hr=165))

    figures = training(imported.catalog, imported.ride(NO_POWER))

    assert (figures.threshold_hr, figures.threshold_hr_estimated) == (165, False)


def test_rides_with_power_keep_power_tss(imported: ImportedLibrary):
    """Heart rate doesn't change the TSS of a ride with power.

    Given: FTP 250 and threshold HR 120 (far below the ride's heart rate) from 10 Aug; the
    12 Aug ride, 30 min at 180 W.
    Expect: the power TSS of 25.9, from power.
    """
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 10), ftp=250, threshold_hr=120))

    figures = training(imported.catalog, imported.ride(SMART))

    assert figures.tss == pytest.approx(25.92)
    assert figures.tss_source is TssSource.POWER


@pytest.mark.parametrize("year", [1899, 2026], ids=["too-early", "future"])
def test_impossible_birth_years_are_refused(imported: ImportedLibrary, year: int):
    """Years of birth before 1900 or in the future are refused, and nothing is saved.

    Given: today in 2025; a year before 1900, then next year.
    Expect: ``BadBirthYear``, and still no year of birth.
    """
    with pytest.raises(BadBirthYear, match="from 1900 to 2025"):
        set_birth_year(imported.catalog, year, today=date(2025, 6, 1))

    assert athlete_profile(imported.catalog).birth_year is None


def test_birth_year_can_be_cleared(imported: ImportedLibrary):
    """A year of birth can be set and cleared.

    Given: 1980 set, then cleared.
    Expect: 1980, then none.
    """
    set_birth_year(imported.catalog, 1980)
    saved = athlete_profile(imported.catalog).birth_year
    set_birth_year(imported.catalog, None)

    assert (saved, athlete_profile(imported.catalog).birth_year) == (1980, None)


# -- threshold heart rate from your rides ------------------------------------------------------

FTP_240 = AthleteEntry(date(2025, 1, 1), ftp=240)


def steady(day: int, *, np: float | None = 200.0, bpm: int = 150, minutes: int = 60, month=8):
    """A ride of one steady heart rate (and power, unless ``np`` is ``None``) in 2025.

    Args:
        day: Day of the month.
        np: Normalized Power, or ``None`` for a ride without power.
        bpm: Its heart rate throughout.
        minutes: Its riding time.
        month: Its month.

    Returns:
        The ride.
    """
    seconds = minutes * 60
    power: dict[str, Any] = {} if np else {"has_power": False, "avg_power": None, "power_curve": (),
                           "power_histogram": (), "kj": None}  # fmt: skip
    return make_ride(start=datetime(2025, month, day, 8, tzinfo=UTC), moving_s=seconds, np=np,
                     hr_histogram=((bpm, seconds),), **power)  # fmt: skip


def library(*rides, entries=(FTP_240,)) -> MemoryCatalog:
    """A library holding some rides and athlete entries.

    Args:
        *rides: The rides.
        entries: Athlete history entries.

    Returns:
        The catalog.
    """
    catalog = MemoryCatalog()
    for ride in rides:
        catalog.add_ride(ride)
    for entry in entries:
        catalog.set_athlete_entry(entry)
    return catalog


def test_threshold_from_your_rides_matches_their_power_tss():
    """Rides with power and heart rate give a threshold that makes the two TSS agree.

    Given: FTP 240; three hours at NP 200 W and 150 bpm (0.75 bpm per watt) on 1-3 Aug, then
    an hour without power at 162 bpm on 4 Aug.
    Expect: threshold 240 x 0.75 = 180 bpm, from your rides; TSS (162 / 180)² x 100 = 81.
    A power ride's own heart-rate TSS at that threshold equals its power TSS, (200/240)² x 100.
    """
    rides = [steady(1), steady(2), steady(3), steady(4, np=None, bpm=162)]
    catalog = library(*rides)

    figures = training(catalog, rides[3])
    power_ride = training(catalog, rides[2])

    assert (figures.threshold_hr, figures.threshold_hr_source) == (180, ThresholdSource.RIDES)
    assert figures.tss == pytest.approx(81)
    assert power_ride.tss == pytest.approx(100 * (200 / 240) ** 2)
    assert power_ride.tss == pytest.approx(100 * (150 / 180) ** 2), "the two TSS should agree"


@pytest.mark.parametrize(
    "others",
    [
        [steady(1), steady(2)],
        [steady(1), steady(2), steady(3, minutes=19)],
        [steady(1, month=4), steady(2, month=4), steady(3)],
        [steady(1), steady(2), steady(3, np=None)],
    ],
    ids=["two-rides", "one-too-short", "two-too-old", "one-without-power"],
)
def test_threshold_from_your_rides_needs_three_recent_rides(others):
    """It takes three rides with power and heart rate, of 20 minutes or more, in 90 days.

    Given: born 1980; only two such rides (another under 20 minutes, two in April more than 90
    days before, or one without power) before an hour without power on 4 Aug.
    Expect: the threshold from age instead (159).
    """
    ride = steady(4, np=None, bpm=162)
    catalog = library(*others, ride)
    set_birth_year(catalog, 1980)

    figures = training(catalog, ride)

    assert (figures.threshold_hr, figures.threshold_hr_source) == (159, ThresholdSource.AGE)


def test_threshold_from_your_rides_uses_the_estimated_ftp():
    """Without an FTP set, the day's estimated FTP gives the threshold.

    Given: no athlete history; three hours at NP 200 W and 150 bpm, whose best 20 minutes is
    the factory's 250 W (estimated FTP 237.5), then a ride without power.
    Expect: threshold round(237.5 x 0.75) = 178.
    """
    rides = [steady(1), steady(2), steady(3), steady(4, np=None, bpm=162)]
    catalog = library(*rides, entries=())

    figures = training(catalog, rides[3])

    assert (figures.threshold_hr, figures.threshold_hr_source) == (178, ThresholdSource.RIDES)


def test_a_set_threshold_wins_over_your_rides():
    """A threshold set in the history is used rather than one from your rides.

    Given: three calibrating rides and threshold HR 170 set from 1 Jan.
    Expect: 170, set.
    """
    ride = steady(4, np=None, bpm=162)
    entries = (FTP_240, AthleteEntry(date(2025, 1, 2), threshold_hr=170))
    catalog = library(steady(1), steady(2), steady(3), ride, entries=entries)

    figures = training(catalog, ride)

    assert (figures.threshold_hr, figures.threshold_hr_source) == (170, ThresholdSource.SET)


def test_threshold_today():
    """Today's threshold is worked out as a ride today would.

    Given: FTP 240 and three calibrating rides on 1-3 Aug 2025; today 10 Aug, then 1 Dec.
    Expect: 180 from your rides on 10 Aug; nothing on 1 Dec (no rides in 90 days, no year of
    birth).
    """
    catalog = library(steady(1), steady(2), steady(3))
    athlete = athlete_profile(catalog)

    assert threshold_today(athlete, date(2025, 8, 10)) == (180, ThresholdSource.RIDES)
    assert threshold_today(athlete, date(2025, 12, 1)) == (None, None)


AUG_1 = datetime(2025, 8, 1, 7, 0, tzinfo=UTC)


def efforts(*pairs: tuple[int, float]) -> EffortHistory:
    """An effort history from ``(days after 1 Aug 2025 07:00, best 20 min)`` pairs.

    Args:
        *pairs: Each ride's day offset and best 20-minute power.

    Returns:
        The history.
    """
    rides = sorted((AUG_1 + timedelta(days=d), watts) for d, watts in pairs)
    return EffortHistory(tuple(r[0] for r in rides), tuple(r[1] for r in rides))


def test_effort_window_includes_both_ends():
    """The estimate takes rides from exactly six weeks before up to the moment itself.

    Given: 300 W exactly 42 days before the moment, 200 W at the moment, 400 W a second after.
    Expect: 0.95 × 300 W; a second later, the 300 W ride is out of the window and the 400 W one in.
    """
    history = efforts((0, 300.0), (42, 200.0))
    later = EffortHistory(
        (*history.starts, AUG_1 + timedelta(days=42, seconds=1)), (*history.best, 400.0)
    )
    moment = AUG_1 + timedelta(days=42)

    assert later.estimated_ftp(moment) == pytest.approx(0.95 * 300)
    assert later.estimated_ftp(moment + timedelta(seconds=1)) == pytest.approx(0.95 * 400)


def test_effort_window_with_nothing_in_it():
    """No ride in the six weeks up to a moment means no estimate.

    Given: One ride 50 days before the moment, and an empty history.
    Expect: ``None`` for both.
    """
    moment = AUG_1 + timedelta(days=50)

    assert efforts((0, 300.0)).estimated_ftp(moment) is None
    assert EffortHistory().estimated_ftp(moment) is None


def test_effort_history_matches_a_brute_force_over_every_fixture_ride(imported: ImportedLibrary):
    """Each ride's estimate from the profile is the best stored 20 minutes in its window.

    Given: The fixture library (no FTP set), and a brute force over every ride's stored power
        curve.
    Expect: The same estimate for every ride; rides without power skipped.
    """
    rides = [imported.catalog.get_ride(i) for i in imported.catalog.ride_ids()]
    history = athlete_profile(imported.catalog).efforts

    for ride in rides:
        start = ride.summary.start
        window = [
            dict(other.summary.power_curve).get(20 * 60)
            for other in rides
            if start - timedelta(days=42) <= other.summary.start <= start
        ]
        best = max((w for w in window if w is not None), default=None)
        expected = 0.95 * best if best else None
        assert history.estimated_ftp(start) == pytest.approx(expected), (
            f"{ride.source_name} should have the brute-force estimate"
        )
