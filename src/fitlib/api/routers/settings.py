"""Settings: the config file's (read-only here) and the library's (the default time zone)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fitlib.analysis.timezone import default_zone, set_default_zone
from fitlib.api.deps import ConfigDep, StoresDep
from fitlib.ingest.localtime import time_zones
from fitlib.models import Units

router = APIRouter(prefix="/settings", tags=["settings"])


class Settings(BaseModel):
    """Settings for the browser app.

    Attributes:
        units: The default units for showing figures. The app may let the viewer switch.
        library: The library folder, for display.
        timezone: The library's default time zone (an IANA name such as
            ``"America/New_York"``), for rides whose files don't say; ``null`` for none.
    """

    units: Units
    library: str
    timezone: str | None


class TimeZoneIn(BaseModel):
    """A new default time zone.

    Attributes:
        timezone: An IANA name such as ``"America/New_York"`` (one of
            ``GET /api/settings/time-zones``), or ``null`` for none (UTC).
    """

    timezone: str | None


class TimeZoneChange(BaseModel):
    """What changing the default time zone did.

    Attributes:
        timezone: The new default, or ``null``.
        updated: Rides whose time zone changed (those without one of their own).
        bikes_to_check: Of those, rides now on another day whose bike came from a default
            bike: "Apply defaults" on the Bikes page brings their bike in line.
    """

    timezone: str | None
    updated: int
    bikes_to_check: int


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
