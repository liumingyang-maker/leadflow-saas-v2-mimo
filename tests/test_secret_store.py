from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session


def _engine(monkeypatch, *, key: str = "current-secret-key") -> object:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", key)
    monkeypatch.delenv("TENANT_SECRET_KEY_PREVIOUS", raising=False)

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return engine


def test_secret_store_encrypts_values_and_masks_plaintext(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant, TenantSecret
    from app.modules.accounts.secret_store import SecretStore

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        store = SecretStore(session)
        store.save(tenant.id, "smtp_password", "super-secret-value")
        session.commit()

        row = session.scalars(select(TenantSecret)).one()
        assert "super-secret-value" not in row.ciphertext
        assert store.load(tenant.id, "smtp_password") == "super-secret-value"
        masked = store.mask(tenant.id, "smtp_password")
        assert len(masked) == len("super-secret-value")
        assert masked.startswith("*" * (len("super-secret-value") - 4))
        assert masked.endswith("alue")


def test_secret_store_preserves_existing_value_on_empty_submit(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant
    from app.modules.accounts.secret_store import SecretStore

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        store = SecretStore(session)
        store.save(tenant.id, "hunter_api_key", "first-value")
        store.save(tenant.id, "hunter_api_key", "")
        session.commit()

        assert store.load(tenant.id, "hunter_api_key") == "first-value"


def test_secret_store_reads_previous_key_and_rotates_to_current(monkeypatch) -> None:
    engine = _engine(monkeypatch, key="old-secret-key")

    from app.modules.accounts.models import Tenant, TenantSecret
    from app.modules.accounts.secret_store import SecretStore

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        old_store = SecretStore(session)
        old_store.save(tenant_id, "deepseek_api_key", "rotating-secret")
        session.commit()
        old_ciphertext = session.scalars(select(TenantSecret.ciphertext)).one()

    monkeypatch.setenv("TENANT_SECRET_KEY", "new-secret-key")
    monkeypatch.setenv("TENANT_SECRET_KEY_PREVIOUS", "old-secret-key")
    with Session(engine) as session:
        new_store = SecretStore(session)
        assert new_store.load(tenant_id, "deepseek_api_key") == "rotating-secret"
        new_store.rotate(tenant_id, "deepseek_api_key")
        session.commit()
        new_ciphertext = session.scalars(select(TenantSecret.ciphertext)).one()

        assert new_ciphertext != old_ciphertext
        assert new_store.load(tenant_id, "deepseek_api_key") == "rotating-secret"


def test_other_tenant_cannot_read_secret(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant
    from app.modules.accounts.secret_store import SecretStore, SecretStoreError

    with Session(engine) as session:
        tenant_a = Tenant(company_name="A")
        tenant_b = Tenant(company_name="B")
        session.add_all([tenant_a, tenant_b])
        session.commit()

        store_a = SecretStore(session)
        store_a.save(tenant_a.id, "api_key", "secret-a-value")
        session.commit()

        store_b = SecretStore(session)
        with pytest.raises(SecretStoreError):
            store_b.load(tenant_b.id, "api_key")


def test_wrong_key_cannot_decrypt(monkeypatch) -> None:
    """Encrypt with key-A then try to decrypt with key-B (no previous)."""
    engine = _engine(monkeypatch, key="key-a")

    from app.modules.accounts.models import Tenant
    from app.modules.accounts.secret_store import SecretStore, SecretStoreError

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        store = SecretStore(session)
        store.save(tenant_id, "pin", "1234")
        session.commit()

    monkeypatch.setenv("TENANT_SECRET_KEY", "key-b")
    monkeypatch.delenv("TENANT_SECRET_KEY_PREVIOUS", raising=False)
    with Session(engine) as session:
        bad_store = SecretStore(session)
        with pytest.raises(SecretStoreError, match="failed to decrypt"):
            bad_store.load(tenant_id, "pin")


def test_same_plaintext_produces_different_ciphertext(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant, TenantSecret
    from app.modules.accounts.secret_store import SecretStore

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        store = SecretStore(session)
        store.save(tenant_id, "token", "same-value")
        session.commit()
        ct1 = session.scalars(select(TenantSecret.ciphertext)).one()

    with Session(engine) as session:
        store = SecretStore(session)
        store.save(tenant_id, "token", "same-value")
        session.commit()
        ct2 = session.scalars(select(TenantSecret.ciphertext)).one()

    assert ct1 != ct2


def test_error_message_does_not_include_plaintext(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant
    from app.modules.accounts.secret_store import SecretStore, SecretStoreError

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        store = SecretStore(session)
        store.save(tenant_id, "smtp_password", "shhh-dont-tell-anyone")
        session.commit()

    monkeypatch.setenv("TENANT_SECRET_KEY", "different-key")
    with Session(engine) as session:
        bad_store = SecretStore(session)
        try:
            bad_store.load(tenant_id, "smtp_password")
        except SecretStoreError as exc:
            msg = str(exc)
            assert "shhh" not in msg
            assert "dont-tell" not in msg
            assert "failed to decrypt" in msg
        else:
            pytest.fail("expected SecretStoreError")


def test_failed_rotation_keeps_existing_ciphertext(monkeypatch) -> None:
    engine = _engine(monkeypatch, key="original-key")

    from app.modules.accounts.models import Tenant, TenantSecret
    from app.modules.accounts.secret_store import SecretStore, SecretStoreError

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        store = SecretStore(session)
        store.save(tenant_id, "smtp_password", "stable-secret")
        session.commit()
        before = session.scalars(select(TenantSecret.ciphertext)).one()

    monkeypatch.setenv("TENANT_SECRET_KEY", "wrong-current-key")
    monkeypatch.delenv("TENANT_SECRET_KEY_PREVIOUS", raising=False)
    with Session(engine) as session:
        store = SecretStore(session)
        with pytest.raises(SecretStoreError):
            store.rotate(tenant_id, "smtp_password")
        session.rollback()
        after = session.scalars(select(TenantSecret.ciphertext)).one()

    assert after == before


def test_empty_secret_name_is_rejected(monkeypatch) -> None:
    engine = _engine(monkeypatch)

    from app.modules.accounts.models import Tenant
    from app.modules.accounts.secret_store import SecretStore, SecretStoreError

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        session.add(tenant)
        session.commit()
        store = SecretStore(session)
        with pytest.raises(SecretStoreError, match="name is required"):
            store.save(tenant.id, "", "value")
