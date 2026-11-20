"""Rules for what users add to rides: tag names, edits, and which bike a ride gets by default."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from fitlib.models import BikeDefault, BikeSlot, RideMeta, RideSummary, Source

MAX_TAG_LENGTH = 40
# Rides that can be edited at once, from the library or the API.
MAX_BULK_RIDES = 500


class Keep(Enum):
    """Marks a field an edit leaves as it is (``None`` clears a field instead)."""

    KEEP = "keep"


KEEP = Keep.KEEP


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


def normalize_tags(tags: Iterable[str]) -> tuple[str, ...]:
    """Put tags in their stored form, without repeats.

    Args:
        tags: The tags as typed.

    Returns:
        The stored forms, in the order first given.

    Raises:
        InvalidTag: A tag is empty, too long or contains a comma.
    """
    return tuple(dict.fromkeys(normalize_tag(t) for t in tags))


@dataclass(frozen=True)
class MetaEdit:
    """A change to what the user added to rides, applied the same way to each ride.

    Fields set to ``KEEP`` stay as they are; ``None`` clears them. Tags are in stored form.

    Attributes:
        name: The new name.
        notes: The new notes.
        rpe: The new perceived effort, 1-10.
        bike_id: The new bike; setting or clearing it counts as chosen by the user.
        tags: All the ride's tags, replacing the current ones.
        add_tags: Tags to add (after ``tags`` and ``remove_tags``).
        remove_tags: Tags to take off.
    """

    name: str | None | Keep = KEEP
    notes: str | None | Keep = KEEP
    rpe: int | None | Keep = KEEP
    bike_id: str | None | Keep = KEEP
    tags: tuple[str, ...] | Keep = KEEP
    add_tags: tuple[str, ...] = ()
    remove_tags: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Whether the edit changes nothing."""
        fields = (self.name, self.notes, self.rpe, self.bike_id, self.tags)
        return all(f is KEEP for f in fields) and not self.add_tags and not self.remove_tags


def apply_edit(meta: RideMeta, edit: MetaEdit) -> RideMeta:
    """Work out a ride's metadata after an edit.

    Args:
        meta: The ride's metadata now.
        edit: The change.

    Returns:
        The new metadata. Tags keep their order, removed ones dropped and new ones added
        at the end. A bike set or cleared by the edit is no longer from the defaults.
    """
    tags = meta.tags if isinstance(edit.tags, Keep) else edit.tags
    kept = [t for t in tags if t not in edit.remove_tags]
    return RideMeta(
        name=meta.name if isinstance(edit.name, Keep) else edit.name,
        notes=meta.notes if isinstance(edit.notes, Keep) else edit.notes,
        rpe=meta.rpe if isinstance(edit.rpe, Keep) else edit.rpe,
        bike_id=meta.bike_id if isinstance(edit.bike_id, Keep) else edit.bike_id,
        tags=tuple(dict.fromkeys([*kept, *edit.add_tags])),
        bike_from_default=meta.bike_from_default and isinstance(edit.bike_id, Keep),
    )


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
