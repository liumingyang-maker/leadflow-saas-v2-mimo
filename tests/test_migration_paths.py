"""Migration upgrade path tests for 0011 -> 0012 compatibility."""

from __future__ import annotations

import os
import tempfile

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic_cfg(db_path: str) -> Config:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def test_fresh_database_to_head() -> None:
    """Empty database upgrades to head successfully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        cfg = _alembic_cfg(db_path)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        tables = insp.get_table_names()
        assert "coupons" in tables
        assert "payments" in tables
        assert "payment_events" in tables

        # Verify claim_token and processing_expires_at exist (from 0012)
        idem_cols = [c["name"] for c in insp.get_columns("inbound_idempotency")]
        assert "claim_token" in idem_cols
        assert "processing_expires_at" in idem_cols

        # Verify auth_version exists (from 0011)
        user_cols = [c["name"] for c in insp.get_columns("users")]
        assert "auth_version" in user_cols

        admin_cols = [c["name"] for c in insp.get_columns("admin_users")]
        assert "auth_version" in admin_cols
        engine.dispose()


def test_upgrade_0011_to_0012() -> None:
    """Database at 0011 upgrades to 0012 adding lease fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        cfg = _alembic_cfg(db_path)

        # Upgrade to 0011 only
        command.upgrade(cfg, "0011_security_hardening")

        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        idem_cols = [c["name"] for c in insp.get_columns("inbound_idempotency")]
        # 0011 does NOT have claim_token
        assert "claim_token" not in idem_cols
        engine.dispose()

        # Now upgrade to head (currently 0013)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        idem_cols = [c["name"] for c in insp.get_columns("inbound_idempotency")]
        assert "claim_token" in idem_cols
        assert "processing_expires_at" in idem_cols
        engine.dispose()


def test_upgrade_0012_to_0013_adds_admin_auth_version() -> None:
    """Database at 0012 gains the admin session revocation field in 0013."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        cfg = _alembic_cfg(db_path)
        command.upgrade(cfg, "0012_idempotency_lease")

        engine = create_engine(f"sqlite:///{db_path}")
        assert "auth_version" not in {
            column["name"] for column in inspect(engine).get_columns("admin_users")
        }
        engine.dispose()

        command.upgrade(cfg, "0013_admin_auth_version")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "auth_version" in {
            column["name"] for column in inspect(engine).get_columns("admin_users")
        }
        engine.dispose()

        command.downgrade(cfg, "0012_idempotency_lease")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "auth_version" not in {
            column["name"] for column in inspect(engine).get_columns("admin_users")
        }
        engine.dispose()

        command.upgrade(cfg, "0013_admin_auth_version")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "auth_version" in {
            column["name"] for column in inspect(engine).get_columns("admin_users")
        }
        engine.dispose()


def test_modified_0011_compat_skips_existing_columns() -> None:
    """Database that already has claim_token (modified 0011) skips add in 0012."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        cfg = _alembic_cfg(db_path)

        # Upgrade to 0011
        command.upgrade(cfg, "0011_security_hardening")

        # Simulate modified 0011: manually add the columns
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            conn.execute(
                text(
                    "ALTER TABLE inbound_idempotency"
                    " ADD COLUMN claim_token VARCHAR(64) NOT NULL DEFAULT ''"
                )
            )
            conn.execute(
                text("ALTER TABLE inbound_idempotency ADD COLUMN processing_expires_at DATETIME")
            )
            conn.commit()
        engine.dispose()

        # Upgrade to head (0012 should skip adding columns)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        idem_cols = [c["name"] for c in insp.get_columns("inbound_idempotency")]
        assert "claim_token" in idem_cols
        assert "processing_expires_at" in idem_cols
        engine.dispose()


def test_null_processing_lease_backfill() -> None:
    """Historical processing records with NULL lease get backfilled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        cfg = _alembic_cfg(db_path)

        # Upgrade to 0011
        command.upgrade(cfg, "0011_security_hardening")

        # Insert a historical processing record with NULL lease
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            # First add the columns manually (simulating modified 0011)
            conn.execute(
                text(
                    "ALTER TABLE inbound_idempotency"
                    " ADD COLUMN claim_token VARCHAR(64) NOT NULL DEFAULT ''"
                )
            )
            conn.execute(
                text("ALTER TABLE inbound_idempotency ADD COLUMN processing_expires_at DATETIME")
            )
            # Insert a stuck processing record
            conn.execute(
                text(
                    "INSERT INTO inbound_idempotency"
                    " (id, tenant_id, token_digest, idempotency_key, payload_digest,"
                    "  status, claim_token, response_json, expires_at, processing_expires_at,"
                    "  created_at, updated_at)"
                    " VALUES ('id1', 't1', 'd1', 'k1', 'p1',"
                    "  'processing', '', '{}', '2026-01-01', NULL,"
                    "  '2026-01-01', '2026-01-01')"
                )
            )
            conn.commit()
        engine.dispose()

        # Upgrade to 0012 (should backfill NULL lease)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT processing_expires_at FROM inbound_idempotency WHERE id = 'id1'")
            ).fetchone()
        # Should be backfilled to a past date (not NULL)
        assert row is not None
        assert row[0] is not None
        assert "2020" in str(row[0])
        engine.dispose()


def test_acquisition_core_tables_and_crm_columns_exist_at_head() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "acquisition.db")
        cfg = _alembic_cfg(db_path)
        command.upgrade(cfg, "head")

        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        tables = set(insp.get_table_names())
        lead_columns = {column["name"] for column in insp.get_columns("leads")}
        company_columns = {column["name"] for column in insp.get_columns("companies")}
        engine.dispose()

        assert {
            "product_knowledge_snapshots",
            "acquisition_missions",
            "acquisition_candidates",
            "candidate_evidence",
            "candidate_assessments",
            "mission_suggestions",
            "notifications",
            "provider_statuses",
            "radar_competitor_suggestions",
            "competitor_profiles",
        } <= tables
        assert {
            "opportunity_country_code",
            "fit_score",
            "intent_score",
            "data_quality_score",
            "priority_score",
            "priority_band",
            "score_version",
            "score_explanation_json",
            "acquisition_candidate_id",
        } <= lead_columns
        assert "country_code" in company_columns

        command.downgrade(cfg, "0013_admin_auth_version")
        engine = create_engine(f"sqlite:///{db_path}")
        insp = inspect(engine)
        assert "acquisition_candidates" not in set(insp.get_table_names())
        assert "acquisition_candidate_id" not in {
            column["name"] for column in insp.get_columns("leads")
        }
        assert "country_code" not in {column["name"] for column in insp.get_columns("companies")}
        engine.dispose()

        command.upgrade(cfg, "0014_acquisition_core")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "acquisition_candidates" in set(inspect(engine).get_table_names())
        engine.dispose()


def test_browser_foundation_roundtrip_0014_to_0015() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "browser.db")
        cfg = _alembic_cfg(db_path)

        command.upgrade(cfg, "0014_acquisition_core")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "browser_research_runs" not in set(inspect(engine).get_table_names())
        engine.dispose()

        command.upgrade(cfg, "0015_browser_foundation")
        engine = create_engine(f"sqlite:///{db_path}")
        assert {"browser_site_policies", "browser_research_runs"} <= set(
            inspect(engine).get_table_names()
        )
        engine.dispose()

        command.downgrade(cfg, "0014_acquisition_core")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "browser_research_runs" not in set(inspect(engine).get_table_names())
        assert "browser_site_policies" not in set(inspect(engine).get_table_names())
        engine.dispose()

        command.upgrade(cfg, "0015_browser_foundation")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "browser_research_runs" in set(inspect(engine).get_table_names())
        engine.dispose()


def test_radar_profiles_roundtrip_0015_to_0016() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "radar.db")
        cfg = _alembic_cfg(db_path)

        command.upgrade(cfg, "0015_browser_foundation")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "competitor_profiles" not in set(inspect(engine).get_table_names())
        assert "radar_competitor_suggestions" not in set(inspect(engine).get_table_names())
        engine.dispose()

        command.upgrade(cfg, "0016_radar_profiles")
        engine = create_engine(f"sqlite:///{db_path}")
        assert {"competitor_profiles", "radar_competitor_suggestions"} <= set(
            inspect(engine).get_table_names()
        )
        engine.dispose()

        command.downgrade(cfg, "0015_browser_foundation")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "competitor_profiles" not in set(inspect(engine).get_table_names())
        assert "radar_competitor_suggestions" not in set(inspect(engine).get_table_names())
        engine.dispose()

        command.upgrade(cfg, "0016_radar_profiles")
        engine = create_engine(f"sqlite:///{db_path}")
        assert "competitor_profiles" in set(inspect(engine).get_table_names())
        engine.dispose()
