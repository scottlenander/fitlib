"""The ``fitlib bikes`` commands: bikes and which bike rides get by default."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Annotated

import typer
from rich.table import Table

from fitlib import display
from fitlib.analysis.bikes import NO_BIKE, backfill_bikes
from fitlib.cli.common import UnitsOption, bikes_app, fail, find_bike, library, out
from fitlib.models import (
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
)
from fitlib.store.interfaces import (
    CatalogStore,
    DuplicateBike,
)


@bikes_app.command("add", help='Add a bike. Quote names with spaces: "Giant Contend 1".')
def bikes_add(
    ctx: typer.Context,
    name: Annotated[str, typer.Argument(help="The bike's name.", show_default=False)],
    kind: Annotated[BikeKind | None, typer.Option(help="What sort of bike.")] = None,
    default_for: Annotated[
        BikeSlot | None,
        typer.Option(help="Also make it the default for this kind of ride, from --from."),
    ] = None,
    from_date: Annotated[
        datetime | None,
        typer.Option("--from", formats=["%Y-%m-%d"], help="With --default-for: from this day."),
    ] = None,
) -> None:
    """Add a bike, optionally making it a default for one kind of ride.

    Args:
        ctx: Typer context holding the config path.
        name: The bike's name.
        kind: What sort of bike it is.
        default_for: Which kind of ride it becomes the default for, if any.
        from_date: The first day of the default; required with ``default_for``.

    Raises:
        typer.Exit: The name is empty or taken, or ``--default-for`` lacks ``--from`` (code 2).
    """
    clean = " ".join(name.split())
    if not clean:
        raise fail("Bike names can't be empty.")
    if default_for is not None and from_date is None:
        raise fail("--default-for needs --from (the first day it applies).")
    bike = Bike(id=str(uuid.uuid4()), name=clean, kind=kind)
    with library(ctx) as lib:
        try:
            lib.stores.catalog.add_bike(bike)
        except DuplicateBike:
            raise fail(f"There is already a bike called {clean!r}.") from None
        if default_for is not None and from_date is not None:
            lib.stores.catalog.set_bike_default(BikeDefault(default_for, from_date.date(), bike.id))
    out.print(f"Added {clean}.")
    if default_for is not None and from_date is not None:
        out.print(f"Default for {default_for.value} rides from {from_date:%Y-%m-%d}.")


@bikes_app.command("list", help="List bikes with their rides, distance and riding time.")
def bikes_list(
    ctx: typer.Context,
    all_bikes: Annotated[bool, typer.Option("--all", help="Include retired bikes.")] = False,
    units: UnitsOption = None,
) -> None:
    """Print each bike with its kind, ride count, distance and riding time.

    Args:
        ctx: Typer context holding the config path.
        all_bikes: Include retired bikes.
        units: Units for distance; the config's by default.
    """
    with library(ctx) as lib:
        totals = lib.stores.catalog.bike_totals()
        chosen = lib.units(units)
    shown = [t for t in totals if all_bikes or not t.bike.retired]
    if not shown:
        out.print('No bikes yet. Add one with `fitlib bikes add "Name"`.')
        return
    table = Table("Bike", "Kind", "Rides", "Distance", "Time", box=None)
    for t in shown:
        name = f"{t.bike.name} (retired)" if t.bike.retired else t.bike.name
        table.add_row(
            name,
            t.bike.kind.value if t.bike.kind else display.DASH,
            str(t.rides),
            display.distance(t.distance_m, chosen),
            display.duration(t.moving_s),
        )
    out.print(table)


@bikes_app.command("rename", help="Rename a bike.")
def bikes_rename(
    ctx: typer.Context,
    bike: Annotated[str, typer.Argument(help="Current name (or a unique start of it).")],
    new_name: Annotated[str, typer.Argument(help="New name.", show_default=False)],
) -> None:
    """Rename a bike; its rides become findable by the new name.

    Args:
        ctx: Typer context holding the config path.
        bike: The bike's current name or a unique prefix.
        new_name: The new name.

    Raises:
        typer.Exit: The bike isn't found, or the new name is empty or taken (code 2).
    """
    clean = " ".join(new_name.split())
    if not clean:
        raise fail("Bike names can't be empty.")
    with library(ctx) as lib:
        found = find_bike(lib.stores.catalog, bike)
        try:
            lib.stores.catalog.update_bike(replace(found, name=clean))
        except DuplicateBike:
            raise fail(f"There is already a bike called {clean!r}.") from None
    out.print(f"Renamed {found.name} to {clean}.")


def _set_retired(ctx: typer.Context, bike: str, retired: bool) -> None:
    """Retire or bring back a bike.

    Args:
        ctx: Typer context holding the config path.
        bike: The bike's name or a unique prefix.
        retired: Whether the bike is retired afterwards.

    Raises:
        typer.Exit: The bike isn't found (code 2).
    """
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        found = find_bike(catalog, bike)
        catalog.update_bike(replace(found, retired=retired))
        current = current_defaults(catalog)
    out.print(f"{'Retired' if retired else 'Brought back'} {found.name}.")
    slots = [slot.value for slot, bike_id in current.items() if bike_id == found.id]
    if retired and slots:
        out.print(
            f"It is still the default for {', '.join(slots)} rides; set the next bike with "
            "`fitlib bikes default NAME --for SLOT --from DATE`."
        )


@bikes_app.command("retire", help="Retire a bike. Its rides keep it.")
def bikes_retire(
    ctx: typer.Context,
    bike: Annotated[str, typer.Argument(help="Bike name (or a unique start of it).")],
) -> None:
    """Retire a bike: it keeps its rides but is hidden from ``bikes list``.

    Args:
        ctx: Typer context holding the config path.
        bike: The bike's name or a unique prefix.
    """
    _set_retired(ctx, bike, retired=True)


@bikes_app.command("unretire", help="Bring a retired bike back.")
def bikes_unretire(
    ctx: typer.Context,
    bike: Annotated[str, typer.Argument(help="Bike name (or a unique start of it).")],
) -> None:
    """Bring a retired bike back.

    Args:
        ctx: Typer context holding the config path.
        bike: The bike's name or a unique prefix.
    """
    _set_retired(ctx, bike, retired=False)


def current_defaults(catalog: CatalogStore) -> dict[BikeSlot, str | None]:
    """Find each slot's most recent default-bike entry.

    Args:
        catalog: The library's catalog.

    Returns:
        The bike id (or ``None`` for "stop defaulting") of the latest entry per slot that has
        any entries.
    """
    latest: dict[BikeSlot, str | None] = {}
    for entry in catalog.bike_defaults():  # by slot, then date
        latest[entry.slot] = entry.bike_id
    return latest


@bikes_app.command(
    "default",
    help="Set the bike rides of one kind get by default, from a date on. New imports use "
    "it; run `fitlib bikes backfill` for rides already imported.",
)
def bikes_default(
    ctx: typer.Context,
    slot: Annotated[BikeSlot, typer.Option("--for", help="Which kind of ride.")],
    from_date: Annotated[
        datetime, typer.Option("--from", formats=["%Y-%m-%d"], help="First day it applies.")
    ],
    bike: Annotated[
        str | None, typer.Argument(help="Bike name (or start). Leave out with --clear.")
    ] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Stop defaulting from this date.")] = False,
    remove: Annotated[
        bool, typer.Option("--remove", help="Delete the entry for this kind and date instead.")
    ] = False,
) -> None:
    """Add, replace or remove a dated default-bike entry for one kind of ride.

    Args:
        ctx: Typer context holding the config path.
        slot: Which kind of ride (zwift, indoor or outdoor).
        from_date: The first day the entry applies.
        bike: The bike, by name or unique prefix; not with ``clear`` or ``remove``.
        clear: Add an entry that stops defaulting from this date.
        remove: Delete the existing entry for this slot and date.

    Raises:
        typer.Exit: Not exactly one of a bike, ``--clear`` and ``--remove``; an unknown bike;
            or no entry to remove (code 2).
    """
    if sum([bike is not None, clear, remove]) != 1:
        raise fail("Give a bike, --clear or --remove (exactly one).")
    day = from_date.date()
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        if remove:
            if not catalog.delete_bike_default(slot, day):
                raise fail(f"No {slot.value} default starts on {day:%Y-%m-%d}.")
            out.print(f"Removed the {slot.value} default from {day:%Y-%m-%d}.")
            return
        found = find_bike(catalog, bike) if bike is not None else None
        catalog.set_bike_default(BikeDefault(slot, day, found.id if found else None))
    if found is None:
        out.print(f"No default bike for {slot.value} rides from {day:%Y-%m-%d}.")
    else:
        out.print(f"{found.name} is the default for {slot.value} rides from {day:%Y-%m-%d}.")


@bikes_app.command("defaults", help="Show the default bikes over time.")
def bikes_defaults(ctx: typer.Context) -> None:
    """Print every dated default-bike entry, by kind of ride then date.

    Args:
        ctx: Typer context holding the config path.
    """
    with library(ctx) as lib:
        entries = lib.stores.catalog.bike_defaults()
        names = {b.id: b.name for b in lib.stores.catalog.list_bikes()}
    if not entries:
        out.print(
            "No default bikes. Set one with `fitlib bikes default NAME --for SLOT --from DATE`."
        )
        return
    table = Table("For", "From", "Bike", box=None)
    for entry in entries:
        table.add_row(
            entry.slot.value,
            f"{entry.effective_from:%Y-%m-%d}",
            names.get(entry.bike_id, "?") if entry.bike_id else "(none)",
        )
    out.print(table)


@bikes_app.command(
    "backfill",
    help="Apply the default bikes to rides without a bike, and update rides whose bike came "
    "from a default. Bikes you set with `fitlib edit` are never changed.",
)
def bikes_backfill(
    ctx: typer.Context,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Only show what would change.")
    ] = False,
) -> None:
    """Re-apply the dated default bikes to rides whose bike wasn't chosen by hand.

    Args:
        ctx: Typer context holding the config path.
        dry_run: Only count what would change.
    """
    with library(ctx) as lib:
        assigned = backfill_bikes(lib.stores.catalog, dry_run=dry_run)
        names = {b.id: b.name for b in lib.stores.catalog.list_bikes()}
    if not assigned:
        out.print("No rides to update.")
        return
    verb = "Would set" if dry_run else "Set"
    for bike_id, count in sorted(assigned.items(), key=lambda kv: names.get(kv[0], kv[0])):
        if bike_id == NO_BIKE:
            out.print(
                f"{'Would clear' if dry_run else 'Cleared'} the default bike on {count} ride(s)."
            )
        else:
            out.print(f"{verb} {names.get(bike_id, bike_id)} on {count} ride(s).")
