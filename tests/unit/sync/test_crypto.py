"""The encrypted formats: sealed objects, object names and the passphrase keyfile."""

from __future__ import annotations

import json

import pytest

from fitlib.sync.crypto import (
    CannotDecrypt,
    KdfParams,
    Keys,
    WeakPassphrase,
    WrongPassphrase,
    keyfile_key_id,
    new_master_key,
    object_name,
    open_sealed,
    seal,
    unwrap_master_key,
    wrap_master_key,
)

# Small Argon2id settings so the tests run quickly; real keyfiles use the defaults.
FAST_KDF = KdfParams(memory_kib=1024, time_cost=1, parallelism=1)
PASSPHRASE = "correct horse battery"
KEY = "streams/2025/0f9c3c1e-6d4b-4a4c-9f53-0d6f1f5b1c2a.parquet"
DATA = b"power,heart rate\n" * 200


@pytest.fixture
def keys() -> Keys:
    """Keys from a fresh random master key.

    Returns:
        The derived keys.
    """
    return Keys.from_master(new_master_key())


def test_sealed_object_opens_to_the_same_bytes(keys: Keys):
    """An object opens with the same key and logical key it was sealed with.

    Given: 3.4 KB of text sealed, compressed and not.
    Expect: Both open to the original bytes; the compressed one is smaller than the text.
    """
    compressed = seal(keys, KEY, DATA)
    plain = seal(keys, KEY, DATA, compress=False)

    assert open_sealed(keys, KEY, compressed) == DATA
    assert open_sealed(keys, KEY, plain) == DATA
    assert len(compressed) < len(DATA), "should compress repetitive text before encrypting"


def test_sealing_twice_gives_different_bytes(keys: Keys):
    """Each seal uses a fresh nonce.

    Given: The same bytes sealed twice under the same key.
    Expect: The two sealed objects differ.
    """
    assert seal(keys, KEY, DATA) != seal(keys, KEY, DATA)


def test_sealed_object_has_no_plaintext(keys: Keys):
    """Nothing of the plaintext or its logical key shows in a sealed object.

    Given: Text sealed without compression (so encryption alone hides it).
    Expect: Neither the text nor the logical key appears in the result.
    """
    sealed = seal(keys, KEY, DATA, compress=False)

    assert b"heart rate" not in sealed
    assert KEY.encode() not in sealed


@pytest.mark.parametrize(
    ("region", "offset"),
    [("magic", 0), ("flags", 5), ("key id", 6), ("nonce", 14), ("ciphertext", 30), ("tag", -1)],
)
def test_changed_byte_anywhere_fails_to_open(keys: Keys, region: str, offset: int):
    """Changing any byte of a sealed object makes it fail to open.

    Given: A sealed object with one byte flipped in the named region.
    Expect: ``CannotDecrypt``.
    """
    sealed = bytearray(seal(keys, KEY, DATA))
    sealed[offset] ^= 0x01

    with pytest.raises(CannotDecrypt):
        open_sealed(keys, KEY, bytes(sealed))


def test_object_moved_to_another_key_fails_to_open(keys: Keys):
    """An object sealed for one logical key can't stand in for another.

    Given: An object sealed for one stream, opened as another ride's stream.
    Expect: ``CannotDecrypt``, so a swapped object is caught.
    """
    sealed = seal(keys, KEY, DATA)

    with pytest.raises(CannotDecrypt):
        open_sealed(keys, "streams/2025/another-ride.parquet", sealed)


def test_another_key_fails_to_open(keys: Keys):
    """An object only opens with the library's key.

    Given: An object sealed with one master key, opened with another.
    Expect: ``CannotDecrypt`` naming a different key.
    """
    sealed = seal(keys, KEY, DATA)

    with pytest.raises(CannotDecrypt, match="different key"):
        open_sealed(Keys.from_master(new_master_key()), KEY, sealed)


def test_truncated_object_fails_to_open(keys: Keys):
    """Something shorter than a header isn't a sealed object.

    Given: 10 bytes.
    Expect: ``CannotDecrypt``.
    """
    with pytest.raises(CannotDecrypt):
        open_sealed(keys, KEY, b"FLB1\x01\x00\x00\x00\x00\x00")


def test_object_names_are_opaque_and_stable(keys: Keys):
    """Object names hide the logical key and hash, and are the same each time.

    Given: Names for one key and hash, the same key with another hash, and another library.
    Expect: ``objects/<2 hex>/<64 hex>``; same inputs give the same name; a new hash or
        another library's keys give a new one.
    """
    sha = "ab" * 32
    name = object_name(keys, KEY, sha)

    assert name == object_name(keys, KEY, sha)
    assert name.startswith(f"objects/{name.split('/')[2][:2]}/")
    assert len(name.split("/")[2]) == 64
    assert "2025" not in name and sha not in name
    assert object_name(keys, KEY, "cd" * 32) != name
    assert object_name(Keys.from_master(new_master_key()), KEY, sha) != name


def test_keyfile_opens_with_the_passphrase():
    """The keyfile gives back the master key with the right passphrase.

    Given: A master key wrapped with a passphrase.
    Expect: Unwrapping returns it; the key id is readable without the passphrase.
    """
    master = new_master_key()
    keyfile = wrap_master_key(master, PASSPHRASE, FAST_KDF)

    assert unwrap_master_key(keyfile, PASSPHRASE) == master
    assert keyfile_key_id(keyfile) == Keys.from_master(master).key_id


def test_keyfile_refuses_the_wrong_passphrase():
    """A wrong passphrase doesn't open the keyfile.

    Given: A keyfile and a different passphrase.
    Expect: ``WrongPassphrase``.
    """
    keyfile = wrap_master_key(new_master_key(), PASSPHRASE, FAST_KDF)

    with pytest.raises(WrongPassphrase):
        unwrap_master_key(keyfile, "incorrect horse battery")


def test_keyfile_with_changed_settings_fails_to_open():
    """The keyfile's plain settings are authenticated.

    Given: A keyfile whose stored key id was edited.
    Expect: ``WrongPassphrase`` even with the right passphrase.
    """
    fields = json.loads(wrap_master_key(new_master_key(), PASSPHRASE, FAST_KDF))
    fields["key_id"] = "AAAAAAAAAAA="

    with pytest.raises(WrongPassphrase):
        unwrap_master_key(json.dumps(fields).encode(), PASSPHRASE)


def test_keyfile_holds_no_key_material_in_plain():
    """The keyfile shows the settings and salt, never the master key.

    Given: A keyfile.
    Expect: The master key's bytes and base64 don't appear; the Argon2id settings do.
    """
    master = new_master_key()
    keyfile = wrap_master_key(master, PASSPHRASE, FAST_KDF)
    fields = json.loads(keyfile)

    assert master not in keyfile
    assert fields["kdf"] == "argon2id"
    assert fields["memory_kib"] == FAST_KDF.memory_kib
    assert PASSPHRASE.encode() not in keyfile


def test_short_passphrase_is_refused():
    """Passphrases need at least 12 characters.

    Given: An 11-character passphrase.
    Expect: ``WeakPassphrase``.
    """
    with pytest.raises(WeakPassphrase, match="12"):
        wrap_master_key(new_master_key(), "elevenchars", FAST_KDF)


def test_not_a_keyfile_is_refused():
    """Something other than a keyfile is reported as unreadable.

    Given: JSON without the keyfile format.
    Expect: ``CannotDecrypt``.
    """
    with pytest.raises(CannotDecrypt):
        unwrap_master_key(b'{"format": "other"}', PASSPHRASE)
