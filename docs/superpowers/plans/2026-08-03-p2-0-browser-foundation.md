# P2-0 Browser Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a disabled-by-default Browser execution foundation whose browser process is isolated from application data and private networks and whose outputs can later be imported by Radar through bounded, tenant-owned contracts.

**Architecture:** The application creates tenant-owned `BrowserResearchRun` rows and sends a bounded descriptor to a dedicated Browser Redis. A database-free Browser Worker executes a strict Playwright MCP allowlist, reaches HTTPS public sites only through a resolving egress proxy, writes content-addressed artifacts, and returns a bounded result. The application polls and imports the result after token, attempt, URL, sanitizer, manifest, and tenant checks; P2-0 exposes this service but does not connect it to Acquisition or Radar.

**Tech Stack:** Python 3.11/3.12, Flask, SQLAlchemy 2, Alembic, Pydantic 2, RQ/Redis, Node.js 22, `@playwright/mcp@0.0.78`, Chromium, Docker Compose, pytest, Ruff, PowerShell.

---

## 0. Preconditions and scope

- Execution baseline is `e090356`; verify it before creating the worktree.
- Migration head is `0014_acquisition_core`; verify with `python -m alembic heads`.
- `Capability.BROWSER_RESEARCH` remains explicit opt-in and false by default.
- The historical Phase 1B plan is reference material only.
- This plan creates no Radar profile, run, snapshot, relationship, signal, Candidate, UI, notification,
  email, export, scheduler, or production enablement.
- Browser supports public HTTPS GET/navigation only. It does not log in, submit forms, upload/download,
  execute arbitrary JavaScript, persist cookies/storage, solve CAPTCHA, rotate proxies, or automate
  LinkedIn.
- If container-layer egress isolation cannot be proven, finish the code with Browser disabled and mark
  the P2-0 release gate failed; do not weaken the gate.

## 1. File structure

### Create

```text
package.json
package-lock.json
Dockerfile.browser
Dockerfile.browser-egress
run_browser_worker.py
run_browser_egress.py
app/integrations/browser/__init__.py
app/integrations/browser/contracts.py
app/integrations/browser/models.py
app/integrations/browser/repository.py
app/integrations/browser/policy.py
app/integrations/browser/egress_proxy.py
app/integrations/browser/mcp_client.py
app/integrations/browser/gateway.py
app/integrations/browser/sanitizer.py
app/integrations/browser/worker.py
app/integrations/browser/service.py
migrations/versions/0015_browser_foundation.py
tests/browser/__init__.py
tests/browser/conftest.py
tests/browser/test_models.py
tests/browser/test_repository.py
tests/browser/test_policy.py
tests/browser/test_egress_proxy.py
tests/browser/test_gateway.py
tests/browser/test_worker.py
tests/browser/test_service.py
tests/browser/test_runtime_contract.py
scripts/smoke_browser_runtime.ps1
docs/RUNBOOK_BROWSER_RESEARCH.md
```

### Modify

```text
app/config.py
app/extensions.py
docker-compose.yml
tests/test_capabilities.py
tests/test_migration_paths.py
docs/SECRETS_AND_ENVIRONMENT.md
docs/RUNBOOK_BACKUP_RESTORE.md
docs/RUNBOOK_STAGING.md
```

## Task 1: Pin the disabled runtime and dedicated transport

**Files:**
- Create: `package.json`
- Create: `package-lock.json`
- Create: `Dockerfile.browser`
- Create: `Dockerfile.browser-egress`
- Create: `run_browser_worker.py`
- Create: `run_browser_egress.py`
- Modify: `app/config.py`
- Modify: `docker-compose.yml`
- Modify: `tests/test_capabilities.py`
- Test: `tests/browser/test_runtime_contract.py`

- [ ] **Step 1: Write failing configuration tests**

Append tests that clear all Browser variables before resolution:

```python
def test_browser_runtime_is_disabled_and_bounded(monkeypatch):
    for name in (
        "BROWSER_RESEARCH_ENABLED",
        "BROWSER_MAX_PAGES",
        "BROWSER_MAX_SECONDS",
        "BROWSER_MAX_TOOL_CALLS",
        "BROWSER_MAX_ARTIFACT_BYTES",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.config import resolve_config
    from app.core.capabilities import Capability, resolve_capabilities

    config = resolve_config("development")
    assert resolve_capabilities("internal")[Capability.BROWSER_RESEARCH] is False
    assert config.BROWSER_MAX_PAGES == 10
    assert config.BROWSER_MAX_SECONDS == 120
    assert config.BROWSER_MAX_TOOL_CALLS == 12
    assert config.BROWSER_MAX_ARTIFACT_BYTES == 5 * 1024 * 1024


def test_browser_budget_rejects_oversized_value(monkeypatch):
    import pytest
    from app.config import resolve_config

    monkeypatch.setenv("BROWSER_MAX_SECONDS", "301")
    with pytest.raises(RuntimeError, match="BROWSER_MAX_SECONDS"):
        resolve_config("development")
```

- [ ] **Step 2: Run the tests and verify the new budget assertions fail**

Run: `python -m pytest tests/test_capabilities.py -q`

Expected: FAIL because the four Browser budget attributes are not defined; the disabled capability
assertion remains green.

- [ ] **Step 3: Add bounded Browser configuration**

Add class defaults to `BaseConfig`, then assign these values in `resolve_config` using the existing
`_bounded_int` helper:

```python
config_class.BROWSER_MAX_PAGES = _bounded_int(
    "BROWSER_MAX_PAGES", 10, minimum=1, maximum=25
)
config_class.BROWSER_MAX_SECONDS = _bounded_int(
    "BROWSER_MAX_SECONDS", 120, minimum=10, maximum=300
)
config_class.BROWSER_MAX_TOOL_CALLS = _bounded_int(
    "BROWSER_MAX_TOOL_CALLS", 12, minimum=1, maximum=30
)
config_class.BROWSER_MAX_ARTIFACT_BYTES = _bounded_int(
    "BROWSER_MAX_ARTIFACT_BYTES",
    5 * 1024 * 1024,
    minimum=1024,
    maximum=20 * 1024 * 1024,
)
config_class.BROWSER_REDIS_URL = os.environ.get(
    "BROWSER_REDIS_URL", "redis://localhost:6380/0"
)
```

Do not add Browser to development/testing auto-enable behavior; it already belongs to
`_EXPLICIT_OPT_IN_CAPABILITIES`.

- [ ] **Step 4: Pin the MCP package**

Create:

```json
{
  "name": "leadflow-browser-runtime",
  "private": true,
  "version": "1.0.0",
  "engines": {"node": ">=22 <23"},
  "dependencies": {"@playwright/mcp": "0.0.78"}
}
```

Run: `npm install --package-lock-only --ignore-scripts`

Expected: lockfile version 3 and an exact resolved `@playwright/mcp` dependency. Then run
`npx --no-install playwright-mcp --help` after `npm ci`; if the required flags in Task 5 are absent,
stop and revise this plan rather than guessing another CLI contract.

- [ ] **Step 5: Create a minimal Browser Worker image**

`Dockerfile.browser` must copy only the Browser integration package, shared web sanitizer/safety
package, entry point, Python dependency locks, and npm locks. It must use a non-root UID, install only
Chromium, retain the Chromium sandbox, and contain no `.env`, application database, templates,
Acquisition module, MiMo integration, or secret store.

The final command is:

```dockerfile
USER browser
CMD ["python", "run_browser_worker.py", "browser"]
```

Do not use `--no-sandbox`, `--ignore-https-errors`, a persistent profile, or a storage-state file.

- [ ] **Step 6: Create a minimal egress image**

`Dockerfile.browser-egress` uses the same pinned Python base as the Browser image, copies only
`app/integrations/browser/egress_proxy.py` and `run_browser_egress.py`, runs as a non-root UID, and
exposes port 8080 only to the internal Compose network.

```dockerfile
USER browserproxy
CMD ["python", "run_browser_egress.py"]
```

- [ ] **Step 7: Add dedicated Compose networks and Redis**

Configure:

```yaml
services:
  browser-redis:
    image: redis:7.4.2-alpine
    networks: [browser-control]
    command: ["redis-server", "--save", "", "--appendonly", "no"]

  browser-egress:
    build:
      context: .
      dockerfile: Dockerfile.browser-egress
    networks: [browser-control, browser-public]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]

  browser-worker:
    build:
      context: .
      dockerfile: Dockerfile.browser
    environment:
      - BROWSER_REDIS_URL=redis://browser-redis:6379/0
      - BROWSER_ARTIFACT_DIR=/artifacts
      - HTTPS_PROXY=http://browser-egress:8080
    networks: [browser-control]
    volumes: [leadflow_browser_artifacts:/artifacts]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 256
    mem_limit: 1536m
    cpus: 1.0

networks:
  browser-control:
    internal: true
  browser-public: {}

volumes:
  leadflow_browser_artifacts:
```

Add the application `worker` to `browser-control`, mount the artifact volume, and give it
`BROWSER_REDIS_URL`; do not add Web, database, application Redis, or reconciler to that network.
Do not publish Browser Redis, proxy, or Browser Worker ports to the host.

- [ ] **Step 8: Verify and commit**

Run:

```powershell
python -m pytest tests/test_capabilities.py tests/browser/test_runtime_contract.py -q
docker compose config
docker compose build browser-worker browser-egress
```

Expected: tests PASS, Compose config PASS, and both images build without a live public navigation.

```powershell
git add package.json package-lock.json Dockerfile.browser Dockerfile.browser-egress run_browser_worker.py run_browser_egress.py app/config.py docker-compose.yml tests/test_capabilities.py tests/browser/__init__.py tests/browser/test_runtime_contract.py
git commit -m "feat(browser): add disabled isolated runtime"
```

## Task 2: Persist Browser policy and run state in migration 0015

**Files:**
- Create: `app/integrations/browser/models.py`
- Create: `app/integrations/browser/repository.py`
- Create: `migrations/versions/0015_browser_foundation.py`
- Create: `tests/browser/conftest.py`
- Create: `tests/browser/test_models.py`
- Create: `tests/browser/test_repository.py`
- Modify: `app/extensions.py`
- Modify: `tests/test_migration_paths.py`

- [ ] **Step 1: Write failing model and tenant tests**

```python
def test_browser_run_stores_digest_and_bounded_owner(browser_app, db_session):
    from app.integrations.browser.models import BrowserResearchRun

    run = BrowserResearchRun(
        tenant_id="t1",
        owner_type="radar_run",
        owner_id="owner-1",
        requested_url="https://example.com/dealers",
        canonical_domain="example.com",
        run_token_digest="a" * 64,
        budget_json='{"max_pages":3,"max_seconds":120,"max_tool_calls":12}',
    )
    db_session.add(run)
    db_session.commit()
    assert run.status == "queued"
    assert not hasattr(run, "run_token")


def test_browser_repository_requires_matching_tenant(browser_app, db_session):
    import pytest
    from app.integrations.browser.repository import BrowserRunRepository

    repository = BrowserRunRepository(db_session)
    with pytest.raises(ValueError, match="tenant_id is required"):
        repository.get("missing", tenant_id="")
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_models.py tests/browser/test_repository.py -q`

Expected: FAIL because Browser models/repositories do not exist.

- [ ] **Step 3: Implement `BrowserSitePolicy`**

Persist these fields and constraints:

```text
id, tenant_id, canonical_domain
access_mode: auto_public | review_required | manual_only | blocked
terms_status: unknown | approved | rejected
robots_status: unknown | allowed | disallowed
allowed_origins_json, allowed_paths_json
max_pages, max_seconds, action_delay_seconds
approved_by, approved_at, reviewed_at, created_at, updated_at
unique: tenant_id + canonical_domain
```

- [ ] **Step 4: Implement `BrowserResearchRun`**

Persist:

```text
id, tenant_id, owner_type, owner_id, site_policy_id
status: queued | running | completed | partial | blocked | failed | cancelled
requested_url, final_url, canonical_domain
policy_decision_json, plan_hash, budget_json
descriptor_hash, run_token_digest, transport_job_id, attempt
page_count, tool_call_count, bytes_written
result_json, artifact_manifest_json
error_code, error_summary
heartbeat_at, lease_expires_at, started_at, finished_at, created_at, updated_at
```

`owner_type` is limited to `radar_run | acquisition_candidate | smoke`; no consumer is connected in
P2-0. URLs are query-redacted before persistence. Result JSON is bounded to 100,000 characters and
contains sanitized page metadata only. Artifact entries are relative content-addressed names, never
page- or model-supplied filesystem paths.

- [ ] **Step 5: Implement tenant repositories and compare-and-set updates**

All methods require `tenant_id`. Claiming a Run matches tenant, ID, `queued`, and absent/expired lease;
completion matches tenant, ID, attempt, and token digest. A stale Worker cannot overwrite a later
attempt. Repository list methods never accept an optional tenant.

- [ ] **Step 6: Create migration 0015 and roundtrip test**

Set:

```python
revision = "0015_browser_foundation"
down_revision = "0014_acquisition_core"
```

Create only `browser_site_policies` and `browser_research_runs` plus named indexes/constraints. Do not
alter Acquisition or Job tables. Extend `tests/test_migration_paths.py` to execute
`0014 -> 0015 -> 0014 -> 0015` and assert both tables disappear and return.

- [ ] **Step 7: Verify and commit**

Run: `python -m pytest tests/browser/test_models.py tests/browser/test_repository.py tests/test_migration_paths.py -q`

Expected: PASS.

```powershell
git add app/integrations/browser/models.py app/integrations/browser/repository.py app/extensions.py migrations/versions/0015_browser_foundation.py tests/browser/conftest.py tests/browser/test_models.py tests/browser/test_repository.py tests/test_migration_paths.py
git commit -m "feat(browser): persist policies and research runs"
```

## Task 3: Define bounded descriptors and URL/site policy

**Files:**
- Create: `app/integrations/browser/__init__.py`
- Create: `app/integrations/browser/contracts.py`
- Create: `app/integrations/browser/policy.py`
- Create: `tests/browser/test_policy.py`
- Modify: `app/integrations/web/url_safety.py`

- [ ] **Step 1: Write failing schema and policy tests**

```python
def test_plan_forbids_evaluate_form_upload_and_download():
    import pytest
    from pydantic import ValidationError
    from app.integrations.browser.contracts import BrowserResearchPlan

    for forbidden in ("evaluate", "fill", "submit", "upload", "download"):
        with pytest.raises(ValidationError):
            BrowserResearchPlan.model_validate(
                {
                    "version": "browser-plan-v1",
                    "start_url": "https://example.com/dealers",
                    "allowed_origins": ["https://example.com"],
                    "actions": [{"tool": forbidden}],
                }
            )


def test_final_navigation_rejects_cross_origin_redirect():
    import pytest
    from app.integrations.browser.policy import BrowserPolicyError, validate_navigation

    with pytest.raises(BrowserPolicyError, match="origin_not_allowed"):
        validate_navigation(
            requested_url="https://example.com/dealers",
            final_url="https://attacker.example/path",
            allowed_origins=("https://example.com",),
        )
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_policy.py -q`

Expected: FAIL because Browser contracts and policy do not exist.

- [ ] **Step 3: Implement frozen strict contracts**

```python
AllowedBrowserTool = Literal[
    "open_allowed_url",
    "read_current_public_page",
    "follow_same_site_link",
    "capture_evidence",
    "stop_research",
]


class BrowserAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool: AllowedBrowserTool
    url: HttpUrl | None = None
    element_ref: str = Field(default="", pattern=r"^[A-Za-z0-9_-]{0,80}$")


class BrowserResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal["browser-plan-v1"]
    start_url: HttpUrl
    allowed_origins: list[str] = Field(min_length=1, max_length=5)
    allowed_paths: list[str] = Field(default_factory=lambda: ["/"], max_length=20)
    actions: list[BrowserAction] = Field(min_length=1, max_length=12)
```

Also define `BrowserTaskDescriptor`, `BrowserPageResult`, `BrowserArtifactEntry`, and
`BrowserTaskResult`. Set `extra="forbid"`, frozen values, string/list limits, page maximum 25, tool-call
maximum 30, wall-time maximum 300, and artifact-byte maximum 20 MiB. The descriptor contains opaque
run ID, raw one-time run token, attempt, plan JSON, budgets, and artifact subdirectory only. It contains
no tenant ID, database URL, application Job payload, model key, or user token.

- [ ] **Step 4: Implement policy precedence**

Precedence is immutable:

```text
system blocked
  > non-HTTPS Browser request
  > robots/terms rejected
  > tenant blocked/manual_only
  > tenant review_required
  > approved auto_public
```

System-blocked roots include `linkedin.com` and configured prohibited platforms. Unknown sites are
`review_required`, never auto-public. The caller derives allowed origin/path and budgets; model output
cannot widen them.

- [ ] **Step 5: Reuse and strengthen public URL validation**

Expose a resolution result from `app/integrations/web/url_safety.py` that canonicalizes host, port, and
all DNS answers. Reject userinfo, fragments carrying secrets, non-HTTPS Browser URLs, non-443 ports,
localhost, private, loopback, link-local, multicast, reserved, unspecified, and metadata destinations.
Apply it before enqueue, before each action, and to every returned final/evidence URL.

- [ ] **Step 6: Verify and commit**

Run: `python -m pytest tests/browser/test_policy.py tests/acquisition/test_static_fetcher.py -q`

Expected: PASS with existing static-fetch behavior unchanged.

```powershell
git add app/integrations/browser/__init__.py app/integrations/browser/contracts.py app/integrations/browser/policy.py app/integrations/web/url_safety.py tests/browser/test_policy.py
git commit -m "feat(browser): constrain descriptors and navigation policy"
```

## Task 4: Implement the resolving HTTPS egress proxy

**Files:**
- Create: `app/integrations/browser/egress_proxy.py`
- Create: `tests/browser/test_egress_proxy.py`
- Modify: `run_browser_egress.py`

- [ ] **Step 1: Write failing proxy policy tests**

```python
def test_proxy_rejects_private_or_mixed_dns_answers():
    from app.integrations.browser.egress_proxy import decide_connect

    assert decide_connect("example.com", 443, ("93.184.216.34",)).allowed is True
    assert decide_connect("example.com", 443, ("127.0.0.1",)).allowed is False
    assert decide_connect("example.com", 443, ("93.184.216.34", "10.0.0.4")).allowed is False


def test_proxy_rejects_plain_http_non_443_and_metadata():
    from app.integrations.browser.egress_proxy import decide_connect

    assert decide_connect("169.254.169.254", 443, ("169.254.169.254",)).allowed is False
    assert decide_connect("example.com", 80, ("93.184.216.34",)).reason == "port_blocked"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_egress_proxy.py -q`

Expected: FAIL because the proxy module does not exist.

- [ ] **Step 3: Implement a CONNECT-only bounded proxy**

Use Python standard-library `asyncio`, `ipaddress`, and `socket`. Accept only an HTTP `CONNECT
host:443` request with a header block no larger than 16 KiB and a hostname no longer than 253
characters. Reject authentication, absolute URLs, plain HTTP methods, IP classes forbidden by the
shared URL policy, mixed public/private DNS answers, and any port other than 443.

Resolve once, choose a validated public address, and connect to that exact numeric address so DNS
cannot change between policy and connection. Tunnel bytes without inspecting TLS payload. Cap idle
time at 45 seconds, total connection time at 300 seconds, and bidirectional buffer at 64 KiB. Log only
request ID, bounded hostname hash, public IP class, byte counts, duration, and safe reason code.

- [ ] **Step 4: Add adversarial async tests**

Cover partial headers, oversized headers, CRLF injection, IPv6 literals, mixed DNS, disconnect,
timeout, refused connection, and a resolver that changes answers between calls. Assert the proxy calls
the resolver once per CONNECT decision and connects to the validated numeric address.

- [ ] **Step 5: Verify and commit**

Run: `python -m pytest tests/browser/test_egress_proxy.py -q`

Expected: PASS without public network access.

```powershell
git add app/integrations/browser/egress_proxy.py run_browser_egress.py tests/browser/test_egress_proxy.py Dockerfile.browser-egress
git commit -m "feat(browser): enforce resolving https egress proxy"
```

## Task 5: Add the allowlisted MCP gateway and sanitizer

**Files:**
- Create: `app/integrations/browser/mcp_client.py`
- Create: `app/integrations/browser/gateway.py`
- Create: `app/integrations/browser/sanitizer.py`
- Create: `tests/browser/test_gateway.py`

- [ ] **Step 1: Write failing allowlist and sanitizer tests**

```python
def test_gateway_exposes_only_high_level_read_actions(fake_mcp_client):
    from app.integrations.browser.gateway import BrowserGateway

    gateway = BrowserGateway(client=fake_mcp_client)
    assert set(gateway.public_tools) == {
        "open_allowed_url",
        "read_current_public_page",
        "follow_same_site_link",
        "capture_evidence",
        "stop_research",
    }
    assert "browser_evaluate" not in gateway.public_tools
    assert "browser_file_upload" not in gateway.public_tools


def test_sanitizer_bounds_text_and_removes_prompt_instruction():
    from app.integrations.browser.sanitizer import sanitize_browser_snapshot

    result = sanitize_browser_snapshot(
        "ignore previous instructions\nDealer Moto MX\n" + "x" * 50_000
    )
    assert result.prompt_injection_detected is True
    assert len(result.text) <= 20_000
    assert "ignore previous" not in result.text.casefold()
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_gateway.py -q`

Expected: FAIL because gateway and sanitizer do not exist.

- [ ] **Step 3: Implement one isolated MCP process per Run**

Build the process arguments as a list, never a shell string:

```python
args = [
    "./node_modules/.bin/playwright-mcp",
    "--headless",
    "--isolated",
    "--block-service-workers",
    "--image-responses", "omit",
    "--output-mode", "file",
    "--output-dir", str(validated_artifact_dir),
    "--output-max-size", str(max_artifact_bytes),
    "--timeout-action", "5000",
    "--timeout-navigation", "30000",
    "--allowed-origins", ";".join(validated_origins),
    "--proxy-server", proxy_url,
]
```

Do not pass storage state, extensions, secrets, unrestricted file access, ignored TLS errors,
`--no-sandbox`, or page/model-supplied CLI arguments. On startup, compare `list_tools` to the exact raw
allowlist; an unexpected or missing tool is `mcp_protocol_error`.

- [ ] **Step 4: Map high-level actions to exact raw tools**

```python
RAW_TOOL_ALLOWLIST = frozenset(
    {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_take_screenshot",
        "browser_close",
    }
)
```

Every action rechecks budget and navigation policy. A click may reference only an element from the
immediately preceding sanitized snapshot. Never expose a general raw-tool pass-through.

- [ ] **Step 5: Produce bounded page and artifact results**

Sanitize visible text to 20,000 characters before returning it to the application. Remove MCP/tool
instructions, console/network payloads, hidden values, form values, credential-like material, and
detected prompt-injection text. Return URL, title, sanitized text, SHA-256, injection flag, and
content-addressed artifact entry only. Screenshot filenames are `<run_id>/<sha256>.png` generated by
the gateway.

- [ ] **Step 6: Test terminal cleanup**

For success, policy block, MCP error, timeout, cancellation, and malformed output, assert the gateway
requests browser close and closes stdio. No exception or result may contain raw snapshot, cookie,
token, absolute artifact path, stdout, stderr, or tool transcript.

- [ ] **Step 7: Verify and commit**

Run: `python -m pytest tests/browser/test_gateway.py -q`

Expected: PASS using fake MCP transport only.

```powershell
git add app/integrations/browser/mcp_client.py app/integrations/browser/gateway.py app/integrations/browser/sanitizer.py tests/browser/test_gateway.py
git commit -m "feat(browser): add sanitized allowlisted mcp gateway"
```

## Task 6: Implement the database-free Browser Worker

**Files:**
- Create: `app/integrations/browser/worker.py`
- Create: `tests/browser/test_worker.py`
- Modify: `run_browser_worker.py`

- [ ] **Step 1: Write failing environment, path, and cleanup tests**

```python
def test_worker_rejects_application_environment(monkeypatch):
    import pytest
    from app.integrations.browser.worker import assert_isolated_environment

    monkeypatch.setenv("DATABASE_URL", "sqlite:///secret.db")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        assert_isolated_environment()


def test_artifact_subdirectory_cannot_escape(tmp_path):
    import pytest
    from app.integrations.browser.worker import resolve_artifact_directory

    with pytest.raises(ValueError, match="artifact_path_invalid"):
        resolve_artifact_directory(tmp_path, "../escape")
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_worker.py -q`

Expected: FAIL because the worker module does not exist.

- [ ] **Step 3: Implement the RQ entry point**

```python
def execute_browser_request(descriptor_json: str) -> dict[str, object]:
    assert_isolated_environment()
    descriptor = BrowserTaskDescriptor.model_validate_json(descriptor_json)
    artifact_dir = resolve_artifact_directory(
        Path(os.environ["BROWSER_ARTIFACT_DIR"]), descriptor.artifact_subdir
    )
    plan = BrowserResearchPlan.model_validate_json(descriptor.plan_json)
    result = BrowserGateway.from_descriptor(
        descriptor,
        artifact_dir=artifact_dir,
        proxy_url=os.environ["HTTPS_PROXY"],
    ).execute(plan)
    return BrowserTaskResult.model_validate(result).model_dump(mode="json")
```

The module must not import `app.create_app`, SQLAlchemy, Acquisition, Radar, SecretStore, or MiMo.
Forbidden environment names are `DATABASE_URL`, `SECRET_KEY`, `TENANT_SECRET_KEY`, `MIMO_API_KEY`,
`MIMO_BASE_URL`, user-token variables, and application Redis URL.

- [ ] **Step 4: Add heartbeat and cancellation through dedicated Redis**

Write bounded keys `browser:heartbeat:<run_id>:<attempt>` and `browser:cancel:<run_id>:<attempt>` only.
Heartbeat values contain timestamp, action count, and page count; TTL is twice the maximum Run time.
The Worker checks cancellation before/after every action. It never enumerates unrelated keys.

- [ ] **Step 5: Implement process-group teardown**

Use `CREATE_NEW_PROCESS_GROUP` on Windows tests and `start_new_session=True` in the Linux container.
Every exit runs close, waits five seconds, terminates the process group, waits five seconds, and kills
the group if still alive. Close pipes and delete `.active`; preserve only validated result artifacts.
Fake-process tests assert `close -> terminate -> kill` ordering.

- [ ] **Step 6: Enforce artifact budgets and orphan cleanup**

Resolved paths must remain under `<BROWSER_ARTIFACT_DIR>/<run_id>`. Allow `.png`, `.json`, and `.txt`
only. Stop writes at the descriptor byte budget. Startup cleanup deletes only directories older than
24 hours with no live `.active` lease and no `.retain` marker.

- [ ] **Step 7: Verify and commit**

Run: `python -m pytest tests/browser/test_worker.py -q`

Expected: PASS with no Flask application or database initialized.

```powershell
git add app/integrations/browser/worker.py run_browser_worker.py tests/browser/test_worker.py
git commit -m "feat(browser): execute isolated browser requests"
```

## Task 7: Add tenant-owned submit, poll, cancel, and import services

**Files:**
- Create: `app/integrations/browser/service.py`
- Create: `tests/browser/test_service.py`
- Modify: `app/integrations/browser/repository.py`

- [ ] **Step 1: Write failing submit and import tests**

```python
def test_submit_persists_before_enqueue(browser_app, approved_policy, monkeypatch):
    from app.integrations.browser.service import submit_browser_run

    observed = []

    def fake_enqueue(descriptor_json: str):
        observed.append(descriptor_json)
        return "transport-job-1"

    monkeypatch.setattr("app.integrations.browser.service._enqueue_descriptor", fake_enqueue)
    result = submit_browser_run(
        browser_app,
        tenant_id="t1",
        owner_type="smoke",
        owner_id="owner-1",
        requested_url="https://example.com/dealers",
        requested_actions=("read_current_public_page",),
    )
    assert result.status == "queued"
    assert observed


def test_old_attempt_result_cannot_complete_new_attempt(browser_app):
    from app.integrations.browser.service import import_browser_result

    assert import_browser_result(
        browser_app,
        tenant_id="t1",
        run_id="run-1",
        attempt=1,
        result={"run_token": "old-token"},
    ).decision == "stale_result_ignored"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/browser/test_service.py -q`

Expected: FAIL because Browser service does not exist.

- [ ] **Step 3: Implement `submit_browser_run`**

The public signature is:

```python
def submit_browser_run(
    app,
    *,
    tenant_id: str,
    owner_type: str,
    owner_id: str,
    requested_url: str,
    requested_actions: tuple[str, ...],
) -> BrowserSubmitResult: ...
```

It requires capability, approved tenant SitePolicy, HTTPS public URL, bounded caller actions, and
healthy dedicated Browser Redis. It generates 32 random bytes, stores only SHA-256 digest, persists
the Run and commits, then enqueues the descriptor. Enqueue failure updates the same Run to failed with
`browser_transport_unavailable`. The descriptor contains no tenant or business content.

- [ ] **Step 4: Implement poll/import**

`poll_browser_run(app, tenant_id, run_id)` reads only the stored transport job ID from dedicated Redis.
It validates strict result schema, run ID, attempt, token digest, budgets, final/evidence URLs,
sanitizer result, manifest paths/hashes/sizes, and tenant-owned SQL Run before compare-and-set import.
Import stores bounded sanitized result JSON and manifest metadata, then deletes the raw transport
result/token. A stale result is ignored and audited with IDs/reason code only.

- [ ] **Step 5: Implement cancellation and cleanup**

`cancel_browser_run` conditionally marks queued/running Run cancelled, sets the dedicated Redis cancel
key, requests RQ cancellation, and prevents later import from changing terminal state.
`cleanup_browser_artifacts` defaults to dry-run, deletes only terminal tenant-owned directories older
than 30 days without `.retain`, records a bounded audit event, and clears artifact references while
preserving source URL, hash, excerpt metadata, and Run history.

- [ ] **Step 6: Test idempotency and tenant isolation**

Cover repeated submit for the same active owner, repeated poll, duplicate result, wrong tenant, wrong
token, wrong attempt, cancelled Run, RQ eviction, Redis outage, oversized result, path traversal,
checksum mismatch, and cleanup retry. No test uses a real browser or public network.

- [ ] **Step 7: Verify and commit**

Run: `python -m pytest tests/browser/test_service.py tests/browser/test_repository.py -q`

Expected: PASS.

```powershell
git add app/integrations/browser/service.py app/integrations/browser/repository.py tests/browser/test_service.py
git commit -m "feat(browser): orchestrate tenant owned browser runs"
```

## Task 8: Prove runtime isolation and document operations

**Files:**
- Create: `scripts/smoke_browser_runtime.ps1`
- Create: `docs/RUNBOOK_BROWSER_RESEARCH.md`
- Modify: `docs/SECRETS_AND_ENVIRONMENT.md`
- Modify: `docs/RUNBOOK_BACKUP_RESTORE.md`
- Modify: `docs/RUNBOOK_STAGING.md`
- Test: `tests/browser/test_runtime_contract.py`

- [ ] **Step 1: Add image-content and environment assertions**

The smoke script builds the two images, inspects their environment and filesystem, and fails if the
Browser image contains application database files, `.env`, Acquisition/Radar modules, secret-store
code, or forbidden environment variables. It verifies non-root UID, read-only root filesystem,
capability drops, no published ports, and artifact-volume write access.

- [ ] **Step 2: Add network isolation assertions**

Start only Browser Redis, egress, and Browser Worker. From Browser Worker, assert Web/database/
application Redis service names are unresolved or unreachable. Through the proxy, assert loopback,
RFC1918, link-local, reserved, metadata, non-443, mixed-DNS, and redirect-to-private fixtures return a
safe denial. A public HTTPS probe runs only when `RUN_LIVE_BROWSER_MCP=1` and uses a user-approved URL.

- [ ] **Step 3: Add process and artifact cleanup assertions**

Run fake success, partial, blocked, failed, cancelled, timeout, and killed-Worker cases. Assert no MCP
child process, `.active` lease, raw Redis token/result, or over-budget temporary artifact remains.

- [ ] **Step 4: Write the runbook**

Document capability-off default, separate Redis/network topology, permitted actions, blocked sites,
policy approval, startup/shutdown, health, cancellation, 30-day cleanup dry-run/apply, artifact backup
boundary, incident disable procedure, safe error codes, and proof required before any environment
enables Browser. State that local/static Radar remains available when Browser is off.

- [ ] **Step 5: Run focused gates**

```powershell
python -m ruff check app/integrations/browser tests/browser run_browser_worker.py run_browser_egress.py
python -m ruff format --check app/integrations/browser tests/browser run_browser_worker.py run_browser_egress.py
python -m pytest tests/browser tests/test_capabilities.py tests/test_migration_paths.py -q
docker compose build browser-worker browser-egress
powershell -ExecutionPolicy Bypass -File scripts/smoke_browser_runtime.ps1
git diff --check
```

Expected: every command exits 0; smoke prints `PASS browser runtime isolation`; no public request runs
by default.

- [ ] **Step 6: Run non-browser regression**

Run: `python -m pytest -q -k "not browser"`

Expected: all baseline non-browser tests PASS with `BROWSER_RESEARCH_ENABLED` absent.

- [ ] **Step 7: Commit documentation and evidence harness**

```powershell
git add scripts/smoke_browser_runtime.ps1 docs/RUNBOOK_BROWSER_RESEARCH.md docs/SECRETS_AND_ENVIRONMENT.md docs/RUNBOOK_BACKUP_RESTORE.md docs/RUNBOOK_STAGING.md tests/browser/test_runtime_contract.py
git commit -m "docs(browser): add isolation and operations gates"
```

## P2-0 completion checklist

- [ ] Eight tasks are committed separately and only named files were staged.
- [ ] `0015_browser_foundation` roundtrip passes without changing 0014.
- [ ] Browser capability is false by default and no route or consumer enables it.
- [ ] Dedicated Browser Redis contains descriptors/results only.
- [ ] Browser container cannot reach application Redis, Web, database, or private/metadata networks.
- [ ] URL checks and resolving proxy both fail closed; MCP allowed origins are defense in depth only.
- [ ] Browser Worker imports no Flask app, SQLAlchemy, Acquisition, Radar, SecretStore, or MiMo.
- [ ] Raw tokens, cookies, storage, page bodies, MCP transcripts, and absolute paths never reach SQL/logs.
- [ ] Every terminal path cleans process groups, heartbeats, leases, raw results, and temporary artifacts.
- [ ] Focused, migration, image, network, cleanup, and full non-browser gates pass.
- [ ] `.autopilot/evidence/P2-0/` contains exact commands, outputs, image metadata, network assertions,
  cleanup assertions, secret scan, and independent code/security review.
- [ ] Browser remains disabled after merge; P2-1 planning uses the merged baseline.
