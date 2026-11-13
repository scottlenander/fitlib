"""Write the synthetic .fit fixtures described in ``specs.py``.

Usage (from the repo root)::

    uv run python -m tests.fixtures.generate

Output is deterministic: the same specs always produce byte-identical files, which
``tests/test_fixtures_current.py`` checks.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.event_message import EventMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.lap_message import LapMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import (
    Activity,
    Event,
    EventType,
    FileType,
    GarminProduct,
    Manufacturer,
    Sport,
    SubSport,
)

from tests.fixtures.specs import CORRUPT, DUPLICATES, RIDES, Loop, RideSpec, Source

FIT_DIR = Path(__file__).parent / "fit"

METRES_PER_DEG_LAT = 111_320.0
# Speed model: v = (P / k) ** (1/3) m/s. 200 W -> ~9.3 m/s (33 km/h). Coasting at 0 W stops.
SPEED_K = 0.25


@dataclass(frozen=True)
class Sample:
    """One second of the synthetic ride."""

    timestamp_ms: int
    power: int
    heart_rate: int
    cadence: int
    speed: float
    distance: float
    lat: float
    lon: float
    altitude: float


def speed_for_power(power: int) -> float:
    return (power / SPEED_K) ** (1 / 3) if power > 0 else 0.0


def position_on_loop(loop: Loop, distance_m: float) -> tuple[float, float, float]:
    """Latitude, longitude and altitude after riding ``distance_m`` around ``loop``."""
    angle = 2 * math.pi * (distance_m % loop.lap_length_m) / loop.lap_length_m
    radius = loop.lap_length_m / (2 * math.pi)
    # A circle centred on the loop's point, ridden anticlockwise from its east side.
    north = radius * math.sin(angle)
    east = radius * math.cos(angle)
    lat = loop.center_lat + north / METRES_PER_DEG_LAT
    lon = loop.center_lon + east / (METRES_PER_DEG_LAT * math.cos(math.radians(loop.center_lat)))
    altitude = loop.base_altitude_m + loop.altitude_amplitude_m * math.sin(angle)
    return lat, lon, altitude


def samples(spec: RideSpec) -> list[Sample]:
    start_ms = int(spec.start.timestamp()) * 1000
    out: list[Sample] = []
    distance = 0.0
    for i, (power, hr, cadence) in enumerate(
        zip(spec.powers(), spec.heart_rates(), spec.cadences(), strict=True)
    ):
        speed = speed_for_power(power)
        lat, lon, altitude = position_on_loop(spec.loop, distance)
        out.append(
            Sample(
                timestamp_ms=start_ms + i * 1000,
                power=power,
                heart_rate=hr,
                cadence=cadence if power > 0 else 0,
                speed=speed,
                distance=distance,
                lat=lat,
                lon=lon,
                altitude=altitude,
            )
        )
        distance += speed
    return out


def _file_id(spec: RideSpec) -> FileIdMessage:
    msg = FileIdMessage()
    msg.type = FileType.ACTIVITY
    if spec.source is Source.ZWIFT:
        msg.manufacturer = Manufacturer.ZWIFT.value
        msg.product = 0
    else:
        msg.manufacturer = Manufacturer.GARMIN.value
        msg.product = GarminProduct.EDGE_540.value
    msg.serial_number = spec.serial_number
    msg.time_created = int(spec.start.timestamp()) * 1000
    return msg


def _timer_event(timestamp_ms: int, event_type: EventType) -> EventMessage:
    msg = EventMessage()
    msg.timestamp = timestamp_ms
    msg.event = Event.TIMER
    msg.event_type = event_type
    return msg


def _record(s: Sample) -> RecordMessage:
    msg = RecordMessage()
    msg.timestamp = s.timestamp_ms
    msg.position_lat = s.lat
    msg.position_long = s.lon
    msg.altitude = s.altitude
    msg.distance = s.distance
    msg.speed = s.speed
    msg.power = s.power
    msg.heart_rate = s.heart_rate
    msg.cadence = s.cadence
    return msg


def _ascent(rows: Iterable[Sample]) -> int:
    return round(sum(max(0.0, b.altitude - a.altitude) for a, b in pairwise(rows)))


def _summary(msg: LapMessage | SessionMessage, spec: RideSpec, rows: list[Sample]) -> None:
    """Fill the totals that lap and session messages share."""
    elapsed = len(rows)
    end_ms = rows[-1].timestamp_ms + 1000
    total_distance = rows[-1].distance + rows[-1].speed
    msg.timestamp = end_ms
    msg.start_time = rows[0].timestamp_ms
    msg.start_position_lat = rows[0].lat
    msg.start_position_long = rows[0].lon
    msg.event = Event.LAP if isinstance(msg, LapMessage) else Event.SESSION
    msg.event_type = EventType.STOP
    msg.sport = Sport.CYCLING
    msg.sub_sport = SubSport.VIRTUAL_ACTIVITY if spec.source is Source.ZWIFT else SubSport.ROAD
    msg.total_elapsed_time = float(elapsed)
    msg.total_timer_time = float(elapsed)
    msg.total_distance = total_distance
    msg.avg_speed = total_distance / elapsed
    msg.max_speed = max(r.speed for r in rows)
    msg.avg_power = round(sum(r.power for r in rows) / elapsed)
    msg.max_power = max(r.power for r in rows)
    msg.avg_heart_rate = round(sum(r.heart_rate for r in rows) / elapsed)
    msg.max_heart_rate = max(r.heart_rate for r in rows)
    msg.avg_cadence = round(sum(r.cadence for r in rows) / elapsed)
    msg.max_cadence = max(r.cadence for r in rows)
    msg.total_ascent = _ascent(rows)


def build(spec: RideSpec) -> bytes:
    """Encode one ride as a FIT activity file."""
    rows = samples(spec)
    end_ms = rows[-1].timestamp_ms + 1000

    builder = FitFileBuilder(auto_define=True)
    builder.add(_file_id(spec))
    builder.add(_timer_event(rows[0].timestamp_ms, EventType.START))
    builder.add_all([_record(s) for s in rows])
    builder.add(_timer_event(end_ms, EventType.STOP_ALL))

    lap = LapMessage()
    _summary(lap, spec, rows)
    builder.add(lap)

    session = SessionMessage()
    _summary(session, spec, rows)
    session.first_lap_index = 0
    session.num_laps = 1
    builder.add(session)

    activity = ActivityMessage()
    activity.timestamp = end_ms
    activity.total_timer_time = float(len(rows))
    activity.num_sessions = 1
    activity.type = Activity.MANUAL
    activity.event = Event.ACTIVITY
    activity.event_type = EventType.STOP
    builder.add(activity)

    return builder.build().to_bytes()


def build_all() -> dict[str, bytes]:
    """Every fixture file, keyed by file name."""
    files = {f"{spec.name}.fit": build(spec) for spec in RIDES}
    for copy_name, source_name in DUPLICATES.items():
        files[f"{copy_name}.fit"] = files[f"{source_name}.fit"]
    for name, (source_name, keep) in CORRUPT.items():
        files[f"{name}.fit"] = files[f"{source_name}.fit"][:keep]
    return files


def write_all(out_dir: Path = FIT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in sorted(build_all().items()):
        path = out_dir / name
        path.write_bytes(data)
        written.append(path)
    return written


def main() -> None:
    for path in write_all():
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    main()
