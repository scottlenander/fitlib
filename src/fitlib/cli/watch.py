"""The ``fitlib watch`` commands: folders whose new rides ``fitlib serve`` imports."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from fitlib.cli.common import app, fail, library, out
from fitlib.cli.output import print_report, section
from fitlib.models import WatchOutcome
from fitlib.services.importing import ImportReport
from fitlib.services.watching import BadWatchFolder, check_folder, scan, watch_folder

watch_app = typer.Typer(
    help="Folders whose new rides are imported while `fitlib serve` runs.",
    no_args_is_help=True,
)
app.add_typer(watch_app, name="watch")

FolderArgument = Annotated[
    str, typer.Argument(help="The folder's full path, e.g. ~/Documents/Zwift/Activities.")
]


@watch_app.command("add", help="Watch a folder: `fitlib serve` imports new rides from it.")
def watch_add(ctx: typer.Context, folder: FolderArgument) -> None:
    """Add a watched folder.

    Args:
        ctx: Typer context holding the config path.
        folder: The folder; ``~`` is expanded.

    Raises:
        typer.Exit: The folder can't be watched, or already is (code 2).
    """
    with library(ctx) as lib:
        try:
            path = check_folder(folder, lib.config.library)
        except BadWatchFolder as exc:
            raise fail(str(exc)) from exc
        if not lib.stores.catalog.add_watch_folder(watch_folder(path)):
            raise fail(f"{path} is already watched.")
    out.print(f"Watching {path}.")
    out.print(
        "A running `fitlib serve` picks it up within 30 seconds and imports what's in it; "
        "`fitlib watch scan` imports it now."
    )


@watch_app.command("remove", help="Stop watching a folder. Its rides stay in the library.")
def watch_remove(ctx: typer.Context, folder: FolderArgument) -> None:
    """Remove a watched folder.

    Args:
        ctx: Typer context holding the config path.
        folder: The folder, as listed (or as typed when it was added).

    Raises:
        typer.Exit: The folder isn't watched (code 2).
    """
    expanded = Path(folder).expanduser()
    tries = [folder, str(expanded)]
    if expanded.exists():
        tries.append(str(expanded.resolve()))
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        if not any(catalog.remove_watch_folder(path) for path in dict.fromkeys(tries)):
            raise fail(f"{folder} isn't a watched folder. `fitlib watch list` shows them.")
    out.print(f"No longer watching {folder}.")


@watch_app.command("list", help="List the watched folders and the latest files found in them.")
def watch_list(ctx: typer.Context) -> None:
    """Print the watched folders and the files found in them lately.

    Args:
        ctx: Typer context holding the config path.
    """
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        folders = catalog.watch_folders()
        counts = catalog.watched_file_counts()
        recent = catalog.recent_watched_files()
    if not folders:
        out.print("No watched folders. Add one with `fitlib watch add FOLDER`.")
        return
    section("Watched folders")
    table = Table("Folder", "Found", "Files", box=None)
    for folder in folders:
        found = "yes" if Path(folder.path).is_dir() else "missing"
        table.add_row(folder.path, found, str(counts.get(folder.path, 0)))
    out.print(table)
    if recent:
        section("Latest files")
        files = Table("When (UTC)", "File", "Outcome", "Ride", "Detail", box=None)
        for f in recent:
            files.add_row(
                f"{f.seen_at:%Y-%m-%d %H:%M}",
                Path(f.path).name,
                f.outcome.value,
                f.ride_id[:8] if f.ride_id else "",
                f.detail or "",
            )
        out.print(files)


@watch_app.command("scan", help="Import new rides from the watched folders now.")
def watch_scan(ctx: typer.Context) -> None:
    """Import every new or changed file in the watched folders.

    Args:
        ctx: Typer context holding the config path.
    """
    with library(ctx) as lib:
        folders = [f.path for f in lib.stores.catalog.watch_folders()]
        if not folders:
            out.print("No watched folders. Add one with `fitlib watch add FOLDER`.")
            return
        result = scan(lib.stores, folders)
    report = ImportReport()
    lists = {
        WatchOutcome.IMPORTED: report.imported,
        WatchOutcome.DUPLICATE: report.duplicates,
        WatchOutcome.SKIPPED: report.skipped,
        WatchOutcome.FAILED: report.failed,
    }
    for f in result.files:
        lists[f.outcome].append((Path(f.path).name, f.detail or f.ride_id or ""))
    if not result.files:
        out.print("Nothing new in the watched folders.")
    else:
        print_report(report)
    if result.still_writing:
        files = "file is" if result.still_writing == 1 else "files are"
        out.print(f"{result.still_writing} {files} still being written; scan again shortly.")
