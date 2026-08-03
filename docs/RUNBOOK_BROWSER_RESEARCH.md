# Runbook: Browser Research Foundation

## Current release state

Browser research is a **disabled-by-default foundation**. It has no UI route, no Acquisition/Radar
consumer, no scheduler, and no automatic CRM or outreach action. Keep `BROWSER_RESEARCH_ENABLED`
absent or `false` until every gate below passes.

The feature is deliberately not usable just because its containers start. A Browser run requires an
explicit capability opt-in, an approved tenant-owned Site Policy, a public HTTPS URL, bounded caller
actions, and a healthy dedicated Browser Redis instance.

## Intended isolation

```text
Application Worker -- browser-control --> Browser Redis
Application Worker -- artifact volume --> Browser artifacts
Browser Worker -- browser-control --> Browser Redis / resolving egress proxy
Egress proxy -- browser-public --> public HTTPS:443 only
```

The Browser Worker must not receive `DATABASE_URL`, application `REDIS_URL`, Flask secrets, tenant
keys, MiMo configuration, user tokens, database access, or the normal application network. It may
only use `BROWSER_REDIS_URL`, `BROWSER_ARTIFACT_DIR`, and `HTTPS_PROXY`.

## Local Docker validation

After Docker Desktop is installed and running, execute:

```powershell
docker version
docker compose version
python -m pytest tests/browser tests/test_capabilities.py tests/test_migration_paths.py -q
powershell -ExecutionPolicy Bypass -File scripts/smoke_browser_runtime.ps1
```

The smoke exits with code `0` only after proving container isolation and the exact restricted MCP
tool-list contract. It does not create a page or make a public navigation.

## Restricted MCP compatibility gate

The pinned `@playwright/mcp@0.0.78` CLI exposes additional dangerous tools such as JavaScript
evaluation, form entry, upload and download. The local `restricted_playwright_mcp.cjs` stdio facade
is the only process started by the Python gateway; it validates requests and exposes exactly:

```text
browser_navigate
browser_snapshot
browser_click
browser_take_screenshot
browser_close
```

Do not weaken that equality check or invoke Playwright MCP directly. The smoke captures the actual
facade tool list without a public navigation. Browser research remains disabled until all other
operator and tenant-policy gates are also satisfied.

## Operator boundaries

- Browser permits public HTTPS navigation on port 443 only; it does not log in, submit forms, upload
  or download files, use persistent storage, or use ignored TLS errors.
- Unknown sites require review. `linkedin.com`, rejected terms/robots, `manual_only`, and `blocked`
  policies are denied before work is queued.
- One-time run tokens are sent only in the isolated descriptor and stored as SHA-256 digests in SQL.
  Never log, export, or persist a raw run token in application records.
- Artifacts live under a content-addressed tenant-owned run directory. Cleanup is dry-run by default;
  it skips `.retain` and active lease markers.

## Incident response

If the Browser worker sees any forbidden environment variable, an unexpected MCP tool, unsafe DNS
answer, cross-origin redirect, artifact path escape, sanitizer violation, or token/attempt mismatch:

1. Keep Browser capability disabled.
2. Preserve only safe IDs, reason codes, hashes, and bounded metadata for review.
3. Stop the Browser services with `docker compose stop browser-worker browser-egress browser-redis`.
4. Do not retry against a different host, protocol, or historical archive automatically.
5. Re-enable only after the specific gate has an automated regression test and a reviewed result.
