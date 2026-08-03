# Phase 1A Acquisition Result Quality Recovery Design

**Date:** 2026-08-03

**Status:** Approved direction; written-spec review pending

**Scope:** Solo acquisition workflow from discovered candidate through evidence, assessment, and review UI

## 1. Problem statement

The first real Mexico motorcycle-parts Mission discovered ten candidates, but only two reached assessment and both were rejected. Eight candidates remained in `needs_evidence`; nine partial failures were recorded. The UI consequently exposed empty facts, inferences, and scores without explaining whether the data was unknown, processing had failed, or the field was intentionally not applicable.

The failure was not a single MiMo outage. The observed causes were:

- HTML sanitizer crashes on some nested hidden elements;
- the 200 KiB decompressed response limit rejects ordinary modern pages;
- a ten-second static-fetch timeout leaves no secondary evidence path;
- MiMo extraction responses that miss the strict schema are discarded without a schema-repair attempt;
- successful official evidence can therefore exist without extracted facts or an assessment;
- the background assessment path does not update the legacy `ai_confidence` field;
- rejected candidates can still display an A priority band;
- technical values such as `None`, internal mode names, and empty arrays leak into the primary user experience.

## 2. Goals

1. A malformed or large public page must not crash the verification worker.
2. A candidate must always end in one of three understandable outcomes: verified assessment, provisional assessment, or an explicit actionable failure reason.
3. Official evidence must be retained even when MiMo extraction fails.
4. One schema-repair attempt must be made before extraction is degraded.
5. Unverified search evidence may produce a provisional assessment, but cannot silently become a verified fact.
6. A hard-gate rejection must override the visible priority band.
7. The user-facing page must show concise business conclusions, evidence gaps, and the next action; it must not display model chain-of-thought.
8. The change must preserve the existing tenant boundary, job persistence, scoring versions, and Phase 1B browser-extension path.

## 3. Non-goals

- Adding GitHub, YouTube, LinkedIn, MCP, or browser-automation channels.
- Automatically accepting a candidate or sending outreach.
- Weakening SSRF, redirect, DNS-rebinding, content-type, or prompt-injection protection.
- Persisting raw MiMo responses or chain-of-thought.
- Replacing RQ/Redis, Flask, SQLAlchemy, or the existing acquisition domain model.
- Retrospectively rewriting old migration files.

## 4. Considered approaches

### A. Evidence-aware degradation with bounded retries — selected

Keep the strict pipeline, repair the deterministic failures, add one bounded MiMo schema-repair attempt, and persist a clearly labelled provisional assessment when only lower-trust evidence is available. This preserves the SaaS-grade evidence model while making the solo product usable.

### B. Loosen every validation rule

Accept partial MiMo JSON and substantially increase network limits. This is faster but would mix unsupported claims with observed facts and weaken the future public-SaaS boundary. Rejected.

### C. Send every failed page to a browser agent

This could improve coverage but introduces browser lifecycle, site-policy, anti-bot, and account-safety work already assigned to Phase 1B. It is too heavy for the current recovery. Deferred.

## 5. Architecture and data flow

The existing stages remain:

`web_discovery -> website_verify -> candidate_assess -> human review`

The recovery behavior becomes:

1. `web_discovery` stores MiMo search evidence as unverified Trust D evidence.
2. `website_verify` attempts the bounded static fetch.
3. If the page is fetched, sanitized official evidence is stored as valid Trust A evidence.
4. MiMo extracts structured facts from that snapshot.
5. If schema validation fails, the provider performs exactly one repair request using the same sanitized input plus safe validation-path feedback; the raw invalid response is neither logged nor persisted.
6. If extraction still fails, the valid official evidence remains stored and a provisional assessment is enqueued.
7. If static fetch fails, the fetch error is persisted with a safe, specific reason code and a provisional assessment is enqueued from the existing search evidence.
8. A later successful retry creates a new assessment keyed by the new evidence bundle; the latest assessment becomes the visible result.

No new database table or migration is required. Existing versioned `CandidateAssessment` rows provide the audit trail.

## 6. Fetcher recovery

### 6.1 Sanitizer

The BeautifulSoup path must tolerate tags whose parent was decomposed earlier in the traversal. Nodes with missing attributes or detached parents are skipped. The stdlib fallback behavior remains unchanged.

### 6.2 Bounded response size

- Default decompressed download limit changes from 200 KiB to 1 MiB.
- `FETCH_MAX_BYTES` remains configurable.
- Sanitized evidence text remains capped at 20,000 characters.
- Unsupported content types, unsafe URLs, DNS changes, redirect limits, and private addresses remain blocked.

### 6.3 Error fidelity

`response_too_large`, `source_timeout`, `source_unreachable`, and sanitizer failures remain separate safe reason codes through the Job and Evidence layers. The UI translates them into an explanation and retry/fallback action instead of reducing all of them to “website unavailable.”

## 7. MiMo extraction repair

`MiMoProvider._validated_request` gains a bounded schema-repair path for structured outputs:

- initial request;
- validate with the existing Pydantic schema;
- on schema failure, derive safe validation locations only;
- make one second request with the original sanitized input and an instruction to return the exact schema;
- validate again;
- return `invalid_response` after the second failure.

Network/auth/quota retry behavior remains unchanged. Raw provider output and validation values are not logged. The repair adds at most one provider request per failed extraction.

## 8. Provisional assessment semantics

The gate inputs that may be genuinely unknown become tri-state rather than conflating “unknown” with “false.” In particular, buyer role, product evidence, and contact path distinguish:

- confirmed positive;
- confirmed negative;
- unknown because extraction or verification is incomplete.

Only confirmed negative hard-gate evidence causes rejection. Unknown fields produce `needs_evidence`.

A provisional assessment:

- uses only persisted evidence and known identity fields;
- does not manufacture observed facts or AI inferences;
- uses a distinct versioned priority mode;
- has a maximum visible band of B;
- records evidence coverage and unknowns;
- cannot make the candidate eligible;
- is superseded in the UI by a later assessment created from a stronger evidence bundle.

The assessment explanation is a concise reason code–driven business summary, not chain-of-thought.

## 9. Scoring and display semantics

The primary card presents these concepts:

- **Final decision:** eligible, needs evidence, rejected, or accepted;
- **Fit:** product, buyer role, and country match when known;
- **Evidence quality:** source trust, identity, recency, and contactability;
- **Intent:** shown as “not yet observed” rather than `None` when absent;
- **Priority:** shown only when the candidate is not rejected.

For a rejected candidate, the primary badge is “Rejected” and the priority is “Not applicable.” The pre-gate score remains available only in technical details for auditability.

The current `AI confidence` label is removed from the primary experience. Self-reported model confidence is not treated as a trustworthy business metric. Existing stored values remain backward compatible; the UI uses evidence quality and signal coverage instead.

The `AI inference` section becomes `AI analysis conclusion`:

- when structured inferences exist, show concise evidence-linked conclusions;
- when none exist, explicitly state that no unsupported inference was needed and the conclusion is based on public evidence;
- when extraction failed, state that AI analysis is pending and explain the retry/fallback action.

## 10. UI behavior for missing data

Every empty state must answer both “why” and “what next.” Examples:

- `Official page exceeded the safe download limit; provisional score uses search evidence. Retry verification.`
- `Official evidence was saved, but structured extraction failed twice. Retry AI analysis.`
- `No purchase-intent signal was observed. Priority currently uses fit and evidence quality only.`
- `Country is not confirmed. Add public country evidence.`

Internal strings such as `None`, `fit_quality_provisional_v1`, and raw JSON keys stay inside technical details.

## 11. Mission-level recovery

The Mission remains `failed` when terminal job failures exist, but its retrospective and workbench summary distinguish:

- verified assessments;
- provisional assessments;
- actionable verification failures;
- rejected candidates;
- eligible candidates.

If no eligible candidate exists and unused candidate/search budget remains, this design only exposes an explicit “continue research” recommendation. Automatic query expansion is deferred to a separate feedback-loop design so the current fix does not silently spend additional MiMo quota.

## 12. Security and tenancy

- Every assessment, evidence, Job, and retry remains tenant-scoped.
- Provider keys remain in `SecretStore`; no key enters a Job payload.
- URLs are still validated on every redirect and after response DNS resolution.
- Provisional output cannot auto-accept, promote, or send outreach.
- Raw HTML remains bounded and sanitized before AI input.
- Raw provider responses and exception bodies are not logged.

## 13. Testing and acceptance

The implementation uses test-first red-green cycles and must cover:

1. nested/decomposed hidden HTML no longer raises `AttributeError`;
2. pages between 200 KiB and 1 MiB can be sanitized, while pages above 1 MiB remain blocked;
3. unsafe URL and DNS-rebinding tests remain green;
4. one invalid MiMo response triggers one repair request;
5. two invalid responses produce a safe terminal extraction failure;
6. fetch or extraction failure retains evidence and creates a provisional assessment;
7. unknown evidence does not become a hard rejection;
8. provisional priority cannot exceed B and cannot become eligible;
9. rejected candidates do not show A/B/S priority in the primary card;
10. UI empty states contain a reason and next action;
11. no raw provider response or sensitive exception is logged;
12. tenant-isolation and idempotent retry tests remain green.

Release gates:

- targeted acquisition and fetcher suites;
- full non-browser pytest suite;
- Ruff lint and Python format check;
- migration head smoke even though no migration is expected;
- authenticated route smoke for Mission detail and Workbench;
- a fresh local Mission sample or deterministic fixture demonstrating verified, provisional, and rejected cards.

## 14. Success criteria

- No candidate card displays an unexplained blank score or `None`.
- No hard-rejected candidate displays a primary A/B/S priority.
- A static-page incompatibility cannot crash the worker.
- Valid official evidence survives an AI extraction failure.
- Each candidate has either a verified assessment, a provisional assessment, or an explicit safe failure with a user action.
- Existing automation remains research-only and requires human acceptance before CRM promotion.
