"""The athlete: FTP, weight, max and threshold heart rate over time, and year of birth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fitlib.analysis.training import athlete_profile, threshold_today
from fitlib.metrics.load import AthleteValues, ThresholdSource, estimated_threshold_hr, values_on
from fitlib.models import AthleteEntry
from fitlib.services.errors import AthleteEntryNotFound
from fitlib.store.interfaces import CatalogStore


@dataclass(frozen=True)
class AthleteToday:
    """The athlete's history and where things stand today.

    Attributes:
        history: Every entry, oldest first.
        today: Today's (local) date.
        values: The values in effect today.
        birth_year: The year of birth, if set.
        estimated_threshold_hr: Today's threshold heart rate estimated from the year of birth.
        threshold_hr: Today's threshold heart rate: set, from your rides, or from your age.
        threshold_source: Where ``threshold_hr`` came from.
    """

    history: list[AthleteEntry]
    today: date
    values: AthleteValues
    birth_year: int | None
    estimated_threshold_hr: int | None
    threshold_hr: int | None
    threshold_source: ThresholdSource | None


def athlete_today(catalog: CatalogStore, today: date | None = None) -> AthleteToday:
    """Gather the athlete history and the values in effect today.

    Args:
        catalog: The library's catalog.
        today: The day to report on; today's local date if not given.

    Returns:
        The history, today's values and today's threshold heart rate with its source.
    """
    day = today or date.today()
    profile = athlete_profile(catalog)
    history = sorted(profile.history, key=lambda e: e.effective_from)
    threshold, source = threshold_today(catalog, profile, day)
    return AthleteToday(
        history=history,
        today=day,
        values=values_on(history, day),
        birth_year=profile.birth_year,
        estimated_threshold_hr=estimated_threshold_hr(profile.birth_year, day),
        threshold_hr=threshold,
        threshold_source=source,
    )


def remove_entry(catalog: CatalogStore, day: date) -> None:
    """Remove the athlete history entry on a date.

    Args:
        catalog: The library's catalog.
        day: The entry's date.

    Raises:
        AthleteEntryNotFound: There's no entry on that date.
    """
    if not catalog.delete_athlete_entry(day):
        raise AthleteEntryNotFound(f"{day:%Y-%m-%d}")
