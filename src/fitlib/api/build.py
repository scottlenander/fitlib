"""Which code a running server was started from, so the launcher can spot an old one."""

from __future__ import annotations

import hashlib
from pathlib import Path

import fitlib

# Written next to the built browser app by the launcher's build check.
WEB_STAMP = Path("web_dist") / ".fitlib-build"
LENGTH = 12


def build_id(package_dir: Path | None = None) -> str:
    """Fingerprint fitlib's Python code and its built browser app.

    Two servers started from the same code give the same id. After an update (new Python
    code, or the browser app rebuilt) the id changes.

    Args:
        package_dir: The ``fitlib`` package's folder; the installed one by default.

    Returns:
        The first 12 hex digits of a sha256 over every ``.py`` file (by path and content)
        and the browser app's build stamp, if it has one.
    """
    root = package_dir or Path(fitlib.__file__).parent
    digest = hashlib.sha256()
    files = sorted(root.rglob("*.py"))
    stamp = root / WEB_STAMP
    if stamp.is_file():
        files.append(stamp)
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:LENGTH]
