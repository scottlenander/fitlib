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
from fitlib.metrics.zwift import UnknownWorld
from fitlib.services.errors import NotFound, ServiceError
from fitlib.store.interfaces import (
    AmbiguousBike,
    AmbiguousRideId,
    BikeNotFound,
    BlobNotFound,
    DuplicateBike,
    MissingRides,
    RideNotFound,
)
from fitlib.watcher import AlreadyWatched, BadWatchFolder, NotWatched

STATUS: dict[type[Exception], int] = {
    RideNotFound: 404,
    MissingRides: 404,
    BikeNotFound: 404,
    BlobNotFound: 404,
    AmbiguousRideId: 409,
    AmbiguousBike: 409,
    DuplicateBike: 409,
    InvalidTag: 422,
    UnknownTimeZone: 422,
    BadRange: 422,
    BadBirthYear: 422,
    UnknownWorld: 422,
    ServiceError: 422,
    NotFound: 404,
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
        The error's status code, with ``detail``; for ambiguous references, ``candidates``;
        for several rides asked for at once, ``missing`` (those not in the library).
    """
    body: dict[str, object] = {"detail": str(exc)}
    if isinstance(exc, AmbiguousRideId | AmbiguousBike):
        body["candidates"] = exc.candidates
    if isinstance(exc, MissingRides):
        body["missing"] = exc.refs
    # The closest class listed: services' errors are listed by their base class.
    status = next(STATUS[c] for c in type(exc).__mro__ if c in STATUS)
    return JSONResponse(body, status_code=status)


def install(app: FastAPI) -> None:
    """Register a handler for every error in ``STATUS``.

    Args:
        app: The FastAPI app.
    """
    for error in STATUS:
        app.add_exception_handler(error, _respond)
