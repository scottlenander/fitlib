"""The athlete's dated FTP, weight and heart rates."""

from __future__ import annotations

from datetime import date

from fitlib.models import (
    AthleteEntry,
)
from fitlib.store.memory.catalog.base import _Base


class _Athlete(_Base):
    """The athlete's dated FTP, weight and heart rates."""

    def athlete_history(self) -> list[AthleteEntry]:
        """List the athlete history.

        Returns:
            Every entry, oldest first.
        """
        return [self._athlete[d] for d in sorted(self._athlete)]

    def set_athlete_entry(self, entry: AthleteEntry) -> None:
        """Add an athlete history entry, replacing any entry on the same date.

        Args:
            entry: The entry.
        """
        self._athlete[entry.effective_from] = entry

    def delete_athlete_entry(self, effective_from: date) -> bool:
        """Remove the athlete history entry on a date.

        Args:
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        return self._athlete.pop(effective_from, None) is not None
