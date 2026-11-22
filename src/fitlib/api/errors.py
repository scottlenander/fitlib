"""Turning fitlib's errors into HTTP responses.

Bodies always have a ``detail`` message. Ambiguous references also list ``candidates``, so
the browser app can offer a choice.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fitlib.analysis.training import BadBirthYear
from fitlib.analysis.trends import BadRange
from fitlib.ingest.localtime import UnknownTimeZone
from fitlib.metadata import InvalidTag
from fitlib.store.interfaces import (
    AmbiguousBike,
    AmbiguousRideId,
    BikeNotFound,
    BlobNotFound,
    DuplicateBike,
    RideNotFound,
)
from fitlib.watcher import AlreadyWatched, BadWatchFolder, NotWatched

STATUS: dict[type[Exception], int] = {
    RideNotFound: 404,
    BikeNotFound: 404,
    BlobNotFound: 404,
    AmbiguousRideId: 409,
    AmbiguousBike: 409,
    DuplicateBike: 409,
    InvalidTag: 422,
    UnknownTimeZone: 422,
    BadRange: 422,
    BadBirthYear: 422,
    BadWatchFolder: 422,
    AlreadyWatched: 409,
    NotWatched: 404,
}


def _respond(request: Request, exc: Exception) -> JSONResponse:
    """Build the JSON response for one of the errors in ``STATUS``.

    Args:
        request: The request that failed (unused; required by Starlette).
        exc: The error.

    Returns:
        The error's status code, with ``detail`` and, for ambiguous references,
        ``candidates``.
    """
    body: dict[str, object] = {"detail": str(exc)}
    if isinstance(exc, AmbiguousRideId | AmbiguousBike):
        body["candidates"] = exc.candidates
    return JSONResponse(body, status_code=STATUS[type(exc)])


def install(app: FastAPI) -> None:
    """Register a handler for every error in ``STATUS``.

    Args:
        app: The FastAPI app.
    """
    for error in STATUS:
        app.add_exception_handler(error, _respond)
