"""The ``fitlib trends`` commands and ``fitlib progress``: riding over weeks, months and routes."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import typer
from rich.table import Table

from fitlib import display
from fitlib.analysis import trends
from fitlib.analysis.training import athlete_profile, training
from fitlib.analysis.trends import BadRange, Period, View, resolve_range
from fitlib.cli.common import UnitsOption, app, fail, find_ride, library, out
from fitlib.cli.output import print_tss_notes, section, tss_text

trends_app = typer.Typer(
    help="Trends: volume, fitness, FTP, efficiency and best efforts over time.",
    no_args_is_help=True,
)
app.add_typer(trends_app, name="trends")

SinceOption = Annotated[
    datetime | None,
    typer.Option(formats=["%Y-%m-%d"], help="First day (local date). Default depends on view."),
]
UntilOption = Annotated[
    datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Last day (local date). Today.")
]
MonthOption = Annotated[bool, typer.Option("--month", help="By month instead of by week.")]


def _range(
    view: View, since: datetime | None, until: datetime | None, period: Period = Period.WEEK
) -> tuple[date, date]:
    """Turn the date options into a checked range.

    Args:
        view: Which trend the range is for.
        since: ``--since``, if given.
        until: ``--until``, if given.
        period: For volume, by week or month.

    Returns:
        The first and last days.

    Raises:
        typer.Exit: ``--since`` is after ``--until`` (code 2).
    """
    try:
        return resolve_range(
            view, since.date() if since else None, until.date() if until else None, period
        )
    except BadRange as exc:
        raise fail(str(exc)) from exc


def effort_label(seconds: int) -> str:
    """Name a best-effort duration.

    Args:
        seconds: The duration.

    Returns:
        For example ``"5 s"``, ``"20 min"``, ``"90 min"`` or ``"2 h"``.
    """
    if seconds < 60:
        return f"{seconds} s"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} h"
    return f"{seconds // 60} min"


def _without_tss(count: int) -> None:
    """Say how many rides add no TSS, if any.

    Args:
        count: Rides without TSS.
    """
    if count:
        rides = "ride has" if count == 1 else "rides have"
        out.print(
            f"{count} {rides} no TSS (no power or FTP, and no heart rate or threshold heart "
            "rate) and count as 0."
        )


@trends_app.command(
    "volume", help="Rides, time, distance, climbing, work and TSS per week (Mon-Sun) or month."
)
def volume(
    ctx: typer.Context,
    month: MonthOption = False,
    since: SinceOption = None,
    until: UntilOption = None,
    units: UnitsOption = None,
) -> None:
    """Print riding per week or month; 12 weeks or 12 months by default.

    Args:
        ctx: Typer context holding the config path.
        month: Group by month instead of by week.
        since: First day.
        until: Last day.
        units: Units for distance and climbing; the config's by default.
    """
    period = Period.MONTH if month else Period.WEEK
    first, last = _range(View.VOLUME, since, until, period)
    with library(ctx) as lib:
        buckets = trends.volume(lib.stores.catalog, period, first, last)
        chosen = lib.units(units)
    section(f"Volume by {period}, {first} to {last}")
    table = Table(box=None)
    label = "Week of" if period is Period.WEEK else "Month"
    for column in (label, "Rides", "Time", "Distance", "Climbing", "Work", "TSS"):
        table.add_column(column, no_wrap=True, justify="left" if column == label else "right")
    for b in buckets:
        table.add_row(
            b.start.isoformat() if period is Period.WEEK else f"{b.start:%b %Y}",
            str(b.rides),
            display.duration(b.moving_s),
            display.distance(b.distance_m, chosen),
            display.elevation(b.ascent_m, chosen),
            display.kilojoules(b.kj),
            display.tss(b.tss),
        )
    out.print(table)
    _without_tss(sum(b.rides_without_tss for b in buckets))


@trends_app.command(
    "fitness", help="Fitness (CTL), fatigue (ATL) and form (TSB), at the end of each week."
)
def fitness(
    ctx: typer.Context,
    since: SinceOption = None,
    until: UntilOption = None,
    daily: Annotated[bool, typer.Option("--daily", help="Every day, not just Sundays.")] = False,
) -> None:
    """Print fitness, fatigue and form; 90 days by default.

    Args:
        ctx: Typer context holding the config path.
        since: First day.
        until: Last day.
        daily: Show every day rather than each Sunday and the last day.
    """
    first, last = _range(View.FITNESS, since, until)
    with library(ctx) as lib:
        result = trends.fitness(lib.stores.catalog, first, last)
    days = [d for d in result.days if daily or d.day.weekday() == 6 or d.day == last]
    section(f"Fitness, fatigue and form, {first} to {last}")
    table = Table(box=None)
    for column in ("Day", "TSS", "Fitness", "Fatigue", "Form"):
        table.add_column(column, no_wrap=True, justify="left" if column == "Day" else "right")
    for d in days:
        table.add_row(
            f"{d.day:%a %Y-%m-%d}",
            display.tss(d.tss),
            f"{d.fitness:.0f}",
            f"{d.fatigue:.0f}",
            f"{d.form:+.0f}",
        )
    out.print(table)
    out.print("Fitness: 42-day load. Fatigue: 7-day load. Form: yesterday's fitness - fatigue.")
    _without_tss(result.rides_without_tss)


@trends_app.command("ftp", help="Set and estimated FTP at the end of each week or month.")
def ftp(
    ctx: typer.Context,
    month: MonthOption = False,
    since: SinceOption = None,
    until: UntilOption = None,
) -> None:
    """Print set and estimated FTP over time; a year by default.

    Args:
        ctx: Typer context holding the config path.
        month: By month instead of by week.
        since: First day.
        until: Last day.
    """
    period = Period.MONTH if month else Period.WEEK
    first, last = _range(View.FTP, since, until)
    with library(ctx) as lib:
        points = trends.ftp_history(lib.stores.catalog, period, first, last)
    section(f"FTP by {period}, {first} to {last}")
    table = Table(box=None)
    for column in ("Up to", "Set FTP", "Estimated"):
        table.add_column(column, no_wrap=True, justify="left" if column == "Up to" else "right")
    for p in points:
        table.add_row(p.day.isoformat(), display.watts(p.ftp), display.watts(p.estimated))
    out.print(table)
    out.print("Estimated: 95 % of the best 20 minutes in the six weeks up to that day.")


@trends_app.command(
    "efficiency", help="Efficiency (NP / average heart rate) of rides of 20 minutes or more."
)
def efficiency(ctx: typer.Context, since: SinceOption = None, until: UntilOption = None) -> None:
    """Print each ride's efficiency factor; a year by default.

    Args:
        ctx: Typer context holding the config path.
        since: First day.
        until: Last day.
    """
    first, last = _range(View.EFFICIENCY, since, until)
    with library(ctx) as lib:
        points = trends.efficiency(lib.stores.catalog, first, last)
    if not points:
        out.print(f"No rides with power and heart rate from {first} to {last}.")
        return
    section(f"Efficiency, {first} to {last}")
    table = Table(box=None)
    for column in ("Date", "ID", "NP", "Heart rate", "Efficiency", "Decoupling", "Where"):
        table.add_column(column, no_wrap=True)
    for p in points:
        table.add_row(
            p.day.isoformat(),
            p.ride_id[:8],
            display.watts(p.np),
            display.bpm(p.avg_hr),
            f"{p.efficiency:.2f}",
            display.signed_percent(p.decoupling_pct),
            "indoor" if p.indoor else "outdoor",
        )
    out.print(table)
    out.print("Efficiency: NP / average heart rate (W per bpm); higher is more power per beat.")


@trends_app.command("curve", help="Best power (or heart rate, --hr) at each duration.")
def curve(
    ctx: typer.Context,
    hr: Annotated[bool, typer.Option("--hr", help="Heart rate instead of power.")] = False,
    since: SinceOption = None,
    until: UntilOption = None,
) -> None:
    """Print the best effort at every duration and the ride it came from; 42 days by default.

    Args:
        ctx: Typer context holding the config path.
        hr: Heart rate instead of power.
        since: First day.
        until: Last day.
    """
    first, last = _range(View.CURVE, since, until)
    with library(ctx) as lib:
        points = trends.best_curve(lib.stores.catalog, "hr" if hr else "power", first, last)
    what = "heart rate" if hr else "power"
    if not points:
        out.print(f"No {what} from {first} to {last}.")
        return
    section(f"Best {what}, {first} to {last}")
    table = Table(box=None)
    for column in ("Best", "Value", "Date", "ID"):
        table.add_column(column, no_wrap=True)
    for p in points:
        table.add_row(
            effort_label(p.duration_s),
            display.bpm(p.value) if hr else display.watts(p.value),
            display.date(p.start),
            p.ride_id[:8],
        )
    out.print(table)


@app.command(help="List every ride on the same route as a ride, oldest first, to see progress.")
def progress(
    ctx: typer.Context,
    ride: Annotated[str, typer.Argument(help="Ride id or a unique prefix (4+ characters).")],
    units: UnitsOption = None,
) -> None:
    """Print a route's rides with their times, speeds, power and heart rate.

    Args:
        ctx: Typer context holding the config path.
        ride: The ride's id, or a prefix of at least 4 characters that matches one ride.
        units: Units for distance and speed; the config's by default.

    Raises:
        typer.Exit: No ride matches, or the prefix matches several (code 2).
    """
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        found = find_ride(catalog, ride)
        chosen = lib.units(units)
        has_route = bool(catalog.route_cells(found.id))
        rides = trends.route_progress(catalog, found)
        athlete = athlete_profile(catalog)
        figures = {r.id: training(catalog, r, athlete) for r in rides}
    if not has_route:
        out.print(f"{found.display_name} has no GPS positions, so it has no route to follow.")
        return
    section(f"Progress on the route of {found.display_name}")
    table = Table(box=None)
    for column in ("Date", "ID", "Time", "Distance", "Speed", "Power", "NP", "HR", "TSS"):
        table.add_column(column, no_wrap=True)
    table.add_column("")
    for r in rides:
        s = r.summary
        speed = s.distance_m / s.moving_s if s.distance_m and s.moving_s else None
        table.add_row(
            display.date(s.local_start or s.start),
            r.short_id,
            display.duration(s.moving_s),
            display.distance(s.distance_m, chosen),
            display.speed(speed, chosen),
            display.watts(s.avg_power),
            display.watts(s.np),
            display.bpm(s.avg_hr),
            tss_text(figures[r.id]),
            "this ride" if r.id == found.id else "",
        )
    out.print(table)
    print_tss_notes(figures.values())
    if len(rides) == 1:
        out.print("No other rides on this route yet.")
