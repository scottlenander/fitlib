"""Pushing a library to a sync folder and restoring it: round trips, safety and privacy."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import re
import struct
from pathlib import Path

import pytest

from fitlib.config import Config
from fitlib.services.importing import Importer
from fitlib.services.watching import watch_folder
from fitlib.store.factory import (
    catalog_path,
    latest_schema_version,
    library_blobs,
    open_remote,
    open_stores,
    restore_catalog,
)
from fitlib.store.interfaces import BlobStore
from fitlib.store.local import FsBlobStore
from fitlib.sync.crypto import CannotDecrypt, WrongPassphrase, open_sealed
from fitlib.sync.engine import (
    GENERATION_SETTING,
    KEYFILE,
    MANIFEST,
    KeyMissing,
    NewerLibrary,
    NothingPushed,
    RemoteAhead,
    RemoteInUse,
    change_passphrase,
    library_id,
    local_generation,
    push,
    read_keyfile,
    remote_manifest,
    restore,
    setup,
    status,
    unlock,
)
from fitlib.sync.keys import MemoryKeyStore
from tests.fixtures.generate import FIT_DIR
from tests.unit.sync.conftest import FAST_KDF, PASSPHRASE, Synced, local, restore_into

EXTRA_RIDE = FIT_DIR.parent / "extra" / "garmin_arras_hr_only.fit"
NOTE = "Secret notes about the climb"
TAG = "hilltop"
OPAQUE_NAME = re.compile(r"objects/[0-9a-f]{2}/[0-9a-f]{64}")


class FailingRemote(FsBlobStore):
    """A sync folder whose writes start failing after a number of them, like a lost drive.

    Args:
        root: The folder.
        puts_allowed: Writes that succeed before the rest fail.
    """

    def __init__(self, root: Path, puts_allowed: int) -> None:
        super().__init__(root)
        self.puts_left = puts_allowed

    def put(self, key: str, data: bytes) -> None:
        """Store bytes, unless the allowed writes are used up.

        Args:
            key: Where to store them.
            data: The bytes.

        Raises:
            OSError: The allowed writes are used up.
        """
        if self.puts_left == 0:
            raise OSError("The drive went away")
        self.puts_left -= 1
        super().put(key, data)


def push_once(s: Synced, remote: BlobStore | None = None, force: bool = False):
    """Push the library once.

    Args:
        s: The synced library.
        remote: The sync folder to push to; the usual one by default.
        force: Push even if another computer pushed since.

    Returns:
        The push report.
    """
    with open_stores(s.config) as stores:
        keys = unlock(stores.catalog, s.remote, s.keystore)
        return push(local(stores), remote or s.remote, keys, force=force)


def library_contents(config: Config) -> tuple[dict[str, str], dict[str, bytes], str]:
    """Everything a restore must bring back.

    Args:
        config: The library.

    Returns:
        Each ride's display name, notes and tags by id; every blob's bytes by key; the
        library id.
    """
    with open_stores(config) as stores:
        rides = {
            i: repr((r.display_name, r.meta, r.summary))
            for i in stores.catalog.ride_ids()
            for r in [stores.catalog.get_ride(i)]
        }
        blobs = {k: stores.blobs.get(k) for k in stores.blobs.list()}
        return rides, blobs, library_id(stores.catalog)


def test_push_then_restore_brings_back_the_same_library(synced: Synced, tmp_path: Path):
    """A pushed library restores to the same rides, metadata, streams and original files.

    Given: The fixture library with a note and a tag on one ride and a watched folder,
        pushed, then restored into an empty library.
    Expect: Same rides (summaries and metadata), same blobs byte for byte, same library id;
        the watched folder stays behind; the restored library is at the pushed generation.
    """
    with open_stores(synced.config) as stores:
        ride_id = synced.ids["garmin_nord_intervals_5x4.fit"]
        ride = stores.catalog.get_ride(ride_id)
        stores.catalog.update_meta(ride_id, dataclasses.replace(ride.meta, notes=NOTE, tags=(TAG,)))
        stores.catalog.add_watch_folder(watch_folder(tmp_path / "watched"))
    report = push_once(synced)
    copy = Config(library=tmp_path / "restored")

    restore_into(copy, synced.remote, MemoryKeyStore())

    assert report.generation == 1
    assert library_contents(copy) == library_contents(synced.config)
    with open_stores(copy) as stores:
        assert stores.catalog.watch_folders() == [], "should leave this computer's folders out"
        assert local_generation(stores.catalog) == 1
        assert stores.catalog.get_ride(ride_id).meta.notes == NOTE


def test_sync_folder_listing_reveals_nothing(synced: Synced):
    """The sync folder's file names say nothing about the rides.

    Given: A pushed library.
    Expect: Only ``keyfile``, ``manifest`` and ``objects/<2 hex>/<64 hex>`` files, one per
        blob plus the catalog.
    """
    push_once(synced)

    names = synced.remote.list()
    objects = [n for n in names if n not in {KEYFILE, MANIFEST}]

    assert KEYFILE in names and MANIFEST in names
    assert all(OPAQUE_NAME.fullmatch(n) for n in objects), objects
    with open_stores(synced.config) as stores:
        assert len(objects) == len(stores.blobs.list()) + 1


def test_no_plaintext_reaches_the_sync_folder(synced: Synced):
    """Nothing readable about the rides is in any byte of the sync folder.

    Short patterns turn up in random bytes by chance (a given 4 bytes about once per 4 GB,
    so once in a few dozen runs over this many patterns), so they're judged by how many
    show up, not by any one.

    Given: The fixture library with a note and a tag, pushed.
    Expect: Every object starts with the encrypted header. No ride id, file hash, note, tag,
        device or source name, and no GPS point as float64, in any file. Of each GPS ride's
        first 20 points as float32 or FIT semicircles (4 bytes each), at most 2 turn up
        (by chance); a stored stream or file would show all of them.
    """
    secrets: list[bytes] = [NOTE.encode(), TAG.encode()]
    short_patterns: list[tuple[str, list[bytes]]] = []
    with open_stores(synced.config) as stores:
        for ride_id in stores.catalog.ride_ids():
            ride = stores.catalog.get_ride(ride_id)
            secrets += [ride.id.encode(), ride.sha256.encode(), ride.source_name.encode()]
            if ride.summary.device:
                secrets.append(ride.summary.device.encode())
            if ride.summary.has_gps:
                frame = stores.streams.get(ride.id, ride.summary.start).drop_nulls("lat")
                points = frame.select("lat", "lon").unique(maintain_order=True).head(20)
                values = [*points["lat"], *points["lon"]]
                secrets += [struct.pack(order, v) for v in values for order in ("<d", ">d")]
                short_patterns.append(
                    (f"{ride.id} float32", [struct.pack("<f", v) for v in values])
                )
                short_patterns.append(
                    (
                        f"{ride.id} semicircles",
                        [struct.pack("<i", round(v * 2**31 / 180)) for v in values],
                    )
                )
        some_id = stores.catalog.ride_ids()[0]
        stores.catalog.update_meta(
            some_id,
            dataclasses.replace(stores.catalog.get_ride(some_id).meta, notes=NOTE, tags=(TAG,)),
        )
    push_once(synced)

    objects = [n for n in synced.remote.list() if n.startswith("objects/")]
    headers = {(synced.folder / n).read_bytes()[:4] for n in objects}
    contents = b"".join((synced.folder / name).read_bytes() for name in synced.remote.list())

    assert headers == {b"FLB1"}, "every object should be encrypted, not a plain file"
    found = [s for s in secrets if s in contents]
    assert found == [], "should find nothing of the library in the sync folder"
    for label, patterns in short_patterns:
        hits = sum(p in contents for p in patterns)
        assert hits <= 2, f"{label}: {hits} of {len(patterns)} points found in the sync folder"


def test_second_push_uploads_only_changes(synced: Synced):
    """Pushing again uploads only what changed, and removes what's gone.

    Given: A pushed library; pushed again unchanged; then a note edited; then a ride
        imported; then a stream deleted.
    Expect: Nothing uploaded the second time; only the catalog after the note; the new
        ride's file, stream and the catalog after the import; one object deleted after the
        stream is gone.
    """
    first = push_once(synced)
    unchanged = push_once(synced)
    with open_stores(synced.config) as stores:
        ride_id = synced.ids["garmin_nord_intervals_5x4.fit"]
        meta = stores.catalog.get_ride(ride_id).meta
        stores.catalog.update_meta(ride_id, dataclasses.replace(meta, notes=NOTE))
    after_note = push_once(synced)
    with open_stores(synced.config) as stores:
        Importer(stores.catalog, stores.blobs, stores.streams, workers=1).run([EXTRA_RIDE])
    after_import = push_once(synced)
    with open_stores(synced.config) as stores:
        stores.blobs.delete(stores.blobs.list("streams/")[0])
    after_delete = push_once(synced)

    assert (unchanged.uploaded, unchanged.unchanged) == (0, first.uploaded - 1)
    assert after_note.uploaded == 1, "should upload only the catalog after a note"
    assert after_import.uploaded == 3, "should upload the file, its stream and the catalog"
    assert (after_delete.uploaded, after_delete.deleted) == (0, 1), "should delete the stream"
    assert after_delete.generation == 5


def test_interrupted_push_keeps_the_previous_copy(synced: Synced, tmp_path: Path):
    """A push that fails part way leaves the last good copy whole.

    Given: A pushed library; a ride imported; a push whose writes fail after the first two.
    Expect: The push raises; the manifest is still generation 1; restoring gives the rides
        from before the import. A later push completes as generation 2.
    """
    push_once(synced)
    with open_stores(synced.config) as stores:
        before = stores.catalog.count()
        Importer(stores.catalog, stores.blobs, stores.streams, workers=1).run([EXTRA_RIDE])

    with pytest.raises(OSError):
        push_once(synced, remote=FailingRemote(synced.folder, puts_allowed=2))
    copy = Config(library=tmp_path / "restored")
    restore_into(copy, synced.remote, MemoryKeyStore())

    with open_stores(copy) as stores:
        assert stores.catalog.count() == before
    assert push_once(synced).generation == 2


def test_push_after_another_computer_pushed_is_refused(synced: Synced, tmp_path: Path):
    """Only one computer writes at a time: a push over a newer copy needs --force.

    Given: Library A pushed; restored as B on "another computer"; B pushed.
    Expect: A's push raises ``RemoteAhead``; with ``force`` it succeeds as generation 3.
    """
    push_once(synced)
    other = Synced(
        Config(library=tmp_path / "other"),
        synced.remote,
        synced.folder,
        MemoryKeyStore(),
        synced.ids,
    )
    restore_into(other.config, other.remote, other.keystore)
    assert push_once(other).generation == 2

    with pytest.raises(RemoteAhead, match="--force"):
        push_once(synced)
    assert push_once(synced, force=True).generation == 3


def test_push_interrupted_after_its_manifest_is_not_another_computer(synced: Synced):
    """A push that stopped just after writing its manifest doesn't block the next push.

    Given: A pushed library whose local generation was lost (as if it stopped right after
        the manifest was written).
    Expect: The next push goes ahead, as generation 2.
    """
    push_once(synced)
    with open_stores(synced.config) as stores:
        stores.catalog.set_setting(GENERATION_SETTING, None)

    assert push_once(synced).generation == 2


def test_setup_refuses_a_folder_with_other_files(tmp_path: Path, synced: Synced):
    """A new sync folder must be empty.

    Given: A folder holding an unrelated file.
    Expect: ``RemoteInUse``.
    """
    folder = tmp_path / "busy"
    folder.mkdir()
    (folder / "notes.txt").write_text("mine")

    with open_stores(synced.config) as stores, pytest.raises(RemoteInUse, match="empty"):
        setup(stores.catalog, open_remote(folder), synced.keystore, PASSPHRASE, FAST_KDF)


def test_setup_takes_back_its_own_folder_and_refuses_another_librarys(
    synced: Synced, tmp_path: Path
):
    """Setting up a folder this library already uses needs no passphrase; another's is refused.

    Given: The library's own sync folder, and an empty library with a new key.
    Expect: Setup on its own folder returns ``True`` without a passphrase; the other
        library's setup raises ``RemoteInUse`` pointing at restore.
    """
    with open_stores(synced.config) as stores:
        assert setup(stores.catalog, synced.remote, synced.keystore, None) is True
    with (
        open_stores(Config(library=tmp_path / "empty")) as stores,
        pytest.raises(RemoteInUse, match="restore"),
    ):
        setup(stores.catalog, synced.remote, MemoryKeyStore(), PASSPHRASE, FAST_KDF)


def test_setup_of_a_new_folder_needs_a_passphrase(synced: Synced, tmp_path: Path):
    """A new keyfile can't be made without a passphrase.

    Given: An empty folder and no passphrase.
    Expect: ``KeyMissing``, and the folder stays empty.
    """
    folder = tmp_path / "new"
    folder.mkdir()

    with open_stores(synced.config) as stores, pytest.raises(KeyMissing):
        setup(stores.catalog, open_remote(folder), synced.keystore, None)
    assert list(folder.iterdir()) == []


def test_unlock_without_the_key_needs_the_passphrase(synced: Synced):
    """A computer without the key opens the keyfile with the passphrase and keeps the key.

    Given: The library's key gone from this computer.
    Expect: ``KeyMissing`` without a passphrase; ``WrongPassphrase`` with a wrong one; with
        the right one the key is kept, and a push works without asking again.
    """
    synced.keystore.keys.clear()

    with open_stores(synced.config) as stores:
        with pytest.raises(KeyMissing):
            unlock(stores.catalog, synced.remote, synced.keystore)
        with pytest.raises(WrongPassphrase):
            unlock(stores.catalog, synced.remote, synced.keystore, "not the passphrase")
        unlock(stores.catalog, synced.remote, synced.keystore, PASSPHRASE)

    assert len(synced.keystore.keys) == 1
    assert push_once(synced).generation == 1


def test_restore_before_any_push_says_so(synced: Synced, tmp_path: Path):
    """A sync folder with only a keyfile has nothing to restore.

    Given: A set-up folder never pushed to.
    Expect: ``NothingPushed``.
    """
    copy = Config(library=tmp_path / "restored")

    with pytest.raises(NothingPushed):
        restore_into(copy, synced.remote, MemoryKeyStore())


def test_restore_refuses_a_copy_from_a_newer_fitlib(synced: Synced, tmp_path: Path):
    """A copy with a newer catalog schema isn't restored.

    Given: A push that records a schema version past the newest this fitlib knows.
    Expect: ``NewerLibrary``, and no catalog is written.
    """
    with open_stores(synced.config) as stores:
        keys = unlock(stores.catalog, synced.remote, synced.keystore)
        newer = dataclasses.replace(local(stores), schema_version=latest_schema_version() + 1)
        push(newer, synced.remote, keys)
    copy = Config(library=tmp_path / "restored")

    with pytest.raises(NewerLibrary):
        restore_into(copy, synced.remote, MemoryKeyStore())
    assert not catalog_path(copy).exists()


def test_restore_refuses_a_changed_object(synced: Synced, tmp_path: Path):
    """A tampered object stops the restore before the catalog is written.

    Given: A pushed library with one byte of one stored object changed.
    Expect: ``CannotDecrypt``, and the restored library has no catalog.
    """
    push_once(synced)
    victim = synced.folder / [n for n in synced.remote.list() if n.startswith("objects/")][0]
    data = bytearray(victim.read_bytes())
    data[-5] ^= 0xFF
    victim.write_bytes(bytes(data))
    copy = Config(library=tmp_path / "restored")

    with pytest.raises(CannotDecrypt):
        restore_into(copy, synced.remote, MemoryKeyStore())
    assert not catalog_path(copy).exists()


def test_restore_refuses_an_object_swapped_for_an_older_one(synced: Synced, tmp_path: Path):
    """An old version of an object can't be passed off as the current one.

    Given: A pushed library; one sealed stream copied over another stream's object.
    Expect: ``CannotDecrypt``: each object is bound to its key in the library.
    """
    push_once(synced)
    with open_stores(synced.config) as stores:
        keys = unlock(stores.catalog, synced.remote, synced.keystore)
    manifest = remote_manifest(synced.remote, keys)
    first, second = [e.name for k, e in manifest.objects.items() if k.startswith("streams/")][:2]
    (synced.folder / second).write_bytes((synced.folder / first).read_bytes())

    with pytest.raises(CannotDecrypt):
        restore(
            synced.remote,
            read_keyfile(synced.remote, PASSPHRASE),
            library_blobs(Config(library=tmp_path / "restored")),
            lambda data: restore_catalog(Config(library=tmp_path / "restored"), data),
            latest_schema_version(),
        )


def test_status_reports_what_a_push_would_do(synced: Synced):
    """Status compares the library with the sync folder.

    Given: A set-up folder before any push; then after a push.
    Expect: Before, no copy and every blob to upload; after, generation 1 on both sides
        and nothing to upload.
    """
    with open_stores(synced.config) as stores:
        keys = unlock(stores.catalog, synced.remote, synced.keystore)
        before = status(local(stores), synced.remote, keys)
        blob_count = len(stores.blobs.list())
    push_once(synced)
    with open_stores(synced.config) as stores:
        after = status(local(stores), synced.remote, keys)

    assert (before.remote, before.to_upload) == (None, blob_count)
    assert before.to_upload_bytes > 0
    assert (after.local_generation, after.remote.generation, after.to_upload) == (1, 1, 0)
    assert after.remote_ahead is False


def test_changed_passphrase_replaces_the_old_one(synced: Synced):
    """After changing the passphrase, only the new one opens the keyfile.

    Given: A set-up folder whose passphrase is changed.
    Expect: The old passphrase fails; the new one gives the same key.
    """
    with open_stores(synced.config) as stores:
        master = synced.keystore.get(library_id(stores.catalog))
        change_passphrase(
            stores.catalog, synced.remote, synced.keystore, "a brand new passphrase", FAST_KDF
        )

    with pytest.raises(WrongPassphrase):
        read_keyfile(synced.remote, PASSPHRASE)
    assert read_keyfile(synced.remote, "a brand new passphrase") == master


def test_push_logs_no_ride_details(synced: Synced, caplog: pytest.LogCaptureFixture):
    """Pushing logs counts only: no ride ids, keys or coordinates.

    Given: A push with INFO logging captured.
    Expect: A log line with the generation, and no ride id or blob key in any line.
    """
    with caplog.at_level(logging.DEBUG):
        push_once(synced)

    text = caplog.text
    assert "Pushed copy 1" in text
    assert not any(ride_id in text for ride_id in synced.ids.values())
    assert "streams/" not in text and "raw/" not in text


def test_manifest_is_encrypted_under_its_own_name(synced: Synced):
    """The manifest only opens as the manifest.

    Given: A pushed library's manifest, opened under another logical key.
    Expect: ``CannotDecrypt``; under ``manifest`` it lists every blob, with hashes.
    """
    push_once(synced)
    with open_stores(synced.config) as stores:
        keys = unlock(stores.catalog, synced.remote, synced.keystore)
        blobs = {k: hashlib.sha256(stores.blobs.get(k)).hexdigest() for k in stores.blobs.list()}

    with pytest.raises(CannotDecrypt):
        open_sealed(keys, "catalog.sqlite3", synced.remote.get(MANIFEST))
    manifest = remote_manifest(synced.remote, keys)
    assert {k: e.sha256 for k, e in manifest.objects.items()} == blobs
