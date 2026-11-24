"""The library's own settings, by key."""

from __future__ import annotations

from fitlib.store.memory.catalog.base import _Base


class _Settings(_Base):
    """The library's own settings, by key."""

    def get_setting(self, key: str) -> str | None:
        """Read a library setting.

        Args:
            key: The setting's name.

        Returns:
            Its value, or ``None`` if it isn't set.
        """
        return self._settings.get(key)

    def set_setting(self, key: str, value: str | None) -> None:
        """Set or clear a library setting.

        Args:
            key: The setting's name.
            value: Its new value; ``None`` clears it.
        """
        if value is None:
            self._settings.pop(key, None)
        else:
            self._settings[key] = value
