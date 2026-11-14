"""Editing a ride's metadata, and the tag list that follows from it."""

from __future__ import annotations

import pytest

from tests.api.conftest import Api

ZWIFT = "zwift_watopia_steady_60min.fit"
INTERVALS = "garmin_nord_intervals_5x4.fit"


def add_bike(api: Api, name: str) -> str:
    """Add a bike through the API.

    Args:
        api: The client.
        name: The bike's name.

    Returns:
        The new bike's id.
    """
    return api.client.post("/api/bikes", json={"name": name}).json()["id"]


def test_patch_sets_every_field_and_returns_the_ride(writer: Api):
    """Every metadata field can be set at once, and the reply is the updated ride.

    Given: a bike, and a patch with name, notes, effort, bike and tags for the Zwift ride.
    Expect: the reply and a fresh fetch both show the new values, with tags tidied (and
    sorted, as the catalog keeps them) and the
    bike marked as set by hand.
    """
    bike_id = add_bike(writer, "Giant Contend 1")
    patch = {
        "name": "  Tempo in Watopia ",
        "notes": "Felt good",
        "rpe": 6,
        "bike_id": bike_id,
        "tags": ["Tempo", " base ", "tempo"],
    }

    response = writer.client.patch(f"/api/rides/{writer.ids[ZWIFT]}/meta", json=patch)
    fetched = writer.client.get(f"/api/rides/{writer.ids[ZWIFT]}").json()

    assert response.status_code == 200
    assert response.json() == fetched, "the reply should be the ride as stored"
    assert fetched["name"] == "Tempo in Watopia"
    assert fetched["meta"] == {
        "name": "Tempo in Watopia",
        "notes": "Felt good",
        "rpe": 6,
        "bike": {"id": bike_id, "name": "Giant Contend 1"},
        "bike_from_default": False,
        "tags": ["base", "tempo"],
    }


def test_patch_leaves_out_fields_unchanged_and_null_clears(writer: Api):
    """Fields left out stay; ``null`` (or blank text) clears.

    Given: a ride with notes, effort and tags, then a patch clearing the notes (blank) and
    effort (null) and leaving tags out.
    Expect: notes and effort cleared; tags kept.
    """
    url = f"/api/rides/{writer.ids[ZWIFT]}/meta"
    writer.client.patch(url, json={"notes": "x", "rpe": 4, "tags": ["base"]})

    response = writer.client.patch(url, json={"notes": "   ", "rpe": None})

    meta = response.json()["meta"]
    assert (meta["notes"], meta["rpe"]) == (None, None)
    assert meta["tags"] == ["base"], "tags weren't in the patch, so they should stay"


def test_patch_works_with_an_id_prefix(writer: Api):
    """Rides can be edited by the same prefixes they're fetched by.

    Given: the first 8 characters of the Zwift ride's id.
    Expect: the edit lands on that ride.
    """
    prefix = writer.ids[ZWIFT][:8]

    response = writer.client.patch(f"/api/rides/{prefix}/meta", json={"rpe": 3})

    assert response.json()["id"] == writer.ids[ZWIFT]


@pytest.mark.parametrize(
    ("patch", "status"),
    [
        ({"rpe": 11}, 422),
        ({"rpe": 0}, 422),
        ({"tags": ["a,b"]}, 422),
        ({"tags": ["x" * 41]}, 422),
        ({"bike_id": "no-such-bike"}, 404),
        ({"colour": "red"}, 422),
    ],
    ids=["rpe-high", "rpe-low", "comma-tag", "long-tag", "unknown-bike", "unknown-field"],
)
def test_patch_rejects_bad_values_and_changes_nothing(writer: Api, patch: dict, status: int):
    """Bad values are refused, and nothing in the patch is saved.

    Given: an effort outside 1-10, a bad tag, an unknown bike or an unknown field.
    Expect: the error status, and the ride's metadata still empty.
    """
    url = f"/api/rides/{writer.ids[ZWIFT]}"

    response = writer.client.patch(f"{url}/meta", json=patch)

    assert response.status_code == status
    meta = writer.client.get(url).json()["meta"]
    assert meta["rpe"] is None and meta["tags"] == [] and meta["bike"] is None


def test_patch_of_unknown_ride_is_404(writer: Api):
    """Editing a ride that doesn't exist is a 404.

    Given: an unknown id.
    Expect: 404.
    """
    response = writer.client.patch("/api/rides/zzzzzzzz/meta", json={"rpe": 5})

    assert response.status_code == 404


def test_tags_count_rides_and_filter_the_list(writer: Api):
    """Tags in use are counted, and the list can filter on several at once.

    Given: two rides tagged ``base``, one of them also ``tempo``.
    Expect: tag counts of 1 and 2; filtering on both tags finds only the ride with both.
    """
    writer.client.patch(f"/api/rides/{writer.ids[ZWIFT]}/meta", json={"tags": ["base", "tempo"]})
    writer.client.patch(f"/api/rides/{writer.ids[INTERVALS]}/meta", json={"tags": ["base"]})

    counts = writer.client.get("/api/tags").json()
    both = writer.client.get("/api/rides", params={"tag": ["base", "Tempo"]}).json()

    assert counts == [{"name": "base", "rides": 2}, {"name": "tempo", "rides": 1}]
    assert [r["id"] for r in both["items"]] == [writer.ids[ZWIFT]]


def test_text_search_finds_notes_and_bike_names(writer: Api):
    """Search covers what the user adds: notes and the bike's name.

    Given: notes on the interval ride and a bike on the Zwift ride.
    Expect: searching a word from the notes finds the interval ride; the bike's name finds
    the Zwift ride.
    """
    bike_id = add_bike(writer, "Giant Contend 1")
    writer.client.patch(f"/api/rides/{writer.ids[INTERVALS]}/meta", json={"notes": "windy"})
    writer.client.patch(f"/api/rides/{writer.ids[ZWIFT]}/meta", json={"bike_id": bike_id})

    by_notes = writer.client.get("/api/rides", params={"q": "windy"}).json()["items"]
    by_bike = writer.client.get("/api/rides", params={"q": "contend"}).json()["items"]

    assert [r["id"] for r in by_notes] == [writer.ids[INTERVALS]]
    assert [r["id"] for r in by_bike] == [writer.ids[ZWIFT]]
