"""The encrypted formats: sealed objects, opaque object names and the passphrase keyfile.

A sealed object is::

    b"FLB1" | version (1 byte) | flags (1) | key id (8) | nonce (12) | AES-256-GCM ciphertext

The header and the object's logical key (e.g. ``raw/ab/ab12....fit``) are authenticated with
it, so an object copied over another one, or edited anywhere, fails to open. Flag bit 0 means
the plaintext was zstd-compressed before encrypting.

The library's 256-bit master key is never used directly: HKDF derives a content key (AES-GCM)
and a name key (HMAC-SHA256 for object names). The keyfile holds the master key encrypted with
a key from the passphrase (Argon2id); its parameters are plain JSON so they can change later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
from compression import zstd
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b"FLB1"
VERSION = 1
FLAG_ZSTD = 0b1
KEY_BYTES = 32
NONCE_BYTES = 12
KEY_ID_BYTES = 8
_HEADER = struct.Struct(f"!4sBB{KEY_ID_BYTES}s{NONCE_BYTES}s")
MIN_PASSPHRASE = 12
KEYFILE_FORMAT = "fitlib-keyfile"


class SyncError(Exception):
    """Base class for sync errors; the message is meant for the user."""


class CannotDecrypt(SyncError):
    """An object is damaged, was changed, belongs elsewhere, or needs another key."""


class WrongPassphrase(SyncError):
    """The passphrase doesn't open the keyfile."""


class WeakPassphrase(SyncError):
    """The passphrase is too short."""


@dataclass(frozen=True)
class KdfParams:
    """Argon2id settings for turning a passphrase into a key.

    Attributes:
        memory_kib: Memory used, in KiB.
        time_cost: Passes over that memory.
        parallelism: Lanes.
    """

    memory_kib: int = 64 * 1024
    time_cost: int = 3
    parallelism: int = 4


DEFAULT_KDF = KdfParams()


def new_master_key() -> bytes:
    """Make a random master key for a library.

    Returns:
        32 random bytes.
    """
    return os.urandom(KEY_BYTES)


def _derive(master: bytes, purpose: bytes) -> bytes:
    """Derive one sub-key from the master key.

    Args:
        master: The master key.
        purpose: What the key is for, e.g. ``b"content"``.

    Returns:
        A 32-byte key, different for each purpose.
    """
    hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=None, info=b"fitlib " + purpose)
    return hkdf.derive(master)


@dataclass(frozen=True)
class Keys:
    """The keys derived from a library's master key.

    Attributes:
        key_id: 8 bytes naming the master key, stored in each object's header.
        content: Encrypts objects.
        names: Turns logical keys into remote object names.
    """

    key_id: bytes
    content: bytes
    names: bytes

    @classmethod
    def from_master(cls, master: bytes) -> Keys:
        """Derive every key from a master key.

        Args:
            master: The 32-byte master key.

        Returns:
            The derived keys.

        Raises:
            ValueError: The master key isn't 32 bytes.
        """
        if len(master) != KEY_BYTES:
            raise ValueError("A master key is 32 bytes")
        return cls(
            key_id=_derive(master, b"key id")[:KEY_ID_BYTES],
            content=_derive(master, b"content"),
            names=_derive(master, b"names"),
        )


def object_name(keys: Keys, logical_key: str, sha256: str) -> str:
    """The remote name of one version of an object.

    The content hash is part of it, so a changed object gets a new name and the previous
    version stays readable until a newer manifest replaces it.

    Args:
        keys: The library's keys.
        logical_key: The object's key in the library, e.g. ``streams/2025/<id>.parquet``.
        sha256: Hex sha256 of the plaintext.

    Returns:
        ``objects/<2 hex>/<64 hex>``, revealing neither argument.
    """
    digest = hmac.new(keys.names, f"{logical_key}\0{sha256}".encode(), hashlib.sha256).hexdigest()
    return f"objects/{digest[:2]}/{digest}"


def _aad(header: bytes, logical_key: str) -> bytes:
    """The data authenticated with an object besides its contents.

    Args:
        header: The object's header.
        logical_key: The object's key in the library.

    Returns:
        The header followed by the logical key.
    """
    return header + logical_key.encode()


def seal(keys: Keys, logical_key: str, data: bytes, compress: bool = True) -> bytes:
    """Encrypt an object for the remote.

    Args:
        keys: The library's keys.
        logical_key: The object's key in the library; it must be given again to open it.
        data: The plaintext.
        compress: zstd-compress before encrypting (not worth it for Parquet).

    Returns:
        The sealed object.
    """
    flags = FLAG_ZSTD if compress else 0
    header = _HEADER.pack(MAGIC, VERSION, flags, keys.key_id, os.urandom(NONCE_BYTES))
    body = zstd.compress(data) if compress else data
    return header + AESGCM(keys.content).encrypt(
        header[-NONCE_BYTES:], body, _aad(header, logical_key)
    )


def open_sealed(keys: Keys, logical_key: str, sealed: bytes) -> bytes:
    """Decrypt an object from the remote.

    Args:
        keys: The library's keys.
        logical_key: The key it was sealed under.
        sealed: The sealed object.

    Returns:
        The plaintext.

    Raises:
        CannotDecrypt: It isn't a sealed object, was sealed with another key or under another
            logical key, or was changed.
    """
    if len(sealed) < _HEADER.size:
        raise CannotDecrypt(f"{logical_key}: too short to be an encrypted object")
    header = sealed[: _HEADER.size]
    magic, version, flags, key_id, nonce = _HEADER.unpack(header)
    if magic != MAGIC or version != VERSION:
        raise CannotDecrypt(f"{logical_key}: not an encrypted object this version can read")
    if key_id != keys.key_id:
        raise CannotDecrypt(f"{logical_key}: encrypted with a different key")
    try:
        body = AESGCM(keys.content).decrypt(
            nonce, sealed[_HEADER.size :], _aad(header, logical_key)
        )
    except InvalidTag:
        raise CannotDecrypt(f"{logical_key}: damaged or changed") from None
    return zstd.decompress(body) if flags & FLAG_ZSTD else body


def check_passphrase(passphrase: str) -> None:
    """Refuse a passphrase too short to protect the keyfile.

    Args:
        passphrase: The passphrase chosen.

    Raises:
        WeakPassphrase: It has fewer than ``MIN_PASSPHRASE`` characters.
    """
    if len(passphrase) < MIN_PASSPHRASE:
        raise WeakPassphrase(f"Use a passphrase of at least {MIN_PASSPHRASE} characters.")


def _b64(data: bytes) -> str:
    """Encode bytes for JSON.

    Args:
        data: Any bytes.

    Returns:
        Standard base64 text.
    """
    return base64.b64encode(data).decode()


def _passphrase_key(passphrase: str, salt: bytes, params: KdfParams) -> bytes:
    """Turn a passphrase into a key with Argon2id.

    Args:
        passphrase: The passphrase.
        salt: Random salt from the keyfile.
        params: Argon2id settings.

    Returns:
        A 32-byte key.
    """
    return hash_secret_raw(
        passphrase.encode(),
        salt,
        time_cost=params.time_cost,
        memory_cost=params.memory_kib,
        parallelism=params.parallelism,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def wrap_master_key(master: bytes, passphrase: str, params: KdfParams = DEFAULT_KDF) -> bytes:
    """Encrypt the master key with a passphrase, for the remote's keyfile.

    Args:
        master: The library's master key.
        passphrase: The passphrase, at least ``MIN_PASSPHRASE`` characters.
        params: Argon2id settings.

    Returns:
        The keyfile: JSON with the Argon2id settings, salt, nonce and wrapped key.

    Raises:
        WeakPassphrase: The passphrase is too short.
    """
    check_passphrase(passphrase)
    salt, nonce = os.urandom(16), os.urandom(NONCE_BYTES)
    header = {
        "format": KEYFILE_FORMAT,
        "version": VERSION,
        "kdf": "argon2id",
        "memory_kib": params.memory_kib,
        "time_cost": params.time_cost,
        "parallelism": params.parallelism,
        "salt": _b64(salt),
        "key_id": _b64(Keys.from_master(master).key_id),
    }
    wrapped = AESGCM(_passphrase_key(passphrase, salt, params)).encrypt(
        nonce, master, json.dumps(header, sort_keys=True).encode()
    )
    return json.dumps({**header, "nonce": _b64(nonce), "wrapped": _b64(wrapped)}, indent=2).encode()


def _keyfile_fields(keyfile: bytes) -> dict:
    """Parse a keyfile.

    Args:
        keyfile: The keyfile's bytes.

    Returns:
        Its fields.

    Raises:
        CannotDecrypt: It isn't a keyfile this version can read.
    """
    try:
        fields = json.loads(keyfile)
        ok = fields["format"] == KEYFILE_FORMAT and fields["version"] == VERSION
    except ValueError, KeyError, TypeError:
        ok = False
    if not ok:
        raise CannotDecrypt("The keyfile isn't one this version of fitlib can read")
    return fields


def keyfile_key_id(keyfile: bytes) -> bytes:
    """Read which master key a keyfile holds, without the passphrase.

    Args:
        keyfile: The keyfile's bytes.

    Returns:
        The master key's 8-byte id.

    Raises:
        CannotDecrypt: It isn't a keyfile this version can read.
    """
    return base64.b64decode(_keyfile_fields(keyfile)["key_id"])


def unwrap_master_key(keyfile: bytes, passphrase: str) -> bytes:
    """Recover the master key from the keyfile.

    Args:
        keyfile: The keyfile's bytes.
        passphrase: The passphrase it was made with.

    Returns:
        The master key.

    Raises:
        CannotDecrypt: It isn't a keyfile this version can read.
        WrongPassphrase: The passphrase is wrong, or the keyfile was changed.
    """
    fields = _keyfile_fields(keyfile)
    header = {k: v for k, v in fields.items() if k not in {"nonce", "wrapped"}}
    params = KdfParams(fields["memory_kib"], fields["time_cost"], fields["parallelism"])
    key = _passphrase_key(passphrase, base64.b64decode(fields["salt"]), params)
    try:
        return AESGCM(key).decrypt(
            base64.b64decode(fields["nonce"]),
            base64.b64decode(fields["wrapped"]),
            json.dumps(header, sort_keys=True).encode(),
        )
    except InvalidTag:
        raise WrongPassphrase("That passphrase doesn't open this sync folder.") from None
