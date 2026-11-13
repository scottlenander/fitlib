"""Where a ride was recorded, and whether it was indoors."""

from __future__ import annotations

from fitlib.ingest.decoder import DecodedActivity
from fitlib.models import Source

INDOOR_SUB_SPORTS = {"virtual_activity", "indoor_cycling"}
CYCLING_SPORTS = {"cycling", "e_biking"}


def detect_source(decoded: DecodedActivity) -> Source:
    """Work out who recorded a ride.

    Args:
        decoded: The decoded file.

    Returns:
        Zwift or Garmin from the manufacturer field, otherwise ``Source.OTHER``.
    """
    match decoded.manufacturer:
        case "zwift":
            return Source.ZWIFT
        case "garmin":
            return Source.GARMIN
        case _:
            return Source.OTHER


def device_name(decoded: DecodedActivity) -> str | None:
    """Build a readable name for the recording device.

    Args:
        decoded: The decoded file.

    Returns:
        For example ``"Garmin Edge 540"`` or ``"Zwift"``. Product ids the FIT profile doesn't
        name are left out. ``None`` if the manufacturer is unknown.
    """
    maker = decoded.manufacturer
    if maker is None:
        return None
    maker_label = maker.replace("_", " ").title()
    product = decoded.product
    if product is None or product.isdigit():
        return maker_label
    return f"{maker_label} {product.replace('_', ' ').title()}"


def is_cycling(decoded: DecodedActivity) -> bool:
    """Decide whether a file records a ride.

    Args:
        decoded: The decoded file.

    Returns:
        ``True`` for cycling and e-biking, and for files with no sport information.
    """
    return decoded.sport is None or decoded.sport in CYCLING_SPORTS


def is_indoor(decoded: DecodedActivity, has_gps: bool) -> bool:
    """Decide whether a ride was indoors.

    Args:
        decoded: The decoded file.
        has_gps: Whether the ride recorded any position.

    Returns:
        ``True`` for virtual and indoor-cycling sub-sports, and for rides without GPS.
    """
    return decoded.sub_sport in INDOOR_SUB_SPORTS or not has_gps
