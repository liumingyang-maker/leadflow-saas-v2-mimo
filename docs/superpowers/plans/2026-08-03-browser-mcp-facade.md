# Browser MCP Facade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Browser Worker expose only five audited MCP operations while retaining the pinned Playwright MCP implementation behind a local stdio boundary.

**Architecture:** `restricted_playwright_mcp.cjs` starts the fixed Playwright MCP argv supplied after `--`, proxies initialization and approved operations, returns its own exact `tools/list` result, validates approved call arguments, and rejects everything else. The Python gateway starts this facade rather than Playwright MCP directly.

**Tech Stack:** Node.js 22 stdio processes, JSON-RPC 2.0, Python pytest, Docker Compose, `@playwright/mcp@0.0.78`.

---

## File structure

- Create: `app/integrations/browser/restricted_playwright_mcp.cjs` — stdio facade and upstream child lifecycle.
- Create: `tests/browser/fixtures/fake_playwright_mcp.cjs` — deterministic JSON-RPC upstream.
- Create: `tests/browser/test_restricted_mcp.py` — black-box facade tests.
- Modify: `app/integrations/browser/gateway.py` — fixed facade argv.
- Modify: `Dockerfile.browser` — copy the facade into the minimal image.
- Modify: `tests/browser/test_gateway.py` — fixed command test.
- Modify: `tests/browser/test_runtime_contract.py` — image and smoke contract tests.
- Modify: `scripts/smoke_browser_runtime.ps1` — exact-tool test with no navigation.
- Modify: `docs/RUNBOOK_BROWSER_RESEARCH.md` — closed compatibility gate.

### Task 1: Black-box facade tests

**Files:** `tests/browser/fixtures/fake_playwright_mcp.cjs`, `tests/browser/test_restricted_mcp.py`

- [ ] **Step 1: Write a failing exact-tool-list test.**

Launch `node app/integrations/browser/restricted_playwright_mcp.cjs -- node tests/browser/fixtures/fake_playwright_mcp.cjs`; send `initialize` and `tools/list` and assert:

```python
assert set(result["tools_by_name"]) == {
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_take_screenshot", "browser_close",
}
assert "browser_evaluate" not in result["tools_by_name"]
```

- [ ] **Step 2: Run `python -m pytest -q tests/browser/test_restricted_mcp.py::test_facade_lists_exact_allowlist`.**

Expected: FAIL because the facade process is absent.

- [ ] **Step 3: Write failing forwarding and rejection tests.**

The fake upstream records `tools/call`. Assert screenshot forwarding adds `scale: "css"`; assert `browser_evaluate` returns JSON-RPC error `-32601` and never appears in the upstream record.

```python
assert forwarded_screenshot == {
    "type": "png", "filename": "a" * 64 + ".png", "scale": "css"
}
assert rejected["error"]["code"] == -32601
assert "browser_evaluate" not in upstream_recorded_tool_names
```

- [ ] **Step 4: Run `python -m pytest -q tests/browser/test_restricted_mcp.py::test_facade_normalizes_screenshot_and_rejects_unknown_tool`.**

Expected: FAIL before the fake upstream receives a permitted call.

### Task 2: Fail-closed stdio facade

**Files:** `app/integrations/browser/restricted_playwright_mcp.cjs`, `tests/browser/fixtures/fake_playwright_mcp.cjs`

- [ ] **Step 1: Define the only accepted calls.**

The facade accepts command and arguments only after literal `--`. It rejects extra properties and accepts screenshot filenames only when they match `^[a-f0-9]{64}\.png$`.

```javascript
const forwards = {
  browser_navigate: ({ url }) => ({ url }),
  browser_snapshot: () => ({}),
  browser_click: ({ target }) => ({ target }),
  browser_take_screenshot: ({ type, filename }) => ({ type, filename, scale: 'css' }),
  browser_close: () => ({}),
};
```

`browser_navigate` and `browser_click` require nonempty strings; screenshot requires `type === "png"`.

- [ ] **Step 2: Implement JSON-RPC mediation.**

Forward `initialize` and `notifications/initialized` to the child, answer `tools/list` locally, and forward only validated `tools/call` requests. Return `-32601` for unknown method/tool and `-32602` for malformed parameters. Never write child stderr to facade stdout. On stdin close, SIGTERM, or child exit, close child stdin and terminate the child.

- [ ] **Step 3: Run `python -m pytest -q tests/browser/test_restricted_mcp.py`.**

Expected: PASS with no upstream forwarding of an unapproved tool.

- [ ] **Step 4: Commit with message `feat(browser): add restricted mcp facade`.**

### Task 3: Fixed Python and Docker wiring

**Files:** `app/integrations/browser/gateway.py`, `Dockerfile.browser`, `tests/browser/test_gateway.py`, `tests/browser/test_runtime_contract.py`

- [ ] **Step 1: Write a failing fixed-command test.**

```python
command = build_mcp_command(
    artifact_dir=Path("/artifacts"), max_artifact_bytes=1024,
    allowed_origins=("https://example.com",), proxy_url="http://browser-egress:8080",
)
assert command[:3] == ["node", "./restricted_playwright_mcp.cjs", "--"]
assert command[3] == "./node_modules/.bin/playwright-mcp"
```

The runtime-contract test also asserts Docker copies the facade source.

- [ ] **Step 2: Run `python -m pytest -q tests/browser/test_gateway.py tests/browser/test_runtime_contract.py`.**

Expected: FAIL because the pre-change command points directly to Playwright MCP.

- [ ] **Step 3: Make the command fixed.**

The gateway returns the facade executable, literal `--`, the existing literal pinned Playwright executable, and its existing fixed flags. No plan, descriptor, environment, or model can choose an executable, tool, or additional flag. Docker copies only the facade source in addition to the existing Browser image allowlist.

- [ ] **Step 4: Run `python -m pytest -q tests/browser/test_gateway.py tests/browser/test_runtime_contract.py tests/browser/test_restricted_mcp.py`.**

Expected: PASS.

- [ ] **Step 5: Commit with message `fix(browser): route gateway through restricted facade`.**

### Task 4: Actual Docker no-navigation gate

**Files:** `scripts/smoke_browser_runtime.ps1`, `docs/RUNBOOK_BROWSER_RESEARCH.md`, `tests/browser/test_runtime_contract.py`

- [ ] **Step 1: Write failing smoke-source assertions.**

Assert the smoke invokes `BrowserGateway.assert_raw_tool_contract`, contains no `OPEN GATE`, and has no `exit 2` after its tool-list check.

- [ ] **Step 2: Run `python -m pytest -q tests/browser/test_runtime_contract.py`.**

Expected: FAIL because the current smoke reports an open gate.

- [ ] **Step 3: Change smoke and runbook.**

After image, environment, filesystem, and network checks, the smoke runs Python inside `browser-worker` to construct a fixed `BrowserGateway` and call `assert_raw_tool_contract`. It does not call `execute`, `browser_navigate`, or any public URL. On success it prints `PASS exact restricted MCP tool contract`, exits `0`, and stops only Browser services. The runbook records the proof but retains the disabled-default capability.

- [ ] **Step 4: Run the actual gates.**

```powershell
python -m pytest -q tests/browser tests/test_capabilities.py tests/test_migration_paths.py
docker compose build browser-worker browser-egress
powershell -ExecutionPolicy Bypass -File scripts/smoke_browser_runtime.ps1
git diff --check
```

Expected: each exits `0`; the smoke prints isolation and exact-tool-contract PASS lines with no public navigation.

- [ ] **Step 5: Commit with message `test(browser): verify restricted mcp runtime contract`.**

## Completion checklist

- [ ] The facade exposes exactly five tools with no configuration escape hatch.
- [ ] Unknown tools and malformed arguments are rejected before forwarding.
- [ ] Screenshot forwarding fixes PNG type, content-addressed filename, and CSS scale.
- [ ] The Python gateway can launch only the facade and pinned upstream with fixed flags.
- [ ] Docker smoke proves the actual tool list without public navigation.
- [ ] Browser remains disabled by default and no consumer, UI, or scheduler is added.

