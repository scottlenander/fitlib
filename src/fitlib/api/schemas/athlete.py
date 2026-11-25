"""The athlete history, today's values and year of birth."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from fitlib.metrics.load import ThresholdSource


class AthleteValuesIn(BaseModel):
    """Athlete values from a date. Values left out carry forward from earlier entries.

    Attributes:
        ftp: FTP in watts.
        weight_kg: Body weight in kilograms.
        max_hr: Max heart rate in bpm.
        threshold_hr: Threshold heart rate in bpm, for TSS on rides without power.
    """

    model_config = ConfigDict(extra="forbid")

    ftp: Annotated[int | None, Field(gt=0, le=2000)] = None
    weight_kg: Annotated[float | None, Field(gt=0, le=300)] = None
    max_hr: Annotated[int | None, Field(gt=0, le=250)] = None
    threshold_hr: Annotated[int | None, Field(gt=0, le=250)] = None


class AthleteEntryOut(AthleteValuesIn):
    """One dated entry in the athlete history.

    Attributes:
        effective_from: The first day the entry applies.
    """

    effective_from: date


class Athlete(BaseModel):
    """The athlete history and the values in effect today.

    Attributes:
        history: Every entry, oldest first.
        today: FTP, weight, max and threshold heart rate in effect today, each from the
            latest entry that sets it.
        birth_year: The rider's year of birth, if given.
        estimated_threshold_hr: Today's threshold heart rate estimated from age; ``null``
            without a year of birth.
        threshold_hr_today: The threshold heart rate a ride today would use: set, from your
            rides, or from your age.
        threshold_hr_source_today: Where ``threshold_hr_today`` comes from.
    """

    history: list[AthleteEntryOut]
    today: AthleteValuesIn
    birth_year: int | None
    estimated_threshold_hr: int | None
    threshold_hr_today: int | None
    threshold_hr_source_today: ThresholdSource | None


class BirthYearIn(BaseModel):
    """The rider's year of birth.

    Attributes:
        birth_year: The year, or ``null`` to clear it.
    """

    model_config = ConfigDict(extra="forbid")

    birth_year: int | None
