"""``POST /api/imports``: import uploaded .fit files and .zip archives.

Uploads are written to a temporary folder and imported like ``fitlib import``: duplicates
are recognised by hash, overlapping recordings and non-rides are skipped, and one bad file
never stops the rest. The request returns when the import is done.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from pydantic import BaseModel

from fitlib.api.deps import StoresDep
from fitlib.importer import Importer, ImportReport
from fitlib.ingest.scanner import FIT_SUFFIX, ZIP_SUFFIX

router = APIRouter(prefix="/imports", tags=["imports"])


class FileOutcome(BaseModel):
    """What happened to one file.

    Attributes:
        file: The file's name; ``<zip>:<member>`` for files inside a zip.
        detail: The new or existing ride's id, or why the file was skipped or failed.
    """

    file: str
    detail: str


class ImportResult(BaseModel):
    """What an import did with every file.

    Attributes:
        imported: Files added to the library; detail is the new ride's id.
        duplicates: Files already in the library; detail says which ride or file.
        skipped: Files left out on purpose: not a ride, or overlapping a ride already there.
        failed: Files that couldn't be read, or weren't .fit or .zip files.
    """

    imported: list[FileOutcome]
    duplicates: list[FileOutcome]
    skipped: list[FileOutcome]
    failed: list[FileOutcome]


def import_result(report: ImportReport, rejected: Sequence[tuple[str, str]] = ()) -> ImportResult:
    """Build the API's view of an import report.

    Args:
        report: What the importer did.
        rejected: Uploads refused before importing, as ``(file name, reason)``.

    Returns:
        The outcome of every file; refused uploads count as failed.
    """
    return ImportResult(
        imported=_outcomes(report.imported),
        duplicates=_outcomes(report.duplicates),
        skipped=_outcomes(report.skipped),
        failed=_outcomes([*report.failed, *rejected]),
    )


def _outcomes(rows: list[tuple[str, str]]) -> list[FileOutcome]:
    """Turn report rows into outcomes.

    Args:
        rows: ``(file name, detail)`` pairs.

    Returns:
        The same pairs as outcomes.
    """
    return [FileOutcome(file=name, detail=detail) for name, detail in rows]


@router.post("")
def import_files(
    request: Request,
    stores: StoresDep,
    files: Annotated[list[UploadFile], File(description=".fit files and .zip archives.")],
) -> ImportResult:
    """Import uploaded files.

    Args:
        request: The request (for the app's worker setting).
        stores: The library's stores.
        files: The uploads.

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
        report = importer.run(paths)
    return import_result(report, rejected)
