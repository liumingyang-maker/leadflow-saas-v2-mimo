# RC2 Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete all RC2 tasks (RC2-001 through RC2-012) to bring LeadFlow SaaS V2 from v1.0.0-rc1 to v1.0.0 production-ready release.

**Architecture:** Modular monolith Flask SaaS with SQLAlchemy 2, Alembic, Redis/RQ, Jinja2+HTMX. Three-party governance: Qingyan(Controller), MiMo(Worker), DeepSeek(Reviewer). Strict 15-step autopilot flow per task.

**Tech Stack:** Python 3.12, Flask 3.1, SQLAlchemy 2.0, Alembic, Redis 7.4, RQ, Jinja2, HTMX 2.0, Tabler/Bootstrap 5, pytest, Playwright, Ruff, Docker Compose

## Global Constraints

- All tenant data queries MUST carry tenant_id scope
- All background jobs MUST be persisted and record tenant ownership
- No real secrets in code — all credentials via environment variables
- No `git add .` or `git add -A` — explicit file adds only
- No production deployment without explicit user approval
- Every PASS claim requires evidence in `.autopilot/evidence/`
- One task card = one branch = one PR
- Fake adapters only in dev/test environments — production MUST use real providers or fail explicitly

---

## Phase 0: Environment Setup & Configuration

### Task 0.1: Configure DeepSeek API and update autopilot config

**Covers:** V3 §六 配置与文档更新

**Files:**
- Modify: `config/autopilot.json`
- Create: `.env`
- Create: `.env.example`

**Steps:**

- [ ] **Step 1: Create .env file with DeepSeek API key**

```bash
# .env — local development environment variables
APP_ENV=development
SECRET_KEY=dev-only-change-me
TENANT_SECRET_KEY=dev-tenant-secret-key-change-me
DATABASE_URL=sqlite:///leadflow-v2-dev.db
REDIS_URL=redis://localhost:6379/0
DEEPSEEK_API_KEY=<your-deepseek-api-key>
```

- [ ] **Step 2: Create .env.example (no real keys)**

```bash
# .env.example — template for environment setup
APP_ENV=development
SECRET_KEY=<generate-32+-char-secret>
TENANT_SECRET_KEY=<generate-32+-char-secret>
DATABASE_URL=sqlite:///leadflow-v2-dev.db
REDIS_URL=redis://localhost:6379/0
DEEPSEEK_API_KEY=<your-deepseek-api-key>
```

- [ ] **Step 3: Update config/autopilot.json for V3 governance**

Update the autopilot config to reflect the three-party model:
- controller.name → "Qingyan (GLM)"
- worker.name → "Xiaomi MiMo"
- Add reviewer block: name=DeepSeek, max_review_rounds=4
- reasonix_mcp_tool_hint → "mimo"
- direct_feature_code_max_changed_lines → 30

- [ ] **Step 4: Verify .gitignore includes .env**

Ensure `.env` is in `.gitignore` (not `.env.example`).

- [ ] **Step 5: Commit**

```bash
git add .env.example config/autopilot.json
git commit -m "chore: configure V3 governance and DeepSeek API integration"
```

---

### Task 0.2: Create V3 governance documents

**Covers:** V3 §六 配置与文档更新

**Files:**
- Create: `docs/AGENT_ALLOCATION_V3.md`
- Create: `docs/ROLE_MATRIX_V3.md`
- Create: `docs/REMAINING_WORK_V3.md`

**Steps:**

- [ ] **Step 1: Create AGENT_ALLOCATION_V3.md**

Three-party role mapping, 15-step responsibility matrix, collaboration protocol, evidence directory, state machine, communication rules. Content from V3 document §二 and §三.

- [ ] **Step 2: Create ROLE_MATRIX_V3.md**

Full responsibility matrix with Qingyan/MiMo/DeepSeek across all work categories.

- [ ] **Step 3: Create REMAINING_WORK_V3.md**

12 task cards (RC2-001 through RC2-012) with branch names, goals, allowed/forbidden files, acceptance criteria, evidence format, blocking items.

- [ ] **Step 4: Commit**

```bash
git add docs/AGENT_ALLOCATION_V3.md docs/ROLE_MATRIX_V3.md docs/REMAINING_WORK_V3.md
git commit -m "docs: add V3 three-party governance documents"
```

---

## Phase 1: Security Hardening (No External Dependencies)

### Task 1.1: RC2-005 — Production config strong secret validation

**Covers:** V3 §5 RC2-005, PRODUCTION_READINESS_CHECKLIST.md Security section

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_security_middleware.py` (or create new test file)

**Interfaces:**
- Consumes: BaseConfig, ProductionConfig, WEAK_SECRET_KEYS from config.py
- Produces: Enhanced ProductionConfig with TENANT_SECRET_KEY validation

**Steps:**

- [ ] **Step 1: Write failing tests for enhanced secret validation**

```python
# tests/test_production_config.py
import os
import pytest

def test_production_rejects_missing_tenant_secret_key(monkeypatch):
    """Production config MUST fail without TENANT_SECRET_KEY."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.delenv("TENANT_SECRET_KEY", raising=False)
    from app.config import resolve_config
    with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY"):
        resolve_config()

def test_production_rejects_weak_tenant_secret_key(monkeypatch):
    """Production config MUST reject short TENANT_SECRET_KEY."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("TENANT_SECRET_KEY", "short")
    from app.config import resolve_config
    with pytest.raises(RuntimeError, match="weak"):
        resolve_config()

def test_production_accepts_strong_secrets(monkeypatch):
    """Production config accepts strong SECRET_KEY and TENANT_SECRET_KEY."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
    from app.config import resolve_config
    config = resolve_config()
    assert config is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest tests/test_production_config.py -v`
Expected: FAIL (tests may already pass if validation exists — check)

- [ ] **Step 3: Enhance ProductionConfig if needed**

If tests fail, add TENANT_SECRET_KEY validation to ProductionConfig in config.py. If already present, verify it matches the test expectations.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest tests/test_production_config.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest -q`
Expected: All tests pass (269+ passed)

- [ ] **Step 6: Commit**

```bash
git add tests/test_production_config.py app/config.py
git commit -m "feat(security): enhance production config secret validation"
```

---

### Task 1.2: RC2-006 — Security headers/CSP/upload limits/rate limiting hardening

**Covers:** V3 §5 RC2-006, LAUNCH_CHECKLIST.md Security section

**Files:**
- Modify: `app/core/security.py`
- Create: `tests/test_security_hardening.py`

**Steps:**

- [ ] **Step 1: Audit current security headers**

Read `app/core/security.py` and identify which headers are currently set. Check against LAUNCH_CHECKLIST.md requirements:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy
- Permissions-Policy
- Content-Security-Policy (CSP baseline)

- [ ] **Step 2: Write failing tests for missing security headers**

```python
# tests/test_security_hardening.py
def test_csp_baseline_header(client):
    """Responses should include a baseline CSP header."""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert "Content-Security-Policy" in resp.headers

def test_upload_size_limit_config(app):
    """MAX_CONTENT_LENGTH should be configured."""
    assert app.config.get("MAX_CONTENT_LENGTH", 0) > 0
    assert app.config["MAX_CONTENT_LENGTH"] <= 50 * 1024 * 1024  # 50MB max
```

- [ ] **Step 3: Implement missing security headers**

Add CSP baseline header to `app/core/security.py` after_request hook.

- [ ] **Step 4: Run tests**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest tests/test_security_hardening.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/core/security.py tests/test_security_hardening.py
git commit -m "feat(security): add CSP baseline and harden security headers"
```

---

### Task 1.3: RC2-001 — Docker runtime verification and compose hardening

**Covers:** V3 §5 RC2-001, LAUNCH_CHECKLIST.md Operations section

**Files:**
- Modify: `docker-compose.yml`
- Modify: `Dockerfile`
- Create: `docker-compose.staging.yml`
- Modify: `tests/test_docker_baseline.py`

**Steps:**

- [ ] **Step 1: Write failing tests for Docker hardening**

```python
# tests/test_docker_hardening.py
def test_dockerfile_uses_non_root_user():
    """Dockerfile should run as non-root user for security."""
    with open("Dockerfile") as f:
        content = f.read()
    assert "USER" in content, "Dockerfile should specify a non-root USER"

def test_docker_compose_healthchecks():
    """All services should have healthchecks."""
    import yaml
    with open("docker-compose.yml") as f:
        config = yaml.safe_load(f)
    for name, svc in config.get("services", {}).items():
        assert "healthcheck" in svc, f"Service {name} missing healthcheck"

def test_docker_compose_no_secrets_in_env():
    """Production compose should not have hardcoded secrets."""
    with open("docker-compose.yml") as f:
        content = f.read()
    # In production, secrets should come from .env or secrets manager
    # For dev compose, this is acceptable but should be documented
```

- [ ] **Step 2: Harden Dockerfile**

Add non-root user, improve layer caching, add security best practices:
```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app:create_app

RUN groupadd -r leadflow && useradd -r -g leadflow -d /app -s /sbin/nologin leadflow

WORKDIR /app

COPY requirements.txt requirements.lock* ./
RUN if [ -f requirements.lock ]; then \
      pip install --no-cache-dir -r requirements.lock; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini .
COPY run_worker.py .

RUN chown -R leadflow:leadflow /app

USER leadflow

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/live', timeout=3).read()"

CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]
```

- [ ] **Step 3: Create docker-compose.staging.yml**

Staging-specific compose file with:
- PostgreSQL instead of SQLite
- Redis with persistence
- Proper environment variable references (no hardcoded secrets)
- Restart policies
- Resource limits

- [ ] **Step 4: Run Docker build test**

Run: `cd /home/brian/projects/leadflow-saas-v2 && docker build -t leadflow-test .`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml docker-compose.staging.yml tests/test_docker_hardening.py
git commit -m "feat(devops): harden Docker config with non-root user and staging compose"
```

---

## Phase 2: Real Provider Adapters (Depends on User Credentials)

> **BLOCKED**: RC2-002, RC2-003, RC2-004 require user to provide API credentials.
> The tasks below implement the adapter scaffolding with environment-based provider selection.
> Real credentials are plugged in via .env when available.

### Task 2.1: RC2-002 — Real SMTP/Mail provider adapter

**Covers:** V3 §5 RC2-002, PRODUCTION_READINESS_CHECKLIST.md Third-Party Providers

**Files:**
- Modify: `app/modules/outreach/mailer.py`
- Create: `tests/test_smtp_adapter.py`

**BLOCKING:** Requires SMTP/SendGrid/Mailgun credentials from user.

**Steps:**

- [ ] **Step 1: Write failing tests for SMTP adapter**

```python
# tests/test_smtp_adapter.py
def test_smtp_adapter_protocol_compliance():
    """SMTP adapter must implement Mailer protocol."""
    from app.modules.outreach.mailer import Mailer
    # Structural type check
    assert hasattr(SmtpMailer, 'send')

def test_get_mailer_returns_smtp_in_production_with_config(monkeypatch):
    """When SMTP is configured, production should use it."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "password")
    monkeypatch.setenv("SMTP_FROM", "noreply@example.com")
    from app.modules.outreach.mailer import get_mailer
    mailer = get_mailer()
    assert not isinstance(mailer, NotConfiguredMailer)

def test_production_without_smtp_returns_not_configured(monkeypatch):
    """Production without SMTP config should return NotConfiguredMailer."""
    monkeypatch.setenv("APP_ENV", "production")
    for key in ["SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"]:
        monkeypatch.delenv(key, raising=False)
    from app.modules.outreach.mailer import get_mailer
    mailer = get_mailer()
    assert isinstance(mailer, NotConfiguredMailer)
```

- [ ] **Step 2: Implement SmtpMailer class**

Add to `app/modules/outreach/mailer.py`:
- `SmtpMailer` class using Python's `smtplib`
- Environment variable configuration: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM
- TLS support
- Error handling that never leaks credentials

- [ ] **Step 3: Update get_mailer() factory**

Add SMTP detection logic: if SMTP_HOST is set, use SmtpMailer; otherwise fall back to FakeMailer (dev) or NotConfiguredMailer (prod).

- [ ] **Step 4: Run tests**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest tests/test_smtp_adapter.py -v`

- [ ] **Step 5: Commit**

```bash
git add app/modules/outreach/mailer.py tests/test_smtp_adapter.py
git commit -m "feat(outreach): add SMTP mailer adapter with env-based selection"
```

---

### Task 2.2: RC2-003 — Real Google Search provider adapter

**Covers:** V3 §5 RC2-003

**Files:**
- Modify: `app/integrations/collection/adapters.py`
- Create: `tests/test_google_search_adapter.py`

**BLOCKING:** Requires Google Custom Search JSON API key and CX from user.

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_google_search_adapter.py
def test_google_search_adapter_protocol():
    """Real adapter must implement CollectionAdapter protocol."""
    from app.integrations.collection.contracts import CollectionAdapter
    # Structural check

def test_adapter_registry_has_google_search():
    """Registry should include google_search adapter."""
    from app.modules.jobs.worker import _ADAPTER_REGISTRY
    assert "google_search" in _ADAPTER_REGISTRY

def test_production_without_api_key_returns_not_configured(monkeypatch):
    """Without API key, production should use sentinel adapter."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("GOOGLE_SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_SEARCH_CX", raising=False)
    # Verify sentinel adapter is used
```

- [ ] **Step 2: Implement GoogleSearchAdapter**

Add to `app/integrations/collection/adapters.py`:
- `GoogleSearchAdapter` class using `urllib.request` (no extra deps)
- Environment variables: GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_CX
- Rate limiting awareness
- Error handling that never leaks API keys
- Candidate mapping from Google API response to Candidate dataclass

- [ ] **Step 3: Update adapter registry**

Modify `app/modules/jobs/worker.py` to register real adapter when API key is available.

- [ ] **Step 4: Run tests and commit**

---

### Task 2.3: RC2-004 — Real Google Maps provider adapter

**Covers:** V3 §5 RC2-004

**Files:**
- Modify: `app/integrations/collection/adapters.py`
- Create: `tests/test_google_maps_adapter.py`

**BLOCKING:** Requires Google Places API key from user.

**Steps:**

- [ ] **Step 1: Write failing tests**

- [ ] **Step 2: Implement GoogleMapsAdapter**

Add to `app/integrations/collection/adapters.py`:
- `GoogleMapsAdapter` class using Places API (Text Search)
- Environment variable: GOOGLE_MAPS_API_KEY
- Pagination support
- Error handling

- [ ] **Step 3: Update adapter registry**

- [ ] **Step 4: Run tests and commit**

---

## Phase 3: Operations Tooling

### Task 3.1: RC2-009 — Migration rollback rehearsal and downgrade scripts

**Covers:** V3 §5 RC2-009, LAUNCH_CHECKLIST.md Operations

**Files:**
- Create: `scripts/migration_rollback.py`
- Create: `tests/test_migration_rollback.py`

**Steps:**

- [ ] **Step 1: Write tests for migration rollback script**

```python
# tests/test_migration_rollback.py
def test_migration_rollback_script_exists():
    """Rollback script should exist and be executable."""
    import os
    assert os.path.isfile("scripts/migration_rollback.py")

def test_alembic_upgrade_downgrade_cycle():
    """Alembic upgrade -> downgrade -> upgrade should work."""
    # This tests the migration chain integrity
```

- [ ] **Step 2: Create migration_rollback.py**

Script that:
1. Backs up current database
2. Runs `alembic upgrade head`
3. Runs `alembic downgrade -1`
4. Runs `alembic upgrade head` again
5. Verifies no data loss
6. Reports results

- [ ] **Step 3: Test the rollback cycle**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python scripts/migration_rollback.py --dry-run`

- [ ] **Step 4: Commit**

---

### Task 3.2: RC2-008 — Backup and restore rehearsal tools

**Covers:** V3 §5 RC2-008, PRODUCTION_READINESS_CHECKLIST.md Operations

**Files:**
- Create: `scripts/backup.py`
- Create: `scripts/restore.py`
- Create: `tests/test_backup_restore.py`

**Steps:**

- [ ] **Step 1: Write tests for backup/restore**

- [ ] **Step 2: Create backup.py**

Supports:
- SQLite: file copy with verification
- PostgreSQL: pg_dump
- Redis: RDB snapshot
- Backup naming with timestamp
- Backup directory configuration

- [ ] **Step 3: Create restore.py**

Supports:
- SQLite: file replacement
- PostgreSQL: psql restore
- Pre-restore backup
- Verification step

- [ ] **Step 4: Test backup/restore cycle**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python scripts/backup.py --dry-run`

- [ ] **Step 5: Commit**

---

## Phase 4: Staging Environment

### Task 4.1: RC2-007 — Staging environment deployment and smoke tests

**Covers:** V3 §5 RC2-007, docs/ALIYUN_STAGING_DEPLOYMENT.md

**Files:**
- Create: `scripts/staging_smoke.py`
- Create: `tests/test_staging_smoke.py`

**BLOCKING:** Requires staging host (Aliyun ECS) and DNS from user.

**Steps:**

- [ ] **Step 1: Write staging smoke test script**

Script that:
1. Checks health endpoints (/health/live, /health/ready)
2. Verifies database connectivity
3. Tests login flow
4. Tests onboarding flow
5. Verifies security headers
6. Checks that fake adapters are NOT used in staging

- [ ] **Step 2: Write automated smoke tests**

- [ ] **Step 3: Test locally with docker-compose.staging.yml**

Run: `cd /home/brian/projects/leadflow-saas-v2 && docker compose -f docker-compose.staging.yml up -d`

- [ ] **Step 4: Commit**

---

## Phase 5: Acceptance & Release

### Task 5.1: RC2-010 — Manual acceptance matrix automation

**Covers:** V3 §5 RC2-010, PRODUCTION_READINESS_CHECKLIST.md Manual Acceptance

**Files:**
- Create: `tests/test_manual_acceptance_matrix.py`

**Steps:**

- [ ] **Step 1: Automate manual acceptance checklist**

Create Playwright tests covering:
- Login/logout
- Onboarding
- CRM list, import, drawer, stage change, note, tag
- Collection job creation
- Outreach send, tracking, unsubscribe
- Inbound token, origin allowlist, API submission
- Admin dashboard
- Audit logs
- Mobile layouts (390x844 viewport)
- Keyboard focus and Escape behavior

- [ ] **Step 2: Run Playwright tests**

Run: `cd /home/brian/projects/leadflow-saas-v2 && source .venv/bin/activate && python -m pytest tests/test_manual_acceptance_matrix.py -v`

- [ ] **Step 3: Commit**

---

### Task 5.2: RC2-011 — Production Go/No-Go evidence summary

**Covers:** V3 §5 RC2-011

**Files:**
- Create: `docs/V1.0.0_RELEASE_EVIDENCE.md`

**Steps:**

- [ ] **Step 1: Compile all evidence**

Aggregate from `.autopilot/evidence/`:
- All gate run results
- Security review verdicts
- UI review verdicts
- Migration test results
- Staging deployment evidence
- Backup/restore test results
- Manual acceptance results

- [ ] **Step 2: Create release evidence document**

- [ ] **Step 3: Present Go/No-Go recommendation**

---

### Task 5.3: RC2-012 — v1.0.0 release and rollback scripts

**Covers:** V3 §5 RC2-012

**Files:**
- Create: `scripts/release.py`
- Create: `scripts/rollback.py`

**Steps:**

- [ ] **Step 1: Create release.py**

Script that:
1. Verifies all gates pass
2. Creates release branch
3. Updates version in pyproject.toml
4. Runs final tests
5. Creates git tag
6. Generates release notes

- [ ] **Step 2: Create rollback.py**

Script that:
1. Identifies current version
2. Checks out previous tag
3. Runs database downgrade
4. Restarts services
5. Verifies health

- [ ] **Step 3: Commit**

---

## Verification

After all tasks complete:

1. `make check` passes (ruff + format + pytest + diff-check)
2. Docker build succeeds: `docker build -t leadflow-v1.0.0 .`
3. Docker compose up: `docker compose up -d` and health checks pass
4. All Playwright tests pass
5. Migration rollback cycle works
6. Backup/restore cycle works
7. Staging smoke tests pass
8. All evidence collected in `.autopilot/evidence/`
9. Release evidence document complete
10. User approves Go/No-Go
