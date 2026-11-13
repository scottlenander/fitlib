"""Fitlib configuration, read from a TOML file.

Location: ``--config`` on the command line, else ``$FITLIB_CONFIG``, else
``~/.fitlib/config.toml``. A missing file means all defaults.

Example::

    library = "~/Rides/fitlib"

    [store]
    backend = "local"
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.fitlib/config.toml")
DEFAULT_LIBRARY = Path("~/.fitlib/library")
BACKENDS = ("local",)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    library: Path
    backend: str = "local"


def config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    env = os.environ.get("FITLIB_CONFIG")
    return Path(env).expanduser() if env else DEFAULT_CONFIG_PATH.expanduser()


def load_config(explicit: Path | None = None) -> Config:
    path = config_path(explicit)
    if not path.exists():
        if explicit is not None:
            raise ConfigError(f"Config file not found: {path}")
        return Config(library=DEFAULT_LIBRARY.expanduser())
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid config file {path}: {exc}") from exc

    library = Path(data.get("library", DEFAULT_LIBRARY)).expanduser()
    if not library.is_absolute():
        library = (path.parent / library).resolve()
    backend = data.get("store", {}).get("backend", "local")
    if backend not in BACKENDS:
        raise ConfigError(
            f"Unknown store backend {backend!r} in {path}; expected one of {BACKENDS}"
        )
    return Config(library=library, backend=backend)
