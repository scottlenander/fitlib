"""FTP-based figures for imported rides, from the athlete history or an estimated FTP."""

from __future__ import annotations

from datetime import date

import pytest

from fitlib.analysis.training import training
from fitlib.models import AthleteEntry
from tests.conftest import ImportedLibrary

ZWIFT = "zwift_watopia_steady_60min.fit"  # 2 Aug, 60 min at 200 W
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

    Given: FTP 250 and max HR 190 from 1 Aug; the 16 Aug ride with heart rate but no power.
    Expect: no IF, TSS or power zones; HR zones for all 2700 s.
    """
    imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 1), ftp=250, max_hr=190))

    figures = training(imported.catalog, imported.ride(NO_POWER))

    assert (figures.intensity_factor, figures.tss, figures.power_zones) == (None, None, None)
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
