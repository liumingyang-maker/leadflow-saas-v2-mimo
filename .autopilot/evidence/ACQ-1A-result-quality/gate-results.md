# ACQ-1A Result Quality Recovery — Gate Evidence

- Date: 2026-08-03
- Branch: `fix/acquisition-result-quality`
- Affected Mission: `93d10a606ecc47199037645554836107`
- Validation method: automated tests plus an authenticated render against a SQLite backup of the affected Mission
- Safety: no live database writes, provider calls, browser automation, API keys, cookies, or raw provider bodies

## Automated gates

| Gate | Result |
|---|---|
| Focused red/green regression tests | PASS — evidence-only quality no longer becomes lead priority; pending UI copy verified |
| `python -m pytest tests/acquisition -q` | PASS — 359 passed, 0 failed |
| Complete non-browser suite | PASS — 659 passed, 0 failed |
| `python -m ruff check .` | PASS |
| `python -m ruff format --check app tests run_worker.py` | PASS — 136 files |
| `git diff --check` | PASS |
| Disposable SQLite migration round trip | PASS — upgrade head → downgrade `0013_admin_auth_version` → upgrade head |
| Final migration revision | PASS — `0014_acquisition_core (head)` |

The complete non-browser suite excluded only the four repository Playwright launch files:

- `tests/test_playwright_launch_acceptance.py`
- `tests/test_playwright_collection.py`
- `tests/test_playwright_crm.py`
- `tests/test_playwright_outreach_inbound.py`

## Affected Mission replay

All ten candidates were reassessed on a consistent database backup with `eligibility-v2` and `priority-v4`. The authenticated Mission detail returned HTTP 200 and rendered ten candidate cards.

| Candidate | Decision shown | Lead priority shown | Evidence quality | Coverage | Analysis | Next action |
|---|---|---|---:|---:|---|---|
| Amililla Group | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| Importadora RPM | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| MEXTEC AUTOPARTES | Needs evidence | Not assigned | 86 | 16% | Present | Re-verify |
| MPI MEXICO - MPI Latinoamerica | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| Moto Avanzada | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| Motorepuestos Biker | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| Motos y Equipos | Needs evidence | Not assigned | 67 | 16% | Present | Re-verify |
| Refacciones Motozoon | Needs evidence | Not assigned | 86 | 16% | Present | Re-verify |
| Morsa Click | Rejected | Hidden | 89 | 65% | Present | No retry required |
| Proveedores Plus | Rejected | Hidden | 84 | 65% | Present | No retry required |

## Semantic output audit

PASS:

- no raw `None` value is visible;
- no candidate shows an empty or unexplained AI conclusion;
- no evidence-only candidate receives a fabricated A/B/S lead priority;
- rejected candidates expose only the rejected primary decision, not a high-priority badge;
- all eight incomplete candidates show `待补充匹配证据`, a concrete reason, and a re-verification action;
- evidence quality remains visible separately from lead priority;
- unverified search excerpts are not promoted to confirmed structured facts;
- model/version/hash diagnostics remain confined to technical details.

## Output-driven tuning

The first replay exposed a product-level defect: with only 16% signal coverage, evidence quality scores of 67 and 86 were both converted into `暂定 B`. This confused source quality with customer value and provided no useful ordering.

The corrected `priority-v4` behavior retains the evidence quality score but sets lead priority to unknown until at least one product, buyer-role, or industry-fit signal exists. The primary card now says `待补充匹配证据`. This correction was implemented only after a focused regression test failed on the observed output, then passed after the minimal scoring and presentation changes.

## Local runtime smoke

The verified branch was started locally with exactly one Web process and one RQ Worker against the existing Solo SQLite database. The existing affected Mission was then reassessed without network/provider calls.

| Check | Result |
|---|---|
| `/health/ready` | PASS — HTTP 200, database `ok`, Redis `ok` |
| Latest assessment version | PASS — all 10 candidates use `priority-v4` |
| Candidate states | 8 `needs_evidence`, 2 `rejected` |
| Authenticated Mission render | PASS — HTTP 200, 10 cards |
| Primary labels | PASS — 8 `待补充匹配证据`, 2 `已拒绝` |
| Analysis conclusions | PASS — 10 of 10 present |
| Re-verification actions | PASS — 8 of 8 incomplete candidates |
| Semantic violations | PASS — 0 |
| Reconciler pass | PASS — 0 additional Mission changes required |
