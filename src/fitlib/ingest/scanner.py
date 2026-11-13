"""Find .fit files to import: in folders (recursively), given directly, or inside .zip archives."""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

FIT_SUFFIX = ".fit"
ZIP_SUFFIX = ".zip"


@dataclass(frozen=True)
class FitSource:
    """One .fit file to import. ``name`` is for display: ``ride.fit`` or ``export.zip:ride.fit``."""

    name: str
    read: Callable[[], bytes]


def _hidden(name: str) -> bool:
    return name.startswith(".") or "__MACOSX" in name


def _from_zip(path: Path) -> Iterator[FitSource]:
    with zipfile.ZipFile(path) as archive:
        members = sorted(
            info.filename
            for info in archive.infolist()
            if not info.is_dir()
            and info.filename.lower().endswith(FIT_SUFFIX)
            and not any(_hidden(part) for part in info.filename.split("/"))
        )

    for member in members:

        def read(member: str = member) -> bytes:
            with zipfile.ZipFile(path) as archive:
                return archive.read(member)

        yield FitSource(name=f"{path.name}:{member}", read=read)


def _from_file(path: Path) -> Iterator[FitSource]:
    suffix = path.suffix.lower()
    if suffix == FIT_SUFFIX:
        yield FitSource(name=path.name, read=path.read_bytes)
    elif suffix == ZIP_SUFFIX:
        yield from _from_zip(path)


def scan(paths: Iterable[Path]) -> Iterator[FitSource]:
    """Every .fit file under ``paths``, in a stable order (sorted by path within each argument).

    Hidden files and folders are skipped. Other file types are ignored. A path that doesn't
    exist raises ``FileNotFoundError`` before anything is yielded.
    """
    paths = list(paths)
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)

    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                relative = child.relative_to(path).parts
                if child.is_file() and not any(_hidden(part) for part in relative):
                    yield from _from_file(child)
        else:
            yield from _from_file(path)
