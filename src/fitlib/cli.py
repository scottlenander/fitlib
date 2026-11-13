"""The ``fitlib`` command line: ``import``, ``list`` and ``show``.

Command help shown by ``--help`` comes from each command's ``help=`` argument; the docstrings
are for developers.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn
from rich.table import Table

from fitlib import display
from fitlib.config import ConfigError, load_config
from fitlib.importer import Importer, ImportReport
from fitlib.ingest.scanner import scan
from fitlib.models import Filters, Ride, SortKey, Source
from fitlib.store.factory import Stores, open_stores
from fitlib.store.interfaces import AmbiguousRideId, RideNotFound

app = typer.Typer(
    name="fitlib",
    help="Store and analyse cycling .fit files from Zwift and Garmin.",
    no_args_is_help=True,
    add_completion=False,
)
out = Console()
err = Console(stderr=True)

EXIT_ERROR = 2  # bad input, unknown ride, config problem
EXIT_IMPORT_FAILURES = 1  # import ran but some files couldn't be read


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


@contextmanager
def stores(ctx: typer.Context) -> Generator[Stores]:
    """Open the library's stores for one command, and close them afterwards.

    Args:
        ctx: Typer context holding the config path from ``--config``.

    Yields:
        The catalog, blob and stream stores.

    Raises:
        typer.Exit: The config file is missing or invalid (exit code 2).
    """
    try:
        config = load_config(ctx.obj)
    except ConfigError as exc:
        raise fail(str(exc)) from None
    with open_stores(config) as opened:
        yield opened


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

    with stores(ctx) as s:
        importer = Importer(s.catalog, s.blobs, s.streams, workers=workers)
        with Progress(
            TextColumn("Importing"), BarColumn(), MofNCompleteColumn(), console=err,
            transient=True,
        ) as progress:  # fmt: skip
            task = progress.add_task("import", total=total)
            report = importer.run(paths, on_progress=lambda _: progress.advance(task))

    print_report(report)
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
    """
    filters = Filters(
        text=text,
        since=_date(since),
        until=_date(until),
        source=source,
        indoor=indoor,
        min_duration_s=min_minutes * 60 if min_minutes is not None else None,
        max_duration_s=max_minutes * 60 if max_minutes is not None else None,
    )
    with stores(ctx) as s:
        page = s.catalog.search(filters, sort=sort, descending=not asc, offset=offset, limit=limit)

    if not page.items:
        out.print("No rides found.")
        return
    # Figures never wrap or truncate; on a narrow terminal the name wraps instead.
    table = Table(box=None)
    for column in ("ID", "Date", "Time", "Distance", "Power", "HR"):
        table.add_column(column, no_wrap=True)
    table.add_column("Name")
    for ride in page.items:
        r = ride.summary
        table.add_row(
            ride.short_id,
            display.date(r.local_start or r.start),
            display.duration(r.moving_s),
            display.km(r.distance_m),
            display.watts(r.avg_power),
            display.bpm(r.avg_hr),
            ride.display_name,
        )
    out.print(table)
    shown_to = page.offset + len(page.items)
    out.print(f"Showing {page.offset + 1}–{shown_to} of {page.total}.")


# -- show -------------------------------------------------------------------------------------


@app.command(help="Show one ride's summary.")
def show(
    ctx: typer.Context,
    ride: Annotated[str, typer.Argument(help="Ride id or a unique prefix (4+ characters).")],
) -> None:
    """Print one ride's summary, found by id or id prefix.

    Args:
        ctx: Typer context holding the config path.
        ride: The ride's id, or a prefix of at least 4 characters that matches one ride.

    Raises:
        typer.Exit: No ride matches, or the prefix matches several (code 2).
    """
    with stores(ctx) as s:
        try:
            found = s.catalog.get_ride(s.catalog.resolve_id(ride))
        except RideNotFound:
            raise fail(f"No ride matches {ride!r}.") from None
        except AmbiguousRideId as exc:
            raise fail(f"{exc}: {', '.join(c[:8] for c in exc.candidates)}") from None
    print_ride(found)


def print_ride(ride: Ride) -> None:
    """Print a ride's name, when and where, main figures, laps, notes and tags.

    Args:
        ride: The ride to print.
    """
    r = ride.summary
    out.print(f"[bold]{ride.display_name}[/bold]  ({ride.short_id})")
    where = "indoor" if r.indoor else "outdoor"
    out.print(f"{display.start_time(r)} · {r.device or r.source.label} · {where}")
    out.print()

    facts = Table(show_header=False, box=None)
    facts.add_row("Riding time", display.duration(r.moving_s))
    facts.add_row("Elapsed time", display.duration(r.elapsed_s))
    facts.add_row("Distance", display.km(r.distance_m))
    facts.add_row("Climbing", display.metres(r.ascent_m))
    facts.add_row(
        "Speed", f"{display.kmh(r.avg_speed_mps)} avg, {display.kmh(r.max_speed_mps)} max"
    )
    facts.add_row("Power", f"{display.watts(r.avg_power)} avg, {display.watts(r.max_power)} max")
    facts.add_row("Heart rate", f"{display.bpm(r.avg_hr)} avg, {display.bpm(r.max_hr)} max")
    facts.add_row("Cadence", display.rpm(r.avg_cadence))
    out.print(facts)

    if len(r.laps) > 1:
        laps = Table("Lap", "Time", "Distance", "Power", "HR", title="Laps", title_justify="left")
        for lap in r.laps:
            laps.add_row(
                str(lap.index + 1),
                display.duration(lap.elapsed_s),
                display.km(lap.distance_m),
                display.watts(lap.avg_power),
                display.bpm(lap.avg_hr),
            )
        out.print(laps)

    if ride.meta.notes:
        out.print(f"\nNotes: {ride.meta.notes}")
    if ride.meta.tags:
        out.print(f"Tags: {', '.join(ride.meta.tags)}")
    out.print(f"\n[dim]Imported from {ride.source_name}[/dim]")
