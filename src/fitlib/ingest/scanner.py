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
    """One .fit file to import, read only when needed.

    Attributes:
        name: For display: ``ride.fit``, or ``export.zip:ride.fit`` for a zip member.
        read: Returns the file's bytes.
    """

    name: str
    read: Callable[[], bytes]


def _hidden(name: str) -> bool:
    """Whether a file or folder name should be skipped.

    Args:
        name: One path component.

    Returns:
        ``True`` for dot-files and macOS's ``__MACOSX`` zip folders.
    """
    return name.startswith(".") or "__MACOSX" in name


def _from_zip(path: Path) -> Iterator[FitSource]:
    """The .fit files inside a zip archive, sorted by member name.

    Args:
        path: The .zip file.

    Yields:
        One source per .fit member; each reopens the archive when read.
    """
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
            """Read one member's bytes from the archive."""
            with zipfile.ZipFile(path) as archive:
                return archive.read(member)

        yield FitSource(name=f"{path.name}:{member}", read=read)


def _from_file(path: Path) -> Iterator[FitSource]:
    """The .fit files a single file provides.

    Args:
        path: Any file.

    Yields:
        The file itself if it is a .fit file, the .fit members if it is a .zip, else nothing.
    """
    suffix = path.suffix.lower()
    if suffix == FIT_SUFFIX:
        yield FitSource(name=path.name, read=path.read_bytes)
    elif suffix == ZIP_SUFFIX:
        yield from _from_zip(path)


def scan(paths: Iterable[Path]) -> Iterator[FitSource]:
    """Find every .fit file under ``paths``, in a stable order.

    Hidden files and folders are skipped and other file types are ignored. Within each path,
    files come in sorted order.

    Args:
        paths: Folders (searched recursively), .fit files and .zip archives.

    Yields:
        One source per .fit file found, including files inside zip archives.

    Raises:
        FileNotFoundError: A path doesn't exist. Raised before anything is yielded.
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
