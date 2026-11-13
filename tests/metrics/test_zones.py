"""Histograms and time in power and heart-rate zones."""

from __future__ import annotations

from functools import cache

import polars as pl

from fitlib.ingest.decoder import decode
from fitlib.ingest.normalize import to_frame
from fitlib.metrics.zones import HR_ZONE_BOUNDS, POWER_ZONE_BOUNDS, histogram, zone_times
from tests.fixtures.generate import committed_bytes


@cache
def frame_for(name: str) -> pl.DataFrame:
    return to_frame(decode(committed_bytes(name)).records)


def test_histogram_counts_riding_seconds_per_value():
    """The histogram counts riding seconds at each whole value, leaving out pauses.

    Given: the interval ride (power), and the paused ride (30 min at 190 W around a pause).
    Expect: intervals: 600 s at 150 W, 1200 s at 300 W, 1200 s at 120 W, 600 s at 130 W;
    paused ride: 1800 s at 190 W, not 2400.
    """
    intervals = dict(histogram(frame_for("garmin_nord_intervals_5x4"), "power"))
    paused = dict(histogram(frame_for("garmin_nord_pause_10min"), "power"))

    assert intervals == {120: 1200, 130: 600, 150: 600, 300: 1200}
    assert paused == {190: 1800}, "paused seconds should not count"


def test_histogram_of_a_missing_channel_is_empty():
    """No heart-rate strap means no heart-rate histogram.

    Given: the indoor ride without heart rate.
    Expect: an empty histogram.
    """
    assert histogram(frame_for("garmin_indoor_no_hr"), "heart_rate") == ()


def test_power_zones_at_ftp_250():
    """Power zone times follow Coggan's bands of % FTP.

    Given: the interval ride's histogram and FTP 250 W: 120 W (48 %) and 130 W (52 %) are Z1,
    150 W (60 %) is Z2, 300 W (120 %) is Z5.
    Expect: Z1 1800 s, Z2 600 s, Z5 1200 s, nothing elsewhere.
    """
    hist = histogram(frame_for("garmin_nord_intervals_5x4"), "power")

    seconds = zone_times(hist, 250, POWER_ZONE_BOUNDS)

    assert seconds == (1800, 600, 0, 0, 1200, 0, 0)


def test_zone_boundaries_are_inclusive_at_the_top():
    """A value exactly on a boundary belongs to the lower zone.

    Given: 1 s each at 55 %, 56 %, 150 % and 151 % of a 100 W FTP.
    Expect: 55 % in Z1, 56 % in Z2, 150 % in Z6, 151 % in Z7.
    """
    hist = ((55, 1), (56, 1), (150, 1), (151, 1))

    seconds = zone_times(hist, 100, POWER_ZONE_BOUNDS)

    assert seconds == (1, 1, 0, 0, 0, 1, 1)


def test_heart_rate_zones_at_max_190():
    """Heart-rate zone times follow % of max heart rate; below 50 % still counts in Z1.

    Given: the interval ride's heart rates (128, 165, 120 and 122 bpm) and max HR 190; plus
    one second at 80 bpm (42 %).
    Expect: 165 bpm (87 %) in Z4 for 1200 s; everything else, including 80 bpm, in Z2 or Z1.
    """
    hist = (*histogram(frame_for("garmin_nord_intervals_5x4"), "heart_rate"), (80, 1))

    seconds = zone_times(hist, 190, HR_ZONE_BOUNDS)

    assert seconds == (1, 2400, 0, 1200, 0), "80 bpm in Z1; 120-128 bpm in Z2; 165 bpm in Z4"
