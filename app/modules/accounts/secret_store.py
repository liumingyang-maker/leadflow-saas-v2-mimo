from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_crypto import (
    SecretCryptoError,
    decrypt_secret,
    encrypt_secret,
    mask_secret,
)
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
        return mask_secret(self.load(tenant_id, name))

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
        try:
            return encrypt_secret(plaintext)
        except SecretCryptoError as exc:
            raise SecretStoreError(str(exc)) from exc

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return decrypt_secret(ciphertext)
        except SecretCryptoError as exc:
            raise SecretStoreError(
                "failed to decrypt secret – key mismatch or corrupt data"
            ) from exc
