"""``GET /api/settings``: settings from the config file that the browser app needs."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from fitlib.api.deps import ConfigDep
from fitlib.models import Units

router = APIRouter(prefix="/settings", tags=["settings"])


class Settings(BaseModel):
    """Settings for the browser app.

    Attributes:
        units: The default units for showing figures. The app may let the viewer switch.
        library: The library folder, for display.
    """

    units: Units
    library: str


@router.get("")
def get_settings(config: ConfigDep) -> Settings:
    """Return the settings from the config file.

    Args:
        config: The app's config.

    Returns:
        The default units and the library folder.
    """
    return Settings(units=config.units, library=str(config.library))
