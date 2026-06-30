# Remaining Work V3 — RC2 Task Cards

## Overview

12 task cards (RC2-001 through RC2-012) for rc1 → v1.0.0 finalization. All tasks follow the mandatory 15-step flow. Worker: MiMo (except RC2-011). Reviewer: DeepSeek.

## Execution Order

1. **Phase 1** (no external deps): RC2-005 → RC2-006 → RC2-001
2. **Phase 2** (needs user credentials): RC2-002 / RC2-003 / RC2-004
3. **Phase 3**: RC2-009 → RC2-008
4. **Phase 4** (needs user host): RC2-007
5. **Phase 5**: RC2-010
6. **Phase 6** (needs user approval): RC2-011 → RC2-012

---

## RC2-001: Docker Runtime Verification and Compose Hardening

- **Branch:** `task/rc2-001-docker-runtime-verification`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Verify Docker containers run correctly, harden Dockerfile with non-root user, create staging compose variant
- **Allowed files:** `Dockerfile`, `docker-compose.yml`, `docker-compose.staging.yml`, `tests/test_docker_*.py`
- **Forbidden files:** `app/modules/*`, `migrations/*`
- **Acceptance criteria:**
  - Docker build succeeds
  - Container starts and passes health check
  - Non-root user configured
  - Staging compose file exists with PostgreSQL
  - All existing tests still pass
- **Evidence:** Docker build log, health check response, test results
- **Blocking:** None

---

## RC2-002: Real SMTP/Mail Provider Adapter

- **Branch:** `task/rc2-002-smtp-mail-adapter`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Implement real SMTP email sending alongside existing FakeMailer
- **Allowed files:** `app/modules/outreach/mailer.py`, `tests/test_smtp_adapter.py`, `.env.example`
- **Forbidden files:** `app/modules/outreach/models.py`, `app/modules/outreach/routes.py`
- **Acceptance criteria:**
  - SmtpMailer class implements Mailer protocol
  - Environment-based provider selection (SMTP_HOST presence)
  - Production without SMTP → NotConfiguredMailer
  - Credentials never leaked in errors/logs
  - TLS support
- **Evidence:** Test results, security grep for credential leaks
- **Blocking:** SMTP credentials from user

---

## RC2-003: Real Google Search Provider Adapter

- **Branch:** `task/rc2-003-google-search-adapter`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Implement real Google Custom Search API adapter alongside existing FakeSearchAdapter
- **Allowed files:** `app/integrations/collection/adapters.py`, `tests/test_google_search_adapter.py`, `.env.example`
- **Forbidden files:** `app/modules/jobs/models.py`, `app/modules/jobs/worker.py` (except adapter registration)
- **Acceptance criteria:**
  - GoogleSearchAdapter implements CollectionAdapter protocol
  - Uses GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX env vars
  - Adapter registry updated
  - API key never leaked
  - Rate limit awareness
- **Evidence:** Test results, adapter protocol compliance
- **Blocking:** Google Custom Search API key and CX from user

---

## RC2-004: Real Google Maps Provider Adapter

- **Branch:** `task/rc2-004-google-maps-adapter`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Implement real Google Places API adapter alongside existing FakeMapsAdapter
- **Allowed files:** `app/integrations/collection/adapters.py`, `tests/test_google_maps_adapter.py`, `.env.example`
- **Forbidden files:** `app/modules/jobs/models.py`
- **Acceptance criteria:**
  - GoogleMapsAdapter implements CollectionAdapter protocol
  - Uses GOOGLE_MAPS_API_KEY env var
  - Text Search API integration
  - Pagination support
  - API key never leaked
- **Evidence:** Test results, adapter protocol compliance
- **Blocking:** Google Places API key from user

---

## RC2-005: Production Config Strong Secret Validation

- **Branch:** `task/rc2-005-production-secret-validation`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Ensure production config fails hard on missing/weak secrets
- **Allowed files:** `app/config.py`, `tests/test_production_config.py`
- **Forbidden files:** None
- **Acceptance criteria:**
  - Production rejects missing SECRET_KEY
  - Production rejects weak SECRET_KEY (<32 chars or in WEAK_SECRET_KEYS)
  - Production rejects missing TENANT_SECRET_KEY
  - Production rejects weak TENANT_SECRET_KEY
  - Error messages never expose secret values
- **Evidence:** Test results, error message audit
- **Blocking:** None

---

## RC2-006: Security Headers/CSP/Upload Limits Hardening

- **Branch:** `task/rc2-006-security-hardening`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Add CSP baseline header, verify all security headers, harden upload limits
- **Allowed files:** `app/core/security.py`, `tests/test_security_hardening.py`
- **Forbidden files:** `app/modules/*`
- **Acceptance criteria:**
  - CSP baseline header present
  - All security headers from LAUNCH_CHECKLIST verified
  - Upload size limits documented and tested
  - No regression in existing security tests
- **Evidence:** Header audit, test results
- **Blocking:** None

---

## RC2-007: Staging Environment Deployment and Smoke Tests

- **Branch:** `task/rc2-007-staging-smoke-tests`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Create staging deployment runbook and automated smoke tests
- **Allowed files:** `scripts/staging_smoke.py`, `tests/test_staging_smoke.py`, `docker-compose.staging.yml`
- **Forbidden files:** `app/modules/*`
- **Acceptance criteria:**
  - Smoke test script checks health, DB, login, security headers
  - Staging compose uses PostgreSQL
  - No fake adapters in staging mode
  - Smoke tests pass locally
- **Evidence:** Smoke test results, staging compose validation
- **Blocking:** Staging host and DNS from user

---

## RC2-008: Backup and Restore Rehearsal Tools

- **Branch:** `task/rc2-008-backup-restore-tools`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Create backup/restore scripts for SQLite and PostgreSQL
- **Allowed files:** `scripts/backup.py`, `scripts/restore.py`, `tests/test_backup_restore.py`
- **Forbidden files:** `app/modules/*`
- **Acceptance criteria:**
  - SQLite backup: file copy with verification
  - PostgreSQL backup: pg_dump
  - Restore script with pre-restore backup
  - Dry-run mode
  - Backup naming with timestamp
- **Evidence:** Backup/restore cycle test results
- **Blocking:** None

---

## RC2-009: Migration Rollback Rehearsal and Downgrade Scripts

- **Branch:** `task/rc2-009-migration-rollback`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Verify Alembic migration rollback capability and create rehearsal script
- **Allowed files:** `scripts/migration_rollback.py`, `tests/test_migration_rollback.py`
- **Forbidden files:** `migrations/*` (read-only verification)
- **Acceptance criteria:**
  - upgrade → downgrade → upgrade cycle works
  - Rollback script with dry-run mode
  - Data integrity verification
  - All 10 migrations tested
- **Evidence:** Migration cycle logs, test results
- **Blocking:** None

---

## RC2-010: Manual Acceptance Matrix Automation

- **Branch:** `task/rc2-010-acceptance-automation`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Automate manual acceptance checklist from PRODUCTION_READINESS_CHECKLIST.md
- **Allowed files:** `tests/test_manual_acceptance_matrix.py`
- **Forbidden files:** `app/modules/*`
- **Acceptance criteria:**
  - Playwright tests cover: login, onboarding, CRM, collection, outreach, inbound, admin, audit
  - Mobile viewport (390x844) tested
  - Keyboard focus and Escape behavior tested
  - All tests pass
- **Evidence:** Playwright test results, screenshots
- **Blocking:** None

---

## RC2-011: Production Go/No-Go Evidence Summary

- **Branch:** `task/rc2-011-go-no-go-evidence`
- **Worker:** Qingyan (GLM) — NOT MiMo
- **Reviewer:** DeepSeek
- **Goal:** Compile all evidence into release decision document
- **Allowed files:** `docs/V1.0.0_RELEASE_EVIDENCE.md`
- **Forbidden files:** All code files
- **Acceptance criteria:**
  - All gate results aggregated
  - All review verdicts listed
  - Migration test results included
  - Staging evidence included
  - Go/No-Go recommendation with justification
- **Evidence:** The document itself IS the evidence
- **Blocking:** All prior RC2 tasks complete, user approval for production

---

## RC2-012: v1.0.0 Release and Rollback Scripts

- **Branch:** `task/rc2-012-release-rollback-scripts`
- **Worker:** MiMo
- **Reviewer:** DeepSeek
- **Goal:** Create release and rollback automation scripts
- **Allowed files:** `scripts/release.py`, `scripts/rollback.py`
- **Forbidden files:** `app/modules/*`
- **Acceptance criteria:**
  - Release script: verify gates, create branch, update version, tag, generate notes
  - Rollback script: identify version, checkout previous tag, downgrade DB, restart
  - Dry-run mode for both
  - No production deployment without explicit flag
- **Evidence:** Script dry-run results
- **Blocking:** RC2-011 Go/No-Go approved
