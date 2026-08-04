# QV-0 Release Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish one reproducible, tenant-safe and remotely published LeadFlow baseline before any result-quality feature changes.

**Architecture:** QV-0 changes no Acquisition scoring, country, entity, browser-policy, CRM, outreach, scheduling or schema behavior. If and only if the current baseline fails its declared Ruff gate, it makes the smallest formatter-produced import-order and whitespace correction, proves no behavior regression, and commits that mechanical repair separately. It then records secret-free evidence, updates the QV design state, and publishes only the verified branch.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy 2, Alembic, Redis/RQ, Docker Compose, pytest, Ruff, PowerShell, Git

---

## Scope and file map

- Create: `.autopilot/evidence/QV-0/release-baseline.md` — exact revision, migration state, quality gates, local readiness and scope audit; no credentials, cookies, raw provider data or database rows.
- Modify: `docs/superpowers/specs/2026-08-04-acquisition-value-validation-design.md` — QV program status only after all gates pass.
- Modify: `docs/superpowers/plans/2026-08-04-qv-0-release-baseline.md` — mark only completed tasks.
- Do not modify: `alembic/`, `docker-compose.yml`, `run_worker.py`, historical Phase 2 plan checkboxes, or `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png`.
- Conditional mechanical-only scope after a demonstrated Ruff failure: `app/modules/acquisition/jobs.py`, `app/modules/acquisition/routes.py`, `app/config.py`, `app/modules/jobs/service.py`, `app/modules/jobs/worker.py`, `tests/acquisition/test_jobs.py`, `tests/test_queue_safety.py`, and `tests/test_worker_contracts.py`. No semantic edit is allowed in these files.

### Task 1: Capture the immutable baseline facts

**Files:**
- Create later in this plan: `.autopilot/evidence/QV-0/release-baseline.md`

- [x] **Step 1: Verify isolation and branch identity**

Run:

```powershell
$gitDir = (Resolve-Path (git rev-parse --git-dir)).Path
$gitCommon = (Resolve-Path (git rev-parse --git-common-dir)).Path
$branch = git branch --show-current
"git_dir=$gitDir"
"git_common=$gitCommon"
"branch=$branch"
git rev-parse --show-superproject-working-tree
```

Expected: the directories differ, no superproject is printed, and branch is `design/solo-ai-acquisition-system`.

- [x] **Step 2: Capture commit, remote, worktree and existing change facts**

Run:

```powershell
git rev-parse HEAD
git log -12 --oneline --decorate
git branch -vv
git remote -v
git worktree list --porcelain
git status --short
python -m alembic current
python -m alembic heads
```

Expected: current and head are `0021_radar_baseline_acceptance`; the user-owned V2-05 screenshot remains unstaged.

### Task 2: Run the reproducible quality gates

**Files:**
- Create later in this plan: `.autopilot/evidence/QV-0/release-baseline.md`

- [x] **Step 1: Run Acquisition regression**

Run:

```powershell
python -m pytest tests/acquisition -q
```

Expected: exit code 0. If the terminal's 60-second request limit interrupts it, run exactly this command as one hidden background process, poll its PID at intervals no longer than 30 seconds, and record its final exit status and output tail. A wrapper timeout is not a test failure.

- [x] **Step 2: Run cross-domain regression**

Run:

```powershell
python -m pytest tests/radar tests/browser tests/test_migration_paths.py tests/test_worker_contracts.py tests/test_queue_safety.py -q
python -m ruff check app tests tools run_worker.py
python -m ruff format --check app tests tools run_worker.py
git diff --check
```

Expected: every command exits 0.

- [x] **Step 3: Repair only a demonstrated Ruff baseline violation**

If and only if Step 2 reports the recorded baseline errors `I001` in `app/modules/acquisition/jobs.py` and `app/modules/acquisition/routes.py`, `E501` in `tests/acquisition/test_jobs.py`, and formatter differences in the eight conditional-scope files, run:

```powershell
python -m ruff check --fix app/modules/acquisition/jobs.py app/modules/acquisition/routes.py
python -m ruff format app/modules/acquisition/jobs.py app/modules/acquisition/routes.py app/config.py app/modules/jobs/service.py app/modules/jobs/worker.py tests/acquisition/test_jobs.py tests/test_queue_safety.py tests/test_worker_contracts.py
python -m ruff check app tests tools run_worker.py
python -m ruff format --check app tests tools run_worker.py
python -m pytest tests/acquisition/test_jobs.py tests/test_queue_safety.py tests/test_worker_contracts.py -q
git diff --check
git diff --word-diff=porcelain -- app/modules/acquisition/jobs.py app/modules/acquisition/routes.py app/config.py app/modules/jobs/service.py app/modules/jobs/worker.py tests/acquisition/test_jobs.py tests/test_queue_safety.py tests/test_worker_contracts.py
```

If Ruff still reports only `tests/acquisition/test_jobs.py:1389:E501`, preserve the pre-existing `FetchResult.text` literal as three existing sentence fragments joined by a single ASCII space, preserve Unicode code points, then re-run the commands above. Do not reproduce raw fixture content in this plan.

Expected: Ruff gates and focused behavior suites exit 0, and the word diff contains only import position, whitespace, line wrapping and line-ending changes. Stage only the eight named files and commit:

```powershell
git add -- app/modules/acquisition/jobs.py app/modules/acquisition/routes.py app/config.py app/modules/jobs/service.py app/modules/jobs/worker.py tests/acquisition/test_jobs.py tests/test_queue_safety.py tests/test_worker_contracts.py
git commit -m "style: restore ruff baseline"
```

If any non-mechanical difference appears, stop the task and report it rather than broadening QV-0.

- [x] **Step 4: Run forward migration on a disposable database**

Run:

```powershell
$tempRoot = 'C:\tmp\leadflow-qv0-migration-20260804'
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null
(Resolve-Path $tempRoot).Path
$env:DATABASE_URL = 'sqlite:///C:/tmp/leadflow-qv0-migration-20260804/qv0.db'
python -m alembic upgrade head
python -m alembic current
```

Expected: the resolved path begins with `C:\tmp\leadflow-qv0-migration-20260804` and current identifies `0021_radar_baseline_acceptance`. Do not delete or modify the live database.

### Task 3: Verify the controlled runtime without provider calls

**Files:**
- Create later in this plan: `.autopilot/evidence/QV-0/release-baseline.md`

- [x] **Step 1: Validate Docker configuration only**

Run:

```powershell
docker compose config -q
docker compose config --services
```

Expected: exit code 0 and services include `web`, `redis`, `worker`, `browser-redis` and `browser-worker`.

- [x] **Step 2: Check existing local readiness**

Run:

```powershell
$response = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/health/ready
"status=$($response.StatusCode)"
$response.Content
```

Expected: status 200 with `ok=true`, `database=ok`, and `redis=ok`. This GET creates no Mission, fetches no public page and calls no Provider.

- [x] **Step 3: Check Worker and Scheduler source/runtime facts**

Run:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'run_worker\.py' } | Select-Object ProcessId, Name, CommandLine
rg -n "worker\.work\(with_scheduler=True\)" run_worker.py
```

Expected: exactly one independent local `run_worker.py` process tree and source confirmation of `with_scheduler=True`. On Windows, a Python launcher may spawn one Python child that executes the Worker; this parent-child pair is one Worker tree, not two Workers. A second matched process is a failure only when it is not a descendant of the one root Worker process. If more than one root tree exists, record the gate failure and do not start or stop any Web or Worker process while the user is testing.

### Task 4: Record verified evidence and synchronize QV state

**Files:**
- Create: `.autopilot/evidence/QV-0/release-baseline.md`
- Modify: `docs/superpowers/specs/2026-08-04-acquisition-value-validation-design.md`
- Modify: `docs/superpowers/plans/2026-08-04-qv-0-release-baseline.md`

- [x] **Step 1: Create a secret-free evidence record**

Create the evidence file with the following sections and actual observed values: `Baseline` (branch, full SHA, current/head migration, preserved V2-05 screenshot), `Automated gates` (each Task 2 command and exit summary), `Controlled runtime` (Docker result, readiness JSON without secrets, Worker count, Provider/browser/CRM/outreach actions all zero), and `Scope audit` (no application behavior changed; historical Phase 2 plans preserved; QV-1 begins only from this commit).

- [x] **Step 2: Update only the approved QV design status**

After Tasks 1–3 pass, replace the design status line with:

```markdown
**状态：** 已批准；QV-0 已验证，QV-1 待执行
```

Do not change QV requirements, thresholds or non-goals.

- [x] **Step 3: Commit only QV-0 documentation and evidence**

Run:

```powershell
git diff --check
git status --short
git add -- docs/superpowers/specs/2026-08-04-acquisition-value-validation-design.md docs/superpowers/plans/2026-08-04-qv-0-release-baseline.md .autopilot/evidence/QV-0/release-baseline.md
git commit -m "docs(release): verify qv-0 baseline"
```

Expected: exactly the three QV-0 files are staged; the user-owned V2-05 screenshot is excluded.

### Task 5: Publish the verified branch

**Files:**
- Modify: `.autopilot/evidence/QV-0/release-baseline.md`
- Modify: `docs/superpowers/plans/2026-08-04-qv-0-release-baseline.md`

- [x] **Step 1: Check publication preconditions**

Run:

```powershell
git status --short
git branch -vv
git log -1 --oneline
```

Expected: only the V2-05 screenshot remains modified and the branch contains the QV-0 evidence commit.

- [x] **Step 2: Push the exact verified branch and set upstream**

Run:

```powershell
git push --set-upstream origin design/solo-ai-acquisition-system
git branch -vv
git ls-remote --heads origin design/solo-ai-acquisition-system
```

Expected: remote SHA equals local HEAD. Do not force-push, merge to `main`, create a PR, deploy production or push the V2-05 screenshot.

- [x] **Step 3: Record publication and commit the final evidence**

Add a `Publication` section with branch name, local SHA, remote SHA and UTC time. Tick Task 5, then run:

```powershell
git add -- docs/superpowers/plans/2026-08-04-qv-0-release-baseline.md .autopilot/evidence/QV-0/release-baseline.md
git commit -m "docs(release): record qv-0 publication"
git push origin design/solo-ai-acquisition-system
```

Expected: publication evidence is a second normal commit; no history rewrite is required.

## Plan self-review

- QV-0 requirements are covered: isolated branch, commit and migration facts, regression, static gates, disposable migration, Docker syntax, local readiness, Worker/Scheduler observation, evidence, status synchronization and remote publication.
- No QV-1 or later feature is mixed in; a separately committed Ruff-only remediation is permitted only for the explicitly recorded existing failure.
- Runtime checks are read-only; the only database write targets a fresh disposable path; no existing user file is staged; evidence excludes secrets and raw user/provider data.
