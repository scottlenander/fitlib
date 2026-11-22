"""The athlete: FTP, weight, max and threshold heart rate over time, and year of birth.

Each entry applies from its date. Values an entry leaves out carry forward from earlier
entries, so training figures always use what was in effect on a ride's date. The year of
birth gives an estimated threshold heart rate for days without one set.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Response

from fitlib.analysis.training import athlete_profile, set_birth_year, threshold_today
from fitlib.api.deps import StoresDep
from fitlib.api.schemas import Athlete, AthleteEntryOut, AthleteValuesIn, BirthYearIn
from fitlib.metrics.load import estimated_threshold_hr, values_on
from fitlib.models import AthleteEntry
from fitlib.store.interfaces import CatalogStore

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
        threshold_hr=entry.threshold_hr,
    )


def _athlete(catalog: CatalogStore) -> Athlete:
    """Gather the athlete history, today's values and the year of birth.

    Args:
        catalog: The library's catalog.

    Returns:
        Every entry, oldest first, the values in effect today (local date), the year of
        birth and today's threshold heart rate estimated from it.
    """
    profile = athlete_profile(catalog)
    history = sorted(profile.history, key=lambda e: e.effective_from)
    today = date.today()
    now = values_on(history, today)
    threshold, source = threshold_today(catalog, profile, today)
    return Athlete(
        history=[_entry_out(e) for e in history],
        today=AthleteValuesIn(
            ftp=now.ftp, weight_kg=now.weight_kg, max_hr=now.max_hr, threshold_hr=now.threshold_hr
        ),
        birth_year=profile.birth_year,
        estimated_threshold_hr=estimated_threshold_hr(profile.birth_year, today),
        threshold_hr_today=threshold,
        threshold_hr_source_today=source,
    )


@router.get("")
def get_athlete(stores: StoresDep) -> Athlete:
    """Show the athlete history, today's values and the year of birth.

    Args:
        stores: The library's stores.

    Returns:
        The athlete.
    """
    return _athlete(stores.catalog)


@router.put("/birth-year")
def put_birth_year(stores: StoresDep, body: BirthYearIn) -> Athlete:
    """Set or clear the rider's year of birth, for estimating threshold heart rate.

    Args:
        stores: The library's stores.
        body: The year, or ``null``.

    Returns:
        The athlete, with the new estimate.

    Raises:
        BadBirthYear: Before 1900 or in the future (a 422; nothing changes).
    """
    set_birth_year(stores.catalog, body.birth_year)
    return _athlete(stores.catalog)


@router.put("/{effective_from}")
def set_entry(stores: StoresDep, effective_from: date, values: AthleteValuesIn) -> AthleteEntryOut:
    """Save the values that apply from a date, replacing any entry on that date.

    Args:
        stores: The library's stores.
        effective_from: The first day the values apply.
        values: FTP, weight, max and/or threshold heart rate; at least one.

    Returns:
        The saved entry.

    Raises:
        HTTPException: 422 if no value is given.
    """
    if all(v is None for v in (values.ftp, values.weight_kg, values.max_hr, values.threshold_hr)):
        raise HTTPException(
            status_code=422, detail="Give at least one of ftp, weight_kg, max_hr, threshold_hr"
        )
    entry = AthleteEntry(
        effective_from=effective_from,
        ftp=values.ftp,
        weight_kg=values.weight_kg,
        max_hr=values.max_hr,
        threshold_hr=values.threshold_hr,
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
