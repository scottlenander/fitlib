"""Library settings: units, the library folder and the default time zone."""

from __future__ import annotations

from pydantic import BaseModel

from fitlib.models import Units


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
