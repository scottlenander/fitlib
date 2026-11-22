"""The ``fitlib sync`` commands, with an in-memory keychain and fast passphrase settings."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitlib.cli import app
from fitlib.config import Config
from fitlib.store.factory import catalog_path, open_stores
from fitlib.sync.keys import MemoryKeyStore, NoKeychain
from tests.unit.sync.conftest import FAST_KDF, PASSPHRASE

runner = CliRunner(env={"COLUMNS": "200", "NO_COLOR": "1"})
NEW_PASSPHRASE = "a brand new passphrase"


def write_config(folder: Path) -> Path:
    """Write a config file for a library in a folder.

    Args:
        folder: Where the config and its ``library`` folder go.

    Returns:
        The config file.
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "fitlib.toml"
    path.write_text(f'library = "{folder / "library"}"\n')
    return path


def run(config: Path, *args: str, input: str | None = None):
    """Run ``fitlib`` with a config file and typed input.

    Args:
        config: The config file.
        *args: The command and its arguments.
        input: What the user types, lines ending in newlines.

    Returns:
        The run's result.
    """
    return runner.invoke(app, ["--config", str(config), *args], input=input)


def twice(passphrase: str) -> str:
    """Input for a passphrase typed and then confirmed.

    Args:
        passphrase: The passphrase.

    Returns:
        It twice, one per line.
    """
    return f"{passphrase}\n{passphrase}\n"


@pytest.fixture
def keystore(monkeypatch: pytest.MonkeyPatch) -> MemoryKeyStore:
    """Replace the Keychain with a dict and use fast Argon2id settings.

    Args:
        monkeypatch: Pytest's patcher.

    Returns:
        The in-memory key store the commands now use.
    """
    store = MemoryKeyStore()
    monkeypatch.setattr("fitlib.cli.sync.key_store", lambda: store)
    monkeypatch.setattr("fitlib.cli.sync.KDF", FAST_KDF)
    return store


@pytest.fixture
def config(tmp_path: Path, template: tuple[Path, dict[str, str]]) -> Path:
    """A config for a copy of the fixture library.

    Args:
        tmp_path: Pytest's per-test temporary folder.
        template: The imported fixture library.

    Returns:
        The config file.
    """
    path = write_config(tmp_path / "home")
    shutil.copytree(template[0], tmp_path / "home" / "library")
    return path


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """An empty folder to sync to.

    Args:
        tmp_path: Pytest's per-test temporary folder.

    Returns:
        The folder.
    """
    path = tmp_path / "sync"
    path.mkdir()
    return path


def ride_count(config: Path) -> int:
    """Count the rides in a config's library.

    Args:
        config: The config file.

    Returns:
        The number of rides.
    """
    with open_stores(Config(library=config.parent / "library")) as stores:
        return stores.catalog.count()


def test_setup_push_status_and_restore(
    config: Path, folder: Path, tmp_path: Path, keystore: MemoryKeyStore
):
    """The whole round trip from the command line.

    Given: The fixture library set up with a new sync folder, pushed, then restored on
        "another computer" (a new config and an empty keychain).
    Expect: Setup warns about the passphrase and says it's ready; push reports copy 1;
        status shows copy 1 and nothing to upload; restore brings back every ride.
    """
    setup = run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    pushed = run(config, "sync", "push")
    shown = run(config, "sync", "status")
    other = write_config(tmp_path / "other")
    keystore.keys.clear()
    restored = run(other, "sync", "restore", str(folder), input=f"{PASSPHRASE}\n")

    assert setup.exit_code == 0, setup.output
    assert "can't recover" in setup.output
    assert f"Sync folder ready: {folder.resolve()}" in setup.output
    assert pushed.exit_code == 0, pushed.output
    assert "Pushed copy 1:" in pushed.output
    assert "Latest copy: 1" in shown.output
    assert "Files up to date" in shown.output
    assert restored.exit_code == 0, restored.output
    assert f"Restored {ride_count(config)} rides from copy 1" in restored.output
    assert ride_count(other) == ride_count(config)
    assert len(keystore.keys) == 1, "should keep the restored library's key"


def test_restored_library_pushes_to_the_same_folder(
    config: Path, folder: Path, tmp_path: Path, keystore: MemoryKeyStore
):
    """A restored library can push straight away, and the first computer is then told.

    Given: A library pushed, restored elsewhere, and pushed from there.
    Expect: The second computer pushes copy 2; the first computer's push is refused with a
        hint about ``--force``, and ``--force`` pushes copy 3.
    """
    run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    run(config, "sync", "push")
    other = write_config(tmp_path / "other")
    run(other, "sync", "restore", str(folder), input=f"{PASSPHRASE}\n")

    from_other = run(other, "sync", "push")
    refused = run(config, "sync", "push")
    status = run(config, "sync", "status")
    forced = run(config, "sync", "push", "--force")

    assert "Pushed copy 2:" in from_other.output
    assert refused.exit_code == 2
    assert "--force" in refused.output
    assert "Another computer pushed" in status.output
    assert "Pushed copy 3:" in forced.output


def test_short_passphrase_is_refused(config: Path, folder: Path, keystore: MemoryKeyStore):
    """Setup refuses a passphrase under 12 characters and leaves the folder empty.

    Given: An 8-character passphrase.
    Expect: Exit code 2 with the minimum length, and nothing in the folder.
    """
    result = run(config, "sync", "setup", str(folder), input=twice("tooshort"))

    assert result.exit_code == 2
    assert "at least 12 characters" in result.output
    assert list(folder.iterdir()) == []


def test_setup_refuses_a_folder_inside_the_library(config: Path, keystore: MemoryKeyStore):
    """The sync folder can't be inside the library it copies.

    Given: The library's blobs folder.
    Expect: Exit code 2, asking for a folder outside the library.
    """
    inside = config.parent / "library" / "blobs"

    result = run(config, "sync", "setup", str(inside))

    assert result.exit_code == 2
    assert "outside the library" in result.output


def test_setup_refuses_a_missing_folder(config: Path, tmp_path: Path, keystore: MemoryKeyStore):
    """Setup needs an existing folder.

    Given: A path that doesn't exist.
    Expect: Exit code 2 asking to create it.
    """
    result = run(config, "sync", "setup", str(tmp_path / "nowhere"))

    assert result.exit_code == 2
    assert "Create it first" in result.output


def test_push_without_a_sync_folder_says_how_to_set_one_up(config: Path, keystore: MemoryKeyStore):
    """Pushing before setup explains what to do.

    Given: A library with no sync folder.
    Expect: Exit code 2 pointing at ``fitlib sync setup``.
    """
    result = run(config, "sync", "push")

    assert result.exit_code == 2
    assert "fitlib sync setup" in result.output


def test_push_asks_for_the_passphrase_when_the_key_is_missing(
    config: Path, folder: Path, keystore: MemoryKeyStore
):
    """A computer without the key asks for the passphrase once, then remembers the key.

    Given: A set-up library whose key was removed from the keychain.
    Expect: A wrong passphrase fails with exit code 2; the right one pushes and keeps the
        key, so the next push doesn't ask.
    """
    run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    keystore.keys.clear()

    wrong = run(config, "sync", "push", input="not the passphrase\n")
    right = run(config, "sync", "push", input=f"{PASSPHRASE}\n")
    again = run(config, "sync", "push")

    assert wrong.exit_code == 2
    assert "doesn't open" in wrong.output
    assert right.exit_code == 0, right.output
    assert "Pushed copy 1" in right.output
    assert again.exit_code == 0
    assert "Passphrase" not in again.output, "should use the key it kept"


def test_restore_refuses_a_library_with_rides(config: Path, folder: Path, keystore: MemoryKeyStore):
    """Restore only writes into an empty library.

    Given: The pushed fixture library, restored into itself.
    Expect: Exit code 2 explaining it isn't empty; its rides are untouched.
    """
    run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    run(config, "sync", "push")
    before = ride_count(config)

    result = run(config, "sync", "restore", str(folder), input=f"{PASSPHRASE}\n")

    assert result.exit_code == 2
    assert "isn't empty" in result.output
    assert ride_count(config) == before


def test_restore_with_the_wrong_passphrase_writes_nothing(
    config: Path, folder: Path, tmp_path: Path, keystore: MemoryKeyStore
):
    """A wrong passphrase stops the restore before anything is written.

    Given: A pushed library, restored elsewhere with the wrong passphrase.
    Expect: Exit code 2, and the new library has no catalog.
    """
    run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    run(config, "sync", "push")
    other = write_config(tmp_path / "other")

    result = run(other, "sync", "restore", str(folder), input="not the passphrase\n")

    assert result.exit_code == 2
    assert not catalog_path(Config(library=other.parent / "library")).exists()


def test_restore_from_a_folder_that_isnt_a_sync_folder(
    tmp_path: Path, folder: Path, keystore: MemoryKeyStore
):
    """Restoring from an ordinary folder says it isn't a sync folder.

    Given: An empty folder.
    Expect: Exit code 2, "isn't a fitlib sync folder".
    """
    other = write_config(tmp_path / "other")

    result = run(other, "sync", "restore", str(folder), input=f"{PASSPHRASE}\n")

    assert result.exit_code == 2
    assert "isn't a fitlib sync folder" in result.output


def test_changed_passphrase_is_the_only_one_that_restores(
    config: Path, folder: Path, tmp_path: Path, keystore: MemoryKeyStore
):
    """After `sync passphrase`, the old passphrase no longer opens the folder.

    Given: A pushed library whose passphrase is changed.
    Expect: The change succeeds; restoring with the old passphrase fails; with the new one
        it works.
    """
    run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))
    run(config, "sync", "push")

    changed = run(config, "sync", "passphrase", input=twice(NEW_PASSPHRASE))
    old = run(write_config(tmp_path / "a"), "sync", "restore", str(folder), input=f"{PASSPHRASE}\n")
    new = run(
        write_config(tmp_path / "b"), "sync", "restore", str(folder), input=f"{NEW_PASSPHRASE}\n"
    )

    assert changed.exit_code == 0, changed.output
    assert "Passphrase changed" in changed.output
    assert old.exit_code == 2
    assert new.exit_code == 0, new.output


def test_missing_keychain_is_reported(config: Path, folder: Path, monkeypatch: pytest.MonkeyPatch):
    """Without a usable keychain, setup fails with a clear message.

    Given: A key store that raises ``NoKeychain``.
    Expect: Exit code 2 with the keychain message, and nothing in the folder.
    """

    class Broken(MemoryKeyStore):
        def get(self, library_id: str) -> bytes | None:
            raise NoKeychain("Can't read the keychain: no backend")

    monkeypatch.setattr("fitlib.cli.sync.key_store", Broken)
    monkeypatch.setattr("fitlib.cli.sync.KDF", FAST_KDF)

    result = run(config, "sync", "setup", str(folder), input=twice(PASSPHRASE))

    assert result.exit_code == 2
    assert "Can't read the keychain" in result.output
    assert list(folder.iterdir()) == []
