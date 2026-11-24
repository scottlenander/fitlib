"""Test-only shortcuts for the browser tests, mounted at ``/e2e`` in e2e mode only.

They put the library into a known state quickly: wipe it and import the fixture rides,
undo a ride's edits, delete a ride, or import one more fixture. Every shortcut also has a real path
through the app, which the browser tests cover separately.

Because ``reset`` deletes the library, e2e mode refuses any library outside the system
temp folder, so it can never touch a real one.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

from fitlib.api.deps import ConfigDep, StoresDep
from fitlib.api.routers.imports import ImportResult, import_result
from fitlib.config import Config
from fitlib.metadata import default_bike
from fitlib.models import RideMeta
from fitlib.services.importing import Importer
from fitlib.services.rides import delete_rides, find_ride
from fitlib.store.factory import open_stores


class UnsafeLibrary(Exception):
    """E2E mode was asked to serve a library outside the system temp folder."""


def check_library(config: Config) -> None:
    """Make sure a library is safe to wipe.

    Args:
        config: The library e2e mode would serve.

    Raises:
        UnsafeLibrary: The library isn't inside the system temp folder.
    """
    temp = Path(tempfile.gettempdir()).resolve()
    library = config.library.resolve()
    if library == temp or not library.is_relative_to(temp):
        raise UnsafeLibrary(
            f"e2e mode only serves a library inside {temp}, so a reset can't delete real "
            f"rides; got {library}"
        )


def _ride_ids(config: Config) -> dict[str, str]:
    """Map each ride's source file name to its id.

    Args:
        config: The library.

    Returns:
        Ride id by file name (``<zip>:<member>`` for zipped files).
    """
    with open_stores(config) as stores:
        catalog = stores.catalog
        rides = catalog.search(limit=max(1, catalog.count())).items
    return {ride.source_name: ride.id for ride in rides}


def make_router(fixtures: Path) -> APIRouter:
    """Build the ``/e2e`` routes.

    Args:
        fixtures: Folder of fixture .fit and .zip files to import.

    Returns:
        The router.
    """
    router = APIRouter(prefix="/e2e", tags=["e2e"], include_in_schema=False)

    @router.get("/rides")
    def rides(config: ConfigDep) -> dict[str, str]:
        """List the library's rides by source file name, for tests to look up ids.

        Args:
            config: The app's config.

        Returns:
            Ride id by file name.
        """
        return _ride_ids(config)

    @router.post("/reset")
    def reset(request: Request, config: ConfigDep) -> dict[str, str]:
        """Delete the library and import every fixture into a fresh one.

        Args:
            request: The request (for the app's worker setting).
            config: The app's config.

        Returns:
            The new ride ids by file name.
        """
        shutil.rmtree(config.library, ignore_errors=True)
        with open_stores(config) as stores:
            Importer(
                stores.catalog, stores.blobs, stores.streams, workers=request.app.state.workers
            ).run([fixtures])
        return _ride_ids(config)

    @router.post("/rides/{ref}/reset-meta", status_code=204)
    def reset_meta(stores: StoresDep, ref: str) -> Response:
        """Undo every edit to a ride, leaving it as a fresh import would.

        Args:
            stores: The library's stores.
            ref: The ride's id or a unique prefix.

        Returns:
            An empty response.
        """
        ride = find_ride(stores.catalog, ref)
        bike_id = default_bike(stores.catalog.bike_defaults(), ride.summary)
        stores.catalog.update_meta(ride.id, RideMeta(bike_id=bike_id, bike_from_default=True))
        return Response(status_code=204)

    @router.post("/rides/{ref}/delete", status_code=204)
    def delete_ride(stores: StoresDep, ref: str) -> Response:
        """Delete a ride with its stream and original file, so it can be imported again.

        Unlike deleting in the app, the file isn't remembered as deleted: set-up wants the
        ride importable again as if it were new.

        Args:
            stores: The library's stores.
            ref: The ride's id or a unique prefix.

        Returns:
            An empty response.
        """
        ride_id = find_ride(stores.catalog, ref).id
        delete_rides(stores, [ride_id], remember=False)
        return Response(status_code=204)

    @router.post("/import/{name}")
    def import_fixture(request: Request, stores: StoresDep, name: str) -> ImportResult:
        """Import one fixture file.

        Args:
            request: The request (for the app's worker setting).
            stores: The library's stores.
            name: The fixture's file name.

        Returns:
            What the import did.

        Raises:
            HTTPException: 404 if there's no such fixture file.
        """
        path = fixtures / name
        if Path(name).name != name or not path.is_file():
            raise HTTPException(status_code=404, detail=f"No fixture called {name!r}")
        importer = Importer(
            stores.catalog, stores.blobs, stores.streams, workers=request.app.state.workers
        )
        return import_result(importer.run([path]))

    return router
