"""The athlete's dated FTP, weight and heart rates."""

from __future__ import annotations

from datetime import date

from fitlib.models import (
    AthleteEntry,
)
from fitlib.store.local.catalog.base import (
    _Base,
)


class _Athlete(_Base):
    """The athlete's dated FTP, weight and heart rates."""

    def set_athlete_entry(self, entry: AthleteEntry) -> None:
        """Add an athlete history entry, replacing any entry on the same date.

        Args:
            entry: The entry.
        """
        with self._tx() as db:
            db.execute(
                "INSERT OR REPLACE INTO athlete_history "
                "(effective_from, ftp, weight_kg, max_hr, threshold_hr) VALUES (?, ?, ?, ?, ?)",
                (
                    entry.effective_from.isoformat(),
                    entry.ftp,
                    entry.weight_kg,
                    entry.max_hr,
                    entry.threshold_hr,
                ),  # fmt: skip
            )

    def delete_athlete_entry(self, effective_from: date) -> bool:
        """Remove the athlete history entry on a date.

        Args:
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        with self._tx() as db:
            deleted = db.execute(
                "DELETE FROM athlete_history WHERE effective_from = ?",
                (effective_from.isoformat(),),
            ).rowcount
        return deleted > 0

    def athlete_history(self) -> list[AthleteEntry]:
        """List the athlete history.

        Returns:
            Every entry, oldest first.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM athlete_history ORDER BY effective_from"
            ).fetchall()
        return [
            AthleteEntry(
                effective_from=date.fromisoformat(r["effective_from"]),
                ftp=r["ftp"],
                weight_kg=r["weight_kg"],
                max_hr=r["max_hr"],
                threshold_hr=r["threshold_hr"],
            )
            for r in rows
        ]
