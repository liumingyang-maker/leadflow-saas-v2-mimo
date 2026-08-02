# Workbench Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair inconsistent acquisition terminal states and make the solo workbench show actionable, live progress instead of permanent historical errors.

**Architecture:** Acquisition reconciliation owns candidate-state recovery and Mission terminal derivation. The workbench exposes a tenant-scoped read projection and an HTMX live partial; candidate retry is an explicit guarded command.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy 2, RQ/Redis, Jinja, HTMX, pytest, Ruff.

---

### Task 1: Candidate and Mission terminal-state recovery

**Files:**
- Modify: `tests/acquisition/test_jobs.py`
- Modify: `app/modules/acquisition/jobs.py`
- Modify: `app/modules/jobs/worker.py`

- [ ] **Step 1: Write failing reconciliation tests**

Add tests that create a `verifying` candidate plus a terminal failed `website_verify` Job, run `reconcile_missions`, and assert the candidate becomes `needs_evidence`, the Mission has zero usable candidates, and the terminal notification does not claim the candidate is usable. Add a logging test that asserts `_handle_worker_error` logs with `exc_info`.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/acquisition/test_jobs.py -q`. Expected: the new assertions fail because candidates remain `verifying`, non-rejected candidates are counted as usable, and traceback metadata is absent.

- [ ] **Step 3: Implement the state transition**

Add an acquisition-owned helper that parses a failed Job payload, finds a tenant-owned candidate for `website_verify`, and changes only `discovered`/`verifying` candidates to `needs_evidence`. Invoke it from reconciliation before Mission derivation. Replace the broad non-rejected usable test with the explicit set `{"eligible", "accepted", "promoted"}`. Pass `(type(exc), exc, exc.__traceback__)` to the worker logger through `exc_info`.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/acquisition/test_jobs.py -q`. Expected: all tests pass.

### Task 2: Actionable workbench projection and live refresh

**Files:**
- Modify: `tests/acquisition/test_workbench.py`
- Modify: `app/modules/acquisition/workbench.py`
- Modify: `app/core/pages.py`
- Create: `app/templates/app/_workbench_live.html`
- Modify: `app/templates/app/workbench.html`

- [ ] **Step 1: Write failing workbench tests**

Add tests asserting `current_jobs` contains only `queued`/`running`/`retrying`, verification failures already represented by `needs_evidence` are not counted as unresolved Job failures, a superseded failure is ignored, `needs_evidence` becomes the next action, and `/workbench/live` renders a polling partial.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/acquisition/test_workbench.py -q`. Expected: failures show in `current_jobs`, historical errors remain counted, and the live route does not exist.

- [ ] **Step 3: Implement the projection and partial**

Build logical Job identities from `job_type` plus `mission_id` or `candidate_id`. Filter terminal failures that are superseded by a later success or represented by a candidate in `needs_evidence`/terminal review state. Render metrics and Job sections from `_workbench_live.html`; poll `/workbench/live` every five seconds with `hx-trigger="load, every 5s"` and `hx-swap="outerHTML"`.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/acquisition/test_workbench.py -q`. Expected: all tests pass.

### Task 3: Tenant-safe candidate re-verification

**Files:**
- Modify: `tests/acquisition/test_routes.py`
- Modify: `app/modules/acquisition/routes.py`
- Modify: `app/templates/app/_workbench_live.html`
- Modify: `app/templates/acquisition/candidate_detail.html`

- [ ] **Step 1: Write failing route tests**

Add tests for a tenant-owned `needs_evidence` candidate that enqueue one `website_verify` Job and set status to `verifying`; reject cross-tenant access, immutable candidate states, and a second active verification.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/acquisition/test_routes.py -q`. Expected: POST returns 404 because the route is absent.

- [ ] **Step 3: Implement the command**

Add a POST-only tenant-guarded route. Load by tenant, require `needs_evidence`, check for an active `website_verify` Job for the candidate, enqueue a new Job with only `candidate_id`, update status after successful enqueue, and redirect to the candidate detail with a safe result banner.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/acquisition/test_routes.py -q`. Expected: all tests pass.

### Task 4: Integration, local data recovery, and release verification

**Files:**
- Modify only if a failing gate identifies a scoped regression.

- [ ] **Step 1: Run focused acquisition tests**

Run `python -m pytest tests/acquisition -q`. Expected: all tests pass.

- [ ] **Step 2: Run quality gates**

Run `python -m ruff check .` and `python -m ruff format --check .`. Expected: both exit zero.

- [ ] **Step 3: Run the non-browser suite and migration smoke**

Run the repository's existing non-browser pytest command and migration smoke command from the Phase 1A evidence. Expected: zero failures and a successful migration round trip.

- [ ] **Step 4: Restart and reconcile local runtime**

Restart Web and the single Windows `SimpleWorker`, leave Redis running, run one acquisition reconcile pass, and query the MX Mission. Expected: no candidate remains `verifying` after a terminal verification failure, the queue is empty, and `/workbench` renders without a Web 500 for a valid session.

- [ ] **Step 5: Final review**

Review the full diff against `docs/superpowers/specs/2026-08-02-workbench-recovery-design.md`, preserve `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png`, and report any remaining external-data limitations.
