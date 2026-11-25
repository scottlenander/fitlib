"""``POST /api/imports``: import uploaded .fit files and .zip archives.

Uploads are written to a temporary folder and imported like ``fitlib import``: duplicates
are recognised by hash, overlapping recordings and non-rides are skipped, and one bad file
never stops the rest. The request returns when the import is done.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile

from fitlib.api.deps import StoresDep
from fitlib.api.schemas.imports import ImportResult, import_result
from fitlib.ingest.scanner import FIT_SUFFIX, ZIP_SUFFIX
from fitlib.services.importing import Importer

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("")
def import_files(
    request: Request,
    stores: StoresDep,
    files: Annotated[list[UploadFile], File(description=".fit files and .zip archives.")],
    include_deleted: Annotated[
        bool, Query(description="Also import rides you deleted (skipped otherwise).")
    ] = False,
) -> ImportResult:
    """Import uploaded files.

    Args:
        request: The request (for the app's worker setting).
        stores: The library's stores.
        files: The uploads.
        include_deleted: Import files of deleted rides too.

    Returns:
        What happened to each file.
    """
    rejected: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="fitlib-upload-") as tmp:
        paths: list[Path] = []
        for index, upload in enumerate(files):
            # Only the base name is kept, so a crafted name can't write outside the folder.
            # Each file gets its own folder so two uploads with the same name both import.
            name = Path(upload.filename or "upload").name
            if Path(name).suffix.lower() not in (FIT_SUFFIX, ZIP_SUFFIX):
                rejected.append((name, "not a .fit or .zip file"))
                continue
            folder = Path(tmp) / str(index)
            folder.mkdir()
            with (folder / name).open("wb") as out:
                shutil.copyfileobj(upload.file, out)
            paths.append(folder / name)
        importer = Importer(
            stores.catalog, stores.blobs, stores.streams, workers=request.app.state.workers
        )
        report = importer.run(paths, include_deleted=include_deleted)
    return import_result(report, rejected)
