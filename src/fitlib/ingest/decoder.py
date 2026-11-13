"""Decode a .fit file's bytes into the parts fitlib uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import fitdecode

SEMICIRCLE_TO_DEG = 180 / 2**31
FIT_EPOCH_S = 631_065_600  # 1989-12-31T00:00:00Z as a Unix timestamp

# Record fields kept, with the preferred ("enhanced", higher-range) source listed first.
_RECORD_FIELDS: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp",),
    "power": ("power",),
    "heart_rate": ("heart_rate",),
    "cadence": ("cadence",),
    "speed": ("enhanced_speed", "speed"),
    "distance": ("distance",),
    "altitude": ("enhanced_altitude", "altitude"),
    "lat": ("position_lat",),
    "lon": ("position_long",),
    "temperature": ("temperature",),
}


class DecodeError(Exception):
    pass


@dataclass(frozen=True)
class DecodedLap:
    start: datetime
    elapsed_s: float | None


@dataclass(frozen=True)
class DecodedActivity:
    manufacturer: str | None
    product: str | None
    sport: str | None
    sub_sport: str | None
    utc_offset_s: int | None
    records: list[dict[str, Any]] = field(repr=False)
    laps: list[DecodedLap]


def _first(fields: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        value = fields.get(name)
        if value is not None:
            return value
    return None


def _degrees(value: Any) -> float | None:
    return value * SEMICIRCLE_TO_DEG if isinstance(value, int) else None


def _name(value: Any) -> str | None:
    """Enum-like values decode as strings; unknown ones as numbers."""
    if value is None:
        return None
    return str(value)


def _utc_offset(activity: dict[str, Any]) -> int | None:
    """Local time minus UTC, from the activity message's local and UTC timestamps.

    fitdecode returns ``local_timestamp`` as a datetime labelled UTC that actually holds local
    wall-clock time, or as raw seconds since the FIT epoch for some files; both are handled.
    Offsets are rounded to the nearest 15 minutes (every real time zone is a multiple).
    """
    local, utc = activity.get("local_timestamp"), activity.get("timestamp")
    if not isinstance(utc, datetime):
        return None
    if isinstance(local, datetime):
        seconds = (local.replace(tzinfo=None) - utc.replace(tzinfo=None)).total_seconds()
    elif isinstance(local, int):
        seconds = local + FIT_EPOCH_S - utc.timestamp()
    else:
        return None
    return round(seconds / 900) * 900


def decode(data: bytes) -> DecodedActivity:
    """Raises ``DecodeError`` for anything fitdecode can't read (bad header, CRC, truncation)."""
    if not data:
        raise DecodeError("the file is empty")
    file_id: dict[str, Any] = {}
    session: dict[str, Any] = {}
    sport: dict[str, Any] = {}
    activity: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    laps: list[DecodedLap] = []

    try:
        with fitdecode.FitReader(
            data,
            check_crc=fitdecode.CrcCheck.RAISE,
            error_handling=fitdecode.ErrorHandling.RAISE,
        ) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                fields = {f.name: f.value for f in frame.fields}
                match frame.name:
                    case "record":
                        row = {key: _first(fields, names) for key, names in _RECORD_FIELDS.items()}
                        row["lat"] = _degrees(row["lat"])
                        row["lon"] = _degrees(row["lon"])
                        if row["timestamp"] is not None:
                            records.append(row)
                    case "lap" if fields.get("start_time") is not None:
                        laps.append(
                            DecodedLap(fields["start_time"], fields.get("total_elapsed_time"))
                        )
                    case "file_id" if not file_id:
                        file_id = fields
                    case "session" if not session:
                        session = fields
                    case "sport" if not sport:
                        sport = fields
                    case "activity":
                        activity = fields
    except fitdecode.FitError as exc:
        raise DecodeError(f"{type(exc).__name__}: {exc}") from exc

    return DecodedActivity(
        manufacturer=_name(file_id.get("manufacturer")),
        product=_name(file_id.get("garmin_product") or file_id.get("product")),
        sport=_name(session.get("sport") or sport.get("sport")),
        sub_sport=_name(session.get("sub_sport") or sport.get("sub_sport")),
        utc_offset_s=_utc_offset(activity),
        records=records,
        laps=sorted(laps, key=lambda lap: lap.start),
    )
