from __future__ import annotations

import pytest


@pytest.fixture
def acquisition_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    Base.metadata.create_all(get_engine(app))
    yield app
    reset_engine_for_tests()


@pytest.fixture
def logged_in_client(acquisition_app):
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.accounts.models import EmailToken, Tenant

    client = acquisition_app.test_client()
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
        },
    )
    with Session(get_engine(acquisition_app)) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
        tenant_id = session.scalars(select(Tenant.id)).one()
    client.get(f"/verify-email/{token}")
    client.post(
        "/login",
        data={"email": "owner@example.com", "password": "safe-password-123"},
    )
    return client, tenant_id


@pytest.fixture
def csrf_client(acquisition_app, logged_in_client):
    client, tenant_id = logged_in_client
    acquisition_app.config["WTF_CSRF_ENABLED"] = True
    return client, tenant_id


@pytest.fixture
def seed_acquisition_mission(acquisition_app):
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot

    def seed(*, tenant_id: str = "t1", suffix: str = "1") -> str:
        product_id = f"product-{tenant_id}-{suffix}"
        mission_id = f"mission-{tenant_id}-{suffix}"
        with Session(get_engine(acquisition_app)) as session:
            session.add(
                ProductKnowledgeSnapshot(
                    id=product_id,
                    tenant_id=tenant_id,
                    version="v1",
                    product_name=f"Engine {suffix}",
                    summary="Motorcycle engine",
                    content_hash=(suffix[-1:] or "a") * 64,
                    approved_by="u1",
                )
            )
            session.add(
                AcquisitionMission(
                    id=mission_id,
                    tenant_id=tenant_id,
                    name=f"Mission {suffix}",
                    product_snapshot_id=product_id,
                    created_by="u1",
                )
            )
            session.commit()
        return mission_id

    return seed
