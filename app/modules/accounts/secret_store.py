from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.accounts.models import TenantSecret


class SecretStoreError(ValueError):
    pass


class SecretStore:
    """Encrypt tenant secrets with Fernet and support key rotation.

    Current key is read from ``TENANT_SECRET_KEY`` env var.
    Previous key (if any) is read from ``TENANT_SECRET_KEY_PREVIOUS``
    and used as a fallback during decryption so that data encrypted
    under an old key can still be read until it is rotated.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self._current_key = _derive_fernet_key(
            _require_env("TENANT_SECRET_KEY", "current tenant secret key")
        )
        previous_raw = os.environ.get("TENANT_SECRET_KEY_PREVIOUS")
        self._previous_key: Fernet | None = (
            _derive_fernet_key(previous_raw) if previous_raw else None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(self, tenant_id: str, name: str, plaintext: str) -> None:
        """Store *plaintext* encrypted under the current key.

        If *plaintext* is empty the existing value is preserved so that
        optional / non-submitted form fields do not erase the stored secret.
        """
        if not name:
            raise SecretStoreError("secret name is required")

        existing = self._find(tenant_id, name)

        if not plaintext:
            if existing is not None:
                return  # keep the existing value
            raise SecretStoreError("cannot store an empty secret")

        ciphertext = self._encrypt(plaintext)

        if existing is not None:
            existing.ciphertext = ciphertext
        else:
            secret = TenantSecret(tenant_id=tenant_id, name=name, ciphertext=ciphertext)
            self.session.add(secret)

    def load(self, tenant_id: str, name: str) -> str:
        """Return the decrypted plaintext or raise
        :class:`SecretStoreError`."""
        secret = self._find(tenant_id, name)
        if secret is None:
            raise SecretStoreError(f"secret {name!r} not found for this tenant")
        return self._decrypt(secret.ciphertext)

    def mask(self, tenant_id: str, name: str) -> str:
        """Return a masked representation (last four chars visible)."""
        plaintext = self.load(tenant_id, name)
        if len(plaintext) <= 4:
            return plaintext
        return "*" * (len(plaintext) - 4) + plaintext[-4:]

    def rotate(self, tenant_id: str, name: str) -> None:
        """Re-encrypt the named secret under the current key.

        This is a no-op if the value is already encrypted with the
        current key.
        """
        secret = self._find(tenant_id, name)
        if secret is None:
            raise SecretStoreError(f"secret {name!r} not found for this tenant")
        plaintext = self._decrypt(secret.ciphertext)
        secret.ciphertext = self._encrypt(plaintext)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find(self, tenant_id: str, name: str) -> TenantSecret | None:
        return self.session.scalar(
            select(TenantSecret).where(
                TenantSecret.tenant_id == tenant_id,
                TenantSecret.name == name,
            )
        )

    def _encrypt(self, plaintext: str) -> str:
        return self._current_key.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def _decrypt(self, ciphertext: str) -> str:
        raw = ciphertext.encode("utf-8")
        try:
            return self._current_key.decrypt(raw).decode("utf-8")
        except InvalidToken:
            pass
        if self._previous_key is not None:
            try:
                return self._previous_key.decrypt(raw).decode("utf-8")
            except InvalidToken:
                pass
        raise SecretStoreError("failed to decrypt secret – key mismatch or corrupt data")


def _derive_fernet_key(raw: str) -> Fernet:
    """Derive a valid 32-byte Fernet key from an arbitrary string.

    Fernet requires a base64-encoded 32-byte key.  We use SHA-256 so
    that any reasonably long passphrase works.
    """
    import base64
    import hashlib

    digest = hashlib.sha256(raw.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _require_env(name: str, hint: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SecretStoreError(f"{name} environment variable is required ({hint})")
    return value
