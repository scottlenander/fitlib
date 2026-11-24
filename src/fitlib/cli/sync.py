"""The ``fitlib sync`` commands: an encrypted copy of the library in a folder of your choice.

Any folder works: iCloud Drive, Dropbox, a NAS or a USB drive. Everything is encrypted on
this computer first; the key stays in the Keychain, with a passphrase-protected copy in the
folder so another computer can restore the library.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated

import typer

from fitlib.cli.common import app, err, fail, library, out
from fitlib.config import ConfigError, load_config
from fitlib.store.factory import (
    Stores,
    latest_schema_version,
    library_blobs,
    library_has_data,
    open_remote,
    open_stores,
    remove_empty_catalog,
    restore_catalog,
    snapshot_catalog,
)
from fitlib.store.interfaces import BadSnapshot, BlobStore
from fitlib.sync.crypto import DEFAULT_KDF, MIN_PASSPHRASE, Keys, SyncError
from fitlib.sync.engine import (
    KEYFILE,
    REMOTE_SETTING,
    KeyMissing,
    LocalLibrary,
    adopt,
    change_passphrase,
    push,
    read_keyfile,
    restore,
    setup,
    status,
    unlock,
)
from fitlib.sync.keys import KeychainKeyStore, KeyStore

sync_app = typer.Typer(
    help="Keep an encrypted copy of the library in a folder, e.g. on iCloud Drive or a NAS.",
    no_args_is_help=True,
)
app.add_typer(sync_app, name="sync")

# Argon2id settings for new keyfiles; tests swap in faster ones.
KDF = DEFAULT_KDF

PASSPHRASE_WARNING = (
    "The passphrase opens this library's copy on another computer. fitlib can't recover "
    "it: if you lose it and this computer's Keychain, the copy can't be read by anyone."
)

FolderArgument = Annotated[
    str,
    typer.Argument(help="The sync folder's path, e.g. ~/Library/Mobile Documents/.../fitlib."),
]


def key_store() -> KeyStore:
    """Where this computer keeps libraries' keys.

    Returns:
        The system keychain (tests replace this).
    """
    return KeychainKeyStore()


def _size(n: float) -> str:
    """Format a byte count.

    Args:
        n: Bytes.

    Returns:
        E.g. ``"12.3 MB"``.
    """
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1000 or unit == "GB":
            return f"{n} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1000
    raise AssertionError("unreachable")


def _local(stores: Stores) -> LocalLibrary:
    """What a push reads from the library.

    Args:
        stores: The open library.

    Returns:
        Its catalog, blobs, snapshot maker and schema version.
    """
    return LocalLibrary(
        stores.catalog, stores.blobs, partial(snapshot_catalog, stores), latest_schema_version()
    )


def _remote(stores: Stores) -> BlobStore:
    """Open the library's sync folder.

    Args:
        stores: The open library.

    Returns:
        The sync folder.

    Raises:
        typer.Exit: No sync folder is set up, or it's missing (code 2).
    """
    folder = stores.catalog.get_setting(REMOTE_SETTING)
    if folder is None:
        raise fail("No sync folder yet. Set one up with `fitlib sync setup FOLDER`.")
    try:
        return open_remote(Path(folder))
    except ConfigError as exc:
        raise fail(f"{exc}. Is the drive connected?") from None


def _keys(stores: Stores, remote: BlobStore, keystore: KeyStore) -> Keys:
    """Get the library's keys, asking for the passphrase if this computer doesn't have them.

    Args:
        stores: The open library.
        remote: The sync folder.
        keystore: Where this computer keeps keys.

    Returns:
        The keys.

    Raises:
        SyncError: The passphrase is wrong, or the keychain can't be used.
    """
    try:
        return unlock(stores.catalog, remote, keystore)
    except KeyMissing:
        err.print("This computer doesn't have the library's key yet.")
        passphrase = typer.prompt("Passphrase", hide_input=True)
        return unlock(stores.catalog, remote, keystore, passphrase)


def _new_passphrase() -> str:
    """Ask for a new passphrase twice.

    Returns:
        The passphrase.
    """
    out.print(PASSPHRASE_WARNING)
    return typer.prompt(
        f"New passphrase (at least {MIN_PASSPHRASE} characters)",
        hide_input=True,
        confirmation_prompt=True,
    )


def _folder(raw: str) -> Path:
    """Check a sync folder typed by the user.

    Args:
        raw: The path; ``~`` is expanded.

    Returns:
        The absolute folder.

    Raises:
        typer.Exit: It isn't an existing folder (code 2).
    """
    folder = Path(raw).expanduser().resolve()
    if not folder.is_dir():
        raise fail(f"{folder} isn't a folder. Create it first.")
    return folder


@sync_app.command("setup", help="Use a folder for the library's encrypted copy.")
def sync_setup(ctx: typer.Context, folder: FolderArgument) -> None:
    """Set up an empty folder as the sync folder, or take back this library's own.

    Args:
        ctx: Typer context holding the config path.
        folder: The folder.

    Raises:
        typer.Exit: The folder can't be used (code 2).
    """
    path = _folder(folder)
    keystore = key_store()
    with library(ctx) as lib:
        root = lib.config.library.resolve()
        if path == root or root in path.parents or path in root.parents:
            raise fail("Choose a folder outside the library, and not one containing it.")
        remote = open_remote(path)
        passphrase = None if remote.exists(KEYFILE) or remote.list() else _new_passphrase()
        try:
            known = setup(lib.stores.catalog, remote, keystore, passphrase, KDF)
        except SyncError as exc:
            raise fail(str(exc)) from None
        lib.stores.catalog.set_setting(REMOTE_SETTING, str(path))
    if known:
        out.print(f"Syncing to {path} again.")
    else:
        out.print(f"Sync folder ready: {path}. Run `fitlib sync push` to copy the library.")


@sync_app.command("push", help="Copy the library's changes to the sync folder.")
def sync_push(
    ctx: typer.Context,
    force: Annotated[
        bool,
        typer.Option(help="Push even if another computer pushed since; its copy is replaced."),
    ] = False,
) -> None:
    """Encrypt and upload what changed, then make it the folder's latest copy.

    Args:
        ctx: Typer context holding the config path.
        force: Replace a copy another computer pushed since.

    Raises:
        typer.Exit: No sync folder, wrong passphrase, or another computer pushed (code 2).
    """
    keystore = key_store()
    with library(ctx) as lib:
        remote = _remote(lib.stores)
        try:
            report = push(_local(lib.stores), remote, _keys(lib.stores, remote, keystore), force)
        except SyncError as exc:
            raise fail(str(exc)) from None
    out.print(
        f"Pushed copy {report.generation}: {report.uploaded} uploaded "
        f"({_size(report.uploaded_bytes)}), {report.unchanged} unchanged, "
        f"{report.deleted} removed."
    )


@sync_app.command("status", help="Compare the library with its copy in the sync folder.")
def sync_status(ctx: typer.Context) -> None:
    """Print the sync folder, both generations and what a push would upload.

    Args:
        ctx: Typer context holding the config path.

    Raises:
        typer.Exit: No sync folder, or the key can't be had (code 2).
    """
    keystore = key_store()
    with library(ctx) as lib:
        remote = _remote(lib.stores)
        folder = lib.stores.catalog.get_setting(REMOTE_SETTING)
        try:
            found = status(_local(lib.stores), remote, _keys(lib.stores, remote, keystore))
        except SyncError as exc:
            raise fail(str(exc)) from None
    out.print(f"Sync folder: {folder}")
    if found.remote is None:
        out.print("Nothing pushed yet.")
    else:
        copy = found.remote
        when = copy.pushed_at.astimezone()
        out.print(
            f"Latest copy: {copy.generation}, pushed {when:%Y-%m-%d %H:%M}, "
            f"{len(copy.objects)} files ({_size(copy.total_size)})"
        )
        out.print(f"This library last synced copy {found.local_generation or 'none'}.")
    if found.remote_ahead:
        err.print(
            "[yellow]Another computer pushed since this library last synced; a push would "
            "replace its copy.[/yellow]"
        )
    if found.to_upload:
        out.print(f"To upload: {found.to_upload} files ({_size(found.to_upload_bytes)}).")
    else:
        out.print("Files up to date; a push uploads only catalog changes.")


@sync_app.command("restore", help="Bring a library from a sync folder into an empty library.")
def sync_restore(ctx: typer.Context, folder: FolderArgument) -> None:
    """Download, check and decrypt the folder's latest copy into the configured library.

    Args:
        ctx: Typer context holding the config path.
        folder: The sync folder.

    Raises:
        typer.Exit: The library isn't empty, the folder isn't a sync folder, the passphrase
            is wrong, or the copy is damaged (code 2).
    """
    path = _folder(folder)
    try:
        config = load_config(ctx.obj)
    except ConfigError as exc:
        raise fail(str(exc)) from None
    if library_has_data(config):
        raise fail(
            f"The library at {config.library} isn't empty. Point `library` in the config "
            "at a new folder to restore into."
        )
    remove_empty_catalog(config)
    remote = open_remote(path)
    keystore = key_store()
    try:
        master = read_keyfile(remote, typer.prompt("Passphrase", hide_input=True))
        restored = restore(
            remote,
            master,
            library_blobs(config),
            partial(restore_catalog, config),
            latest_schema_version(),
        )
    except (SyncError, BadSnapshot) as exc:
        raise fail(str(exc)) from None
    with open_stores(config) as stores:
        try:
            adopt(stores.catalog, keystore, restored)
        except SyncError as exc:
            raise fail(str(exc)) from None
        stores.catalog.set_setting(REMOTE_SETTING, str(path))
        rides = stores.catalog.count()
    copy = restored.manifest
    out.print(
        f"Restored {rides} rides from copy {copy.generation} "
        f"(pushed {copy.pushed_at.astimezone():%Y-%m-%d %H:%M}) into {config.library}."
    )


@sync_app.command("passphrase", help="Change the passphrase that opens the sync folder.")
def sync_passphrase(ctx: typer.Context) -> None:
    """Replace the folder's keyfile with one opened by a new passphrase.

    Args:
        ctx: Typer context holding the config path.

    Raises:
        typer.Exit: No sync folder, the key can't be had, or the new passphrase is too short
            (code 2).
    """
    keystore = key_store()
    with library(ctx) as lib:
        remote = _remote(lib.stores)
        try:
            _keys(lib.stores, remote, keystore)
            change_passphrase(lib.stores.catalog, remote, keystore, _new_passphrase(), KDF)
        except SyncError as exc:
            raise fail(str(exc)) from None
    out.print("Passphrase changed. The old one no longer opens the sync folder.")
