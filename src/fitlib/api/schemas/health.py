"""The server's health and the library's state."""

from __future__ import annotations

from pydantic import BaseModel

from fitlib.services.recompute import RecomputeState


class RecomputeProgress(BaseModel):
    """How far the server's background recompute has got.

    Attributes:
        total: Rides it set out to recompute.
        done: Rides handled so far.
    """

    total: int
    done: int

    @classmethod
    def of(cls, state: RecomputeState | None) -> RecomputeProgress | None:
        """Describe a background recompute's state.

        Args:
            state: The state, or ``None`` when none is running.

        Returns:
            Its progress, or ``None``.
        """
        return None if state is None else cls(total=state.total, done=state.done)


class Health(BaseModel):
    """The server's status.

    Attributes:
        status: Always ``"ok"`` when the server answers.
        version: fitlib's version.
        rides: How many rides the library holds.
        outdated_rides: Rides computed with older calculations; the server brings them up
            to date in the background, or ``fitlib recompute`` does.
        recompute: The background recompute's progress while it runs.
    """

    status: str
    version: str
    rides: int
    outdated_rides: int
    recompute: RecomputeProgress | None
