"""Building the FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException

from fitlib import __version__
from fitlib.api import errors
from fitlib.api.routers import athlete, bikes, health, imports, rides, settings, tags
from fitlib.api.static import PLACEHOLDER_DIR, mount_app
from fitlib.config import Config


def create_app(
    config: Config, static_dir: Path | None = None, workers: int | None = None
) -> FastAPI:
    """Build the app for one library.

    Args:
        config: Which library to serve, and its settings.
        static_dir: Folder with the browser app; a placeholder page by default.
        workers: Processes for decoding imports; up to 4 by default, 1 to decode in the
            server process.

    Returns:
        The app, ready for uvicorn or a test client.
    """
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
    mount_app(app, static_dir or PLACEHOLDER_DIR)
    return app
