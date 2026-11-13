"""Loading ~/.fitlib/config.toml (or the file given by --config / $FITLIB_CONFIG)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fitlib.config import DEFAULT_LIBRARY, ConfigError, load_config


def test_missing_default_config_means_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """With no config file anywhere, fitlib uses its default library location.

    Given: ``$FITLIB_CONFIG`` pointing at a file that doesn't exist, and no ``--config``.
    Expect: the default library (``~/.fitlib/library``, expanded) and the local backend.
    """
    monkeypatch.setenv("FITLIB_CONFIG", str(tmp_path / "absent.toml"))

    config = load_config()

    assert config.library == DEFAULT_LIBRARY.expanduser()
    assert config.backend == "local"


def test_explicit_config_must_exist(tmp_path: Path):
    """A config file named on the command line has to be there.

    Given: ``--config`` pointing at a missing file.
    Expect: ``ConfigError``, rather than silently using defaults.
    """
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")


def test_library_path_is_expanded_and_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Library paths can be relative to the config file, or start with ``~``.

    Given: one config with ``library = "rides"`` and one with ``library = "~/fitlib-rides"``.
    Expect: ``<config folder>/rides`` and ``<home>/fitlib-rides``.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    relative = tmp_path / "relative.toml"
    relative.write_text('library = "rides"\n')
    home = tmp_path / "home.toml"
    home.write_text('library = "~/fitlib-rides"\n')

    from_relative = load_config(relative)
    from_home = load_config(home)

    assert from_relative.library == (tmp_path / "rides").resolve()
    assert from_home.library == tmp_path / "home" / "fitlib-rides"


def test_env_var_picks_the_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """``$FITLIB_CONFIG`` is used when no ``--config`` is given.

    Given: ``$FITLIB_CONFIG`` pointing at a file that sets ``library``.
    Expect: that library.
    """
    path = tmp_path / "fitlib.toml"
    path.write_text(f'library = "{tmp_path / "lib"}"\n')
    monkeypatch.setenv("FITLIB_CONFIG", str(path))

    config = load_config()

    assert config.library == tmp_path / "lib"


@pytest.mark.parametrize(
    ("content", "message"),
    [('[store]\nbackend = "cloud"\n', "Unknown store backend"), ("library = [", "Invalid config")],
    ids=["unknown-backend", "invalid-toml"],
)
def test_bad_config_is_reported(tmp_path: Path, content: str, message: str):
    """Mistakes in the config file are reported clearly.

    Given: a config with an unknown store backend, or broken TOML.
    Expect: ``ConfigError`` naming the problem.
    """
    path = tmp_path / "fitlib.toml"
    path.write_text(content)

    with pytest.raises(ConfigError, match=message):
        load_config(path)
