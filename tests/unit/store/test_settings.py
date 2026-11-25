"""Library settings: declared once with their types, and only read and written that way."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import fitlib
from fitlib.store.memory import MemoryCatalog
from fitlib.store.settings import (
    BIRTH_YEAR,
    DEFAULT_TIME_ZONE,
    LIBRARY_ID,
    MACHINE_LOCAL,
    SETTINGS,
    SYNC_DEVICE,
    SYNC_GENERATION,
    SYNC_REMOTE,
)

SOURCE = Path(fitlib.__file__).parent
# Where raw keys may be used: the store's backends and the settings declarations.
RAW_ACCESS = SOURCE / "store"


def test_values_round_trip_with_their_types():
    """Values come back with the type they were saved with, and ``None`` clears them.

    Given: A year of birth (a number) and a default time zone (text), saved then cleared.
    Expect: 1980 as an int and the zone as text; stored as text; ``None`` once cleared.
    """
    catalog = MemoryCatalog()

    BIRTH_YEAR.set(catalog, 1980)
    DEFAULT_TIME_ZONE.set(catalog, "Europe/Paris")
    saved = (BIRTH_YEAR.get(catalog), DEFAULT_TIME_ZONE.get(catalog))
    stored = catalog.get_setting("birth_year")
    BIRTH_YEAR.set(catalog, None)

    assert saved == (1980, "Europe/Paris")
    assert stored == "1980", "Settings should be stored as text, as before"
    assert BIRTH_YEAR.get(catalog) is None


def test_values_stored_before_read_the_same():
    """Settings written as text by earlier versions read as the same values.

    Given: The sync generation and year of birth stored as text, as before.
    Expect: Numbers back.
    """
    catalog = MemoryCatalog()
    catalog.set_setting("sync_generation", "7")
    catalog.set_setting("birth_year", "1975")

    assert (SYNC_GENERATION.get(catalog), BIRTH_YEAR.get(catalog)) == (7, 1975)


def test_only_this_computers_settings_are_machine_local():
    """Backups leave out exactly the sync settings, and keep the library's own.

    Given: Every declared setting.
    Expect: The machine-local keys are the three sync settings; keys are unique.
    """
    keys = [s.key for s in SETTINGS]

    assert {SYNC_REMOTE.key, SYNC_GENERATION.key, SYNC_DEVICE.key} == MACHINE_LOCAL
    assert LIBRARY_ID.key not in MACHINE_LOCAL, "The library id should travel with backups"
    assert len(keys) == len(set(keys)), "Each setting should have its own key"


def raw_setting_calls(root: Path) -> list[str]:
    """Find calls of ``get_setting``/``set_setting`` outside the store.

    Args:
        root: The package folder to scan.

    Returns:
        ``path:line`` for each call outside ``RAW_ACCESS``.
    """
    found = []
    for path in sorted(root.rglob("*.py")):
        if path.is_relative_to(RAW_ACCESS):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get_setting", "set_setting")
            ):
                found.append(f"{path.relative_to(root)}:{node.lineno}")
    return found


def test_settings_are_only_used_through_their_declarations():
    """Code outside the store reads and writes settings through ``fitlib.store.settings``.

    Given: Every module in the fitlib package.
    Expect: No raw ``get_setting``/``set_setting`` calls outside ``fitlib/store``, so a new
        setting has to be declared (with whether it's machine-local) to be used.
    """
    assert raw_setting_calls(SOURCE) == []


def test_the_scan_finds_raw_calls(tmp_path: Path):
    """The scan above notices a raw call, so an empty result means something.

    Given: A module calling ``catalog.get_setting("x")``.
    Expect: It's reported with its line.
    """
    (tmp_path / "module.py").write_text('def f(catalog):\n    return catalog.get_setting("x")\n')

    assert raw_setting_calls(tmp_path) == ["module.py:2"]


@pytest.mark.parametrize("setting", SETTINGS, ids=lambda s: s.key)
def test_every_setting_clears(setting):
    """Clearing any setting leaves nothing stored.

    Given: Each declared setting, cleared on an empty catalog.
    Expect: ``None``.
    """
    catalog = MemoryCatalog()

    setting.set(catalog, None)

    assert setting.get(catalog) is None
