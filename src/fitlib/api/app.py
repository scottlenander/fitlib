"""Building the FastAPI app."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException

from fitlib import __version__
from fitlib.api import errors
from fitlib.api.routers import (
    athlete,
    bikes,
    compare,
    e2e,
    health,
    imports,
    rides,
    settings,
    tags,
    trends,
)
from fitlib.api.routers import watch as watch_routes
from fitlib.api.static import default_static_dir, mount_app
from fitlib.config import Config
from fitlib.store.factory import open_stores
from fitlib.watcher import Watcher


def create_app(
    config: Config,
    static_dir: Path | None = None,
    workers: int | None = None,
    e2e_fixtures: Path | None = None,
    watch: bool = False,
    watcher: Watcher | None = None,
) -> FastAPI:
    """Build the app for one library.

    Args:
        config: Which library to serve, and its settings.
        static_dir: Folder with the browser app; by default the built app, or a
            placeholder page if it hasn't been built.
        workers: Processes for decoding imports; up to 4 by default, 1 to decode in the
            server process.
        e2e_fixtures: Turns on e2e mode: the ``/e2e`` test shortcuts, importing fixtures
            from this folder. Only allowed for a library inside the system temp folder.
            Watched folders must then be inside the temp folder too.
        watch: Import new rides from the watched folders while the app runs.
        watcher: The watcher to run instead of a new one (for tests); implies ``watch``.

    Returns:
        The app, ready for uvicorn or a test client.

    Raises:
        UnsafeLibrary: e2e mode was asked for a library outside the system temp folder.
    """
    if e2e_fixtures is not None:
        e2e.check_library(config)
    if watcher is None and watch:
        watcher = Watcher(partial(open_stores, config))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Run the watcher, if any, while the app serves."""
        if watcher is not None:
            watcher.start()
        try:
            yield
        finally:
            if watcher is not None:
                watcher.stop()

    app = FastAPI(title="fitlib", version=__version__, lifespan=lifespan)
    app.state.config = config
    app.state.watcher = watcher
    app.state.watch_root = (
        Path(tempfile.gettempdir()).resolve() if e2e_fixtures is not None else None
    )
    app.state.workers = workers
    errors.install(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(rides.router)
    api.include_router(compare.router)
    api.include_router(tags.router)
    api.include_router(bikes.router)
    api.include_router(athlete.router)
    api.include_router(imports.router)
    api.include_router(settings.router)
    api.include_router(trends.router)
    api.include_router(watch_routes.router)

    @api.api_route(
        "/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False
    )
    def unknown(path: str) -> None:
        """Answer any unknown ``/api`` path with a JSON 404, whatever the method.

        Args:
            path: The unknown path.

        Raises:
            HTTPException: Always, 404.
        """
        raise HTTPException(status_code=404)

    app.include_router(api)
    if e2e_fixtures is not None:
        app.include_router(e2e.make_router(e2e_fixtures))
    mount_app(app, static_dir or default_static_dir())
    return app
