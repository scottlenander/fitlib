"""Behaviour every ``BlobStore`` must have, plus the Parquet stream store on top of it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest

from fitlib.store.interfaces import BlobNotFound, BlobStore, InvalidBlobKey
from fitlib.store.local import FsBlobStore
from fitlib.store.memory import MemoryBlobStore
from fitlib.store.streams import StreamStore, raw_key, stream_key


@pytest.fixture(params=["fs", "memory"])
def blobs(request: pytest.FixtureRequest, tmp_path: Path) -> BlobStore:
    """Provide each blob store implementation in turn, empty.

    Args:
        request: Pytest request; its param picks the implementation.
        tmp_path: Folder for the filesystem store.

    Returns:
        A filesystem or in-memory blob store.
    """
    if request.param == "fs":
        return FsBlobStore(tmp_path / "blobs")
    return MemoryBlobStore()


def test_put_then_get_returns_the_same_bytes(blobs: BlobStore):
    """Stored bytes come back unchanged.

    Given: 1 KB of binary data stored under ``raw/ab/abc.fit``.
    Expect: ``get`` returns the same bytes and ``exists`` is true.
    """
    data = bytes(range(256)) * 4

    blobs.put("raw/ab/abc.fit", data)

    assert blobs.get("raw/ab/abc.fit") == data
    assert blobs.exists("raw/ab/abc.fit")


def test_put_replaces_existing_blob(blobs: BlobStore):
    """Writing to an existing key replaces its contents.

    Given: a key written twice with different bytes.
    Expect: the second value is what's stored.
    """
    blobs.put("streams/2025/x.parquet", b"old")

    blobs.put("streams/2025/x.parquet", b"new")

    assert blobs.get("streams/2025/x.parquet") == b"new"


def test_missing_blob_raises_and_delete_is_idempotent(blobs: BlobStore):
    """Reading a missing key is an error; deleting a missing key is not.

    Given: a key that is stored, deleted, then deleted again.
    Expect: no error on either delete; afterwards ``exists`` is false and ``get`` raises
    ``BlobNotFound``.
    """
    blobs.put("raw/aa/a.fit", b"x")

    blobs.delete("raw/aa/a.fit")
    blobs.delete("raw/aa/a.fit")

    assert not blobs.exists("raw/aa/a.fit"), "deleted blob should be gone"
    with pytest.raises(BlobNotFound):
        blobs.get("raw/aa/a.fit")


def test_list_filters_by_prefix_and_sorts(blobs: BlobStore):
    """Keys can be listed by prefix, in sorted order.

    Given: two raw files and one stream, written out of order.
    Expect: the ``raw/`` prefix lists only the raw files, sorted; no prefix lists all three.
    """
    for key in ("raw/bb/b.fit", "streams/2025/s.parquet", "raw/aa/a.fit"):
        blobs.put(key, b"x")

    raw = blobs.list("raw/")
    everything = blobs.list()

    assert raw == ["raw/aa/a.fit", "raw/bb/b.fit"]
    assert everything == ["raw/aa/a.fit", "raw/bb/b.fit", "streams/2025/s.parquet"]


@pytest.mark.parametrize("key", ["", "../escape", "/abs/path", "raw//double", "raw/./x", "Raw/X"])
def test_invalid_keys_are_rejected(blobs: BlobStore, key: str):
    """Keys can't escape the store or use odd paths.

    Given: an empty, parent-relative, absolute, double-slash, dot-segment or upper-case key.
    Expect: ``put`` raises ``InvalidBlobKey``.
    """
    with pytest.raises(InvalidBlobKey):
        blobs.put(key, b"x")


def test_fs_store_writes_plain_files_and_leaves_no_temp_files(tmp_path: Path):
    """The filesystem store keeps each blob as a file at its key's path.

    Given: a blob written to an ``FsBlobStore`` rooted at ``tmp/blobs``.
    Expect: the file exists at ``blobs/raw/ab/abc.fit`` and no temporary files remain.
    """
    root = tmp_path / "blobs"
    store = FsBlobStore(root)

    store.put("raw/ab/abc.fit", b"fit")

    files = sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())
    assert files == ["raw/ab/abc.fit"], "only the blob itself should be on disk"


def test_blob_keys_have_the_documented_layout():
    """Raw files and streams are laid out as the plan describes.

    Given: a sha256 and a ride id starting in 2025.
    Expect: ``raw/<first 2 hex>/<sha>.fit`` and ``streams/<year>/<ride id>.parquet``.
    """
    sha = "ab" + "0" * 62
    start = datetime(2025, 8, 2, tzinfo=UTC)

    assert raw_key(sha) == f"raw/ab/{sha}.fit"
    assert stream_key("ride-id", start) == "streams/2025/ride-id.parquet"


def test_stream_store_round_trips_a_frame(blobs: BlobStore):
    """A ride's samples survive being stored as Parquet.

    Given: a small frame with integer, float, boolean and missing values.
    Expect: the frame read back is identical, including column types and nulls.
    """
    streams = StreamStore(blobs)
    start = datetime(2025, 8, 2, tzinfo=UTC)
    frame = pl.DataFrame(
        {
            "t": [0, 1, 2],
            "active": [True, True, False],
            "power": [200, None, 210],
            "lat": [50.39, 50.391, None],
        },
        schema={"t": pl.Int32, "active": pl.Boolean, "power": pl.Int32, "lat": pl.Float64},
    )

    streams.put("ride-id", start, frame)
    loaded = streams.get("ride-id", start)

    assert loaded.equals(frame), "the stream should read back unchanged"
    assert blobs.exists(stream_key("ride-id", start))
