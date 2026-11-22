"""Trends over many rides: volume, fitness, FTP, efficiency, best efforts and route progress."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from fitlib.analysis import trends
from fitlib.analysis.training import set_birth_year, training
from fitlib.analysis.trends import Period
from fitlib.models import AthleteEntry, Ride
from fitlib.store.memory import MemoryCatalog
from tests.unit.analysis.test_similar import road
from tests.unit.conftest import ImportedLibrary
from tests.unit.factories import make_ride

AUG_1 = date(2025, 8, 1)  # a Friday
AUG_31 = date(2025, 8, 31)
FTP = 250


def add(catalog: MemoryCatalog, when: datetime, route=frozenset(), **summary) -> Ride:
    """Add a ride starting at a given UTC time.

    Args:
        catalog: The catalog to add it to.
        when: Its start (UTC).
        route: Its route cells.
        **summary: ``RideSummary`` fields to change (UTC+2 by default).

    Returns:
        The ride.
    """
    ride = make_ride(start=when, **summary)
    catalog.add_ride(ride, route=route)
    return ride


def utc(day: int, hour: int = 8, month: int = 8) -> datetime:
    """A UTC time in 2025.

    Args:
        day: Day of the month.
        hour: Hour.
        month: Month.

    Returns:
        The time.
    """
    return datetime(2025, month, day, hour, tzinfo=UTC)


def hour_at_ftp(**summary) -> dict:
    """Summary fields for an hour at FTP: 100 TSS once FTP 250 is set.

    Args:
        **summary: More fields to change.

    Returns:
        The fields.
    """
    return {"moving_s": 3600, "np": float(FTP), **summary}


@pytest.fixture
def catalog() -> MemoryCatalog:
    """An empty library with FTP 250 W set from 2025.

    Returns:
        The catalog.
    """
    store = MemoryCatalog()
    store.set_athlete_entry(AthleteEntry(date(2025, 1, 1), ftp=FTP))
    return store


# -- TSS --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "athlete", ["nothing", "ftp", "heart-rate"], ids=["estimated-ftp", "set-ftp", "heart-rate"]
)
def test_tss_matches_the_ride_page(imported: ImportedLibrary, athlete: str):
    """Trend TSS is the same as the ride page's, for every fixture ride.

    Given: the fixture library, with no athlete history; with FTP 250 W from 10 Aug; or born
    1980 with threshold HR 150 from 14 Aug (rides without power before it use the age
    estimate).
    Expect: each ride's FTP, estimate flag, TSS and where it came from equal ``training()``'s.
    """
    if athlete == "ftp":
        imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 10), ftp=FTP))
    if athlete == "heart-rate":
        set_birth_year(imported.catalog, 1980)
        imported.catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 14), threshold_hr=150))

    loads = trends.ride_loads(imported.catalog, None, None)

    assert len(loads) == imported.catalog.count()
    for ride_load in loads:
        page = training(imported.catalog, imported.catalog.get_ride(ride_load.row.id))
        assert (ride_load.ftp, ride_load.ftp_estimated) == (page.ftp, page.ftp_estimated)
        assert ride_load.tss == pytest.approx(page.tss), f"TSS of {ride_load.row.id} should match"
        assert ride_load.tss_source == page.tss_source
    if athlete == "heart-rate":
        assert any(r.tss_source == "hr" for r in loads), "some rides should use heart rate"


def test_estimate_uses_rides_before_the_range():
    """A ride's estimated FTP looks back six weeks, even past the start of the range.

    Given: no FTP set; a ride on 1 Aug with best 20 min 300 W, and one on 10 Aug (best 200 W,
    NP 228, one hour).
    Expect: only the 10 Aug ride from 5 Aug on, with FTP 0.95 × 300 = 285 (estimated) and TSS
    100 × (228/285)² = 64.
    """
    catalog = MemoryCatalog()
    add(catalog, utc(1), power_curve=((1200, 300.0),))
    later = add(catalog, utc(10), power_curve=((1200, 200.0),), moving_s=3600, np=228.0)

    loads = trends.ride_loads(catalog, date(2025, 8, 5), None)

    assert [r.row.id for r in loads] == [later.id]
    assert (loads[0].ftp, loads[0].ftp_estimated) == (pytest.approx(285), True)
    assert loads[0].tss == pytest.approx(64)


# -- volume -----------------------------------------------------------------------------------


def test_weekly_volume_by_local_date(catalog: MemoryCatalog):
    """Rides go in the week of their local date; weeks start Monday; empty weeks are zeros.

    Given: a ride at 23:00 UTC on Sun 3 Aug (01:00 Mon 4 Aug at UTC+2), an hour at FTP on
    Mon 4 Aug, a ride without power on Sun 10 Aug, and a range of Wed 6 to Sun 24 Aug.
    Expect: weeks of 4 (widened back from 6 Aug), 11 and 18 Aug; the first with all 3 rides
    (2 h 58 min, 90 km, 750 m, 1440 kJ, 200 TSS, 1 ride without TSS); the others empty.
    """
    add(catalog, utc(3, 23), **hour_at_ftp())
    add(catalog, utc(4), **hour_at_ftp())
    add(catalog, utc(10), has_power=False, np=None, kj=None, power_curve=())

    weeks = trends.volume(catalog, Period.WEEK, date(2025, 8, 6), date(2025, 8, 24))

    assert [(w.start, w.rides) for w in weeks] == [
        (date(2025, 8, 4), 3),
        (date(2025, 8, 11), 0),
        (date(2025, 8, 18), 0),
    ], "the 3 Aug (UTC) ride is on Monday 4 Aug locally"
    first = weeks[0]
    assert (first.moving_s, first.distance_m, first.ascent_m, first.kj) == (
        10_700,
        90_000.0,
        750.0,
        1440.0,
    )
    assert (first.tss, first.rides_without_tss) == (pytest.approx(200), 1)
    assert weeks[2] == trends.VolumeBucket(date(2025, 8, 18))


def test_rides_without_power_add_heart_rate_tss(catalog: MemoryCatalog):
    """With a threshold heart rate, a ride without power adds TSS to volume and fitness.

    Given: threshold HR 160 from 2 Jan; an hour at FTP on Mon 4 Aug and a ride without power
    on Tue 5 Aug (the factory's heart rates: 600 s at 120, 1800 at 140, 1100 at 160, 1 at
    171 bpm).
    Expect: the week's TSS is 100 + 72,109,241 / 160² / 3600 x 100 (78.2), with no ride
    left without TSS; fitness on 5 Aug counts the day's 78.2.
    """
    catalog.set_athlete_entry(AthleteEntry(date(2025, 1, 2), threshold_hr=160))
    add(catalog, utc(4), **hour_at_ftp())
    add(catalog, utc(5), has_power=False, np=None, kj=None, power_curve=())
    hr_tss = 72_109_241 / 160**2 / 3600 * 100

    week = trends.volume(catalog, Period.WEEK, date(2025, 8, 4), date(2025, 8, 10))[0]
    fitness = trends.fitness(catalog, date(2025, 8, 5), date(2025, 8, 5))

    assert (week.tss, week.rides_without_tss) == (pytest.approx(100 + hr_tss), 0)
    assert fitness.days[0].tss == pytest.approx(hr_tss)
    assert fitness.rides_without_tss == 0


def test_monthly_volume(catalog: MemoryCatalog):
    """Months run from the 1st; a ride late on 31 Jul UTC can be August locally.

    Given: a ride at 23:00 UTC on 31 Jul (1 Aug at UTC+2), one on 15 Sep, and a range of
    20 Jul to 30 Sep.
    Expect: July empty, August and September with one ride each.
    """
    add(catalog, utc(31, 23, month=7))
    add(catalog, utc(15, month=9))

    months = trends.volume(catalog, Period.MONTH, date(2025, 7, 20), date(2025, 9, 30))

    assert [(m.start, m.rides) for m in months] == [
        (date(2025, 7, 1), 0),
        (date(2025, 8, 1), 1),
        (date(2025, 9, 1), 1),
    ]


# -- fitness ----------------------------------------------------------------------------------


def test_fitness_fatigue_and_form_by_hand(catalog: MemoryCatalog):
    """One 100-TSS ride raises fitness by 100/42 and fatigue by 100/7; form follows a day later.

    Given: an hour at FTP on 2 Aug, and the range 1 to 3 Aug.
    Expect: 1 Aug all zeros; 2 Aug fitness 2.381, fatigue 14.286, form 0; 3 Aug both decayed
    (× 41/42 and × 6/7) and form 2.381 − 14.286 = −11.905.
    """
    add(catalog, utc(2), **hour_at_ftp())

    result = trends.fitness(catalog, AUG_1, date(2025, 8, 3))

    days = result.days
    assert [d.day for d in days] == [AUG_1, date(2025, 8, 2), date(2025, 8, 3)]
    assert (days[0].fitness, days[0].fatigue, days[0].form) == (0.0, 0.0, 0.0)
    assert days[1].tss == pytest.approx(100)
    assert (days[1].fitness, days[1].fatigue) == (pytest.approx(100 / 42), pytest.approx(100 / 7))
    assert days[1].form == 0.0, "form is yesterday's balance"
    assert days[2].fitness == pytest.approx(100 / 42 * 41 / 42)
    assert days[2].fatigue == pytest.approx(100 / 7 * 6 / 7)
    assert days[2].form == pytest.approx(100 / 42 - 100 / 7)


def test_fitness_does_not_depend_on_the_range(catalog: MemoryCatalog):
    """Values on a day are the same whatever range is asked for; they start at the first ride.

    Given: hours at FTP on 2, 5 and 9 Aug, and a ride with neither power nor heart rate on
    12 Aug.
    Expect: 10 to 14 Aug alone matches the same days of 1 to 31 Aug; the ride without TSS
    is counted; fitness on 14 Aug isn't zero.
    """
    for day in (2, 5, 9):
        add(catalog, utc(day), **hour_at_ftp())
    add(catalog, utc(12), has_power=False, np=None, kj=None, power_curve=(), has_hr=False,
        avg_hr=None, hr_histogram=(), hr_curve=())  # fmt: skip

    month = trends.fitness(catalog, AUG_1, AUG_31)
    part = trends.fitness(catalog, date(2025, 8, 10), date(2025, 8, 14))

    assert part.days == month.days[9:14]
    assert part.rides_without_tss == 1
    assert part.days[-1].fitness > 0, "earlier rides should still count"


# -- FTP and efficiency -----------------------------------------------------------------------


def test_ftp_history_by_week(catalog: MemoryCatalog):
    """Each week ends with the set FTP and an estimate from the six weeks up to its last day.

    Given: FTP 250 from 1 Jan and 260 from 12 Aug; best 20 min 280 W on Mon 4 Aug and 300 W on
    Wed 13 Aug; weeks from 4 to 20 Aug.
    Expect: Sun 10 Aug: 250 set, 0.95 × 280 = 266; Sun 17 Aug: 260, 285; Wed 20 Aug (the
    range ends there): 260, 285.
    """
    catalog.set_athlete_entry(AthleteEntry(date(2025, 8, 12), ftp=260))
    add(catalog, utc(4), power_curve=((1200, 280.0),))
    add(catalog, utc(13), power_curve=((1200, 300.0),))

    points = trends.ftp_history(catalog, Period.WEEK, date(2025, 8, 4), date(2025, 8, 20))

    assert [(p.day, p.ftp, p.estimated) for p in points] == [
        (date(2025, 8, 10), 250, pytest.approx(266)),
        (date(2025, 8, 17), 260, pytest.approx(285)),
        (date(2025, 8, 20), 260, pytest.approx(285)),
    ]


def test_ftp_estimate_expires_after_six_weeks():
    """An effort stops counting 42 days later; with nothing set, FTP is ``None``.

    Given: no FTP set; best 20 min 280 W on 4 Aug; months August to October.
    Expect: August's estimate is 266, September's (30 Sep, 57 days on) is ``None``.
    """
    catalog = MemoryCatalog()
    add(catalog, utc(4), power_curve=((1200, 280.0),))

    points = trends.ftp_history(catalog, Period.MONTH, AUG_1, date(2025, 9, 30))

    assert [(p.day, p.ftp, p.estimated) for p in points] == [
        (AUG_31, None, pytest.approx(266)),
        (date(2025, 9, 30), None, None),
    ]


def test_efficiency_needs_power_heart_rate_and_twenty_minutes(catalog: MemoryCatalog):
    """Efficiency is NP / average heart rate, for rides with both that last 20 minutes.

    Given: a ride with NP 215 at 142 bpm; one without heart rate; one without power; one of
    19 minutes.
    Expect: only the first, at 215 / 142 = 1.514 W/bpm, with its decoupling.
    """
    good = add(catalog, utc(2))
    add(catalog, utc(3), avg_hr=None, has_hr=False)
    add(catalog, utc(4), np=None, has_power=False)
    add(catalog, utc(5), moving_s=19 * 60)

    points = trends.efficiency(catalog, AUG_1, AUG_31)

    assert [p.ride_id for p in points] == [good.id]
    point = points[0]
    assert point.efficiency == pytest.approx(215 / 142)
    assert (point.day, point.np, point.avg_hr, point.decoupling_pct) == (
        date(2025, 8, 2),
        215.0,
        142.0,
        3.2,
    )


# -- best efforts -----------------------------------------------------------------------------


def test_best_curve_uses_local_dates(catalog: MemoryCatalog):
    """Rides just outside the range by local date are left out of the best efforts.

    Given: 900 W for 5 s at 23:00 UTC on 31 Jul (1 Aug at UTC+2), 800 W on 15 Aug, and 999 W
    at 23:00 UTC on 31 Aug (1 Sep locally); the range is August.
    Expect: 900 W from the 31 Jul ride; the 31 Aug ride is September's.
    """
    early = add(catalog, utc(31, 23, month=7), power_curve=((5, 900.0),))
    add(catalog, utc(15), power_curve=((5, 800.0),))
    add(catalog, utc(31, 23), power_curve=((5, 999.0),))

    best = trends.best_curve(catalog, "power", AUG_1, AUG_31)
    empty = trends.best_curve(catalog, "power", date(2025, 10, 1), date(2025, 10, 31))

    assert [(b.duration_s, b.value, b.ride_id) for b in best] == [(5, 900.0, early.id)]
    assert empty == [], "no rides in October"


# -- route progress ---------------------------------------------------------------------------


def test_route_progress_lists_same_route_rides_oldest_first():
    """A ride's route history has every same-route ride, itself included, oldest first.

    Given: a ride on a 20-cell road on 10 Aug, the same road on 2 and 20 Aug, half of it on
    5 Aug, and a ride with no positions.
    Expect: 2, 10 and 20 Aug; the ride without positions has only itself.
    """
    catalog = MemoryCatalog()
    first = add(catalog, utc(2), road(0, 20))
    add(catalog, utc(5), road(0, 10))
    mine = add(catalog, utc(10), road(0, 20))
    last = add(catalog, utc(20), road(0, 20))
    indoor = add(catalog, utc(21))

    rides = trends.route_progress(catalog, mine)
    alone = trends.route_progress(catalog, indoor)

    assert [r.id for r in rides] == [first.id, mine.id, last.id]
    assert [r.id for r in alone] == [indoor.id]


def test_trends_of_an_empty_library():
    """With no rides, ranges still come back, as zeros.

    Given: an empty library and the range 1 to 14 Aug.
    Expect: three empty weeks (from Mon 28 Jul), 14 days of zero fitness, no efficiency
    points and no best efforts.
    """
    catalog = MemoryCatalog()
    until = date(2025, 8, 14)

    weeks = trends.volume(catalog, Period.WEEK, AUG_1, until)
    result = trends.fitness(catalog, AUG_1, until)

    assert [(w.start, w.rides) for w in weeks] == [
        (date(2025, 7, 28), 0),
        (date(2025, 8, 4), 0),
        (date(2025, 8, 11), 0),
    ]
    assert len(result.days) == 14
    assert all(d.fitness == 0 for d in result.days)
    assert trends.efficiency(catalog, AUG_1, until) == []
    assert trends.best_curve(catalog, "power", AUG_1, until) == []


# -- date ranges ------------------------------------------------------------------------------

TODAY = date(2026, 3, 18)


@pytest.mark.parametrize(
    ("view", "period", "since"),
    [
        (trends.View.VOLUME, Period.WEEK, date(2025, 12, 25)),  # 12 weeks
        (trends.View.VOLUME, Period.MONTH, date(2025, 4, 1)),  # this month and the 11 before
        (trends.View.FITNESS, Period.WEEK, date(2025, 12, 19)),  # 90 days
        (trends.View.FTP, Period.WEEK, date(2025, 3, 19)),  # a year
        (trends.View.EFFICIENCY, Period.WEEK, date(2025, 3, 19)),
        (trends.View.CURVE, Period.WEEK, date(2026, 2, 5)),  # 42 days
    ],
    ids=["volume-week", "volume-month", "fitness", "ftp", "efficiency", "curve"],
)
def test_default_ranges(view: trends.View, period: Period, since: date):
    """Left out, a range ends today and starts a span back that suits the view.

    Given: today 18 Mar 2026 and no dates.
    Expect: the view's default first day, counting today as one of its days.
    """
    assert trends.resolve_range(view, None, None, period, today=TODAY) == (since, TODAY)


def test_given_ranges_are_kept_or_refused():
    """Dates given are kept; a range ending before it starts is refused.

    Given: 1 to 31 Aug; then 31 Aug to 1 Aug.
    Expect: the same dates; then ``BadRange`` naming both.
    """
    kept = trends.resolve_range(trends.View.CURVE, AUG_1, AUG_31)

    assert kept == (AUG_1, AUG_31)
    with pytest.raises(trends.BadRange, match=r"since \(2025-08-31\).*until \(2025-08-01\)"):
        trends.resolve_range(trends.View.CURVE, AUG_31, AUG_1)
