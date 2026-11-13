"""Write the synthetic .fit fixtures described in ``specs.py``.

Usage (from the repo root)::

    uv run python -m tests.fixtures.generate

Output is deterministic: the same specs always produce byte-identical files, which
``tests/test_fixtures_current.py`` checks.
"""

from __future__ import annotations

import io
import math
import zipfile
from collections.abc import Sequence
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
# Fixed timestamp for zip members, so zips are byte-identical between runs.
ZIP_DATE_TIME = (2025, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Sample:
    """One riding second of the synthetic ride. ``None`` means the channel isn't recorded."""

    second: int  # riding seconds since the start (pauses excluded)
    timestamp_ms: int  # wall-clock time (pauses included)
    power: int | None
    heart_rate: int | None
    cadence: int
    speed: float
    distance: float
    lat: float | None
    lon: float | None
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
    """Every riding second of the ride, whether or not it is written to the file."""
    start_ms = int(spec.start.timestamp()) * 1000
    out: list[Sample] = []
    distance = 0.0
    rows = zip(spec.powers(), spec.heart_rates(), spec.cadences(), strict=True)
    for second, (power, hr, cadence) in enumerate(rows):
        speed = speed_for_power(power)
        lat, lon, altitude = position_on_loop(spec.loop, distance)
        out.append(
            Sample(
                second=second,
                timestamp_ms=start_ms + spec.offset_s(second) * 1000,
                power=power if spec.has_power else None,
                heart_rate=hr if spec.has_hr else None,
                cadence=cadence if power > 0 else 0,
                speed=speed,
                distance=distance,
                lat=lat if spec.has_gps else None,
                lon=lon if spec.has_gps else None,
                altitude=altitude,
            )
        )
        distance += speed
    return out


def written_samples(spec: RideSpec) -> list[Sample]:
    """The samples that appear as records in the file (all of them unless smart recording)."""
    every = samples(spec)
    return [every[second] for second in spec.recorded_seconds()]


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
    if s.lat is not None and s.lon is not None:
        msg.position_lat = s.lat
        msg.position_long = s.lon
    msg.altitude = s.altitude
    msg.distance = s.distance
    msg.speed = s.speed
    if s.power is not None:
        msg.power = s.power
    if s.heart_rate is not None:
        msg.heart_rate = s.heart_rate
    msg.cadence = s.cadence
    return msg


def _ascent(rows: Sequence[Sample]) -> int:
    return round(sum(max(0.0, b.altitude - a.altitude) for a, b in pairwise(rows)))


def _sport(spec: RideSpec) -> tuple[Sport, SubSport]:
    if spec.sport == "running":
        return Sport.RUNNING, SubSport.GENERIC
    return Sport.CYCLING, SubSport[spec.sub_sport.upper()]


def _summary(msg: LapMessage | SessionMessage, spec: RideSpec, rows: Sequence[Sample]) -> None:
    """Fill the totals that lap and session messages share, over ``rows`` (riding seconds)."""
    timer = len(rows)
    end_ms = rows[-1].timestamp_ms + 1000
    # Distance covered within these rows (laps start part-way through the ride).
    total_distance = rows[-1].distance + rows[-1].speed - rows[0].distance
    msg.timestamp = end_ms
    msg.start_time = rows[0].timestamp_ms
    if rows[0].lat is not None and rows[0].lon is not None:
        msg.start_position_lat = rows[0].lat
        msg.start_position_long = rows[0].lon
    msg.event = Event.LAP if isinstance(msg, LapMessage) else Event.SESSION
    msg.event_type = EventType.STOP
    msg.sport, msg.sub_sport = _sport(spec)
    msg.total_elapsed_time = (end_ms - rows[0].timestamp_ms) / 1000
    msg.total_timer_time = float(timer)
    msg.total_distance = total_distance
    msg.avg_speed = total_distance / timer
    msg.max_speed = max(r.speed for r in rows)
    powers = [r.power for r in rows if r.power is not None]
    if powers:
        msg.avg_power = round(sum(powers) / len(powers))
        msg.max_power = max(powers)
    heart_rates = [r.heart_rate for r in rows if r.heart_rate is not None]
    if heart_rates:
        msg.avg_heart_rate = round(sum(heart_rates) / len(heart_rates))
        msg.max_heart_rate = max(heart_rates)
    msg.avg_cadence = round(sum(r.cadence for r in rows) / timer)
    msg.max_cadence = max(r.cadence for r in rows)
    msg.total_ascent = _ascent(rows)


def _lap_ranges(spec: RideSpec) -> list[range]:
    """Riding seconds covered by each lap."""
    if not spec.lap_per_segment:
        return [range(spec.duration_s)]
    ranges, start = [], 0
    for segment in spec.segments:
        ranges.append(range(start, start + segment.seconds))
        start += segment.seconds
    return ranges


def build(spec: RideSpec) -> bytes:
    """Encode one ride as a FIT activity file."""
    every = samples(spec)
    written = {s.second: s for s in written_samples(spec)}
    end_ms = every[-1].timestamp_ms + 1000

    builder = FitFileBuilder(auto_define=True)
    builder.add(_file_id(spec))
    builder.add(_timer_event(every[0].timestamp_ms, EventType.START))
    pauses = {p.after_s: p for p in spec.pauses}
    for sample in every:
        if sample.second in pauses:
            builder.add(
                _timer_event(
                    sample.timestamp_ms - pauses[sample.second].seconds * 1000, EventType.STOP_ALL
                )
            )
            builder.add(_timer_event(sample.timestamp_ms, EventType.START))
        if sample.second in written:
            builder.add(_record(sample))
    builder.add(_timer_event(end_ms, EventType.STOP_ALL))

    lap_ranges = _lap_ranges(spec)
    for lap_range in lap_ranges:
        lap = LapMessage()
        _summary(lap, spec, [every[i] for i in lap_range])
        builder.add(lap)

    session = SessionMessage()
    _summary(session, spec, every)
    session.first_lap_index = 0
    session.num_laps = len(lap_ranges)
    builder.add(session)

    activity = ActivityMessage()
    activity.timestamp = end_ms
    activity.total_timer_time = float(spec.duration_s)
    activity.num_sessions = 1
    activity.type = Activity.MANUAL
    activity.event = Event.ACTIVITY
    activity.event_type = EventType.STOP
    builder.add(activity)

    return builder.build().to_bytes()


def _zip(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(members.items()):
            archive.writestr(zipfile.ZipInfo(name, date_time=ZIP_DATE_TIME), data)
    return buffer.getvalue()


def build_rides() -> dict[str, bytes]:
    """Every ride's FIT bytes keyed by spec name, before any zipping."""
    return {spec.name: build(spec) for spec in RIDES}


def build_all() -> dict[str, bytes]:
    """Every fixture file as committed in ``tests/fixtures/fit/``, keyed by file name."""
    rides = build_rides()
    files: dict[str, bytes] = {}
    zips: dict[str, dict[str, bytes]] = {}
    for spec in RIDES:
        if spec.zip_name:
            zips.setdefault(spec.zip_name, {})[f"{spec.name}.fit"] = rides[spec.name]
        else:
            files[f"{spec.name}.fit"] = rides[spec.name]
    for zip_name, members in zips.items():
        files[f"{zip_name}.zip"] = _zip(members)
    for copy_name, source_name in DUPLICATES.items():
        files[f"{copy_name}.fit"] = rides[source_name]
    for name, (source_name, keep) in CORRUPT.items():
        files[f"{name}.fit"] = rides[source_name][:keep]
    return files


def write_all(out_dir: Path = FIT_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    expected = build_all()
    for stale in out_dir.iterdir():
        if stale.is_file() and stale.name not in expected:
            stale.unlink()
    written = []
    for name, data in sorted(expected.items()):
        path = out_dir / name
        path.write_bytes(data)
        written.append(path)
    return written


def main() -> None:
    for path in write_all():
        print(f"wrote {path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path}")


if __name__ == "__main__":
    main()
