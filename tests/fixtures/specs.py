"""Declarative specs for the synthetic .fit fixtures.

Every fixture is fully synthetic: no real ride data. Each spec describes a ride as a list of
constant-power segments, so later phases can assert exact metrics (average power, NP, TSS, best
efforts) against values worked out by hand from the spec.

Generated files live in ``tests/fixtures/fit/`` and are rebuilt with
``uv run python -m tests.fixtures.generate``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class RideSpec:
    name: str
    source: Source
    start: datetime
    segments: tuple[Segment, ...]
    loop: Loop
    # Heart rate is a fixed linear function of power: hr = hr_base + hr_per_watt * power.
    hr_base: float = 90
    hr_per_watt: float = 0.25
    serial_number: int = 0x0F17_0001
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_s(self) -> int:
        return sum(s.seconds for s in self.segments)

    def powers(self) -> list[int]:
        """Power for every second of the ride, in order."""
        return [s.power for s in self.segments for _ in range(s.seconds)]

    def cadences(self) -> list[int]:
        return [s.cadence for s in self.segments for _ in range(s.seconds)]

    def heart_rates(self) -> list[int]:
        return [round(self.hr_base + self.hr_per_watt * p) for p in self.powers()]


def _intervals(
    warmup: Segment, work: Segment, rest: Segment, reps: int, cooldown: Segment
) -> tuple[Segment, ...]:
    return (warmup, *[seg for _ in range(reps) for seg in (work, rest)], cooldown)


RIDES: tuple[RideSpec, ...] = (
    RideSpec(
        name="zwift_watopia_steady_60min",
        source=Source.ZWIFT,
        start=datetime(2025, 8, 2, 6, 30, tzinfo=UTC),
        segments=(Segment(seconds=3600, power=200),),
        loop=WATOPIA_LOOP,
        serial_number=0x0F17_0001,
    ),
    RideSpec(
        name="garmin_nord_intervals_5x4",
        source=Source.GARMIN,
        start=datetime(2025, 8, 5, 17, 0, tzinfo=UTC),
        segments=_intervals(
            warmup=Segment(seconds=600, power=150, cadence=85),
            work=Segment(seconds=240, power=300, cadence=95),
            rest=Segment(seconds=240, power=120, cadence=80),
            reps=5,
            cooldown=Segment(seconds=600, power=130, cadence=85),
        ),
        loop=NORD_LOOP,
        serial_number=0x0F17_0002,
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
