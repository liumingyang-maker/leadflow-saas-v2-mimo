# Workbench Recovery Design

## Context

The first real MX acquisition Mission completed with an inconsistent terminal state: two candidates were assessed and rejected, eight website-verification Jobs failed, and those eight candidates remained `verifying`. The reconciler treated every non-rejected candidate as usable, marked the Mission completed, and emitted a notification claiming eight usable candidates. The workbench then presented historical terminal failures as current work indefinitely. The live browser was also logged out, which correctly redirected `/workbench` to `/login` and was not a Web 500.

## Approved outcome

1. A terminal `website_verify` failure moves a mutable candidate from `verifying` or `discovered` to `needs_evidence`.
2. Reconciliation self-heals pre-existing inconsistent candidates before deriving Mission status.
3. Only `eligible`, `accepted`, and `promoted` candidates count as usable.
4. Active Jobs and unresolved system failures are separate workbench concepts. Candidate verification failures represented by `needs_evidence`, and failures superseded by a later success for the same entity and Job type, do not remain system errors.
5. The workbench gives `needs_evidence` priority over creating another Mission and refreshes its live summary without reloading the entire page.
6. A candidate in `needs_evidence` can be explicitly re-queued for website verification. The route remains tenant scoped, actor initiated, CSRF protected, and idempotently rejects an already-active verification.
7. Worker logs retain the safe user-facing summary and bounded exception type/frame metadata, but never raw exception messages, source lines, locals, or traceback objects.

## Architecture

The acquisition module owns the mapping between Job failures and candidate state. `reconcile_missions` applies the mapping both for newly failed Jobs and for old inconsistent rows, then derives terminal Mission status from explicit usable states. The workbench builds a tenant-scoped projection: active Jobs are shown as progress, unresolved infrastructure failures are shown separately, and candidate evidence gaps are routed to the oldest affected Mission.

Candidate re-verification is an acquisition service command; the HTTP route only supplies identity and maps typed outcomes. A successful retry atomically claims the candidate, reopens only a failed Mission, and archives its stale failure notification. Completed Missions are never demoted by retry. Queue/state compensation remains inside the service boundary.

The HTML shell remains server rendered. A tenant-guarded `/workbench/live` route renders one partial containing metrics, active progress, and unresolved errors; HTMX polls it every five seconds. This avoids a new client state store and fits the single-user local deployment.

## Error handling and safety

- Re-verification never accepts an API key or arbitrary Job type from the browser.
- Only a candidate owned by the active tenant can be re-queued.
- Accepted/promoted/rejected candidates are not mutated by failure recovery.
- A terminal retry failure returns to `needs_evidence`; a successful retry continues through assessment.
- Provider and fetch failures retain safe summaries in the database; full exception details stay in local server logs.

## Verification

Regression tests cover self-healing, explicit usable-state counting, unresolved failure projection, live workbench rendering, retry idempotency, tenant isolation, and secret-safe frame-metadata logging. Existing acquisition tests, the non-browser suite, Ruff checks, formatter checks, and migration smoke must pass. The local runtime is then restarted and one reconciler pass repairs the current MX Mission without ad-hoc SQL edits.
