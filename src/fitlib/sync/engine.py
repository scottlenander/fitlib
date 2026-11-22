"""Pushing a library to a sync folder, and restoring one from it.

The sync folder (the "remote") holds:

- ``keyfile``: the master key, encrypted with the passphrase (see ``crypto``).
- ``manifest``: encrypted; which objects make up the latest copy. Writing it is what makes a
  push count, so an interrupted push leaves the previous copy whole.
- ``objects/<2 hex>/<64 hex>``: encrypted original files, streams and catalog snapshots, named
  so the listing reveals nothing about them.

One computer pushes at a time: the manifest has a generation number, and a push is refused
when another computer pushed after this library last pushed or restored.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from fitlib.store.interfaces import BlobNotFound, BlobStore, CatalogStore
from fitlib.sync.crypto import (
    DEFAULT_KDF,
    CannotDecrypt,
    KdfParams,
    Keys,
    SyncError,
    keyfile_key_id,
    new_master_key,
    object_name,
    open_sealed,
    seal,
    unwrap_master_key,
    wrap_master_key,
)
from fitlib.sync.keys import KeyStore

log = logging.getLogger(__name__)

KEYFILE = "keyfile"
MANIFEST = "manifest"
OBJECTS = "objects/"
CATALOG_KEY = "catalog.sqlite3"

# Library settings. Those starting with SYNC_PREFIX belong to this computer and are left out
# of the catalog snapshot; the library id travels with the library.
LIBRARY_ID = "library_id"
SYNC_PREFIX = "sync_"
REMOTE_SETTING = "sync_remote"
GENERATION_SETTING = "sync_generation"
DEVICE_SETTING = "sync_device"


class RemoteInUse(SyncError):
    """The sync folder holds something other than this library's copy."""


class RemoteAhead(SyncError):
    """Another computer pushed after this library last pushed or restored."""


class KeyMissing(SyncError):
    """This computer doesn't have the library's key; the passphrase is needed."""


class NothingPushed(SyncError):
    """The sync folder has a keyfile but no copy of a library yet."""


class NotARemote(SyncError):
    """The folder isn't a sync folder."""


class NewerLibrary(SyncError):
    """The copy was pushed by a newer fitlib."""


@dataclass(frozen=True)
class Entry:
    """One object in a pushed copy.

    Attributes:
        name: Its name in the sync folder.
        sha256: Hex sha256 of its plaintext.
        size: Bytes of plaintext.
    """

    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Manifest:
    """What one pushed copy is made of.

    Attributes:
        library_id: The library's id.
        generation: Counts pushes, from 1.
        device: Random id of the computer that pushed it.
        pushed_at: When it was pushed.
        schema_version: The catalog's schema version.
        catalog: The catalog snapshot.
        objects: The original files and streams, by key in the library.
    """

    library_id: str
    generation: int
    device: str
    pushed_at: datetime
    schema_version: int
    catalog: Entry
    objects: dict[str, Entry] = field(default_factory=dict)

    def to_bytes(self) -> bytes:
        """Serialize, for sealing.

        Returns:
            JSON.
        """
        data = asdict(self)
        data["pushed_at"] = self.pushed_at.isoformat()
        return json.dumps(data, sort_keys=True).encode()

    @classmethod
    def from_bytes(cls, raw: bytes) -> Manifest:
        """Parse a manifest.

        Args:
            raw: JSON from ``to_bytes``.

        Returns:
            The manifest.
        """
        data = json.loads(raw)
        return cls(
            library_id=data["library_id"],
            generation=data["generation"],
            device=data["device"],
            pushed_at=datetime.fromisoformat(data["pushed_at"]),
            schema_version=data["schema_version"],
            catalog=Entry(**data["catalog"]),
            objects={k: Entry(**v) for k, v in data["objects"].items()},
        )

    @property
    def total_size(self) -> int:
        """Plaintext bytes in the copy.

        Returns:
            The sum of every object's size and the catalog's.
        """
        return self.catalog.size + sum(e.size for e in self.objects.values())


@dataclass(frozen=True)
class LocalLibrary:
    """What a push reads from the library.

    Attributes:
        catalog: The catalog, for settings.
        blobs: Original files and streams.
        snapshot: Makes a catalog snapshot, given the prefix of settings to leave out.
        schema_version: The catalog's schema version.
    """

    catalog: CatalogStore
    blobs: BlobStore
    snapshot: Callable[[str], bytes]
    schema_version: int


@dataclass(frozen=True)
class PushReport:
    """What a push did.

    Attributes:
        generation: The copy's generation number.
        uploaded: Objects uploaded (the catalog included).
        uploaded_bytes: Plaintext bytes uploaded.
        unchanged: Objects already in the sync folder.
        deleted: Objects removed as no longer needed.
    """

    generation: int
    uploaded: int
    uploaded_bytes: int
    unchanged: int
    deleted: int


@dataclass(frozen=True)
class SyncStatus:
    """How the library compares with its copy.

    Attributes:
        local_generation: The generation this library last pushed or restored (0 if never).
        remote: The copy's manifest, if anything was pushed.
        to_upload: Original files and streams a push would upload.
        to_upload_bytes: Their plaintext bytes.
        remote_ahead: Another computer pushed since.
    """

    local_generation: int
    remote: Manifest | None
    to_upload: int
    to_upload_bytes: int
    remote_ahead: bool


@dataclass(frozen=True)
class Restored:
    """A copy written into an empty library.

    Attributes:
        manifest: The copy restored.
        master_key: The library's key, to keep on this computer.
    """

    manifest: Manifest
    master_key: bytes


def _sha256(data: bytes) -> str:
    """Hash bytes.

    Args:
        data: Any bytes.

    Returns:
        Hex sha256.
    """
    return hashlib.sha256(data).hexdigest()


def _compress(key: str) -> bool:
    """Whether an object is worth compressing before encrypting.

    Args:
        key: The object's key in the library.

    Returns:
        ``False`` for Parquet streams, which are compressed already.
    """
    return not key.endswith(".parquet")


def library_id(catalog: CatalogStore) -> str:
    """The library's id, made the first time it's asked for.

    Args:
        catalog: The library's catalog.

    Returns:
        A random UUID, kept in the library's settings.
    """
    found = catalog.get_setting(LIBRARY_ID)
    if found is None:
        found = str(uuid.uuid4())
        catalog.set_setting(LIBRARY_ID, found)
    return found


def _device(catalog: CatalogStore) -> str:
    """This computer's random id for this library, made the first time it's asked for.

    Args:
        catalog: The library's catalog.

    Returns:
        A random UUID; machine-local, so never in a snapshot.
    """
    found = catalog.get_setting(DEVICE_SETTING)
    if found is None:
        found = str(uuid.uuid4())
        catalog.set_setting(DEVICE_SETTING, found)
    return found


def local_generation(catalog: CatalogStore) -> int:
    """The generation this library last pushed or restored.

    Args:
        catalog: The library's catalog.

    Returns:
        The number, 0 if it never synced.
    """
    return int(catalog.get_setting(GENERATION_SETTING) or 0)


def setup(
    catalog: CatalogStore,
    remote: BlobStore,
    keystore: KeyStore,
    passphrase: str | None,
    kdf: KdfParams = DEFAULT_KDF,
) -> bool:
    """Make a folder this library's sync folder.

    An empty folder gets a keyfile, made with the passphrase. A folder this library already
    uses (same key) is taken back without one.

    Args:
        catalog: The library's catalog.
        remote: The sync folder.
        keystore: Where this computer keeps master keys.
        passphrase: The passphrase for a new keyfile; ``None`` to only take back a folder.
        kdf: Argon2id settings for a new keyfile.

    Returns:
        ``True`` if the folder was this library's already, ``False`` if it was set up new.

    Raises:
        RemoteInUse: The folder holds another library's copy, or other files.
        KeyMissing: The folder is empty and no passphrase was given.
        WeakPassphrase: The passphrase is too short.
    """
    lid = library_id(catalog)
    master = keystore.get(lid)
    if remote.exists(KEYFILE):
        mine = master is not None and Keys.from_master(master).key_id == keyfile_key_id(
            remote.get(KEYFILE)
        )
        if not mine:
            raise RemoteInUse(
                "This folder holds another library's copy. To bring that library to this "
                "computer, use `fitlib sync restore` with an empty library."
            )
        return True
    if remote.list():
        raise RemoteInUse("Choose an empty folder: this one already has files in it.")
    if passphrase is None:
        raise KeyMissing("A passphrase is needed to set up a new sync folder.")
    master = master or new_master_key()
    keyfile = wrap_master_key(master, passphrase, kdf)
    # Keep the key here before the keyfile exists, so there's never a copy we can't open.
    keystore.put(lid, master)
    remote.put(KEYFILE, keyfile)
    return False


def unlock(
    catalog: CatalogStore, remote: BlobStore, keystore: KeyStore, passphrase: str | None = None
) -> Keys:
    """Get the library's keys, from this computer or else from the keyfile.

    Args:
        catalog: The library's catalog.
        remote: The sync folder.
        keystore: Where this computer keeps master keys.
        passphrase: Opens the keyfile when this computer has no key; the key is then kept.

    Returns:
        The keys.

    Raises:
        KeyMissing: This computer has no key and no passphrase was given.
        NotARemote: The folder has no keyfile.
        WrongPassphrase: The passphrase doesn't open the keyfile.
        RemoteInUse: The keyfile holds another library's key.
    """
    lid = library_id(catalog)
    master = keystore.get(lid)
    if master is not None:
        return Keys.from_master(master)
    if passphrase is None:
        raise KeyMissing("This computer doesn't have the library's key; enter the passphrase.")
    try:
        keyfile = remote.get(KEYFILE)
    except BlobNotFound:
        raise NotARemote("The sync folder has no keyfile; run `fitlib sync setup`.") from None
    master = unwrap_master_key(keyfile, passphrase)
    manifest = remote_manifest(remote, Keys.from_master(master))
    if manifest is not None and manifest.library_id != lid:
        raise RemoteInUse("This sync folder holds another library's copy.")
    keystore.put(lid, master)
    return Keys.from_master(master)


def remote_manifest(remote: BlobStore, keys: Keys) -> Manifest | None:
    """Read the sync folder's manifest.

    Args:
        remote: The sync folder.
        keys: The library's keys.

    Returns:
        The latest copy's manifest, or ``None`` if nothing was pushed yet.

    Raises:
        CannotDecrypt: The manifest is damaged or was made with another key.
    """
    try:
        sealed = remote.get(MANIFEST)
    except BlobNotFound:
        return None
    return Manifest.from_bytes(open_sealed(keys, MANIFEST, sealed))


def _remote_ahead(catalog: CatalogStore, manifest: Manifest | None) -> bool:
    """Whether another computer pushed after this library last pushed or restored.

    Args:
        catalog: The library's catalog.
        manifest: The sync folder's manifest.

    Returns:
        ``True`` if its generation is newer and it came from another computer. (A newer one
        from this computer is a push interrupted after its manifest was written.)
    """
    return (
        manifest is not None
        and manifest.generation > local_generation(catalog)
        and manifest.device != _device(catalog)
    )


def _pending(
    blobs: BlobStore, previous: dict[str, Entry]
) -> tuple[dict[str, Entry], list[tuple[str, bytes]]]:
    """Work out which blobs a push must upload.

    Args:
        blobs: The library's blobs.
        previous: The objects of the copy in the sync folder.

    Returns:
        The entries already in the sync folder that are still current, and the blobs to
        upload with their bytes.
    """
    kept: dict[str, Entry] = {}
    changed: list[tuple[str, bytes]] = []
    for key in blobs.list():
        old = previous.get(key)
        if old is not None and key.startswith("raw/"):
            # Original files are named by their hash: same key, same bytes.
            kept[key] = old
            continue
        data = blobs.get(key)
        if old is not None and old.sha256 == _sha256(data):
            kept[key] = old
        else:
            changed.append((key, data))
    return kept, changed


def status(library: LocalLibrary, remote: BlobStore, keys: Keys) -> SyncStatus:
    """Compare the library with its copy in the sync folder.

    Args:
        library: The library.
        remote: The sync folder.
        keys: The library's keys.

    Returns:
        The two generations, the copy's manifest, and what a push would upload.
    """
    manifest = remote_manifest(remote, keys)
    _, changed = _pending(library.blobs, manifest.objects if manifest else {})
    return SyncStatus(
        local_generation=local_generation(library.catalog),
        remote=manifest,
        to_upload=len(changed),
        to_upload_bytes=sum(len(data) for _, data in changed),
        remote_ahead=_remote_ahead(library.catalog, manifest),
    )


def push(library: LocalLibrary, remote: BlobStore, keys: Keys, force: bool = False) -> PushReport:
    """Upload the library's changes and make them the sync folder's latest copy.

    Changed original files and streams go first, then a catalog snapshot, then the manifest
    (the moment the push counts), then objects no longer needed are deleted.

    Args:
        library: The library.
        remote: The sync folder.
        keys: The library's keys.
        force: Push even if another computer pushed since; its changes are replaced.

    Returns:
        What was uploaded and deleted.

    Raises:
        RemoteAhead: Another computer pushed since, and ``force`` is off.
        RemoteInUse: The folder holds another library's copy.
    """
    catalog = library.catalog
    lid = library_id(catalog)
    # Snapshot first: blobs are written before the catalog rows that point at them, so
    # every blob this snapshot needs is in the listing taken after it.
    snapshot = library.snapshot(SYNC_PREFIX)
    before = remote_manifest(remote, keys)
    if before is not None and before.library_id != lid:
        raise RemoteInUse("This sync folder holds another library's copy.")
    if not force and _remote_ahead(catalog, before):
        raise RemoteAhead(
            f"Another computer pushed copy {before.generation} after this library's last "
            "sync. Pushing would replace it; use --force to do so anyway."
        )

    entries, changed = _pending(library.blobs, before.objects if before else {})
    uploaded_bytes = 0
    for key, data in changed:
        entry = Entry(object_name(keys, key, _sha256(data)), _sha256(data), len(data))
        remote.put(entry.name, seal(keys, key, data, compress=_compress(key)))
        entries[key] = entry
        uploaded_bytes += entry.size

    cat_sha = _sha256(snapshot)
    cat_entry = Entry(object_name(keys, CATALOG_KEY, cat_sha), cat_sha, len(snapshot))
    uploaded = len(changed)
    if before is None or before.catalog != cat_entry:
        remote.put(cat_entry.name, seal(keys, CATALOG_KEY, snapshot))
        uploaded += 1
        uploaded_bytes += cat_entry.size

    generation = max(before.generation if before else 0, local_generation(catalog)) + 1
    manifest = Manifest(
        library_id=lid,
        generation=generation,
        device=_device(catalog),
        pushed_at=datetime.now(UTC),
        schema_version=library.schema_version,
        catalog=cat_entry,
        objects=entries,
    )
    remote.put(MANIFEST, seal(keys, MANIFEST, manifest.to_bytes()))
    catalog.set_setting(GENERATION_SETTING, str(generation))

    needed = {e.name for e in entries.values()} | {cat_entry.name}
    stale = [name for name in remote.list(OBJECTS) if name not in needed]
    for name in stale:
        remote.delete(name)
    log.info("Pushed copy %d: %d uploaded, %d deleted", generation, uploaded, len(stale))
    return PushReport(
        generation=generation,
        uploaded=uploaded,
        uploaded_bytes=uploaded_bytes,
        unchanged=len(entries) - len(changed),
        deleted=len(stale),
    )


def _open_checked(keys: Keys, remote: BlobStore, key: str, entry: Entry) -> bytes:
    """Download and decrypt one object, checking it's the one the manifest names.

    Args:
        keys: The library's keys.
        remote: The sync folder.
        key: The object's key in the library.
        entry: Its manifest entry.

    Returns:
        The plaintext.

    Raises:
        CannotDecrypt: It's missing, damaged, or not the version the manifest names.
    """
    try:
        sealed = remote.get(entry.name)
    except BlobNotFound:
        raise CannotDecrypt(f"{key}: missing from the sync folder") from None
    data = open_sealed(keys, key, sealed)
    if _sha256(data) != entry.sha256:
        raise CannotDecrypt(f"{key}: not the version the manifest names")
    return data


def read_keyfile(remote: BlobStore, passphrase: str) -> bytes:
    """Open a sync folder's keyfile.

    Args:
        remote: The sync folder.
        passphrase: Its passphrase.

    Returns:
        The library's master key.

    Raises:
        NotARemote: The folder has no keyfile.
        WrongPassphrase: The passphrase is wrong.
    """
    try:
        keyfile = remote.get(KEYFILE)
    except BlobNotFound:
        raise NotARemote("That folder isn't a fitlib sync folder (it has no keyfile).") from None
    return unwrap_master_key(keyfile, passphrase)


def restore(
    remote: BlobStore,
    master_key: bytes,
    blobs: BlobStore,
    write_catalog: Callable[[bytes], None],
    latest_schema: int,
) -> Restored:
    """Write the sync folder's latest copy into an empty library.

    Every object is checked against the manifest. The catalog is written last, so an
    interrupted restore leaves no catalog and can simply be run again.

    Args:
        remote: The sync folder.
        master_key: The library's key, from ``read_keyfile``.
        blobs: The empty library's blobs.
        write_catalog: Writes the catalog snapshot as the library's catalog.
        latest_schema: The newest catalog schema this fitlib knows.

    Returns:
        The manifest restored and the master key, for ``adopt``.

    Raises:
        NothingPushed: Nothing was pushed to the folder yet.
        NewerLibrary: The copy is from a newer fitlib.
        CannotDecrypt: An object is missing, damaged or was replaced.
    """
    keys = Keys.from_master(master_key)
    manifest = remote_manifest(remote, keys)
    if manifest is None:
        raise NothingPushed("Nothing has been pushed to this sync folder yet.")
    if manifest.schema_version > latest_schema:
        raise NewerLibrary("This copy was pushed by a newer fitlib; update fitlib first.")
    for key, entry in manifest.objects.items():
        blobs.put(key, _open_checked(keys, remote, key, entry))
    write_catalog(_open_checked(keys, remote, CATALOG_KEY, manifest.catalog))
    log.info("Restored copy %d: %d objects", manifest.generation, len(manifest.objects))
    return Restored(manifest, master_key)


def adopt(catalog: CatalogStore, keystore: KeyStore, restored: Restored) -> None:
    """Finish a restore: keep the key on this computer and record the copy's generation.

    Args:
        catalog: The restored library's catalog.
        keystore: Where this computer keeps master keys.
        restored: What ``restore`` returned.
    """
    keystore.put(restored.manifest.library_id, restored.master_key)
    catalog.set_setting(GENERATION_SETTING, str(restored.manifest.generation))
    _device(catalog)


def change_passphrase(
    catalog: CatalogStore,
    remote: BlobStore,
    keystore: KeyStore,
    new_passphrase: str,
    kdf: KdfParams = DEFAULT_KDF,
) -> None:
    """Replace the keyfile with one opened by a new passphrase.

    Args:
        catalog: The library's catalog.
        remote: The sync folder.
        keystore: Where this computer keeps master keys.
        new_passphrase: The new passphrase.
        kdf: Argon2id settings for the new keyfile.

    Raises:
        KeyMissing: This computer doesn't have the library's key.
        WeakPassphrase: The new passphrase is too short.
    """
    master = keystore.get(library_id(catalog))
    if master is None:
        raise KeyMissing(
            "This computer doesn't have the library's key yet; run `fitlib sync status` and "
            "enter the current passphrase first."
        )
    remote.put(KEYFILE, wrap_master_key(master, new_passphrase, kdf))
