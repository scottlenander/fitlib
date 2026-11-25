"""The library folder is readable by its owner only."""

from __future__ import annotations

import stat
from pathlib import Path

from fitlib.config import Config
from fitlib.store.factory import library_blobs, open_stores, restore_catalog, snapshot_catalog
from fitlib.store.settings import MACHINE_LOCAL


def mode(path: Path) -> int:
    """A file's permission bits.

    Args:
        path: The file or folder.

    Returns:
        E.g. ``0o700``.
    """
    return stat.S_IMODE(path.stat().st_mode)


def test_new_library_is_private(tmp_path: Path):
    """A library created by opening it is owner-only.

    Given: A library path that doesn't exist yet, inside a missing parent.
    Expect: The library folder is 0700.
    """
    config = Config(library=tmp_path / "home" / "library")

    with open_stores(config):
        pass

    assert mode(config.library) == 0o700


def test_existing_library_is_made_private(tmp_path: Path):
    """An existing library readable by others is tightened when opened.

    Given: A library folder at 0755 (as earlier versions created it).
    Expect: 0700 after opening.
    """
    config = Config(library=tmp_path / "library")
    with open_stores(config):
        pass
    config.library.chmod(0o755)

    with open_stores(config):
        pass

    assert mode(config.library) == 0o700


def test_restored_and_blob_only_libraries_are_private(tmp_path: Path):
    """Restoring a catalog or writing blobs first also creates the folder owner-only.

    Given: A catalog snapshot restored into a new library, and blobs opened for another.
    Expect: Both library folders are 0700.
    """
    with open_stores(Config(library=tmp_path / "source")) as stores:
        data = snapshot_catalog(stores, MACHINE_LOCAL)
    restored = Config(library=tmp_path / "restored")
    blobs_first = Config(library=tmp_path / "blobs-first")

    restore_catalog(restored, data)
    library_blobs(blobs_first)

    assert mode(restored.library) == 0o700
    assert mode(blobs_first.library) == 0o700
