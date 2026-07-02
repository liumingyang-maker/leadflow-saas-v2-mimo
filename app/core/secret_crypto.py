from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class SecretCryptoError(ValueError):
    pass


def encrypt_secret(plaintext: str, *, key_env: str = "TENANT_SECRET_KEY") -> str:
    return _current_key(key_env).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, *, key_env: str = "TENANT_SECRET_KEY") -> str:
    raw = ciphertext.encode("utf-8")
    previous = os.environ.get(f"{key_env}_PREVIOUS")
    keys = [_current_key(key_env)]
    if previous:
        keys.append(_derive_fernet_key(previous))
    for key in keys:
        try:
            return key.decrypt(raw).decode("utf-8")
        except InvalidToken:
            continue
    raise SecretCryptoError("failed to decrypt secret")


def mask_secret(value: str) -> str:
    if len(value) <= 4:
        return value
    return "*" * (len(value) - 4) + value[-4:]


def last4(value: str) -> str:
    return value[-4:] if value else ""


def _current_key(key_env: str) -> Fernet:
    value = os.environ.get(key_env)
    if not value:
        raise SecretCryptoError(f"{key_env} environment variable is required")
    return _derive_fernet_key(value)


def _derive_fernet_key(raw: str) -> Fernet:
    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
