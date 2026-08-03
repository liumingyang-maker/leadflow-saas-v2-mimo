# ACQ-global-quality-p0 gate results

Verified on 2026-08-03 (Asia/Shanghai) in worktree
`work/worktrees/acquisition-global-quality-p0`, branch
`feat/acquisition-global-quality-p0`, against base `02de760`.

## Automated tests

- Focused Slice 0/1 suites:
  `python -m pytest tests/acquisition/test_quality_replay.py tests/acquisition/test_business_results.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py tests/acquisition/test_workbench.py tests/acquisition/test_routes.py -o addopts= -q`
  - Result: `232 passed in 85.56s`
- Complete acquisition suite:
  `python -m pytest tests/acquisition -o addopts= -q`
  - Result: `410 passed in 85.61s`
- Proportionate full non-browser suite:
  `python -m pytest --ignore=tests/test_playwright_launch_acceptance.py --ignore=tests/test_playwright_collection.py --ignore=tests/test_playwright_crm.py --ignore=tests/test_playwright_outreach_inbound.py -o addopts= -q`
  - Result: `710 passed in 155.51s`

## Static and diff gates

- `python -m ruff check .`: passed.
- `python -m ruff format --check app tests tools run_worker.py`: passed; 144 files already formatted.
- `git diff --check`: passed.
- `git diff --check 02de760..HEAD`: passed.
- `git diff --name-only 02de760..HEAD -- migrations`: no output; published migrations are unchanged.
- The production search found only the pre-existing public-suffix entry `com.mx`; no added production line contains `.mx`, `mexicana`, `Spanish`, or `español`, and no country-specific branch was introduced.

## Migration roundtrip

A disposable SQLite database under a task-specific `C:\tmp\leadflow-global-quality-p0-migrations-*` directory was upgraded to head, downgraded to `0013_admin_auth_version`, and upgraded again.

- Final revision: `0014_acquisition_core (head)`
- Result: passed.

## Slice 0 deterministic replay

The replay command was run twice against the versioned, redacted, offline fixture manifest:

`python tools/acquisition_quality_replay.py --manifest tests/fixtures/acquisition/global_quality/cases.json --output .autopilot/evidence/ACQ-global-quality-p0/slice-0-replay.json`

- Suite: `acquisition-global-quality-v1`
- Cases: 14
- Compared fields: 70
- Legacy matches: 33
- Baseline gaps: 37
- Deterministic SHA-256 on both runs: `5C9D9CD6623C745ECC2F463F755316D0D7CE2452B3C03CB2A349B567655C1022`
- External page bodies included: no.
- Secret-, password-, token-, or API-key-named fields included: no.

## Database-copy Mission replay

The source SQLite database was opened read-only and copied with SQLite's online backup API into a task-specific `C:\tmp\leadflow-global-quality-p0-copy-*` directory. All application writes, authentication setup, reconciliation, and UI checks targeted only the copy. The live database was not opened by a write-capable application.

Mission `93d10a606ecc47199037645554836107` projected as:

```text
execution_status=failed
business_result=partial
discovered=10
needs_review=8
ready_to_review=0
crm_ready=0
excluded=2
evidence=19
failed_jobs=8
```

The reconciler backfilled the legacy terminal Mission exactly once and then skipped the
now-consistent row on later runs. The final post-restart replay returned `changed=0`. The current
notification uses the shared `partial` result and the opposite legacy terminal notification is
archived.

## Runtime readiness

Only environment-variable existence was checked; no value was printed or recorded. The five required settings were present.

- Memurai/Redis processes: 1
- Web listeners on port 5000: 1
- Registered RQ Workers: 1 (`idle`)
- Default queue jobs: 0
- `GET /health/ready`: HTTP 200 with database `ok` and Redis `ok`.
- Provider calls made during verification: 0.
- Outreach actions made during verification: 0.

## Single-tab authenticated UI smoke

One in-app browser tab was used sequentially against the database copy. Login, task list, old Mission detail, HTMX status fragment, workbench, and notifications all loaded successfully.

- Task list: `部分完成`, discovered 10, needs evidence 8, excluded 2, verification failures 8.
- Mission detail: `部分完成`, execution status `失败`, the same counts, safe reason `部分官网验证失败`, and action `查看部分结果`.
- HTMX status: the same business result and counts; no raw `None` appeared.
- Workbench recent Missions: the same business result and counts.
- Notifications: the current notification says `找客户任务部分完成` with the same counts and action. Archived legacy completion notifications are excluded from the list.
- Failure, partial, review, and rejection states use distinct tones plus explicit text labels/actions, so meaning does not depend on color alone.
- Browser console errors after the clean post-restart observation window: none. Historical
  `htmx:sendError` entries were limited to the deliberate Web restart window; a fresh reload
  plus a complete 6.5-second polling interval produced no new log entries.

## Demonstrated defects corrected test-first

- Legacy terminal Missions without a structured result were not eligible for reconciliation. A focused regression test failed first, then the reconciler was extended to backfill them once.
- Archived opposite-terminal notifications remained visible and contradicted the current result. A focused regression test failed first, then notification listing was changed to exclude archived rows.
- A non-terminal retry could supersede the latest terminal Job outcome. Regressions now prove
  that queued, running, and retrying Jobs do not erase a prior terminal failure, while a newer
  terminal outcome does supersede it.
- Failed-verification repair previously considered any historical failure. The reconciler now
  uses only the latest terminal verification outcome; later success is preserved and later
  cancellation safely returns a stuck candidate to `needs_evidence` for retry.
- Retrying a completed Mission could demote its execution status or leave its terminal
  notification archived. A pending-reconcile marker now preserves usable completed results
  during active retry and reactivates the current notification after the retry terminates.
- Mission summary projection performed per-Mission candidate/evidence/Job queries. It now batch
  loads tenant-scoped rows and the regression gate caps the summary path at four SELECTs.
- Notification reads previously used a read-then-write ORM sequence. They now use one
  tenant-scoped conditional `UPDATE ... RETURNING`, so a stale read cannot resurrect an archived
  notification.
- Startup reconciliation previously synchronously enumerated tenant business rows. Startup now
  enumerates only the control-plane Tenant registry, persists one tenant-owned
  `acquisition_reconcile` Job per non-deleted tenant, and the registered handler performs all
  Mission, candidate, evidence, provider-status, and Job work under the owning `tenant_id`.
- Independent final review of commit `fa94ae5` reported PASS with no remaining
  Critical/Important findings.

## Scope audit

- All Mission, candidate, evidence, provider-status, Job, and notification business queries in
  reconciliation require explicit tenant scope. The only global scheduler query is against the
  control-plane Tenant registry; every scheduled unit is persisted and tenant-owned.
- Malformed Job payloads are ignored safely; Job payload matching uses bounded IDs.
- No Slice 2+ country/contact/entity resolver or extractor was added.
- No delayed MiMo analysis, cross-Mission evidence reuse, feedback engine, or automatic outreach was added.
- No migration was changed and no live-data rewrite was performed.
- The replay artifact contains fixture metadata, expectations, legacy outputs, and field gaps only; it contains no external page body or credential material.
