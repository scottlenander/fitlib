"""Where a ride was recorded, and whether it was indoors."""

from __future__ import annotations

from fitlib.ingest.decoder import DecodedActivity
from fitlib.models import Source

INDOOR_SUB_SPORTS = {"virtual_activity", "indoor_cycling"}
CYCLING_SPORTS = {"cycling", "e_biking"}


def detect_source(decoded: DecodedActivity) -> Source:
    match decoded.manufacturer:
        case "zwift":
            return Source.ZWIFT
        case "garmin":
            return Source.GARMIN
        case _:
            return Source.OTHER


def device_name(decoded: DecodedActivity) -> str | None:
    """Readable device name, e.g. "Garmin Edge 540" or "Zwift"."""
    maker = decoded.manufacturer
    if maker is None:
        return None
    maker_label = maker.replace("_", " ").title()
    product = decoded.product
    # Product ids the FIT profile doesn't name decode as numbers; they mean nothing to a reader.
    if product is None or product.isdigit():
        return maker_label
    return f"{maker_label} {product.replace('_', ' ').title()}"


def is_cycling(decoded: DecodedActivity) -> bool:
    """Rides without any sport information are assumed to be rides."""
    return decoded.sport is None or decoded.sport in CYCLING_SPORTS


def is_indoor(decoded: DecodedActivity, has_gps: bool) -> bool:
    return decoded.sub_sport in INDOOR_SUB_SPORTS or not has_gps
