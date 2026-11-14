"""Building the FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException

from fitlib import __version__
from fitlib.api.routers import health
from fitlib.api.static import PLACEHOLDER_DIR, mount_app
from fitlib.config import Config


def create_app(config: Config, static_dir: Path | None = None) -> FastAPI:
    """Build the app for one library.

    Args:
        config: Which library to serve, and its settings.
        static_dir: Folder with the browser app; a placeholder page by default.

    Returns:
        The app, ready for uvicorn or a test client.
    """
    app = FastAPI(title="fitlib", version=__version__)
    app.state.config = config

    api = APIRouter(prefix="/api")
    api.include_router(health.router)

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
