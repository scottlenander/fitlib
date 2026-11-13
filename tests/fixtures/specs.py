"""Declarative specs for the synthetic .fit fixtures.

Every fixture is fully synthetic: no real ride data. Each spec describes a ride as a list of
constant-power segments, so later phases can assert exact metrics (average power, NP, TSS, best
efforts) against values worked out by hand from the spec.

Generated files live in ``tests/fixtures/fit/`` and are rebuilt with
``uv run python -m tests.fixtures.generate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Source(StrEnum):
    ZWIFT = "zwift"
    GARMIN = "garmin"


@dataclass(frozen=True)
class Segment:
    """A block of constant output, sampled once per second."""

    seconds: int
    power: int
    cadence: int = 90


@dataclass(frozen=True)
class Loop:
    """A circular course, ridden repeatedly. Altitude follows one sine wave per lap."""

    center_lat: float
    center_lon: float
    lap_length_m: float
    base_altitude_m: float
    altitude_amplitude_m: float


# Outdoor loops: around 50°23'48"N, 3°24'55"E, about 35 km south-east of Roubaix, France.
NORD_LAT = 50 + 23 / 60 + 48 / 3600
NORD_LON = 3 + 24 / 60 + 55 / 3600

# Zwift writes its virtual worlds onto real coordinates; Watopia sits in the Pacific near here.
WATOPIA_LAT = -11.64
WATOPIA_LON = 166.95

NORD_LOOP = Loop(
    NORD_LAT, NORD_LON, lap_length_m=5_000, base_altitude_m=30, altitude_amplitude_m=10
)
WATOPIA_LOOP = Loop(
    WATOPIA_LAT, WATOPIA_LON, lap_length_m=9_000, base_altitude_m=10, altitude_amplitude_m=20
)


class Recording(StrEnum):
    EVERY_SECOND = "every_second"
    # Garmin "smart recording": samples at irregular 1-5 s intervals.
    SMART = "smart"


# Gaps between samples under smart recording, repeated in this order.
SMART_RECORDING_STEPS = (1, 3, 5, 2, 4)


@dataclass(frozen=True)
class Pause:
    """The timer stops after ``after_s`` seconds of riding, for ``seconds`` seconds."""

    after_s: int
    seconds: int


@dataclass(frozen=True)
class RideSpec:
    name: str
    source: Source
    start: datetime
    segments: tuple[Segment, ...]
    loop: Loop
    sport: str = "cycling"
    # Garmin indoor trainer ride: no GPS, sub-sport indoor_cycling. Zwift rides are always virtual.
    indoor: bool = False
    has_power: bool = True
    has_hr: bool = True
    pauses: tuple[Pause, ...] = ()
    recording: Recording = Recording.EVERY_SECOND
    # One lap per segment (as if the lap button were pressed); otherwise one lap for the ride.
    lap_per_segment: bool = False
    # Written inside this .zip in tests/fixtures/fit/ instead of as a standalone .fit file.
    zip_name: str | None = None
    # Heart rate is a fixed linear function of power: hr = hr_base + hr_per_watt * power.
    hr_base: float = 90
    hr_per_watt: float = 0.25
    serial_number: int = 0x0F17_0001
    # Local time minus UTC, written to the activity message. Garmin rides are in CEST (+2 h);
    # Zwift files carry no local time.
    utc_offset_s: int | None = None

    @property
    def duration_s(self) -> int:
        """Seconds of riding (timer running)."""
        return sum(s.seconds for s in self.segments)

    @property
    def elapsed_s(self) -> int:
        """Seconds from start to finish, including pauses."""
        return self.duration_s + sum(p.seconds for p in self.pauses)

    @property
    def has_gps(self) -> bool:
        return not self.indoor

    @property
    def sub_sport(self) -> str:
        if self.sport != "cycling":
            return "generic"
        if self.source is Source.ZWIFT:
            return "virtual_activity"
        return "indoor_cycling" if self.indoor else "road"

    def offset_s(self, second: int) -> int:
        """Seconds from the start at which riding second ``second`` happens, after pauses."""
        return second + sum(p.seconds for p in self.pauses if p.after_s <= second)

    def recorded_seconds(self) -> list[int]:
        """The riding seconds that get a record in the file."""
        if self.recording is Recording.EVERY_SECOND:
            return list(range(self.duration_s))
        seconds, second, step = [], 0, 0
        while second < self.duration_s:
            seconds.append(second)
            second += SMART_RECORDING_STEPS[step % len(SMART_RECORDING_STEPS)]
            step += 1
        if seconds[-1] != self.duration_s - 1:
            seconds.append(self.duration_s - 1)
        return seconds

    def powers(self) -> list[int]:
        """Power for every riding second, in order."""
        return [s.power for s in self.segments for _ in range(s.seconds)]

    def cadences(self) -> list[int]:
        return [s.cadence for s in self.segments for _ in range(s.seconds)]

    def heart_rates(self) -> list[int]:
        return [round(self.hr_base + self.hr_per_watt * p) for p in self.powers()]


def _intervals(
    warmup: Segment, work: Segment, rest: Segment, reps: int, cooldown: Segment
) -> tuple[Segment, ...]:
    return (warmup, *[seg for _ in range(reps) for seg in (work, rest)], cooldown)


CEST = 2 * 3600

ZWIFT_STEADY_START = datetime(2025, 8, 2, 6, 30, tzinfo=UTC)

RIDES: tuple[RideSpec, ...] = (
    RideSpec(
        name="zwift_watopia_steady_60min",
        source=Source.ZWIFT,
        start=ZWIFT_STEADY_START,
        segments=(Segment(seconds=3600, power=200),),
        loop=WATOPIA_LOOP,
        serial_number=0x0F17_0001,
    ),
    RideSpec(
        name="garmin_nord_intervals_5x4",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 5, 17, 0, tzinfo=UTC),
        segments=_intervals(
            warmup=Segment(seconds=600, power=150, cadence=85),
            work=Segment(seconds=240, power=300, cadence=95),
            rest=Segment(seconds=240, power=120, cadence=80),
            reps=5,
            cooldown=Segment(seconds=600, power=130, cadence=85),
        ),
        loop=NORD_LOOP,
        lap_per_segment=True,
        serial_number=0x0F17_0002,
    ),
    RideSpec(
        name="garmin_nord_pause_10min",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 9, 8, 0, tzinfo=UTC),
        segments=(Segment(seconds=1800, power=190),),
        loop=NORD_LOOP,
        pauses=(Pause(after_s=900, seconds=600),),
        serial_number=0x0F17_0003,
    ),
    RideSpec(
        name="garmin_nord_smart_recording",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 12, 18, 0, tzinfo=UTC),
        segments=(Segment(seconds=1800, power=180),),
        loop=NORD_LOOP,
        recording=Recording.SMART,
        serial_number=0x0F17_0004,
    ),
    RideSpec(
        name="garmin_nord_hr_no_power",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 16, 9, 0, tzinfo=UTC),
        segments=(Segment(seconds=2700, power=170, cadence=88),),
        loop=NORD_LOOP,
        has_power=False,
        serial_number=0x0F17_0005,
    ),
    RideSpec(
        name="garmin_indoor_no_hr",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 19, 18, 30, tzinfo=UTC),
        segments=(Segment(seconds=1800, power=210),),
        loop=NORD_LOOP,
        indoor=True,
        has_hr=False,
        serial_number=0x0F17_0006,
    ),
    # The Zwift steady ride recorded a second time by a Garmin on the trainer, 30 s later.
    # Its name sorts after the Zwift file's, so the Zwift ride is imported first and kept.
    RideSpec(
        name="zwift_watopia_steady_60min_head_unit",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 2, 6, 30, 30, tzinfo=UTC),
        segments=(Segment(seconds=3600, power=200),),
        loop=NORD_LOOP,
        indoor=True,
        serial_number=0x0F17_0007,
    ),
    RideSpec(
        name="garmin_nord_run_20min",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 21, 7, 0, tzinfo=UTC),
        sport="running",
        segments=(Segment(seconds=1200, power=20, cadence=85),),
        loop=NORD_LOOP,
        has_power=False,
        serial_number=0x0F17_0008,
    ),
    RideSpec(
        name="garmin_export_ride_a",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 23, 7, 0, tzinfo=UTC),
        segments=(Segment(seconds=1200, power=160),),
        loop=NORD_LOOP,
        zip_name="garmin_export",
        serial_number=0x0F17_0009,
    ),
    RideSpec(
        name="garmin_export_ride_b",
        source=Source.GARMIN,
        utc_offset_s=CEST,
        start=datetime(2025, 8, 24, 7, 0, tzinfo=UTC),
        segments=(Segment(seconds=1500, power=175),),
        loop=NORD_LOOP,
        zip_name="garmin_export",
        serial_number=0x0F17_000A,
    ),
)

# Exact byte copies under another name, for dedupe tests: {copy_name: source_name}.
DUPLICATES: dict[str, str] = {
    "garmin_nord_intervals_5x4_copy": "garmin_nord_intervals_5x4",
}

# Truncated copies that no FIT decoder should accept: {name: (source_name, bytes_kept)}.
CORRUPT: dict[str, tuple[str, int]] = {
    "corrupt_truncated": ("zwift_watopia_steady_60min", 2_000),
}


def ride(name: str) -> RideSpec:
    for spec in RIDES:
        if spec.name == name:
            return spec
    raise KeyError(name)
