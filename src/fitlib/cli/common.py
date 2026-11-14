"""Shared pieces of the command line.

The Typer apps, consoles and exit codes, and the helpers that open the library and resolve
what the user typed.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from fitlib.config import Config, ConfigError, load_config
from fitlib.ingest.summarize import METRICS_VERSION
from fitlib.metadata import InvalidTag, normalize_tag
from fitlib.models import (
    Bike,
    Ride,
    Units,
)
from fitlib.store.factory import Stores, open_stores
from fitlib.store.interfaces import (
    AmbiguousBike,
    AmbiguousRideId,
    BikeNotFound,
    CatalogStore,
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
