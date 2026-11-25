"""Settings: the config file's (read-only here) and the library's (the default time zone)."""

from __future__ import annotations

from fastapi import APIRouter

from fitlib.analysis.timezone import default_zone, set_default_zone
from fitlib.api.deps import ConfigDep, StoresDep
from fitlib.api.schemas.settings import Settings, TimeZoneChange, TimeZoneIn
from fitlib.ingest.localtime import time_zones

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
def get_settings(config: ConfigDep, stores: StoresDep) -> Settings:
    """Return the settings the browser app needs.

    Args:
        config: The app's config.
        stores: The library's stores.

    Returns:
        The default units, the library folder and the default time zone.
    """
    return Settings(
        units=config.units, library=str(config.library), timezone=default_zone(stores.catalog)
    )


@router.get("/time-zones")
def list_time_zones() -> list[str]:
    """List the time zones that can be the default.

    Returns:
        IANA names, sorted.
    """
    return time_zones()


@router.put("/timezone")
def put_time_zone(stores: StoresDep, change: TimeZoneIn) -> TimeZoneChange:
    """Set or clear the default time zone, updating the rides that follow it.

    Args:
        stores: The library's stores.
        change: The new zone, or ``null``.

    Returns:
        How many rides changed, and how many may need their default bike checked.

    Raises:
        UnknownTimeZone: Not a known zone (a 422; nothing changes).
    """
    result = set_default_zone(stores.catalog, change.timezone or None)
    return TimeZoneChange(
        timezone=result.zone, updated=result.updated, bikes_to_check=result.bikes_to_check
    )
