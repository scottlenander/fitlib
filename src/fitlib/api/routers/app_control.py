"""``POST /api/app/quit``: stop the server, for the browser app's Quit button.

Mounted only when the server was started with ``fitlib serve --allow-quit`` (as the
desktop launcher does), so a server run in a terminal isn't stopped from a browser tab.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from fitlib.api.schemas.app_control import Stopping

router = APIRouter(prefix="/app", tags=["app"])


@router.post("/quit", status_code=202)
def quit_app(request: Request, background: BackgroundTasks) -> Stopping:
    """Stop the server once this answer has been sent.

    The watcher and the background recompute stop cleanly as the server shuts down.

    Args:
        request: The current request, whose app holds how to stop the server.
        background: Runs the stop after the answer has gone out.

    Returns:
        That the server is stopping.

    Raises:
        HTTPException: 503 when the app isn't running under a server it can stop.
    """
    stop: Callable[[], None] | None = request.app.state.quit
    if stop is None:
        raise HTTPException(status_code=503, detail="This server can't be stopped from here.")
    background.add_task(stop)
    return Stopping()
