# Phase 1A local gate evidence

Date: 2026-08-02
Branch: `design/solo-ai-acquisition-system`

## Automated gates

| Gate | Result | Evidence |
| --- | --- | --- |
| Ruff lint | PASS | `python -m ruff check .` -> `All checks passed!` |
| Ruff format | PASS | `python -m ruff format --check .` -> `147 files already formatted` |
| Acquisition suite | PASS | `python -m pytest tests/acquisition -q`; 104 tests collected and all passed |
| Non-browser full suite | PASS | `python -m pytest --ignore=tests/test_playwright_launch_acceptance.py -q`; 397 tests collected and all passed in 88.1 seconds |
| Diff whitespace | PASS | `git diff --check` returned no errors |
| Secret pattern scan | PASS | No matching file outside the approved plan and `.env.example` exclusions |
| Compose structure | PASS (static) | YAML parsed; one `default` worker, reconciler, and 10 MB x 5 web/worker log rotation asserted |
| Docker runtime | NOT RUN | The `docker` executable is not installed on this workstation |

The repository's complete `scripts/check.ps1` had also passed earlier in this Task 12 checkpoint, including 397 tests, diff checking, and the secret scan. After the final logging and notification-race hardening, the fresh verification intentionally excluded `tests/test_playwright_launch_acceptance.py`: that one test launches Playwright and overwrites legacy screenshot evidence. The operator reported application crashes from browser command bursts, so no browser was launched again.

## Offline acceptance coverage

- Three-field Mission creation.
- Country-unknown evidence gate.
- Deterministic scoring for identical inputs.
- MiMo-disabled manual-URL flow with injected fetcher/extractor.
- Duplicate promotion protection.
- Workbench counts and notification deduplication.
- Feedback suggestions remain advisory and are never auto-applied.
- Cross-tenant resources return 404.
- Readiness checks both database and Redis and returns only a safe error code.
- Structured logs hash tenant identifiers and reject secret-like fields and unsafe event text.
- Three consecutive MiMo failures produce one notification; the reconciler repairs a missed notification; recovery creates an audit event.

## Visual evidence captured before browser use was stopped

- `mission-desktop.png`
- `candidate-desktop.png`
- `candidate-mobile.png` (390 px viewport)
- `workbench-desktop.png`
- `mimo-disabled-desktop.png`

The captured candidate/workbench desktop views had no horizontal overflow. The 390 px candidate view had no horizontal overflow and its three primary action buttons measured 44 px high. No console errors were observed during those checks.

## Release gates still external to this local checkpoint

- PostgreSQL staging migration, unique-constraint, and concurrent-promotion smoke test.
- Docker Compose runtime smoke test.
- A real 30-company positive/negative sample report covering precision, evidence coverage, acceptance rate, provider cost, and elapsed time.
- Phase 1A release checkpoint creation after those gates pass.
