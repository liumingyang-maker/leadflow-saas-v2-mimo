# P2-4 Radar Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` with red-green-refactor steps.

**Goal:** Create deterministic, reviewable Radar change signals while protecting users from redesign/parser drift and notification floods.

**Architecture:** A pure canonical Diff compares only stored structured Snapshot facts. A pure drift guard evaluates version and coverage loss before signals can create notifications or conversion. Signal rows are tenant/profile/run scoped; one Run has at most one in-app aggregate notification with five bounded highlights.

**Tech Stack:** Python canonical JSON, SQLAlchemy/Alembic, Flask views, pytest and Ruff.

---

### Task 1: Add pure Diff and drift contracts

**Files:**
- Create: `app/modules/radar/diff.py`, `tests/radar/test_diff.py`, `tests/radar/test_drift.py`

- [ ] Write failing deterministic-Diff, baseline, parser-version and coverage-loss tests.
- [ ] Implement byte-identical canonical field delta output and a reason-code drift result requiring three comparable pages.
- [ ] Run the pure tests and commit `feat(radar): add deterministic snapshot diff`.

### Task 2: Persist, render, and aggregate signals

**Files:**
- Modify: `app/modules/radar/models.py`, `app/modules/radar/jobs.py`, `app/modules/radar/views.py`, `app/modules/acquisition/workbench.py`, `app/templates/radar/run_detail.html`
- Create: `migrations/versions/0019_radar_signals.py`, `tests/radar/test_notifications.py`, `tests/radar/test_signal_routes.py`

- [ ] Add signal model and one aggregate-notification uniqueness key; write failing retry/concurrency and baseline-no-notification tests.
- [ ] Reconcile each current Snapshot with its previous valid page identity; retain informational deterministic results when classification is unavailable.
- [ ] Suppress candidate conversion, removals and material notifications for drift; aggregate at most five highlights in one internal Notification.
- [ ] Run complete regression, migration roundtrip, static security checks and commit `feat(radar): add drift-protected change signals`.
