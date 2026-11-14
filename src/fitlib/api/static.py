"""Serving the browser app: real files where they exist, ``index.html`` for app routes.

The browser app routes on the client, so a deep link such as ``/rides/abc`` must load
``index.html``. Paths under ``/api`` and missing files under ``/assets`` stay 404s, so a
typo in an API call or a stale script reference never comes back as an HTML page.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

# Placeholder page until the React app is built (phase 3).
PLACEHOLDER_DIR = Path(__file__).parent / "static"
INDEX = "index.html"
NOT_PAGES = ("api", "assets", "e2e")


def mount_app(app: FastAPI, static_dir: Path) -> None:
    """Serve the browser app from ``static_dir``. Register this after every other route.

    Args:
        app: The FastAPI app.
        static_dir: Folder holding ``index.html`` and the app's other files.
    """
    root = static_dir.resolve()
    router = APIRouter(include_in_schema=False)

    @router.get("/{path:path}")
    def page(path: str) -> FileResponse:
        """Return the file at ``path`` if there is one, otherwise ``index.html``.

        Args:
            path: The requested path, without the leading slash.

        Returns:
            The file, or the app's ``index.html``.

        Raises:
            HTTPException: 404 for unknown ``/api`` and ``/e2e`` paths and missing assets.
        """
        file = (root / path).resolve()
        if path and file.is_relative_to(root) and file.is_file():
            return FileResponse(file)
        if path.split("/", 1)[0] in NOT_PAGES:
            raise HTTPException(status_code=404)
        return FileResponse(root / INDEX)

    app.include_router(router)
