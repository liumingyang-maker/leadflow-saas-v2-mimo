from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


def _engine(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return engine


def _membership_pair(session: Session):
    from app.modules.accounts.models import Tenant, TenantMembership, User

    tenant_a = Tenant(company_name="A")
    tenant_b = Tenant(company_name="B")
    user_a = User(email="a@example.com", password_hash="pbkdf2$a")
    user_b = User(email="b@example.com", password_hash="pbkdf2$b")
    membership_a = TenantMembership(tenant=tenant_a, user=user_a, role="owner")
    membership_b = TenantMembership(tenant=tenant_b, user=user_b, role="owner")
    session.add_all([membership_a, membership_b])
    session.commit()
    return tenant_a, tenant_b, membership_a, membership_b


def test_tenant_scoped_repository_hides_cross_tenant_rows(monkeypatch) -> None:
    from app.modules.accounts.models import TenantMembership
    from app.modules.accounts.tenant_scope import TenantScopedRepository

    engine = _engine(monkeypatch)
    with Session(engine) as session:
        tenant_a, tenant_b, membership_a, _membership_b = _membership_pair(session)
        repo = TenantScopedRepository(session, TenantMembership)

        assert repo.get(membership_a.id, tenant_id=tenant_a.id) == membership_a
        assert repo.get(membership_a.id, tenant_id=tenant_b.id) is None
        assert repo.list(tenant_id=tenant_b.id)[0].tenant_id == tenant_b.id


def test_tenant_scoped_repository_rejects_missing_or_forged_tenant(monkeypatch) -> None:
    from app.modules.accounts.models import Tenant, TenantMembership, User
    from app.modules.accounts.tenant_scope import TenantScopedRepository, TenantScopeError

    engine = _engine(monkeypatch)
    with Session(engine) as session:
        tenant_a = Tenant(company_name="A")
        tenant_b = Tenant(company_name="B")
        user = User(email="a@example.com", password_hash="pbkdf2$a")
        session.add_all([tenant_a, tenant_b, user])
        session.commit()

        repo = TenantScopedRepository(session, TenantMembership)
        forged = TenantMembership(tenant_id=tenant_b.id, user_id=user.id, role="member")

        with pytest.raises(TenantScopeError):
            repo.get("missing", tenant_id="")
        with pytest.raises(TenantScopeError):
            repo.add(forged, tenant_id=tenant_a.id)


def test_current_tenant_identity_requires_session_tenant() -> None:
    from app.modules.accounts.tenant_scope import TenantScopeError, current_tenant_identity

    with pytest.raises(TenantScopeError):
        current_tenant_identity({})

    identity = current_tenant_identity(
        {"tenant_id": "tenant-1", "user_id": "user-1", "tenant_email": "owner@example.com"}
    )

    assert identity.tenant_id == "tenant-1"
    assert identity.user_id == "user-1"
    assert identity.email == "owner@example.com"
