"""The build id: which code a server was started from."""

from __future__ import annotations

from pathlib import Path

from fitlib.api.build import WEB_STAMP, build_id


def package(tmp_path: Path) -> Path:
    """Make a small stand-in for the fitlib package.

    Args:
        tmp_path: Pytest's per-test temporary folder.

    Returns:
        Its folder, with two modules.
    """
    root = tmp_path / "fitlib"
    (root / "api").mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "api" / "app.py").write_text("x = 1\n")
    return root


def test_the_same_code_gives_the_same_id(tmp_path: Path):
    """Asking twice about unchanged code gives the same id.

    Given: a package left as it is.
    Expect: the same 12-digit id both times.
    """
    root = package(tmp_path)

    assert build_id(root) == build_id(root)
    assert len(build_id(root)) == 12


def test_changed_python_code_changes_the_id(tmp_path: Path):
    """An update to any module gives a new id.

    Given: a package, then one module changed.
    Expect: a different id.
    """
    root = package(tmp_path)
    before = build_id(root)

    (root / "api" / "app.py").write_text("x = 2\n")

    assert build_id(root) != before


def test_a_rebuilt_browser_app_changes_the_id(tmp_path: Path):
    """Rebuilding the browser app (a new build stamp) gives a new id.

    Given: a package without a stamp, then with one, then with another.
    Expect: three different ids.
    """
    root = package(tmp_path)
    none = build_id(root)
    (root / WEB_STAMP).parent.mkdir()
    (root / WEB_STAMP).write_text("one")
    first = build_id(root)
    (root / WEB_STAMP).write_text("two")

    assert len({none, first, build_id(root)}) == 3


def test_other_files_do_not_change_the_id(tmp_path: Path):
    """Files that aren't code, such as caches, leave the id alone.

    Given: a package, then a ``.pyc`` file and the built app's assets added.
    Expect: the same id.
    """
    root = package(tmp_path)
    before = build_id(root)

    (root / "api" / "app.cpython-314.pyc").write_bytes(b"cache")
    (root / "web_dist" / "assets").mkdir(parents=True)
    (root / "web_dist" / "assets" / "index.js").write_text("app")

    assert build_id(root) == before
