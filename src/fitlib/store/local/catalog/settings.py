"""The library's own settings, by key."""

from __future__ import annotations

from fitlib.store.local.catalog.base import (
    _Base,
)


class _Settings(_Base):
    """The library's own settings, by key."""

    def get_setting(self, key: str) -> str | None:
        """Read a library setting.

        Args:
            key: The setting's name.

        Returns:
            Its value, or ``None`` if it isn't set.
        """
        with self._lock:
            row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str | None) -> None:
        """Set or clear a library setting.

        Args:
            key: The setting's name.
            value: Its new value; ``None`` clears it.
        """
        with self._tx() as db:
            if value is None:
                db.execute("DELETE FROM settings WHERE key = ?", (key,))
            else:
                db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
