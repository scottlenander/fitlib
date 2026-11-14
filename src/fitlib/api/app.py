"""Building the FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException

from fitlib import __version__
from fitlib.api import errors
from fitlib.api.routers import athlete, bikes, e2e, health, imports, rides, settings, tags
from fitlib.api.static import PLACEHOLDER_DIR, mount_app
from fitlib.config import Config


def create_app(
    config: Config,
    static_dir: Path | None = None,
    workers: int | None = None,
    e2e_fixtures: Path | None = None,
) -> FastAPI:
    """Build the app for one library.

    Args:
        config: Which library to serve, and its settings.
        static_dir: Folder with the browser app; a placeholder page by default.
        workers: Processes for decoding imports; up to 4 by default, 1 to decode in the
            server process.
        e2e_fixtures: Turns on e2e mode: the ``/e2e`` test shortcuts, importing fixtures
            from this folder. Only allowed for a library inside the system temp folder.

    Returns:
        The app, ready for uvicorn or a test client.

    Raises:
        UnsafeLibrary: e2e mode was asked for a library outside the system temp folder.
    """
    if e2e_fixtures is not None:
        e2e.check_library(config)
    app = FastAPI(title="fitlib", version=__version__)
    app.state.config = config
    app.state.workers = workers
    errors.install(app)

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(rides.router)
    api.include_router(tags.router)
    api.include_router(bikes.router)
    api.include_router(athlete.router)
    api.include_router(imports.router)
    api.include_router(settings.router)

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
    mount_app(app, static_dir or PLACEHOLDER_DIR)
    return app
