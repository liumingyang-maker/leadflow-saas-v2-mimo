# Phase 2 Competitor Radar Final Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a manual-only, tenant-safe competitor radar that turns confirmed official dealer or distributor relationships into existing Acquisition review candidates without automatic CRM promotion or outreach.

**Architecture:** Execute six independently reviewable subprojects. P2-0 builds an isolated Browser foundation; P2-1 creates the approved competitor domain; P2-2 captures structured manual-run baselines; P2-3 completes the first radar-to-candidate vertical slice; P2-4 adds deterministic change monitoring; P2-5 is the release and security gate. Each subproject receives a fresh detailed plan after rebasing on the preceding merged baseline.

**Tech Stack:** Python 3.11/3.12, Flask application factory, SQLAlchemy 2, Alembic, RQ/Redis, Pydantic 2, Jinja/HTMX, pytest, Ruff, Playwright MCP/Chromium, Docker Compose, PowerShell smoke scripts.

---

## 1. Document authority and current baseline

This is the final program-level execution contract for:

- design: `docs/superpowers/specs/2026-08-03-phase-2-competitor-radar-core-design.md`;
- execution baseline: Git `e090356` on `feat/acquisition-global-quality-p0`;
- migration head at planning time: `0014_acquisition_core`;
- implemented baseline: global Acquisition quality Slice 0/1 only;
- Browser baseline: `browser_research` capability placeholder only, disabled by default;
- scheduling decision: manual runs only.

The old `2026-08-01-solo-acquisition-phase-1b-browser.md` plan is historical input, not an executable
plan. It mixed Browser foundation with competitor UI, email, CSV, and WhatsApp scope and did not prove
container-layer private-network blocking. P2-0 replaces it.

No feature implementation is authorized by this document alone. The user approves one subproject,
then its detailed plan is executed in an isolated branch/worktree and reviewed before the next plan is
written.

## 2. Independent disposition of external audit suggestions

### Adopted

1. Deliver the initial relationship-to-candidate slice before change monitoring:
   `P2-2 -> P2-3 relationships -> P2-4 signals`.
2. Distinguish `dynamic_content_suspected`, `requires_browser`, and
   `no_relationships_observed`; never infer Browser need from an empty result alone.
3. Add deterministic run-level drift protection; never automatically reset a baseline.
4. Automatic conversion requires a `confirmed` `dealer` or `distributor`; partner and ambiguous
   relationships remain suggestions.
5. Show Radar provenance and the limited meaning of competitor relationship evidence on Candidate UI.
6. Aggregate Radar notifications to at most one notification per tenant/profile/Run and show at most
   five highlights.
7. Use one forward-only migration per Radar subproject.
8. Provide a deterministic link-classification fallback when MiMo is unavailable.

### Rejected or deferred

1. Do not reduce the labeled replay corpus from 50 to 20.
2. Do not add `reusable_for_acquisition`; reuse is contextual and cross-Mission reuse is out of scope.
3. Do not use a raw `>80% pages changed` rule or automatically reset the baseline.
4. Do not use Wayback or another historical archive as current official-site verification.
5. Do not treat search summaries as currently re-entering the extraction prompt; that data-flow claim
   is false on the planning baseline.

### Separate Acquisition work, not Phase 2 scope

Top-N verification ranking, evidence freshness, stage-by-country attribution, remaining-budget UI,
and evidence-to-signal causality remain valid improvements for global Acquisition Slice 2/3. They may
reuse canonical URL, safety, reason-code, and provenance primitives, but they must not be smuggled into
a Radar PR or make Radar depend on unfinished Acquisition slices.

## 3. Non-negotiable release invariants

- [ ] Browser remains disabled by default in internal, commercial, development, and testing modes.
- [ ] No recurring scheduler, `next_run_at`, cron-created Radar Run, or unattended scan exists.
- [ ] Every SQL read/write is tenant-scoped; every logical uniqueness key includes `tenant_id`.
- [ ] Web requests persist business state and SQL Job before queue enqueue.
- [ ] Application RQ payloads contain IDs only; Browser transport contains bounded descriptors only.
- [ ] Browser execution has no database URL, Flask/tenant/MiMo secret, user token, cookie, or storage state.
- [ ] Browser has no direct network path to Web, database, application Redis, localhost, private,
  link-local, reserved, or cloud-metadata destinations.
- [ ] No full HTML, raw model response, raw MCP transcript, cookie, local storage, or chain of thought is
  persisted.
- [ ] AI cannot create an uncited fact, arbitrary crawl URL, deterministic delta, or automatic approval.
- [ ] No Radar path accepts a Candidate, promotes it to CRM, sends outreach, or triggers paid analysis.
- [ ] Cancellation and possible baseline drift prevent later automatic conversion.
- [ ] Historical user decisions and converted Candidates survive capability disable and rollback.

Any violation is Critical and stops the current subproject.

## 4. Dependency and delivery graph

```text
P2-0 Browser Foundation Gate
  -> P2-1 Competitor Suggestions and Approved Profiles
      -> P2-2 Manual Runs and Structured Baselines
          -> P2-3 Confirmed Relationships and Review Candidates
              -> first user-value vertical slice
              -> P2-4 Deterministic Commercial Change Signals
                  -> P2-5 Runtime, Security, UX, and Release Gate
```

P2-1 may start only after P2-0 code review even though static Radar does not require Browser at runtime.
This preserves one known Browser contract for all later fallback integration. Browser fallback itself
remains capability- and policy-gated.

## 5. Branch, migration, and review matrix

| Slice | Branch/PR scope | Expected migration if no intervening revision | Required result |
|---|---|---|---|
| P2-0 | Browser runtime only | `0015_browser_foundation` | disabled isolated runtime and security evidence |
| P2-1 | suggestions/profiles | `0016_radar_profiles` | human-approved competitor profile |
| P2-2 | runs/snapshots | `0017_radar_runs` | manual structured baseline, partial preservation |
| P2-3 | relationships/conversion | `0018_radar_relationships` | confirmed dealer/distributor becomes `needs_evidence` Candidate |
| P2-4 | signals/workbench | `0019_radar_signals` | deterministic Diff, drift guard, aggregated notification |
| P2-5 | release evidence only | none unless a reviewed defect requires forward fix | all release gates pass |

Before creating each migration, run `python -m alembic heads`. If another revision exists, use the
actual current head and update that slice's detailed plan; never create a branch or merge revision
silently and never edit a published migration.

Each slice uses one branch, one focused PR, and small commits. Never use `git add .`, `git add -A`,
force-push, or production deployment. Existing untracked `work/` files are local runtime state and are
never staged.

## 6. P2-0 — Browser Foundation Gate

Executable detailed plan:
`docs/superpowers/plans/2026-08-03-p2-0-browser-foundation.md`.

P2-0 owns only:

- dedicated Browser transport Redis/namespace;
- isolated Browser Worker image and queue;
- egress proxy and container network restrictions;
- `BrowserSitePolicy` and `BrowserResearchRun` persistence;
- bounded descriptor/result contracts;
- per-navigation URL checks, tool allowlist, sanitizer, artifact manifest;
- lease, heartbeat, result import, cancellation, crash recovery, and cleanup;
- offline/runtime security smoke and runbooks.

P2-0 does not add Radar routes, competitor profiles, Acquisition fallback, email, CSV, WhatsApp,
LinkedIn automation, logins, form submission, uploads, downloads, arbitrary JavaScript, proxy rotation,
or a production capability enablement.

### P2-0 exit gate

- [ ] `0014 -> 0015 -> 0014 -> 0015` migration roundtrip passes on a disposable copy.
- [ ] Browser image contains no application secret or database configuration.
- [ ] Browser process reaches only dedicated transport Redis and the egress proxy.
- [ ] Proxy/runtime smoke blocks loopback, RFC1918, link-local, reserved, metadata, redirects to private
  IPs, and DNS rebinding fixtures.
- [ ] Success, partial, blocked, failed, cancelled, timeout, and crash paths release process groups,
  leases, Redis results, and temporary artifacts.
- [ ] Static application behavior and the complete non-browser suite remain green with Browser off.
- [ ] Capability stays off after merge.

## 7. P2-1 — Competitor Profile Domain

Write `docs/superpowers/plans/2026-08-03-p2-1-radar-profiles.md` only after P2-0 merges. The detailed plan
must use the actual baseline and include TDD steps for these contracts:

### Files owned

```text
app/modules/radar/__init__.py
app/modules/radar/models.py
app/modules/radar/contracts.py
app/modules/radar/repository.py
app/modules/radar/policies.py
app/modules/radar/suggestions.py
app/modules/radar/service.py
app/modules/radar/routes.py
app/modules/radar/views.py
app/templates/radar/overview.html
app/templates/radar/suggestions.html
app/templates/radar/profile_detail.html
migrations/versions/0016_radar_profiles.py
tests/radar/conftest.py
tests/radar/test_models.py
tests/radar/test_repositories.py
tests/radar/test_suggestions.py
tests/radar/test_routes.py
```

### Required public contracts

```python
def request_competitor_suggestions(
    app, *, tenant_id: str, actor_id: str, mission_id: str
) -> tuple[str, ...]: ...

def decide_competitor_suggestion(
    app, *, tenant_id: str, actor_id: str, suggestion_id: str, action: str
): ...
```

Suggestion output is capped at 10, schema-valid, evidence-cited, and URL-policy checked. Approval
atomically creates at most one `(tenant_id, mission_id, canonical_domain)` profile. Dismissal is
terminal until the source-evidence hash changes. Routes require authentication, capability, tenant
authorization, and CSRF. No page fetch or Radar Run is introduced.

### P2-1 exit gate

- [ ] Cross-tenant get/list/approve/dismiss returns not-found or authorization failure with no leak.
- [ ] Duplicate approval and repeated POST are idempotent.
- [ ] Model confidence alone cannot persist a suggestion.
- [ ] A terminal or cross-tenant Mission cannot receive a profile.
- [ ] Migration roundtrip and full non-browser regression pass.

## 8. P2-2 — Manual Runs and Structured Baselines

Write `docs/superpowers/plans/2026-08-03-p2-2-radar-runs.md` after P2-1 merges.

### Files owned

```text
app/modules/radar/snapshots.py
app/modules/radar/jobs.py
app/modules/radar/service.py
app/modules/radar/routes.py
app/modules/radar/views.py
app/templates/radar/run_detail.html
migrations/versions/0017_radar_runs.py
tests/radar/test_page_planning.py
tests/radar/test_snapshots.py
tests/radar/test_jobs.py
tests/radar/test_manual_runs.py
```

### Required public contracts

```python
def request_manual_run(
    app, *, tenant_id: str, actor_id: str, profile_id: str
): ...

def cancel_manual_run(
    app, *, tenant_id: str, actor_id: str, run_id: str
): ...

def finalize_snapshot(
    *, profile_id: str, run_id: str, page_kind: str, fetched_page
): ...
```

Only the homepage is implicit. Additional URLs are user-configured or observed same-domain links.
MiMo classification falls back to versioned deterministic anchor/path rules. Static success never
starts Browser. `dynamic_content_suspected` requires positive application-shell evidence; when
Browser is unavailable it becomes `requires_browser`, while ordinary absence becomes
`no_relationships_observed`.

Snapshots contain canonical structured facts, a 4,000-character excerpt, versions, URL, hash, safe
reason codes, and optional opaque artifact reference. Identical content creates no second snapshot.
Repeated manual POST returns the existing active Run. Cancellation preserves finished snapshots and
prevents later children.

### P2-2 exit gate

- [ ] No schedule or unattended run path exists.
- [ ] Page, Browser, wall-time, artifact, and excerpt budgets are persisted and enforced.
- [ ] Partial pages survive any other page/model/Browser failure.
- [ ] Browser result import is tenant-owned, token/attempt-bound, sanitized, and idempotent.
- [ ] Dynamic, static-empty, injection, redirect, unreachable, and multilingual fixtures pass.

## 9. P2-3 — Relationships and Review Candidates

Write `docs/superpowers/plans/2026-08-03-p2-3-radar-relationships.md` after P2-2 merges.

### Files owned

```text
app/modules/radar/relationships.py
app/modules/radar/conversion.py
app/modules/acquisition/service.py
app/modules/acquisition/routes.py
app/templates/radar/profile_detail.html
app/templates/radar/run_detail.html
app/templates/acquisition/_candidate_card.html
migrations/versions/0018_radar_relationships.py
tests/radar/test_relationships.py
tests/radar/test_conversion.py
tests/acquisition/test_radar_candidate_boundary.py
```

### Required public boundary

```python
def create_candidate_from_radar_relationship(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    mission_id: str,
    relationship_id: str,
    expected_domain: str,
): ...
```

Radar never writes Candidate/Evidence tables directly. The Acquisition service re-reads and checks
tenant, active Mission, relationship, domain, official-source evidence, evidence strength, type,
cancellation, and drift state inside one transaction. It returns an existing Mission/domain Candidate
or creates one `needs_evidence` Candidate plus B-tier `competitor_dealer_network` evidence.

Automatic conversion is limited to confirmed dealer/distributor relationships. Partner never
auto-converts. Service-network conversion is human-only and requires a `repair_network` target plus
corpus coverage. Candidate UI explains that competitor provenance does not prove target country,
contactability, buying intent, or own-site identity.

### P2-3 exit gate

- [ ] Confirmed-relationship precision is at least 70% on the versioned corpus.
- [ ] Likely/unknown/partner relationships produce zero automatic Candidates.
- [ ] Retry, race, cancellation, terminal Mission, and domain dedupe produce zero duplicate Candidates.
- [ ] Automatic CRM promotion, analysis enqueue, verification enqueue, and outreach counts remain zero.

## 10. P2-4 — Commercial Change Signals

Write `docs/superpowers/plans/2026-08-03-p2-4-radar-signals.md` after P2-3 merges.

### Files owned

```text
app/modules/radar/diff.py
app/modules/radar/policies.py
app/modules/radar/jobs.py
app/modules/radar/views.py
app/modules/acquisition/workbench.py
app/templates/radar/run_detail.html
app/templates/radar/profile_detail.html
app/templates/app/_workbench_live.html
migrations/versions/0019_radar_signals.py
tests/radar/test_diff.py
tests/radar/test_drift.py
tests/radar/test_notifications.py
tests/radar/test_signal_routes.py
```

### Required pure contracts

```python
def diff_snapshots(previous, current, *, detector_version: str) -> bytes: ...

def detect_baseline_drift(
    *, previous_run, current_run, policy_version: str
): ...

def classify_existing_delta(*, delta, cited_evidence, classifier) -> object: ...
```

The same inputs and detector version produce byte-identical canonical output. The classifier receives
only an existing delta and cited excerpts and cannot invent facts. Baselines and identical snapshots
produce no signal. Classifier failure preserves an informational deterministic Diff.

The drift guard activates for extractor/parser version change, at least 50% comparable page-identity
loss, or at least 60% stable-fact disappearance across two page kinds, with at least three comparable
pages. Drift preserves evidence but suppresses automatic conversion, relationship removals, and
material notifications until explicit human baseline acceptance.

One `(tenant_id, profile_id, run_id)` produces at most one aggregate notification with at most five
highlights. All signals remain available on Run detail.

### P2-4 exit gate

- [ ] Identical-input Diff determinism is 100%.
- [ ] Baseline and identical-run false notifications are zero.
- [ ] Material-change precision is at least 80% on the 50+ case corpus.
- [ ] Redesign/version-drift fixtures cannot delete relationships or create Candidates automatically.
- [ ] Notification row count per profile/Run is at most one under concurrency and retry.

## 11. P2-5 — Runtime, Security, UX, and Release Gate

Write `docs/superpowers/plans/2026-08-03-p2-5-radar-release-gate.md` after P2-4 merges. P2-5 adds evidence,
fixtures, smoke tools, and runbook corrections; it does not add product scope.

### Required evidence

```text
.autopilot/evidence/P2-5/
  environment.txt
  migration-roundtrip.txt
  ruff.txt
  pytest-non-browser.txt
  pytest-radar.txt
  tenant-negative.txt
  browser-image-build.txt
  browser-offline-smoke.txt
  browser-network-smoke.txt
  cleanup-smoke.txt
  local-copy-smoke.txt
  playwright-desktop.txt
  playwright-mobile.txt
  accessibility.txt
  performance.json
  replay-report.json
  secret-scan.txt
  git-diff-check.txt
  independent-review.md
```

### Required commands

```powershell
python -m ruff check .
python -m ruff format --check .
python -m pytest tests/radar tests/acquisition -q
python -m pytest -q -k "not browser"
python -m alembic heads
git diff --check
docker compose build browser-worker browser-egress
powershell -ExecutionPolicy Bypass -File scripts/smoke_browser_runtime.ps1
powershell -ExecutionPolicy Bypass -File scripts/smoke_radar_local_copy.ps1
```

Every command's exact output and exit code is captured. Public-web/provider tests remain opt-in and
never use customer data. Local-copy smoke begins from a backup and writes only to a disposable copy.

### P2-5 release gate

- [ ] 50+ labeled cases, corpus/model/parser/detector versions, denominators, and sample counts recorded.
- [ ] Structured schema success >=98%, confirmed relationship precision >=70%, material precision >=80%.
- [ ] One bounded manual profile Run completes within five minutes on the staging sample.
- [ ] Automatic CRM/outreach and cross-tenant read/write counts are zero.
- [ ] Browser private-network and cleanup gates pass; otherwise Browser remains disabled.
- [ ] Desktop/mobile keyboard, non-color status, CSRF, and authenticated UI smokes pass.
- [ ] Independent code/security/product review reports no Critical or Important finding.
- [ ] User explicitly approves capability enablement; otherwise ship code with the capability off.

## 12. Per-slice execution protocol

For every slice:

- [ ] Rebase an isolated worktree on the actual approved baseline.
- [ ] Read this document, the design spec, AGENTS.md, and the prior slice release evidence.
- [ ] Confirm `git status --short`, `git log -1`, `python -m alembic heads`, and baseline tests.
- [ ] Write the slice's detailed TDD plan with exact current file locations and expected failures.
- [ ] Obtain design/plan review before implementation.
- [ ] Implement one red-green-refactor task at a time.
- [ ] Run focused tests after every task and commit only named files.
- [ ] Run Standards and Spec review, then security review; add UI review when applicable.
- [ ] Correct findings and rerun focused plus full applicable gates.
- [ ] Record `.autopilot/evidence/<slice>/` artifacts before claiming PASS.
- [ ] Merge only after CI and user-authorized release workflow; sync the next baseline afterward.

## 13. Stop conditions

Stop the slice and return to design when any of these occurs:

- hosted network isolation cannot prevent private/metadata egress;
- a required data ownership check cannot be expressed with tenant-inclusive constraints;
- a Radar action can change a human-terminal Candidate or CRM state;
- precision gates require product-specific or country-specific hard-coded confirmation rules;
- implementation requires scheduling, Places, YouTube, paid providers, full-page archives, cross-Mission
  reuse, SaaS billing, or automatic outreach;
- a published migration would need editing or a destructive downgrade;
- the actual baseline materially invalidates the current slice plan.

## 14. Final program completion

Phase 2 is complete only when P2-0 through P2-5 are merged in order, every release artifact exists,
the full manual radar-to-review-candidate path passes against a disposable local-data copy, Browser
is either proven and explicitly enabled or safely left disabled, and the user approves the release.
