"""Importing files: what happened to each."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from fitlib.services.importing import ImportReport


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
        deleted: Files of rides you deleted, left out; import again with
            ``include_deleted`` to bring them back.
    """

    imported: list[FileOutcome]
    duplicates: list[FileOutcome]
    skipped: list[FileOutcome]
    failed: list[FileOutcome]
    deleted: list[FileOutcome] = []


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
        deleted=_outcomes(report.deleted),
    )


def _outcomes(rows: list[tuple[str, str]]) -> list[FileOutcome]:
    """Turn report rows into outcomes.

    Args:
        rows: ``(file name, detail)`` pairs.

    Returns:
        The same pairs as outcomes.
    """
    return [FileOutcome(file=name, detail=detail) for name, detail in rows]
