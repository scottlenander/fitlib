"""The ``fitlib`` command line."""

from __future__ import annotations

import logging
from collections.abc import Iterator
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
    err.print(f"[red]Error:[/red] {message}")
    return typer.Exit(EXIT_ERROR)


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(help="Config file. Default: $FITLIB_CONFIG or ~/.fitlib/config.toml."),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Log each file.")] = False,
) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )
    ctx.obj = config


@contextmanager
def stores(ctx: typer.Context) -> Iterator[Stores]:
    try:
        config = load_config(ctx.obj)
    except ConfigError as exc:
        raise fail(str(exc)) from None
    with open_stores(config) as opened:
        yield opened


# -- import -----------------------------------------------------------------------------------


@app.command("import")
def import_(
    ctx: typer.Context,
    paths: Annotated[
        list[Path], typer.Argument(help="Folders, .fit files or .zip archives.", show_default=False)
    ],
    workers: Annotated[
        int | None, typer.Option(min=1, help="Processes for decoding. Default: up to 4.")
    ] = None,
) -> None:
    """Import rides. Files already in the library are skipped, so re-running is safe."""
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
    return value.replace(tzinfo=UTC) if value is not None else None


@app.command("list")
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
    """List rides, newest first. Dates are UTC."""
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


@app.command()
def show(
    ctx: typer.Context,
    ride: Annotated[str, typer.Argument(help="Ride id or a unique prefix (4+ characters).")],
) -> None:
    """Show one ride's summary."""
    with stores(ctx) as s:
        try:
            found = s.catalog.get_ride(s.catalog.resolve_id(ride))
        except RideNotFound:
            raise fail(f"No ride matches {ride!r}.") from None
        except AmbiguousRideId as exc:
            raise fail(f"{exc}: {', '.join(c[:8] for c in exc.candidates)}") from None
    print_ride(found)


def print_ride(ride: Ride) -> None:
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
