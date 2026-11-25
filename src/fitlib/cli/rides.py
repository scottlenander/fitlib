"""Commands for rides: import, list, show, similar, compare, edit, delete, tags, recompute."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from fitlib import display
from fitlib.analysis.timezone import default_zone
from fitlib.cli.common import (
    EXIT_IMPORT_FAILURES,
    UnitsOption,
    app,
    err,
    fail,
    find_bike,
    find_ride,
    library,
    out,
    outdated_hint,
    tags_from,
)
from fitlib.cli.output import print_report, print_ride, print_tss_notes, section, tss_text
from fitlib.ingest.scanner import scan
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.metadata import KEEP, MetaEdit
from fitlib.metrics.curves import best_at
from fitlib.models import (
    Filters,
    SortKey,
    Source,
)
from fitlib.services import rides as ride_service
from fitlib.services.compare import MAX_RIDES, MIN_RIDES, compared_rides
from fitlib.services.importing import Importer
from fitlib.services.recompute import Recomputer
from fitlib.store.interfaces import (
    AmbiguousRideId,
    RideNotFound,
)


@app.command(
    "import",
    help="Import rides. Files already in the library are skipped, so re-running is safe.",
)
def import_(
    ctx: typer.Context,
    paths: Annotated[
        list[Path], typer.Argument(help="Folders, .fit files or .zip archives.", show_default=False)
    ],
    workers: Annotated[
        int | None, typer.Option(min=1, help="Processes for decoding. Default: up to 4.")
    ] = None,
    include_deleted: Annotated[
        bool,
        typer.Option(
            "--include-deleted", help="Also import rides you deleted (they're skipped otherwise)."
        ),
    ] = False,
) -> None:
    """Import every .fit file under ``paths`` and print a report.

    Args:
        ctx: Typer context holding the config path.
        paths: Folders (searched recursively), .fit files and .zip archives.
        workers: Number of decoding processes; up to 4 by default.
        include_deleted: Import files of deleted rides too.

    Raises:
        typer.Exit: A path doesn't exist (code 2), or some files couldn't be read (code 1).
    """
    try:
        total = sum(1 for _ in scan(paths))
    except FileNotFoundError as exc:
        raise fail(f"No such file or folder: {exc}") from None

    with library(ctx) as lib:
        s = lib.stores
        importer = Importer(s.catalog, s.blobs, s.streams, workers=workers)
        with Progress(
            TextColumn("Importing"), BarColumn(), MofNCompleteColumn(), console=err,
            transient=True,
        ) as progress:  # fmt: skip
            task = progress.add_task("import", total=total)
            report = importer.run(
                paths,
                on_progress=lambda _: progress.advance(task),
                include_deleted=include_deleted,
            )
        print_report(report)
        outdated_hint(s.catalog)

    if report.failed:
        raise typer.Exit(EXIT_IMPORT_FAILURES)


def _date(value: datetime | None) -> datetime | None:
    """Treat a date typed on the command line as midnight UTC.

    Args:
        value: The parsed date (naive), or ``None`` if the option wasn't given.

    Returns:
        The same moment marked as UTC, or ``None``.
    """
    return value.replace(tzinfo=UTC) if value is not None else None


@app.command("list", help="List rides, newest first. Dates are UTC.")
def list_(
    ctx: typer.Context,
    text: Annotated[
        str | None, typer.Option("--text", "-t", help="Words in name, notes, tags or device.")
    ] = None,
    since: Annotated[
        datetime | None, typer.Option(formats=["%Y-%m-%d"], help="On or after this date.")
    ] = None,
    until: Annotated[
        datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Before this date.")
    ] = None,
    source: Annotated[Source | None, typer.Option(help="Only rides from this source.")] = None,
    indoor: Annotated[
        bool | None, typer.Option("--indoor/--outdoor", help="Only indoor or outdoor rides.")
    ] = None,
    min_minutes: Annotated[int | None, typer.Option(min=0, help="Riding time at least.")] = None,
    max_minutes: Annotated[int | None, typer.Option(min=0, help="Riding time at most.")] = None,
    sort: Annotated[SortKey, typer.Option(help="Sort by.")] = SortKey.START,
    asc: Annotated[bool, typer.Option("--asc", help="Ascending (default: descending).")] = False,
    limit: Annotated[int, typer.Option(min=1, help="Rides per page.")] = 20,
    offset: Annotated[int, typer.Option(min=0, help="Skip this many rides.")] = 0,
    tag: Annotated[
        list[str] | None, typer.Option(help="Only rides with this tag; repeat to need several.")
    ] = None,
    bike: Annotated[
        str | None, typer.Option(help="Only rides on this bike (name or start).")
    ] = None,
    min_rpe: Annotated[int | None, typer.Option(min=1, max=10, help="Effort at least.")] = None,
    max_rpe: Annotated[int | None, typer.Option(min=1, max=10, help="Effort at most.")] = None,
    world: Annotated[
        str | None,
        typer.Option(help="Only Zwift rides in this world, e.g. watopia or makuri-islands."),
    ] = None,
    units: UnitsOption = None,
) -> None:
    """Print one page of rides matching the filters as a table.

    Args:
        ctx: Typer context holding the config path.
        text: Words to find in name, notes, tags, source or device.
        since: Only rides starting on or after this date (UTC).
        until: Only rides starting before this date (UTC).
        source: Only rides from this source.
        indoor: Only indoor (``--indoor``) or outdoor (``--outdoor``) rides.
        min_minutes: Only rides with at least this much riding time.
        max_minutes: Only rides with at most this much riding time.
        sort: What to sort by.
        asc: Sort ascending instead of descending.
        limit: Most rides to show.
        offset: Number of matching rides to skip first.
        tag: Tags every listed ride must have.
        bike: Only rides on this bike.
        min_rpe: Only rides with a perceived effort of at least this.
        max_rpe: Only rides with a perceived effort of at most this.
        world: Only Zwift rides in this world.
        units: Units to show distance in; the config's by default.

    Raises:
        typer.Exit: An unknown world, or a world with a source other than Zwift (code 2).
    """
    filters = Filters(
        text=text,
        since=_date(since),
        until=_date(until),
        source=source,
        indoor=indoor,
        min_duration_s=min_minutes * 60 if min_minutes is not None else None,
        max_duration_s=max_minutes * 60 if max_minutes is not None else None,
        tags=tags_from(tag),
        min_rpe=min_rpe,
        max_rpe=max_rpe,
    )
    with library(ctx) as lib:
        if bike is not None:
            filters = replace(filters, bike_id=find_bike(lib.stores.catalog, bike).id)
        found = ride_service.list_rides(lib.stores, filters, world, sort, not asc, offset, limit)
        chosen = lib.units(units)

    page = found.page
    if not page.items:
        out.print("No rides found.")
        return
    # Figures never wrap or truncate; on a narrow terminal the name wraps instead.
    table = Table(box=None)
    for column in ("ID", "Date", "Time", "Distance", "Power", "HR", "TSS"):
        table.add_column(column, no_wrap=True)
    table.add_column("Name")
    for view in found.views:
        ride, r = view.ride, view.ride.summary
        table.add_row(
            ride.short_id,
            display.date(r.local_start or r.start),
            display.duration(r.moving_s),
            display.distance(r.distance_m, chosen),
            display.watts(r.avg_power),
            display.bpm(r.avg_hr),
            tss_text(view.figures),
            ride.display_name,
        )
    out.print(table)
    shown_to = page.offset + len(page.items)
    out.print(f"Showing {page.offset + 1}–{shown_to} of {page.total}.")
    print_tss_notes(v.figures for v in found.views)


@app.command(help="Show one ride's summary.")
def show(
    ctx: typer.Context,
    ride: Annotated[str, typer.Argument(help="Ride id or a unique prefix (4+ characters).")],
    units: UnitsOption = None,
) -> None:
    """Print one ride's summary, found by id or id prefix.

    Args:
        ctx: Typer context holding the config path.
        ride: The ride's id, or a prefix of at least 4 characters that matches one ride.
        units: Units to show distance, speed and height in; the config's by default.

    Raises:
        typer.Exit: No ride matches, or the prefix matches several (code 2).
    """
    with library(ctx) as lib:
        view = ride_service.ride_view(lib.stores, ride)
        chosen = lib.units(units)
        zone = default_zone(lib.stores.catalog)
    print_ride(view, chosen, zone)


@app.command(help="List rides on the same route as a ride, or with a similar effort (--effort).")
def similar(
    ctx: typer.Context,
    ride: Annotated[str, typer.Argument(help="Ride id or a unique prefix (4+ characters).")],
    effort: Annotated[
        bool, typer.Option("--effort", help="Similar effort instead of the same route.")
    ] = False,
    limit: Annotated[int, typer.Option(min=1, max=50, help="How many rides to list.")] = 10,
    units: UnitsOption = None,
) -> None:
    """Print the rides most like one ride, by route or by effort.

    Args:
        ctx: Typer context holding the config path.
        ride: The ride's id, or a prefix of at least 4 characters that matches one ride.
        effort: Match by effort (``--effort``) rather than by route.
        limit: The most rides to list.
        units: Units to show distance in; the config's by default.

    Raises:
        typer.Exit: No ride matches, or the prefix matches several (code 2).
    """
    with library(ctx) as lib:
        matched = ride_service.similar(lib.stores, ride, "effort" if effort else "route", limit)
        chosen = lib.units(units)

    found, matches = matched.ride, matched.matches

    # Default names have the date and time already; a name set by hand gets the date added.
    title = found.display_name
    if found.meta.name:
        title += f" ({display.date(found.summary.local_start or found.summary.start)})"
    if effort:
        if not matches:
            out.print(f"No rides with a similar effort to {title}.")
            return
        section(f"Similar efforts to {title}")
        table = Table(box=None)
        for column in ("ID", "Date", "Time", "Distance", "NP", "TSS", "Similarity", "Name"):
            table.add_column(column, no_wrap=column != "Name")
        for match in matches:
            other = match.view.ride
            r = other.summary
            table.add_row(
                other.short_id,
                display.date(r.local_start or r.start),
                display.duration(r.moving_s),
                display.distance(r.distance_m, chosen),
                display.watts(r.np),
                tss_text(match.view.figures),
                f"{match.similarity}",
                other.display_name,
            )
        out.print(table)
        print_tss_notes(m.view.figures for m in matches)
        return

    if not matched.has_route:
        if found.metrics_version < METRICS_VERSION and found.summary.has_gps:
            out.print("This ride was imported before routes were recorded; run `fitlib recompute`.")
        else:
            out.print(f"{title} has no GPS positions, so it has no route to match.")
        return
    if not matches:
        out.print(f"No other rides share the route of {title}.")
        return
    section(f"Rides on the route of {title}")
    table = Table(box=None)
    for column in ("ID", "Date", "Time", "Distance", "Power", "Overlap", "Route", "Name"):
        table.add_column(column, no_wrap=column != "Name")
    for match in matches:
        other = match.view.ride
        r = other.summary
        table.add_row(
            other.short_id,
            display.date(r.local_start or r.start),
            display.duration(r.moving_s),
            display.distance(r.distance_m, chosen),
            display.watts(r.avg_power),
            f"{match.overlap or 0:.0%}",
            "same" if match.same_route else "partly",
            other.display_name,
        )
    out.print(table)
    out.print("Overlap: how much of this ride's route the other ride covered.")


@app.command(help=f"Compare {MIN_RIDES} to {MAX_RIDES} rides' figures side by side.")
def compare(
    ctx: typer.Context,
    rides: Annotated[
        list[str],
        typer.Argument(help="Ride ids or unique prefixes (4+ characters).", metavar="RIDE"),
    ],
    units: UnitsOption = None,
) -> None:
    """Print a table with one column per ride and one row per figure.

    Args:
        ctx: Typer context holding the config path.
        rides: The rides' ids, or prefixes of at least 4 characters.
        units: Units to show distance, speed and climbing in; the config's by default.

    Raises:
        typer.Exit: Too few or too many rides, the same ride twice, or a ride that can't be
            found (code 2).
    """
    with library(ctx) as lib:
        views = compared_rides(lib.stores, rides)
        chosen = lib.units(units)
    found = [v.ride for v in views]
    figures = [v.figures for v in views]

    rows = {
        "Name": [r.display_name for r in found],
        "Date": [display.date(r.summary.local_start or r.summary.start) for r in found],
        "Moving time": [display.duration(r.summary.moving_s) for r in found],
        "Distance": [display.distance(r.summary.distance_m, chosen) for r in found],
        "Climbing": [display.elevation(r.summary.ascent_m, chosen) for r in found],
        "Avg speed": [display.speed(r.summary.avg_speed_mps, chosen) for r in found],
        "Avg power": [display.watts(r.summary.avg_power) for r in found],
        "NP": [display.watts(r.summary.np) for r in found],
        "IF": [display.ratio(f.intensity_factor) for f in figures],
        "TSS": [tss_text(f) for f in figures],
        "Avg HR": [display.bpm(r.summary.avg_hr) for r in found],
        "Decoupling": [display.signed_percent(r.summary.decoupling_pct) for r in found],
        **{
            f"Best {minutes} min": [
                display.watts(best_at(r.summary.power_curve, minutes * 60)) for r in found
            ]
            for minutes in (1, 5, 20)
        },
    }
    table = Table(box=None)
    table.add_column("")
    for ride in found:
        table.add_column(ride.short_id, justify="right")
    for label, values in rows.items():
        table.add_row(label, *values)
    section("Compared rides")
    out.print(table)
    print_tss_notes(figures)


@app.command(
    help="Edit rides: name, notes, effort (RPE), bike and tags. RPE, bike and tags can be "
    "set on several rides at once."
)
def edit(
    ctx: typer.Context,
    rides: Annotated[list[str], typer.Argument(help="Ride ids or prefixes.", show_default=False)],
    name: Annotated[str | None, typer.Option(help="Name (one ride only).")] = None,
    clear_name: Annotated[bool, typer.Option("--clear-name", help="Use the default name.")] = False,
    note: Annotated[str | None, typer.Option(help="Notes, replacing any (one ride only).")] = None,
    clear_note: Annotated[bool, typer.Option("--clear-note", help="Remove the notes.")] = False,
    rpe: Annotated[
        int | None, typer.Option(min=1, max=10, help="Perceived effort, 1 (easy) to 10 (max).")
    ] = None,
    clear_rpe: Annotated[bool, typer.Option("--clear-rpe", help="Remove the effort.")] = False,
    bike: Annotated[str | None, typer.Option(help="Bike (name or a unique start of it).")] = None,
    clear_bike: Annotated[bool, typer.Option("--clear-bike", help="Remove the bike.")] = False,
    tag: Annotated[list[str] | None, typer.Option(help="Add a tag; repeat for more.")] = None,
    untag: Annotated[list[str] | None, typer.Option(help="Remove a tag; repeat for more.")] = None,
) -> None:
    """Change what the user added to one or more rides, then print each ride's metadata.

    Args:
        ctx: Typer context holding the config path.
        rides: Ride ids or prefixes.
        name: New name; only with a single ride.
        clear_name: Go back to the default name.
        note: New notes, replacing any; only with a single ride.
        clear_note: Remove the notes.
        rpe: New perceived effort, 1-10.
        clear_rpe: Remove the perceived effort.
        bike: New bike, by name or unique prefix.
        clear_bike: Remove the bike.
        tag: Tags to add.
        untag: Tags to remove.

    Raises:
        typer.Exit: Conflicting or missing options, ``--name``/``--note`` with several rides,
            an unknown ride or bike, or an invalid tag (code 2).
    """
    for value, clear, option in ((name, clear_name, "name"), (note, clear_note, "note"),
                                 (rpe, clear_rpe, "rpe"), (bike, clear_bike, "bike")):  # fmt: skip
        if value is not None and clear:
            raise fail(f"Give --{option} or --clear-{option}, not both.")
    if (name is not None or note is not None) and len(rides) > 1:
        raise fail("--name and --note can only be used with one ride.")
    add, remove = tags_from(tag), tags_from(untag)
    values = (name, note, rpe, bike)
    clears = (clear_name, clear_note, clear_rpe, clear_bike)
    if all(v is None for v in values) and not any(clears) and not add and not remove:
        raise fail("Nothing to change. See `fitlib edit --help`.")

    with library(ctx) as lib:
        catalog = lib.stores.catalog
        bike_id = find_bike(catalog, bike).id if bike is not None else None
        change = MetaEdit(
            name=None if clear_name else (KEEP if name is None else name),
            notes=None if clear_note else (KEEP if note is None else note),
            rpe=None if clear_rpe else (KEEP if rpe is None else rpe),
            bike_id=None if clear_bike else (KEEP if bike_id is None else bike_id),
            add_tags=add,
            remove_tags=remove,
        )
        updated = ride_service.edit_rides(lib.stores, rides, change)
        bikes = {b.id: b.name for b in catalog.list_bikes()}

    table = Table("ID", "Name", "Bike", "Effort", "Tags", box=None)
    for ride in updated:
        m = ride.meta
        table.add_row(
            ride.short_id,
            ride.display_name,
            bikes.get(m.bike_id or "", display.DASH),
            f"{m.rpe}/10" if m.rpe is not None else display.DASH,
            ", ".join(m.tags) or display.DASH,
        )
    out.print(f"Updated {len(updated)} ride(s).")
    out.print(table)


@app.command(
    help="Delete rides, with their streams and original files in the library. Your own copies "
    "of the files are kept; importing them again skips them unless --include-deleted."
)
def delete(
    ctx: typer.Context,
    rides: Annotated[list[str], typer.Argument(help="Ride ids or prefixes.", show_default=False)],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Don't ask first.")] = False,
) -> None:
    """List the rides, ask, and delete them.

    Args:
        ctx: Typer context holding the config path.
        rides: Ride ids or prefixes.
        yes: Skip the question.

    Raises:
        typer.Exit: A ride isn't found (code 2), or the user said no (code 1).
    """
    with library(ctx) as lib:
        s = lib.stores
        found = {r.id: r for r in (find_ride(s.catalog, ref) for ref in rides)}
        for ride in found.values():
            out.print(f"{ride.short_id}  {ride.display_name}")
        count = f"{len(found)} ride{'s' if len(found) != 1 else ''}"
        if not yes and not typer.confirm(
            f"Delete {count}? This can't be undone (your own copies of the files are kept).",
        ):
            out.print("Nothing deleted.")
            raise typer.Exit(1)
        ride_service.delete_rides(s, list(found))
    out.print(f"Deleted {count}.")


@app.command(help="List tags and how many rides have each.")
def tags(ctx: typer.Context) -> None:
    """Print every tag in use with its ride count.

    Args:
        ctx: Typer context holding the config path.
    """
    with library(ctx) as lib:
        counts = lib.stores.catalog.tag_counts()
    if not counts:
        out.print("No tags yet. Add some with `fitlib edit RIDE --tag NAME`.")
        return
    table = Table("Tag", "Rides", box=None)
    for tag_name, rides in counts:
        table.add_row(tag_name, str(rides))
    out.print(table)


@app.command(
    help="Recompute rides from their original files after fitlib's calculations change. "
    "FTP changes don't need this."
)
def recompute(
    ctx: typer.Context,
    rides: Annotated[
        list[str] | None,
        typer.Argument(help="Ride ids or prefixes. Default: rides with outdated figures."),
    ] = None,
    all_rides: Annotated[bool, typer.Option("--all", help="Recompute every ride.")] = False,
    workers: Annotated[
        int | None, typer.Option(min=1, help="Processes for decoding. Default: up to 4.")
    ] = None,
) -> None:
    """Recompute rides' figures from their archived original files.

    Args:
        ctx: Typer context holding the config path.
        rides: Ride ids or prefixes; by default every ride with outdated figures.
        all_rides: Recompute every ride (``--all``).
        workers: Number of decoding processes; up to 4 by default.

    Raises:
        typer.Exit: A ride reference doesn't match exactly one ride (code 2), or some rides
            couldn't be recomputed (code 1).
    """
    with library(ctx) as lib:
        s = lib.stores
        recomputer = Recomputer(s.catalog, s.blobs, s.streams, workers=workers)
        try:
            if rides:
                ids = [s.catalog.resolve_id(ref) for ref in rides]
            elif all_rides:
                ids = s.catalog.ride_ids()
            else:
                ids = recomputer.outdated()
        except RideNotFound as exc:
            raise fail(f"No ride matches {exc.args[0]!r}.") from None
        except AmbiguousRideId as exc:
            raise fail(str(exc)) from None
        if not ids:
            out.print("Every ride is up to date.")
            return
        with Progress(
            TextColumn("Recomputing"), BarColumn(), MofNCompleteColumn(), console=err,
            transient=True,
        ) as progress:  # fmt: skip
            task = progress.add_task("recompute", total=len(ids))
            report = recomputer.run(ids, on_progress=lambda _: progress.advance(task))

    out.print(f"Recomputed {len(report.updated)}, failed {len(report.failed)}.")
    if report.gone:
        gone = len(report.gone)
        out.print(
            f"{gone} {'ride was' if gone == 1 else 'rides were'} deleted meanwhile, so skipped."
        )
    for ride_id, reason in report.failed:
        out.print(f"  {ride_id[:8]}  {reason}")
    if report.failed:
        raise typer.Exit(EXIT_IMPORT_FAILURES)
