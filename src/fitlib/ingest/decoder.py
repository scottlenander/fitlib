"""Decode a .fit file's bytes into the parts fitlib uses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import fitdecode

SEMICIRCLE_TO_DEG = 180 / 2**31
FIT_EPOCH_S = 631_065_600  # 1989-12-31T00:00:00Z as a Unix timestamp
FIT_EPOCH = datetime.fromtimestamp(FIT_EPOCH_S, UTC)
# FIT times below this many seconds after the epoch (mid-1998) aren't dates but seconds
# since the device powered on. Zwift writes 0 as its local time.
FIT_DATETIME_MIN = 0x10000000
# Every real time zone is between 12 hours behind UTC and 14 hours ahead.
MIN_UTC_OFFSET_S = -12 * 3600
MAX_UTC_OFFSET_S = 14 * 3600

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
    """The bytes aren't a complete, valid FIT file."""


@dataclass(frozen=True)
class DecodedLap:
    """A lap message from the file.

    Attributes:
        start: When the lap started, in UTC.
        elapsed_s: The lap's length in seconds, if the file says.
    """

    start: datetime
    elapsed_s: float | None


@dataclass(frozen=True)
class DecodedActivity:
    """The parts of a FIT activity file that fitlib uses.

    Attributes:
        manufacturer: FIT manufacturer, e.g. ``"garmin"`` or ``"zwift"``.
        product: Product name (e.g. ``"edge_540"``) or number as text, if known.
        sport: FIT sport, e.g. ``"cycling"``, if the file says.
        sub_sport: FIT sub-sport, e.g. ``"road"``, if the file says.
        utc_offset_s: Local time minus UTC in seconds, if the device recorded local time.
        records: One dict per record, with keys ``timestamp`` (UTC datetime), ``power``,
            ``heart_rate``, ``cadence``, ``speed`` (m/s), ``distance`` (m), ``altitude`` (m),
            ``lat`` and ``lon`` (degrees) and ``temperature``. Missing values are ``None``.
        laps: The file's laps, oldest first.
    """

    manufacturer: str | None
    product: str | None
    sport: str | None
    sub_sport: str | None
    utc_offset_s: int | None
    records: list[dict[str, Any]] = field(repr=False)
    laps: list[DecodedLap]


def _first(fields: dict[str, Any], names: tuple[str, ...]) -> Any:
    """The first of several fields that has a value.

    Args:
        fields: A message's fields by name.
        names: Field names, preferred first.

    Returns:
        The first non-``None`` value, or ``None``.
    """
    for name in names:
        value = fields.get(name)
        if value is not None:
            return value
    return None


def _degrees(value: Any) -> float | None:
    """Convert a FIT position from semicircles to degrees.

    Args:
        value: Semicircles (an int), or anything else for a missing position.

    Returns:
        Degrees, or ``None`` if ``value`` isn't an int.
    """
    return value * SEMICIRCLE_TO_DEG if isinstance(value, int) else None


def _name(value: Any) -> str | None:
    """Turn a FIT enum value into text.

    fitdecode gives known enum values as names (``"garmin"``) and unknown ones as numbers.

    Args:
        value: The decoded value, or ``None``.

    Returns:
        The value as text, or ``None``.
    """
    if value is None:
        return None
    return str(value)


def _utc_offset(activity: dict[str, Any]) -> int | None:
    """Work out the rider's time zone offset from the activity message.

    fitdecode returns ``local_timestamp`` as a datetime labelled UTC that actually holds local
    wall-clock time, or as raw seconds since the FIT epoch for some files; both are handled.
    A local time that isn't a real date (Zwift writes the FIT epoch, 1989-12-31) or that
    gives an offset no time zone has is ignored, as if the file had no local time.

    Args:
        activity: The activity message's fields.

    Returns:
        Local time minus UTC in seconds, rounded to the nearest 15 minutes (every real time
        zone is a multiple), or ``None`` if the file has no usable local time.
    """
    local, utc = activity.get("local_timestamp"), activity.get("timestamp")
    if not isinstance(utc, datetime):
        return None
    if isinstance(local, datetime):
        local_s = (local.replace(tzinfo=UTC) - FIT_EPOCH).total_seconds()
    elif isinstance(local, int):
        local_s = local
    else:
        return None
    if local_s < FIT_DATETIME_MIN:
        return None
    offset = round((local_s + FIT_EPOCH_S - utc.timestamp()) / 900) * 900
    if not MIN_UTC_OFFSET_S <= offset <= MAX_UTC_OFFSET_S:
        return None
    return offset


def decode(data: bytes) -> DecodedActivity:
    """Decode a .fit file into its device, sport, local time, records and laps.

    Args:
        data: The file's bytes.

    Returns:
        The decoded activity. Records without a timestamp are dropped.

    Raises:
        DecodeError: The data is empty, or fitdecode can't read it (bad header, failed CRC,
            truncated file).
    """
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
