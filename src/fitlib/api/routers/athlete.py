"""The athlete history: FTP, weight and max heart rate over time.

Each entry applies from its date. Values an entry leaves out carry forward from earlier
entries, so FTP-based figures always use what was in effect on a ride's date.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Response

from fitlib.api.deps import StoresDep
from fitlib.api.schemas import Athlete, AthleteEntryOut, AthleteValuesIn
from fitlib.metrics.load import values_on
from fitlib.models import AthleteEntry

router = APIRouter(prefix="/athlete", tags=["athlete"])


def _entry_out(entry: AthleteEntry) -> AthleteEntryOut:
    """Copy a history entry.

    Args:
        entry: The entry.

    Returns:
        The entry for the API.
    """
    return AthleteEntryOut(
        effective_from=entry.effective_from,
        ftp=entry.ftp,
        weight_kg=entry.weight_kg,
        max_hr=entry.max_hr,
    )


@router.get("")
def get_athlete(stores: StoresDep) -> Athlete:
    """Show the athlete history and today's values.

    Args:
        stores: The library's stores.

    Returns:
        Every entry, oldest first, and the values in effect today (local date).
    """
    history = sorted(stores.catalog.athlete_history(), key=lambda e: e.effective_from)
    now = values_on(history, date.today())
    return Athlete(
        history=[_entry_out(e) for e in history],
        today=AthleteValuesIn(ftp=now.ftp, weight_kg=now.weight_kg, max_hr=now.max_hr),
    )


@router.put("/{effective_from}")
def set_entry(stores: StoresDep, effective_from: date, values: AthleteValuesIn) -> AthleteEntryOut:
    """Save the values that apply from a date, replacing any entry on that date.

    Args:
        stores: The library's stores.
        effective_from: The first day the values apply.
        values: FTP, weight and/or max heart rate; at least one.

    Returns:
        The saved entry.

    Raises:
        HTTPException: 422 if no value is given.
    """
    if values.ftp is None and values.weight_kg is None and values.max_hr is None:
        raise HTTPException(status_code=422, detail="Give at least one of ftp, weight_kg, max_hr")
    entry = AthleteEntry(
        effective_from=effective_from,
        ftp=values.ftp,
        weight_kg=values.weight_kg,
        max_hr=values.max_hr,
    )
    stores.catalog.set_athlete_entry(entry)
    return _entry_out(entry)


@router.delete("/{effective_from}", status_code=204)
def delete_entry(stores: StoresDep, effective_from: date) -> Response:
    """Remove the entry on a date.

    Args:
        stores: The library's stores.
        effective_from: The entry's date.

    Returns:
        An empty response.

    Raises:
        HTTPException: 404 if there is no entry on that date.
    """
    if not stores.catalog.delete_athlete_entry(effective_from):
        raise HTTPException(status_code=404, detail=f"No athlete entry on {effective_from}")
    return Response(status_code=204)
