"""The library's settings, each declared once with its type.

Settings are stored as text by key (``SettingsStore``). Everything outside ``fitlib.store``
reads and writes them through the declarations here, so each key has one name, one type
and one say on whether it belongs to this computer only (left out of backups).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fitlib.store.interfaces import SettingsStore


@dataclass(frozen=True)
class Setting[T]:
    """One setting: its key, how its value is stored as text, and whether it stays here.

    Attributes:
        key: The name it's stored under.
        parse: Turns the stored text back into a value.
        format: Turns a value into the text stored.
        machine_local: Whether it belongs to this computer only, so backups leave it out.
    """

    key: str
    parse: Callable[[str], T]
    format: Callable[[T], str]
    machine_local: bool = False

    def get(self, store: SettingsStore) -> T | None:
        """Read the setting.

        Args:
            store: The library's settings.

        Returns:
            Its value, or ``None`` if it isn't set.
        """
        text = store.get_setting(self.key)
        return None if text is None else self.parse(text)

    def set(self, store: SettingsStore, value: T | None) -> None:
        """Change the setting, or clear it.

        Args:
            store: The library's settings.
            value: The new value, or ``None`` to clear it.
        """
        store.set_setting(self.key, None if value is None else self.format(value))


def _text(key: str, machine_local: bool = False) -> Setting[str]:
    """Declare a setting holding text.

    Args:
        key: Its name.
        machine_local: Whether it belongs to this computer only.

    Returns:
        The setting.
    """
    return Setting(key, str, str, machine_local)


def _number(key: str, machine_local: bool = False) -> Setting[int]:
    """Declare a setting holding a whole number.

    Args:
        key: Its name.
        machine_local: Whether it belongs to this computer only.

    Returns:
        The setting.
    """
    return Setting(key, int, str, machine_local)


# The IANA time zone for rides whose file doesn't say where they were ridden.
DEFAULT_TIME_ZONE = _text("default_time_zone")
# The rider's year of birth, for a threshold heart rate estimated from age.
BIRTH_YEAR = _number("birth_year")
# The library's own id, a random UUID; travels with backups, naming the library's copy.
LIBRARY_ID = _text("library_id")
# The folder this computer backs up to.
SYNC_REMOTE = _text("sync_remote", machine_local=True)
# The backup copy this computer last pushed or restored.
SYNC_GENERATION = _number("sync_generation", machine_local=True)
# This computer's id, a random UUID, telling its pushes from another computer's.
SYNC_DEVICE = _text("sync_device", machine_local=True)

SETTINGS = (DEFAULT_TIME_ZONE, BIRTH_YEAR, LIBRARY_ID, SYNC_REMOTE, SYNC_GENERATION, SYNC_DEVICE)
# Keys of the settings backups leave out.
MACHINE_LOCAL = frozenset(s.key for s in SETTINGS if s.machine_local)
