"""Bikes, their totals, and the dated default-bike timeline."""

from __future__ import annotations

import sqlite3
from datetime import date

from fitlib.models import (
    Bike,
    BikeDefault,
    BikeKind,
    BikeSlot,
    BikeTotals,
)
from fitlib.store.interfaces import (
    BikeNotFound,
    DuplicateBike,
    match_bike,
)
from fitlib.store.local.catalog.base import (
    _Base,
)


class _Bikes(_Base):
    """Bikes, their totals, and the dated default-bike timeline."""

    def _check_name_free(self, db: sqlite3.Connection, bike: Bike) -> None:
        """Make sure no other bike has this bike's name, ignoring case.

        Compared in Python with ``casefold`` (not SQLite's ASCII-only NOCASE), so every
        catalog treats names the same way.

        Args:
            db: The connection.
            bike: The bike being added or changed.

        Raises:
            DuplicateBike: Another bike has the same name.
        """
        for row in db.execute("SELECT id, name FROM bikes WHERE id != ?", (bike.id,)):
            if row["name"].casefold() == bike.name.casefold():
                raise DuplicateBike(bike.name)

    def add_bike(self, bike: Bike) -> None:
        """Add a bike.

        Args:
            bike: The bike. Its id must be new.

        Raises:
            DuplicateBike: Another bike has the same name (ignoring case).
        """
        with self._tx() as db:
            self._check_name_free(db, bike)
            db.execute(
                "INSERT INTO bikes VALUES (?, ?, ?, ?)",
                (bike.id, bike.name, bike.kind.value if bike.kind else None, int(bike.retired)),
            )

    def update_bike(self, bike: Bike) -> None:
        """Change a bike's name, kind or retired flag; renaming refreshes its rides' search.

        Args:
            bike: The bike with its new values, matched by id.

        Raises:
            BikeNotFound: No bike has this id.
            DuplicateBike: Another bike has the new name (ignoring case).
        """
        with self._tx() as db:
            self._require_bike(db, bike.id)
            self._check_name_free(db, bike)
            db.execute(
                "UPDATE bikes SET name = ?, kind = ?, retired = ? WHERE id = ?",
                (bike.name, bike.kind.value if bike.kind else None, int(bike.retired), bike.id),
            )
            rows = db.execute(
                "SELECT r.* FROM rides r JOIN ride_meta m ON m.ride_id = r.id WHERE m.bike_id = ?",
                (bike.id,),
            ).fetchall()
            for row in rows:
                self._index(db, self._load(row))

    def set_bike_default(self, entry: BikeDefault) -> None:
        """Add a default-bike entry, replacing any for the same slot and date.

        Args:
            entry: The entry.

        Raises:
            BikeNotFound: ``entry.bike_id`` isn't a bike.
        """
        with self._tx() as db:
            if entry.bike_id is not None:
                self._require_bike(db, entry.bike_id)
            db.execute(
                "INSERT OR REPLACE INTO bike_defaults VALUES (?, ?, ?)",
                (entry.slot.value, entry.effective_from.isoformat(), entry.bike_id),
            )

    def delete_bike_default(self, slot: BikeSlot, effective_from: date) -> bool:
        """Remove the default-bike entry for a slot and date.

        Args:
            slot: The entry's slot.
            effective_from: The entry's date.

        Returns:
            ``True`` if there was an entry to remove.
        """
        with self._tx() as db:
            deleted = db.execute(
                "DELETE FROM bike_defaults WHERE slot = ? AND effective_from = ?",
                (slot.value, effective_from.isoformat()),
            ).rowcount
        return deleted > 0

    @staticmethod
    def _bike(row: sqlite3.Row) -> Bike:
        """Build a bike from its row.

        Args:
            row: A row of the ``bikes`` table.

        Returns:
            The bike.
        """
        return Bike(
            id=row["id"],
            name=row["name"],
            kind=BikeKind(row["kind"]) if row["kind"] else None,
            retired=bool(row["retired"]),
        )

    def get_bike(self, bike_id: str) -> Bike:
        """Load one bike.

        Args:
            bike_id: The bike's id.

        Returns:
            The bike.

        Raises:
            BikeNotFound: No bike has this id.
        """
        with self._lock:
            row = self._db.execute("SELECT * FROM bikes WHERE id = ?", (bike_id,)).fetchone()
        if row is None:
            raise BikeNotFound(bike_id)
        return self._bike(row)

    def list_bikes(self, include_retired: bool = True) -> list[Bike]:
        """List bikes, sorted by name (ignoring case).

        Args:
            include_retired: Include retired bikes.

        Returns:
            The bikes.
        """
        with self._lock:
            rows = self._db.execute("SELECT * FROM bikes").fetchall()
        bikes = [self._bike(r) for r in rows if include_retired or not r["retired"]]
        return sorted(bikes, key=lambda b: b.name.casefold())

    def resolve_bike(self, ref: str) -> Bike:
        """Find a bike by name: an exact match ignoring case, else a unique prefix.

        Args:
            ref: A bike name or the start of one.

        Returns:
            The one matching bike.

        Raises:
            BikeNotFound: No bike matches.
            AmbiguousBike: The prefix matches several bikes.
        """
        return match_bike(self.list_bikes(), ref)

    def bike_totals(self) -> list[BikeTotals]:
        """Add up rides, distance and riding time for every bike, retired included.

        Returns:
            One entry per bike, sorted by name (ignoring case); bikes without rides count 0.
        """
        with self._lock:
            rows = {
                r["bike_id"]: r
                for r in self._db.execute(
                    "SELECT m.bike_id, COUNT(*) AS rides, COALESCE(SUM(r.distance_m), 0) AS dist, "
                    "COALESCE(SUM(r.moving_s), 0) AS moving FROM ride_meta m "
                    "JOIN rides r ON r.id = m.ride_id WHERE m.bike_id IS NOT NULL "
                    "GROUP BY m.bike_id"
                )
            }
        totals = []
        for bike in self.list_bikes():
            row = rows.get(bike.id)
            totals.append(
                BikeTotals(
                    bike=bike,
                    rides=row["rides"] if row else 0,
                    distance_m=float(row["dist"]) if row else 0.0,
                    moving_s=int(row["moving"]) if row else 0,
                )
            )
        return totals

    def bike_defaults(self) -> list[BikeDefault]:
        """List the dated default-bike entries.

        Returns:
            Every entry, by slot then date.
        """
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM bike_defaults ORDER BY slot, effective_from"
            ).fetchall()
        return [
            BikeDefault(
                slot=BikeSlot(r["slot"]),
                effective_from=date.fromisoformat(r["effective_from"]),
                bike_id=r["bike_id"],
            )
            for r in rows
        ]
