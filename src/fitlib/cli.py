"""The ``fitlib`` command line: rides, training, the athlete history, bikes and tags.

Command help shown by ``--help`` comes from each command's ``help=`` argument; the docstrings
are for developers.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from fitlib import display
from fitlib.analysis.bikes import backfill_bikes
from fitlib.analysis.training import Training, training
from fitlib.config import Config, ConfigError, load_config
from fitlib.importer import Importer, ImportReport
from fitlib.ingest.scanner import scan
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.metadata import InvalidTag, normalize_tag
from fitlib.metrics import load, zones
from fitlib.metrics.curves import best_at
from fitlib.models import (
    AthleteEntry,
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
    Filters,
    Ride,
    RideMeta,
    SortKey,
    Source,
    Units,
)
from fitlib.recompute import Recomputer
from fitlib.store.factory import Stores, open_stores
from fitlib.store.interfaces import (
    AmbiguousBike,
    AmbiguousRideId,
    BikeNotFound,
    CatalogStore,
    DuplicateBike,
    RideNotFound,
)

app = typer.Typer(
    name="fitlib",
    help="Store and analyse cycling .fit files from Zwift and Garmin.",
    no_args_is_help=True,
    add_completion=False,
)
athlete_app = typer.Typer(help="FTP, weight and max heart rate over time.", no_args_is_help=True)
app.add_typer(athlete_app, name="athlete")
bikes_app = typer.Typer(help="Bikes, and which bike rides get by default.", no_args_is_help=True)
app.add_typer(bikes_app, name="bikes")

out = Console()
err = Console(stderr=True)

EXIT_ERROR = 2  # bad input, unknown ride, config problem
EXIT_IMPORT_FAILURES = 1  # import or recompute ran but some files couldn't be read

# Best efforts shown by `show`, as (label, seconds).
SHOWN_EFFORTS = (("5 s", 5), ("1 min", 60), ("5 min", 300), ("20 min", 1200), ("60 min", 3600))

UnitsOption = Annotated[
    Units | None, typer.Option(help="Units for distance, speed, height and weight.")
]


def fail(message: str) -> typer.Exit:
    """Print an error and build the exit for it.

    Args:
        message: What went wrong, for the user.

    Returns:
        An exit with code ``EXIT_ERROR``, for the caller to raise.
    """
    err.print(f"[red]Error:[/red] {message}")
    return typer.Exit(EXIT_ERROR)


@app.callback(help="Store and analyse cycling .fit files from Zwift and Garmin.")
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(help="Config file. Default: $FITLIB_CONFIG or ~/.fitlib/config.toml."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log each file.")] = False,
) -> None:
    """Set up logging and remember the config file for the command that runs next.

    Args:
        ctx: Typer context; the config path is kept in ``ctx.obj``.
        config: Config file from ``--config``, if given.
        verbose: Log one line per file (``--verbose``).
    """
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    ctx.obj = config


@dataclass(frozen=True)
class Library:
    """An open library for one command.

    Attributes:
        config: The settings it was opened with.
        stores: Its stores.
    """

    config: Config
    stores: Stores

    def units(self, override: Units | None) -> Units:
        """Pick the units to show figures in.

        Args:
            override: Units from ``--units``, if given.

        Returns:
            ``override``, else the config's units.
        """
        return override or self.config.units


@contextmanager
def library(ctx: typer.Context) -> Generator[Library]:
    """Open the library for one command, and close it afterwards.

    Args:
        ctx: Typer context holding the config path from ``--config``.

    Yields:
        The config and the library's stores.

    Raises:
        typer.Exit: The config file is missing or invalid (exit code 2).
    """
    try:
        config = load_config(ctx.obj)
    except ConfigError as exc:
        raise fail(str(exc)) from None
    with open_stores(config) as opened:
        yield Library(config, opened)


def outdated_hint(catalog: CatalogStore) -> None:
    """Point out rides computed with older calculations, if there are any.

    Args:
        catalog: The library's catalog.
    """
    outdated = len(catalog.ride_ids(below_version=METRICS_VERSION))
    if outdated:
        err.print(
            f"[yellow]{outdated} ride(s) were computed with older calculations; "
            "run `fitlib recompute` to update them.[/yellow]"
        )


def find_ride(catalog: CatalogStore, ref: str) -> Ride:
    """Load a ride from an id or id prefix typed by the user.

    Args:
        catalog: The library's catalog.
        ref: A full id or a prefix of at least 4 characters.

    Returns:
        The ride.

    Raises:
        typer.Exit: No ride matches, or the prefix matches several (code 2).
    """
    try:
        return catalog.get_ride(catalog.resolve_id(ref))
    except RideNotFound:
        raise fail(f"No ride matches {ref!r}.") from None
    except AmbiguousRideId as exc:
        raise fail(f"{exc}: {', '.join(c[:8] for c in exc.candidates)}") from None


def find_bike(catalog: CatalogStore, ref: str) -> Bike:
    """Find a bike from a name or name prefix typed by the user.

    Args:
        catalog: The library's catalog.
        ref: A bike name (any case) or a unique start of one.

    Returns:
        The bike.

    Raises:
        typer.Exit: No bike matches (the error lists the bikes), or several do (code 2).
    """
    try:
        return catalog.resolve_bike(ref)
    except AmbiguousBike as exc:
        raise fail(str(exc)) from None
    except BikeNotFound:
        names = ", ".join(b.name for b in catalog.list_bikes()) or "none yet"
        raise fail(f"No bike matches {ref!r}. Bikes: {names}.") from None


def tags_from(raw: list[str] | None) -> tuple[str, ...]:
    """Normalize tags typed on the command line.

    Args:
        raw: The tags as typed, if any.

    Returns:
        The tags in stored form, without duplicates, in the order given.

    Raises:
        typer.Exit: A tag is empty, too long, or contains a comma (code 2).
    """
    try:
        return tuple(dict.fromkeys(normalize_tag(t) for t in raw or ()))
    except InvalidTag as exc:
        raise fail(str(exc)) from None


# -- import -----------------------------------------------------------------------------------


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
) -> None:
    """Import every .fit file under ``paths`` and print a report.

    Args:
        ctx: Typer context holding the config path.
        paths: Folders (searched recursively), .fit files and .zip archives.
        workers: Number of decoding processes; up to 4 by default.

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
            report = importer.run(paths, on_progress=lambda _: progress.advance(task))
        print_report(report)
        outdated_hint(s.catalog)

    if report.failed:
        raise typer.Exit(EXIT_IMPORT_FAILURES)


def print_report(report: ImportReport) -> None:
    """Print the counts from an import, then the skipped and failed files with reasons.

    Args:
        report: The import's outcome.
    """
    out.print(
        f"Imported {len(report.imported)}, already in library {len(report.duplicates)}, "
        f"skipped {len(report.skipped)}, failed {len(report.failed)}."
    )
    for title, rows in (("Skipped", report.skipped), ("Failed", report.failed)):
        if rows:
            table = Table(title=title, title_justify="left", show_header=False, box=None)
            for name, reason in rows:
                table.add_row(name, reason)
            out.print(table)


# -- list -------------------------------------------------------------------------------------


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
        units: Units to show distance in; the config's by default.
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
        catalog = lib.stores.catalog
        if bike is not None:
            filters = replace(filters, bike_id=find_bike(catalog, bike).id)
        page = catalog.search(filters, sort=sort, descending=not asc, offset=offset, limit=limit)
        history = catalog.athlete_history()
        loads = {ride.id: training(catalog, ride, history) for ride in page.items}
        chosen = lib.units(units)

    if not page.items:
        out.print("No rides found.")
        return
    # Figures never wrap or truncate; on a narrow terminal the name wraps instead.
    table = Table(box=None)
    for column in ("ID", "Date", "Time", "Distance", "Power", "HR", "TSS"):
        table.add_column(column, no_wrap=True)
    table.add_column("Name")
    estimated = False
    for ride in page.items:
        r = ride.summary
        t = loads[ride.id]
        marker = ""
        if t.ftp_estimated and t.tss is not None:
            marker, estimated = "*", True
        table.add_row(
            ride.short_id,
            display.date(r.local_start or r.start),
            display.duration(r.moving_s),
            display.distance(r.distance_m, chosen),
            display.watts(r.avg_power),
            display.bpm(r.avg_hr),
            display.tss(t.tss) + marker,
            ride.display_name,
        )
    out.print(table)
    shown_to = page.offset + len(page.items)
    out.print(f"Showing {page.offset + 1}–{shown_to} of {page.total}.")
    if estimated:
        out.print("* TSS from an estimated FTP (no FTP set for that date).")


# -- show -------------------------------------------------------------------------------------


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
        catalog = lib.stores.catalog
        found = find_ride(catalog, ride)
        figures = training(catalog, found)
        bike = catalog.get_bike(found.meta.bike_id) if found.meta.bike_id else None
        chosen = lib.units(units)
    print_ride(found, figures, chosen, bike)


def print_ride(ride: Ride, figures: Training, units: Units, bike: Bike | None = None) -> None:
    """Print a ride: name, when and where, main figures, training, zones, efforts and laps.

    Args:
        ride: The ride to print.
        figures: Its FTP-based figures.
        units: Units for distance, speed and height.
        bike: The ride's bike, if it has one.
    """
    r = ride.summary
    out.print(f"[bold]{ride.display_name}[/bold]  ({ride.short_id})")
    where = "indoor" if r.indoor else "outdoor"
    out.print(f"{display.start_time(r)} · {r.device or r.source.label} · {where}")
    extras = []
    if bike is not None:
        extras.append(f"Bike: {bike.name}")
    if ride.meta.rpe is not None:
        extras.append(f"Effort: {ride.meta.rpe}/10")
    if extras:
        out.print(" · ".join(extras))
    out.print()

    avg_speed, max_speed = (
        display.speed(r.avg_speed_mps, units),
        display.speed(r.max_speed_mps, units),
    )
    facts = Table(show_header=False, box=None)
    facts.add_row("Riding time", display.duration(r.moving_s))
    facts.add_row("Elapsed time", display.duration(r.elapsed_s))
    facts.add_row("Distance", display.distance(r.distance_m, units))
    facts.add_row("Climbing", display.elevation(r.ascent_m, units))
    facts.add_row("Speed", f"{avg_speed} avg, {max_speed} max")
    facts.add_row("Power", f"{display.watts(r.avg_power)} avg, {display.watts(r.max_power)} max")
    facts.add_row("Heart rate", f"{display.bpm(r.avg_hr)} avg, {display.bpm(r.max_hr)} max")
    facts.add_row("Cadence", display.rpm(r.avg_cadence))
    out.print(facts)

    if r.has_power:
        print_training(ride, figures)
    print_zones(figures)
    print_efforts(ride)
    print_laps(ride, units)

    if ride.meta.notes:
        out.print(f"\nNotes: {ride.meta.notes}")
    if ride.meta.tags:
        out.print(f"Tags: {', '.join(ride.meta.tags)}")
    out.print(f"\n[dim]Imported from {ride.source_name}[/dim]")


def section(title: str) -> None:
    """Print a blank line and a section title, on its own line so it never wraps into a table.

    Args:
        title: The section's title.
    """
    out.print()
    out.print(f"[bold]{title}[/bold]")


def print_training(ride: Ride, figures: Training) -> None:
    """Print the Training block: NP, IF, TSS, VI, work, W/kg and decoupling.

    Args:
        ride: The ride.
        figures: Its FTP-based figures.
    """
    r = ride.summary
    if figures.ftp is None:
        ftp_note = "no FTP set or estimable"
    elif figures.ftp_estimated:
        ftp_note = f"estimated FTP {display.watts(figures.ftp)}"
    else:
        ftp_note = f"FTP {display.watts(figures.ftp)}"
    table = Table(show_header=False, box=None)
    table.add_row("Normalized Power", display.watts(r.np))
    table.add_row("Intensity Factor", display.ratio(figures.intensity_factor))
    table.add_row("TSS", display.tss(figures.tss))
    table.add_row("Variability Index", display.ratio(r.vi))
    table.add_row("Work", display.kilojoules(r.kj))
    if figures.weight_kg is not None:
        table.add_row(
            "W/kg",
            f"{display.watts_per_kg(figures.watts_per_kg)} avg, "
            f"{display.watts_per_kg(figures.np_per_kg)} NP",
        )
    table.add_row("Decoupling", display.signed_percent(r.decoupling_pct))
    section(f"Training ({ftp_note})")
    out.print(table)


def print_zones(figures: Training) -> None:
    """Print time in each power and heart-rate zone, when they can be worked out.

    Args:
        figures: The ride's FTP-based figures.
    """
    for title, seconds, names in (
        ("Power zones", figures.power_zones, zones.POWER_ZONE_NAMES),
        ("Heart-rate zones", figures.hr_zones, zones.HR_ZONE_NAMES),
    ):
        if seconds is None:
            continue
        total = sum(seconds) or 1
        table = Table("Zone", "", "Time", "Share", box=None)
        for index, (name, secs) in enumerate(zip(names, seconds, strict=True), start=1):
            table.add_row(f"Z{index}", name, display.duration(secs), f"{secs / total:.0%}")
        section(title)
        out.print(table)


def print_efforts(ride: Ride) -> None:
    """Print the best power and heart rate over a few key durations.

    Args:
        ride: The ride.
    """
    r = ride.summary
    if not r.power_curve and not r.hr_curve:
        return
    table = Table("Best", "Power", "HR", box=None)
    for label, seconds in SHOWN_EFFORTS:
        power, hr = best_at(r.power_curve, seconds), best_at(r.hr_curve, seconds)
        if power is not None or hr is not None:
            table.add_row(label, display.watts(power), display.bpm(hr))
    section("Best efforts")
    out.print(table)


def print_laps(ride: Ride, units: Units) -> None:
    """Print the laps table for rides with more than one lap.

    Args:
        ride: The ride.
        units: Units for distance.
    """
    if len(ride.summary.laps) <= 1:
        return
    laps = Table("Lap", "Time", "Distance", "Power", "HR")
    for lap in ride.summary.laps:
        laps.add_row(
            str(lap.index + 1),
            display.duration(lap.elapsed_s),
            display.distance(lap.distance_m, units),
            display.watts(lap.avg_power),
            display.bpm(lap.avg_hr),
        )
    section("Laps")
    out.print(laps)


# -- edit -----------------------------------------------------------------------------------


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
        found = [find_ride(catalog, ref) for ref in rides]
        bike_id = find_bike(catalog, bike).id if bike is not None else None
        for ride in found:
            m = ride.meta
            tags = [t for t in m.tags if t not in remove] + [t for t in add if t not in m.tags]
            meta = RideMeta(
                name=None if clear_name else (name if name is not None else m.name),
                notes=None if clear_note else (note if note is not None else m.notes),
                rpe=None if clear_rpe else (rpe if rpe is not None else m.rpe),
                bike_id=None if clear_bike else (bike_id if bike_id is not None else m.bike_id),
                tags=tuple(tags),
            )
            catalog.update_meta(ride.id, meta)
        updated = [catalog.get_ride(r.id) for r in found]
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


# -- bikes ------------------------------------------------------------------------------------


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
    help="Give rides without a bike their default bike for their kind and date. "
    "Bikes already set are never changed.",
)
def bikes_backfill(
    ctx: typer.Context,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Only show what would change.")
    ] = False,
) -> None:
    """Apply the dated default bikes to rides that have no bike.

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
    for bike_id, count in sorted(assigned.items(), key=lambda kv: names.get(kv[0], "")):
        out.print(f"{verb} {names.get(bike_id, bike_id)} on {count} ride(s).")


# -- recompute --------------------------------------------------------------------------------


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
    for ride_id, reason in report.failed:
        out.print(f"  {ride_id[:8]}  {reason}")
    if report.failed:
        raise typer.Exit(EXIT_IMPORT_FAILURES)


# -- athlete ----------------------------------------------------------------------------------


@athlete_app.command(
    "set",
    help="Record FTP, weight and/or max heart rate from a date on. Values not given are "
    "unchanged. Weight is in your display units.",
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
    units: UnitsOption = None,
) -> None:
    """Add (or replace) the athlete history entry for a date.

    Args:
        ctx: Typer context holding the config path.
        from_date: The first day the values apply.
        ftp: FTP in watts, if changing.
        weight: Body weight in the display units, if changing.
        max_hr: Max heart rate in bpm, if changing.
        units: Units ``weight`` is given in; the config's by default.

    Raises:
        typer.Exit: No value was given (code 2).
    """
    if ftp is None and weight is None and max_hr is None:
        raise fail("Give at least one of --ftp, --weight or --max-hr.")
    with library(ctx) as lib:
        chosen = lib.units(units)
        entry = AthleteEntry(
            effective_from=from_date.date(),
            ftp=ftp,
            weight_kg=display.kg_from(weight, chosen) if weight is not None else None,
            max_hr=max_hr,
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
        history = lib.stores.catalog.athlete_history()
        chosen = lib.units(units)
    if not history:
        out.print("No athlete history yet. Add some with `fitlib athlete set`.")
        return
    table = Table("From", "FTP", "Weight", "Max HR", box=None)
    for entry in history:
        table.add_row(
            f"{entry.effective_from:%Y-%m-%d}",
            display.watts(entry.ftp),
            display.weight(entry.weight_kg, chosen),
            display.bpm(entry.max_hr),
        )
    out.print(table)
    now = load.values_on(history, date.today())
    out.print(
        f"\nToday: FTP {display.watts(now.ftp)}, weight {display.weight(now.weight_kg, chosen)}, "
        f"max HR {display.bpm(now.max_hr)}."
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
