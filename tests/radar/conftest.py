from __future__ import annotations

import pytest


@pytest.fixture
def radar_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.delenv("COMPETITOR_RADAR_ENABLED", raising=False)

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    Base.metadata.create_all(get_engine(app))
    yield app
    reset_engine_for_tests()


@pytest.fixture
def seed_radar_mission(radar_app):
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot

    def seed(
        *,
        tenant_id: str = "tenant-a",
        mission_id: str = "mission-a",
        status: str = "running",
    ):
        snapshot_id = f"snapshot-{mission_id}"
        with Session(get_engine(radar_app)) as session:
            session.add(
                ProductKnowledgeSnapshot(
                    id=snapshot_id,
                    tenant_id=tenant_id,
                    version="v1",
                    product_name=f"Product {mission_id}",
                    summary="Motorcycle engine distributor product",
                    content_hash="a" * 64,
                    approved_by="owner-a",
                )
            )
            session.add(
                AcquisitionMission(
                    id=mission_id,
                    tenant_id=tenant_id,
                    name=f"Mission {mission_id}",
                    status=status,
                    product_snapshot_id=snapshot_id,
                    target_profile_json='{"country_codes":["MX"]}',
                    created_by="owner-a",
                )
            )
            session.commit()
        return mission_id

    return seed
