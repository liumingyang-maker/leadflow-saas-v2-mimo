from __future__ import annotations

from datetime import UTC, datetime

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session


def test_account_models_register_expected_tables_and_constraints() -> None:
    from app.extensions import Base
    from app.modules.accounts.models import AdminUser, Plan, Tenant, TenantMembership, User

    assert Tenant.__tablename__ in Base.metadata.tables
    assert User.__tablename__ in Base.metadata.tables
    assert TenantMembership.__tablename__ in Base.metadata.tables
    assert AdminUser.__tablename__ in Base.metadata.tables
    assert Plan.__tablename__ in Base.metadata.tables

    tenant_columns = Base.metadata.tables["tenants"].columns
    assert {"id", "company_name", "industry", "status", "plan", "trial_ends_at"}.issubset(
        tenant_columns.keys()
    )
    assert Base.metadata.tables["users"].columns["email"].unique is True
    assert Base.metadata.tables["admin_users"].columns["email"].unique is True


def test_tenant_user_membership_and_admin_defaults_round_trip() -> None:
    from app.extensions import Base, get_engine, reset_engine_for_tests
    from app.modules.accounts.models import AdminUser, Plan, Tenant, TenantMembership, User

    reset_engine_for_tests()
    engine = get_engine(database_uri="sqlite:///:memory:")
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            tenant = Tenant(company_name="Acme Export", industry="industrial")
            user = User(email="owner@example.com", password_hash="pbkdf2$hash")
            membership = TenantMembership(tenant=tenant, user=user, role="owner")
            admin = AdminUser(email="ops@example.com", password_hash="pbkdf2$admin")
            plan = Plan(slug="basic", name="Basic", monthly_price_cents=0)
            session.add_all([membership, admin, plan])
            session.commit()

            stored_tenant = session.scalars(select(Tenant)).one()
            stored_user = session.scalars(select(User)).one()
            stored_admin = session.scalars(select(AdminUser)).one()
            stored_plan = session.scalars(select(Plan)).one()

            assert stored_tenant.status == "trial"
            assert stored_tenant.plan == "basic"
            assert stored_tenant.onboarding_done is False
            assert stored_tenant.memberships[0].role == "owner"
            assert stored_user.email == "owner@example.com"
            assert stored_user.is_active is True
            assert stored_user.email_verified_at is None
            assert stored_admin.must_change_password is True
            assert stored_admin.disabled_at is None
            assert stored_plan.is_active is True
            assert isinstance(stored_plan.created_at, datetime)
            assert stored_plan.created_at.tzinfo in (UTC, None)
    finally:
        engine.dispose()
        reset_engine_for_tests()


def test_empty_database_has_no_default_admin_user() -> None:
    from app.extensions import Base, get_engine, reset_engine_for_tests
    from app.modules.accounts.models import AdminUser

    reset_engine_for_tests()
    engine = get_engine(database_uri="sqlite:///:memory:")
    Base.metadata.create_all(engine)

    try:
        with Session(engine) as session:
            assert session.scalar(select(AdminUser)) is None
    finally:
        engine.dispose()
        reset_engine_for_tests()


def test_alembic_head_creates_account_tables(tmp_path) -> None:
    db_path = tmp_path / "leadflow-v2-accounts.db"
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(cfg, "head")

    from app.extensions import get_engine, reset_engine_for_tests

    engine = get_engine(database_uri=f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert {
            "tenants",
            "users",
            "tenant_memberships",
            "admin_users",
            "plans",
        }.issubset(set(inspector.get_table_names()))
    finally:
        engine.dispose()
        reset_engine_for_tests()
