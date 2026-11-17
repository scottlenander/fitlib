"""The ``fitlib timezone`` command: the library's default time zone."""

from __future__ import annotations

from typing import Annotated

import typer

from fitlib.analysis.timezone import default_zone, set_default_zone
from fitlib.cli.common import app, fail, library, out
from fitlib.ingest.localtime import UnknownTimeZone


@app.command(
    help="Show or set the default time zone, for rides whose files don't say where they were "
    "ridden (e.g. Zwift files that were renamed). Rides using it are updated at once."
)
def timezone(
    ctx: typer.Context,
    zone: Annotated[
        str | None,
        typer.Argument(help="An IANA time zone, e.g. America/New_York.", metavar="ZONE"),
    ] = None,
    clear: Annotated[
        bool, typer.Option("--clear", help="Remove the default (those rides show UTC).")
    ] = False,
) -> None:
    """Show the default time zone, or set or clear it.

    Args:
        ctx: Typer context holding the config path.
        zone: The new default, if setting it.
        clear: Remove the default.

    Raises:
        typer.Exit: Both a zone and ``--clear``, or an unknown zone (code 2).
    """
    if zone and clear:
        raise fail("Give a time zone or --clear, not both.")
    with library(ctx) as lib:
        catalog = lib.stores.catalog
        if zone is None and not clear:
            current = default_zone(catalog)
            out.print(f"Default time zone: {current or 'none (UTC)'}")
            return
        try:
            change = set_default_zone(catalog, None if clear else zone)
        except UnknownTimeZone as exc:
            raise fail(str(exc)) from exc
    rides = "ride" if change.updated == 1 else "rides"
    out.print(
        f"Default time zone: {change.zone or 'none (UTC)'}. Updated {change.updated} {rides}."
    )
    if change.bikes_to_check:
        out.print(
            f"{change.bikes_to_check} of them moved to another day; run "
            "`fitlib bikes backfill` to give them that day's default bike."
        )
