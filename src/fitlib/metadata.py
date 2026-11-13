"""Rules for what users add to rides: tag names, and which bike a ride gets by default."""

from __future__ import annotations

from collections.abc import Iterable

from fitlib.models import BikeDefault, BikeSlot, RideSummary, Source

MAX_TAG_LENGTH = 40


class InvalidTag(ValueError):
    """A tag is empty, too long, or contains a comma."""


def normalize_tag(tag: str) -> str:
    """Put a tag in its stored form, so "Z2", " z2 " and "z2" are the same tag.

    Args:
        tag: The tag as typed.

    Returns:
        The tag trimmed, lower-cased, with inner runs of spaces collapsed to one.

    Raises:
        InvalidTag: The tag is empty, longer than ``MAX_TAG_LENGTH``, or contains a comma.
    """
    clean = " ".join(tag.split()).lower()
    if not clean:
        raise InvalidTag("Tags can't be empty.")
    if "," in clean:
        raise InvalidTag(f"Tags can't contain commas: {tag!r}. Give each tag separately.")
    if len(clean) > MAX_TAG_LENGTH:
        raise InvalidTag(f"Tags can be at most {MAX_TAG_LENGTH} characters: {tag!r}.")
    return clean


def slot_for(summary: RideSummary) -> BikeSlot:
    """Work out which default-bike slot a ride falls in.

    Args:
        summary: The ride's summary.

    Returns:
        ``zwift`` for Zwift rides, ``indoor`` for other indoor rides, else ``outdoor``.
    """
    if summary.source is Source.ZWIFT:
        return BikeSlot.ZWIFT
    return BikeSlot.INDOOR if summary.indoor else BikeSlot.OUTDOOR


def default_bike(defaults: Iterable[BikeDefault], summary: RideSummary) -> str | None:
    """Find the default bike for a ride, from the dated defaults for its slot.

    Args:
        defaults: Every default-bike entry, in any order.
        summary: The ride's summary.

    Returns:
        The bike id of the latest entry for the ride's slot on or before its local date, or
        ``None`` if there is none or that entry stops defaulting.
    """
    slot = slot_for(summary)
    day = (summary.local_start or summary.start).date()
    entries = sorted(
        (d for d in defaults if d.slot is slot and d.effective_from <= day),
        key=lambda d: d.effective_from,
    )
    return entries[-1].bike_id if entries else None
