"""``fitlib serve``: run the web app and API on this computer."""

from __future__ import annotations

import os
import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from fitlib.api import create_app
from fitlib.api.routers.e2e import UnsafeLibrary
from fitlib.api.security import LOOPBACK_HOSTS
from fitlib.cli.common import app, err, fail
from fitlib.config import ConfigError, load_config

LOOPBACK = ("127.0.0.1", "localhost", "::1")
E2E_ENV = "FITLIB_E2E"
E2E_FIXTURES_ENV = "FITLIB_E2E_FIXTURES"
OPEN_DELAY_S = 1.0


@app.command(help="Run the fitlib web app on this computer.")
def serve(
    ctx: typer.Context,
    host: Annotated[
        str, typer.Option(help="Address to listen on. The app has no login: keep it local.")
    ] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="Port to listen on.")] = 8000,
    open_browser: Annotated[
        bool, typer.Option("--open", help="Open the app in a browser once it starts.")
    ] = False,
    watch: Annotated[
        bool,
        typer.Option(
            "--watch/--no-watch",
            help="Import new rides from the watched folders (fitlib watch add) while serving.",
        ),
    ] = True,
) -> None:
    """Serve the API and browser app until stopped.

    Setting ``FITLIB_E2E=1`` turns on e2e mode for the browser tests: the ``/e2e``
    shortcuts, importing fixtures from ``$FITLIB_E2E_FIXTURES``. It only runs over a
    library inside the system temp folder.

    Args:
        ctx: Typer context holding the config path.
        host: Address to listen on.
        port: Port to listen on.
        open_browser: Open the app in the default browser (``--open``).
        watch: Watch the library's watched folders while serving (``--no-watch`` to not).

    Raises:
        typer.Exit: The config is invalid, or e2e mode lacks its fixtures folder or was
            pointed at a library outside the temp folder (code 2).
    """
    try:
        config = load_config(ctx.obj)
    except ConfigError as exc:
        raise fail(str(exc)) from None

    fixtures = None
    if os.environ.get(E2E_ENV) == "1":
        raw = os.environ.get(E2E_FIXTURES_ENV)
        if not raw or not Path(raw).is_dir():
            raise fail(f"{E2E_ENV}=1 needs {E2E_FIXTURES_ENV} set to the fixtures folder.")
        fixtures = Path(raw)
    try:
        web = create_app(
            config,
            e2e_fixtures=fixtures,
            watch=watch,
            allowed_hosts=None if host not in LOOPBACK else LOOPBACK_HOSTS,
        )
    except UnsafeLibrary as exc:
        raise fail(str(exc)) from None

    if host not in LOOPBACK:
        err.print(
            f"[yellow]Listening on {host}: anyone who can reach this address can read and "
            "change your library.[/yellow]"
        )
    url = f"http://{'localhost' if host in LOOPBACK else host}:{port}/"
    err.print(f"fitlib is serving {config.library} at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(OPEN_DELAY_S, webbrowser.open, args=[url]).start()
    uvicorn.run(web, host=host, port=port)
