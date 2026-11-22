"""The ``fitlib athlete`` commands: FTP, weight and heart rates over time, and year of birth.

Threshold heart rate is estimated from the year of birth on days without one set.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

import typer
from rich.table import Table

from fitlib import display
from fitlib.analysis.training import (
    BadBirthYear,
    athlete_profile,
    set_birth_year,
    threshold_today,
)
from fitlib.cli.common import UnitsOption, athlete_app, fail, library, out
from fitlib.metrics import load
from fitlib.models import (
    AthleteEntry,
)


@athlete_app.command(
    "set",
    help="Record FTP, weight, max and/or threshold heart rate from a date on. Values not given "
    "are unchanged. Weight is in your display units.",
)
def athlete_set(
    ctx: typer.Context,
    from_date: Annotated[
        datetime,
        typer.Option("--from", formats=["%Y-%m-%d"], help="First day the values apply."),
    ],
    ftp: Annotated[int | None, typer.Option(min=1, help="FTP in watts.")] = None,
    weight: Annotated[float | None, typer.Option(min=1, help="Body weight (lb or kg).")] = None,
    max_hr: Annotated[int | None, typer.Option(min=1, help="Max heart rate in bpm.")] = None,
    lthr: Annotated[
        int | None,
        typer.Option(
            min=1,
            max=250,
            help="Threshold (lactate threshold) heart rate in bpm, for TSS on rides without "
            "power. Without one, it's estimated from your year of birth.",
        ),
    ] = None,
    units: UnitsOption = None,
) -> None:
    """Add (or replace) the athlete history entry for a date.

    Args:
        ctx: Typer context holding the config path.
        from_date: The first day the values apply.
        ftp: FTP in watts, if changing.
        weight: Body weight in the display units, if changing.
        max_hr: Max heart rate in bpm, if changing.
        lthr: Threshold heart rate in bpm, if changing.
        units: Units ``weight`` is given in; the config's by default.

    Raises:
        typer.Exit: No value was given (code 2).
    """
    if ftp is None and weight is None and max_hr is None and lthr is None:
        raise fail("Give at least one of --ftp, --weight, --max-hr or --lthr.")
    with library(ctx) as lib:
        chosen = lib.units(units)
        entry = AthleteEntry(
            effective_from=from_date.date(),
            ftp=ftp,
            weight_kg=display.kg_from(weight, chosen) if weight is not None else None,
            max_hr=max_hr,
            threshold_hr=lthr,
        )
        lib.stores.catalog.set_athlete_entry(entry)
    out.print(f"Saved athlete values from {entry.effective_from:%Y-%m-%d}.")


@athlete_app.command("show", help="Show the athlete history and today's values.")
def athlete_show(ctx: typer.Context, units: UnitsOption = None) -> None:
    """Print every athlete history entry, then the values in effect today.

    Args:
        ctx: Typer context holding the config path.
        units: Units to show weight in; the config's by default.
    """
    with library(ctx) as lib:
        profile = athlete_profile(lib.stores.catalog)
        threshold, source = threshold_today(lib.stores.catalog, profile)
        chosen = lib.units(units)
    history = profile.history
    today = date.today()
    estimate = load.estimated_threshold_hr(profile.birth_year, today)
    if profile.birth_year is not None:
        out.print(
            f"Born {profile.birth_year}: threshold heart rate estimated at "
            f"{display.bpm(estimate)} when none is set and your rides don't give one."
        )
    if not history:
        out.print("No athlete history yet. Add some with `fitlib athlete set`.")
        return
    table = Table("From", "FTP", "Weight", "Max HR", "Threshold HR", box=None)
    for entry in history:
        table.add_row(
            f"{entry.effective_from:%Y-%m-%d}",
            display.watts(entry.ftp),
            display.weight(entry.weight_kg, chosen),
            display.bpm(entry.max_hr),
            display.bpm(entry.threshold_hr),
        )
    out.print(table)
    now = load.values_on(history, today)
    out.print(
        f"\nToday: FTP {display.watts(now.ftp)}, weight {display.weight(now.weight_kg, chosen)}, "
        f"max HR {display.bpm(now.max_hr)}, threshold HR "
        f"{display.bpm(threshold)}{display.threshold_source(source)}."
    )


@athlete_app.command("remove", help="Remove the athlete history entry for a date.")
def athlete_remove(
    ctx: typer.Context,
    entry_date: Annotated[datetime, typer.Argument(formats=["%Y-%m-%d"], help="The entry's date.")],
) -> None:
    """Remove the athlete history entry for a date.

    Args:
        ctx: Typer context holding the config path.
        entry_date: The entry's date.

    Raises:
        typer.Exit: There is no entry for that date (code 2).
    """
    with library(ctx) as lib:
        removed = lib.stores.catalog.delete_athlete_entry(entry_date.date())
    if not removed:
        raise fail(f"No athlete entry on {entry_date:%Y-%m-%d}.")
    out.print(f"Removed the athlete entry for {entry_date:%Y-%m-%d}.")


@athlete_app.command(
    "born",
    help="Set your year of birth: threshold heart rate is estimated from your age when none is "
    "set, for TSS on rides without power.",
)
def athlete_born(
    ctx: typer.Context,
    year: Annotated[int | None, typer.Argument(help="Year of birth, e.g. 1980.")] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Forget the year of birth.")] = False,
) -> None:
    """Set or clear the rider's year of birth.

    Args:
        ctx: Typer context holding the config path.
        year: The year of birth.
        clear: Clear it instead.

    Raises:
        typer.Exit: Neither or both of a year and ``--clear``, or an impossible year (code 2).
    """
    if (year is None) == (not clear):
        raise fail("Give a year of birth, or --clear.")
    with library(ctx) as lib:
        try:
            set_birth_year(lib.stores.catalog, year)
        except BadBirthYear as exc:
            raise fail(str(exc)) from None
    if year is None:
        out.print("Cleared the year of birth: rides without power need a set threshold HR for TSS.")
        return
    estimate = load.estimated_threshold_hr(year, date.today())
    out.print(f"Saved: born {year}. Estimated threshold heart rate today: {display.bpm(estimate)}.")
