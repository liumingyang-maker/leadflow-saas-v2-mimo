# Phase 2 Competitor Radar Core Design and Audit Execution Report

> Status: Proposed for independent audit. This document is design authority for the
> Phase 2 competitor-radar core only. It does not authorize implementation or production
> deployment until the audit findings are resolved and the user approves the written spec.

**Date:** 2026-08-03

**Repository baseline:** `9125cc7` on `feat/acquisition-global-quality-p0`

**Product mode:** single-operator internal deployment with retained tenant boundaries
**Author review roles:** software engineer, product designer, security/release reviewer

---

## 1. Executive verdict

The proposed competitor-radar core is suitable for LeadFlow if it is delivered as a
dependency-gated sequence of vertical slices. It directly supports the product's strongest
workflow: turning public, attributable company evidence into reviewable acquisition candidates.
It also reuses the existing Candidate, Evidence, Job, Notification, AuditEvent, and CRM promotion
boundaries instead of creating a second lead system.

The design is **not suitable as one large Phase 2 implementation**. The current baseline contains
the `browser_research` capability placeholder and an older Phase 1B plan, but it does not contain
`BrowserResearchRun`, `BrowserSitePolicy`, an isolated Browser Worker, or competitor-radar domain
models. Those missing foundations are a hard dependency gate, not work that an implementation
agent may silently assume is complete.

The accepted first release is intentionally narrow:

- competitor discovery may be suggested by AI but requires human approval;
- a user starts every radar run manually;
- the system stores bounded structured snapshots rather than full page archives;
- only material commercial changes are prominent;
- strong official dealer relationships may create review candidates;
- weak relationships remain suggestions;
- no path may automatically accept a candidate, promote it to CRM, or send outreach;
- Google Places, YouTube, provider dashboards, cross-Mission reuse, and scheduling remain separate
  later specs.

**Verdict:** proceed to independent design audit. Do not begin implementation until the audit
returns PASS or all required changes are incorporated.

## 2. Current-system facts an auditor must verify

The implementation agent and auditor must inspect the repository rather than rely only on this
summary. At baseline `9125cc7`, the relevant facts are:

1. Phase 1A acquisition is implemented around tenant-owned `AcquisitionMission`,
   `AcquisitionCandidate`, `CandidateEvidence`, `CandidateAssessment`, and persistent `Job` rows.
2. Candidate acceptance and CRM promotion are human-controlled boundaries.
3. `BusinessResultResolver` supplies one shared Mission business result to detail, list,
   workbench, notifications, and reconciliation.
4. Mission reconciliation runs as persisted tenant-owned `acquisition_reconcile` Jobs.
5. Static fetching already enforces URL, DNS, redirect, content-type, response-size, and prompt-
   injection controls.
6. `browser_research` exists only as a capability definition. The isolated Browser runtime and
   its database models are not present.
7. Migration `0014_acquisition_core` is published and must never be edited.
8. The final non-browser regression gate at this baseline is 710 passing tests; the auditor must
   run fresh commands rather than treating that historical count as current proof.

## 3. User-approved decisions

These decisions are fixed for the first competitor-radar release:

| Decision | Approved behavior |
|---|---|
| Phase 2 meaning | Product-roadmap Phase 2: competitor radar and stable-channel expansion |
| Delivery order | Competitor radar first |
| Competitor source | AI suggests; a human approves the formal profile |
| Monitored changes | Material commercial signals, not whole-site visual noise |
| Scheduling | Manual runs only; no recurring schedule |
| Planning shape | Separate auditable subprojects rather than one large plan |
| First release completion | Full radar-to-review-candidate vertical slice |
| Snapshot boundary | Structured facts, bounded excerpts, hashes, optional artifacts; no full HTML archive |
| Relationship conversion | Strong official evidence may create a Candidate; weak evidence stays a suggestion |
| Quality posture | Precision first; candidate precision target at least 70% and zero automatic CRM/outreach |

## 4. Goals and non-goals

### 4.1 Goals

The first release must let one authenticated tenant user:

1. request AI-assisted competitor suggestions for an active acquisition Mission;
2. review, approve, or dismiss each suggestion;
3. manually run an approved competitor profile;
4. capture a bounded, attributable structural baseline from official pages;
5. compare a later manual run against that baseline deterministically;
6. view important product, market, dealer-network, partnership, and contact changes;
7. preserve source URLs, bounded excerpts, hashes, versions, and audit events;
8. convert high-confidence official dealer relationships into existing review candidates;
9. retain partial results when one page, model, or Browser fallback fails;
10. use the radar while keeping all tenant, security, human-review, and outreach boundaries intact.

### 4.2 Non-goals

The first release does not include:

- cron, recurring schedules, `next_run_at`, or unattended research;
- Google Places or YouTube integration;
- paid data providers;
- automatic competitor approval;
- full-page HTML retention or arbitrary web archives;
- visual pixel diffs;
- cross-tenant or cross-Mission evidence reuse;
- global company alias resolution or a company master-data system;
- automatic Candidate acceptance, CRM promotion, email, WhatsApp, LinkedIn, or other outreach;
- model-generated facts without a source URL and bounded supporting excerpt;
- public SaaS entitlements, billing, or multi-user approval workflows.

## 5. Program decomposition and dependency graph

Phase 2 is implemented through independent specs and plans in this order:

### P2-0: Browser Foundation Gate

Refresh the existing Phase 1B browser plan against the current baseline. Implement and verify the
disabled-by-default isolated Browser runtime, `BrowserResearchRun`, `BrowserSitePolicy`, browser
queue, lease/heartbeat, bounded descriptors, artifact manifest, cleanup, and network isolation.
Radar may not use Browser fallback until this gate passes.

### P2-1: Competitor Profile Domain

Add radar models, repositories, competitor suggestions, human approval/dismissal, capability
checks, audit events, and a minimal profile UI. No crawling or Diff is introduced here.

### P2-2: Manual Radar Run and Structured Snapshot

Add the manual-run endpoint, `RadarRun` state machine, static page discovery, bounded structured
snapshots, identical-content dedupe, partial-result preservation, and Browser fallback orchestration.

### P2-3: Commercial Change Signals

Add deterministic structured Diff, materiality rules, evidence-bound AI classification, first-run
baseline behavior, signal acknowledgement/dismissal, notifications, and the change workbench.

### P2-4: Dealer Relationship and Candidate Conversion

Add evidence-strength resolution, relationship lifecycle, active-Mission checks, idempotent
Candidate/Evidence conversion through an Acquisition public service, and review-queue integration.

### P2-5: Runtime, Security, and Quality Gate

Run migration roundtrips, tenant and concurrency tests, offline multilingual replay, Browser
container smoke, resource cleanup, local-data-copy smoke, accessibility checks, performance
sampling, and an independent final code review.

Only after P2-5 passes may separate specs begin for Places, YouTube, provider dashboards,
cross-Mission reuse, or scheduling.

## 6. Module boundaries

Create a focused `app/modules/radar/` package. Do not continue growing
`app/modules/acquisition/jobs.py` with radar-specific orchestration.

Expected responsibility map:

```text
app/modules/radar/models.py          persisted radar domain objects only
app/modules/radar/contracts.py       frozen input/output contracts and enums
app/modules/radar/repository.py      tenant-scoped persistence queries
app/modules/radar/policies.py        budgets, state transitions, materiality rules
app/modules/radar/suggestions.py     competitor suggestion and approval service
app/modules/radar/snapshots.py       normalization and immutable snapshot creation
app/modules/radar/diff.py            pure deterministic structured Diff
app/modules/radar/relationships.py   evidence-strength resolver
app/modules/radar/conversion.py      public boundary into Acquisition Candidate/Evidence
app/modules/radar/jobs.py            radar Job handlers and reconciliation
app/modules/radar/service.py         authenticated application use cases
app/modules/radar/routes.py          HTTP/HTMX endpoints
app/modules/radar/views.py           read projections for templates
app/templates/radar/                 profile, run, signal, and relationship UI
```

Existing modules retain these responsibilities:

- Acquisition owns Candidate, Evidence, assessment, human decisions, and Lead promotion.
- Jobs owns SQL Job lifecycle, RQ dispatch, retry, cancellation, and stale recovery.
- Browser integration owns browser process execution and sanitized Browser results.
- Audit owns append-only safe summaries.
- Notifications owns user-visible event dedupe and read/archive behavior.

Radar calls explicit public services at these boundaries. It must not reach into Acquisition
tables with ad hoc writes or import Browser Worker internals.

## 7. Persistent data model

All radar tables require `tenant_id`, tenant-inclusive uniqueness, bounded strings/JSON, explicit
CheckConstraints, and repositories whose public methods require `tenant_id`.

### 7.1 `radar_competitor_suggestions`

Required fields:

- `id`, `tenant_id`, `mission_id`;
- `company_name`, `canonical_domain`, `official_url`;
- `reason_codes_json`, `evidence_json`;
- `status`: `proposed | approved | dismissed`;
- `dedupe_key`, `created_at`, `updated_at`, `decided_by`, `decided_at`.

Unique key: `(tenant_id, mission_id, canonical_domain)`. Approval creates at most one profile.
Dismissed suggestions are not recreated unless the source-evidence hash changes.

### 7.2 `competitor_profiles`

Required fields:

- `id`, `tenant_id`, `mission_id`, `product_snapshot_id`;
- `company_name`, `canonical_domain`, `official_url`;
- `status`: `active | paused | archived`;
- `tracking_config_json` containing only bounded seed URLs and allowed page kinds;
- `source_suggestion_id`, `approved_by`, `approved_at`;
- `created_at`, `updated_at`.

Unique key: `(tenant_id, mission_id, canonical_domain)`. The service must verify that the Mission
and product snapshot belong to the same tenant and that the snapshot matches the Mission.

### 7.3 `radar_runs`

Required fields:

- `id`, `tenant_id`, `profile_id`, `root_job_id`, `requested_by`;
- `status`: `queued | running | succeeded | partial | failed | cancelled`;
- `stage`, `budget_json`, `result_summary_json`;
- `parser_version`, `diff_version`, `classifier_version`;
- `created_at`, `started_at`, `heartbeat_at`, `finished_at`.

Only one active Run (`queued` or `running`) is allowed per tenant/profile. Repeated manual POSTs
return the existing active Run. A retry of a terminal Run creates a new Run and preserves history.

### 7.4 `radar_snapshots`

Required fields:

- `id`, `tenant_id`, `profile_id`, `run_id`;
- `page_kind`: `home | product | dealers | partners | contact | about | other`;
- `requested_url`, `canonical_url`, `content_hash`;
- `facts_json`, `excerpt`, `source_method`: `static | browser`;
- `validation_status`: `valid | partial | rejected | unreachable`;
- `extractor_version`, `artifact_ref`, `observed_at`, `created_at`.

Unique key: `(tenant_id, profile_id, canonical_url, content_hash)`. Snapshots are immutable.
`excerpt` is capped at 4,000 characters. `artifact_ref` is an opaque manifest identifier, never an
arbitrary filesystem path supplied by a Job.

### 7.5 `radar_change_signals`

Required fields:

- `id`, `tenant_id`, `profile_id`, `run_id`;
- `previous_snapshot_id`, `current_snapshot_id`;
- `change_type`: `product | market | dealer_added | dealer_removed | partnership | contact | other`;
- `materiality`: `material | informational | noise`;
- `before_json`, `after_json`, `reason_codes_json`, `evidence_json`;
- `status`: `open | acknowledged | dismissed`;
- `detector_version`, `classifier_version`, `created_at`, `decided_by`, `decided_at`.

The first snapshot for a page is a baseline and creates no ChangeSignal. Identical hashes create
no new snapshot or signal.

### 7.6 `radar_relationships`

Required fields:

- `id`, `tenant_id`, `profile_id`, `run_id`, `source_snapshot_id`;
- `company_name`, `canonical_domain`, `official_url`;
- `relationship_type`: `dealer | distributor | partner | service_network | unknown`;
- `evidence_strength`: `confirmed | likely | unknown`;
- `reason_codes_json`, `evidence_json`;
- `status`: `proposed | converted | dismissed`;
- `candidate_id`, `created_at`, `updated_at`, `decided_by`, `decided_at`.

Unique key: `(tenant_id, profile_id, canonical_domain, relationship_type)`. A converted
relationship cannot later be converted to a second Candidate for the same Mission/domain.

## 8. Job graph and state ownership

Add radar Job types to the existing validated Job registry and database constraint through a new
migration. Job payloads contain bounded IDs only.

```text
radar_competitor_suggest
    -> human approval (not a Job)
    -> radar_scan
         -> zero or more BrowserResearchRun/browser Jobs when allowed
         -> radar_reconcile observes child terminal state
         -> radar_finalize
              -> deterministic Diff
              -> evidence-bound classification
              -> relationship resolution
              -> bounded Candidate conversion
```

Rules:

- `Job` is execution truth; `RadarRun` is business/read-model truth.
- Web requests persist business state and Job rows before enqueueing.
- RQ transports Job IDs, never API keys, page bodies, prompts, cookies, or complete descriptors.
- Browser jobs execute on the browser queue and cannot read the application database or secrets.
- Radar reconciliation is a persisted tenant-owned Job, not a Web-thread scanner.
- An active child Job keeps the RadarRun `running`.
- If at least one valid snapshot exists and another stage fails, the Run becomes `partial`.
- `failed` means no valid snapshot or actionable relationship was produced.
- Cancellation preserves completed snapshots and prevents new child Jobs or conversions.
- Non-terminal retries never supersede the latest terminal result for the same logical page task.

## 9. Algorithms and decision rules

### 9.1 Competitor suggestion

Input is limited to the tenant's active Mission, pinned ProductKnowledgeSnapshot, target profile,
and approved product facts. Output is a strict schema with at most 10 suggestions.

Every suggestion requires:

- a normalized company name;
- an HTTP(S) official URL candidate;
- a canonical domain;
- at least one bounded reason code;
- at least one public source URL and excerpt supporting competitor relevance.

Suggestions whose URL fails policy, whose domain duplicates an existing profile, or whose evidence
does not support competitor relevance are rejected before persistence. A model confidence number
alone never satisfies the evidence requirement.

### 9.2 Radar page planning

The homepage is the only implicit seed. Additional URLs must be either:

- configured by the user/profile; or
- observed as same-domain links in a successfully fetched seed page.

MiMo may classify observed links into approved page kinds but may not invent arbitrary crawl URLs.
Every selected URL passes canonicalization and fetch policy independently.

Pinned default budgets per Run:

| Budget | Default | Hard maximum |
|---|---:|---:|
| total pages | 10 | 25 |
| Browser fallback pages | 3 | 10 |
| total run wall time | 300 seconds | 600 seconds |
| stored excerpt per page | 4,000 chars | 4,000 chars |
| material signals | 50 | 100 |
| relationships | 50 | 100 |
| automatic Candidate conversions | 10 | 20 |

Budgets are saved on `RadarRun`; later config changes do not rewrite historical runs.

### 9.3 Structured snapshot

The normalizer emits versioned facts with explicit source support. Each fact contains a stable key,
normalized value, source URL, bounded excerpt, extractor kind, and reason codes. Stored JSON is
canonicalized before hashing.

The system stores no model chain of thought. It stores only schema-valid outputs, versions,
evidence support, safe error codes, and bounded user-facing explanations.

### 9.4 Deterministic Diff

For each profile/page identity, compare the new snapshot with the newest previous valid snapshot.
The pure Diff layer compares canonical structured facts and produces added, removed, and changed
fields. The same inputs and detector version must produce byte-identical Diff output.

AI classification receives only the structured delta plus cited evidence. It may assign a change
type, materiality, and explanation. It may not add a fact absent from the deterministic delta.
When classification fails, the structural Diff is retained as `informational` with a safe
`classification_unavailable` reason rather than discarded.

### 9.5 Relationship evidence strength

`confirmed` requires all of the following:

1. the source snapshot belongs to the approved competitor's verified official domain;
2. the page contains an observed outbound company URL/domain different from the competitor;
3. a schema-valid relationship claim maps that company to dealer, distributor, partner, or service
   network language in a bounded excerpt;
4. the target has an independent company identity and is not merely a directory, government,
   media, recruitment, login, privacy, or generic platform page;
5. the detector records its version and reason codes.

Missing any requirement downgrades the result to `likely` or `unknown`. No country-specific domain,
language, or keyword branch may act as an automatic confirmation rule.

### 9.6 Candidate conversion

Conversion calls a new Acquisition public service; Radar does not write Candidate tables directly.
The service requires tenant ID, an active destination Mission, the relationship ID, normalized
domain, and evidence references.

It atomically:

1. checks the relationship and Mission belong to the same tenant;
2. returns an existing Candidate when the Mission/domain dedupe key already exists;
3. creates a Candidate with `source_channel=competitor_radar` and `status=needs_evidence`;
4. creates CandidateEvidence with source type `competitor_dealer_network` and trust tier B;
5. records that this evidence proves a competitor relationship, not the target company's own
   website, country, contact path, or purchase intent;
6. marks the relationship converted and stores `candidate_id`;
7. emits a safe audit event.

Conversion does not enqueue paid analysis or website verification automatically. The user can use
the existing re-verification action when the candidate is worth deeper research.

## 10. Browser foundation and security boundary

P2-0 is a hard gate. Radar Browser fallback remains disabled until all of these are proven:

- Browser runtime is disabled by default and controlled by Capability plus tenant/system policy;
- the Browser Worker receives Redis, bounded budgets, and artifact storage only;
- the Browser Worker receives no database URL, Flask secret, tenant secret, MiMo key, or user token;
- each run has an isolated temporary directory, browser context, lease, heartbeat, and process group;
- success, failure, cancellation, timeout, and Worker crash all clean up processes and temporary data;
- network policy blocks localhost, private, link-local, reserved, and cloud metadata ranges at the
  container/network layer, not only in Python URL validation;
- redirect and final URLs are validated again;
- output passes the shared sanitizer and prompt-injection policy;
- artifact manifests are size-bounded, content-addressed, and tenant-owned when imported;
- no browser token, cookie, local storage, complete page body, or raw tool transcript reaches SQL,
  logs, Job payloads, or user-visible error messages.

If any Browser requirement fails, static radar remains usable and the Run closes as partial when it
has valid static results.

## 11. Error handling and recovery

| Failure | Required behavior |
|---|---|
| competitor suggestion schema invalid | one existing safe repair attempt; otherwise no suggestion persisted |
| homepage unreachable | fail if no baseline exists; preserve safe error code |
| secondary page unreachable | preserve other snapshots; Run becomes partial |
| prompt injection detected | reject that page, retain security evidence metadata, never classify its text |
| MiMo unavailable during facts extraction | retain sanitized structural metadata and partial snapshot |
| MiMo unavailable during change classification | retain deterministic Diff as informational |
| Browser disabled or policy-blocked | do not enqueue Browser; keep static result and reason code |
| Browser timeout/crash | clean child process, preserve completed artifacts, Run becomes partial/failed by material output |
| repeated manual POST | return the existing active Run; create no duplicate Job |
| Worker retry | reuse logical task identity; do not duplicate Snapshot, Signal, Relationship, or Candidate |
| target Mission becomes terminal | finish evidence processing but create no Candidate |
| user cancels Run | stop future child enqueue, preserve completed snapshots, no conversion after cancellation |
| reconciler restart | derive state from SQL Jobs and BrowserResearchRuns; do not trust Redis as business truth |

All user-visible failures use bounded reason codes and actions. Raw exceptions, model responses,
page bodies, query strings containing tokens, and credentials are prohibited.

## 12. User experience

Add a top-level internal navigation entry `竞品雷达` only when the capability is enabled.

### 12.1 Radar overview `/radar`

Show active/paused profiles, latest Run result, last manual run time, open material changes, proposed
relationships, and a primary `添加或发现竞品` action. There is no scheduling control.

### 12.2 Suggestion review `/radar/suggestions`

Each suggestion shows name, official URL, source evidence, why it may be a competitor, and explicit
approve/dismiss actions. Confidence alone is never displayed as proof.

### 12.3 Profile detail `/radar/profiles/<id>`

Show pinned Mission/product context, seed pages, the `立即运行` action, active Run progress, recent
material changes, relationships, and run history. If the Mission is terminal, explain that runs may
be inspected but new Candidate conversion is paused until a new active Mission is chosen.

### 12.4 Run detail `/radar/runs/<id>`

Show stage, bounded budgets, per-page status, static/Browser source method, safe failures, snapshots,
changes, relationship decisions, and audit timestamps. Do not render raw JSON by default.

### 12.5 Workbench integration

Add compact counts for open material changes, proposed relationships, and partial/failed manual Runs.
Notifications are created only for material changes, newly confirmed relationships, and terminal
partial/failed Runs. Baselines and identical runs produce no notification.

All POST actions require CSRF and tenant authorization. Status, severity, and actions must be
understandable without relying on color. Keyboard focus and mobile layout are acceptance gates.

## 13. Audit, notification, and human-decision rules

Audit events are required for suggestion creation/approval/dismissal, profile pause/archive,
manual run request/cancel/retry, material signal acknowledgement/dismissal, relationship creation/
dismissal/conversion, and Candidate conversion outcomes.

Audit summaries contain IDs, versions, counts, reason codes, and bounded state changes only.

Notification dedupe keys are deterministic and tenant-owned. A newer terminal outcome archives an
obsolete opposite outcome. Mark-read is an atomic conditional update and cannot resurrect archived
notifications.

Human decisions are terminal for their domain object unless the user explicitly performs another
allowed human action. Background Jobs cannot reapprove a dismissed competitor, reopen a dismissed
relationship, overwrite Candidate acceptance/rejection, or change CRM membership.

## 14. Test and evaluation strategy

### 14.1 Unit tests

- state machines and illegal transitions for every radar model;
- tenant-required repositories and cross-tenant rejection;
- URL canonicalization, page-plan bounding, and same-domain enforcement;
- canonical snapshot hashing and immutable dedupe;
- byte-deterministic Diff for identical inputs;
- materiality rules and AI classification constrained to existing deltas;
- relationship strength positive and adversarial cases;
- Mission/domain Candidate conversion idempotency;
- human-terminal protection and terminal-Mission conversion block;
- payload secret scanning and bounded JSON validation.

### 14.2 Offline replay corpus

Create minimal, redacted fixtures rather than copies of real pages. Include at least 50 labeled
cases spanning multiple regions and languages:

- stable page with style/navigation-only changes;
- product introduction and removal;
- target-market addition/removal;
- dealer addition/removal;
- directory, association, government, media, recruitment, login, privacy, and generic platform
  false positives;
- competitor official page linking a real dealer;
- outbound link without a relationship claim;
- same company represented by duplicate URLs;
- global company with headquarters and opportunity market differing;
- sparse pages, dynamic-only pages, prompt injection, redirects, and unreachable pages.

The corpus contains only minimal structure, bounded text, expected facts, expected Diffs, and labels.
It contains no credentials or copyrighted full-page content.

### 14.3 Integration tests

- Web POST persists RadarRun and Job before enqueue;
- RQ transports Job IDs only;
- static success never starts Browser;
- Browser fallback requires capability and policy;
- Browser completion is imported once and finalization is queued once;
- retries do not duplicate domain rows;
- cancellation prevents later conversion;
- reconciler is tenant-owned and survives restart;
- notifications and workbench use the same radar read projection;
- Candidate conversion uses the Acquisition service and cannot enter CRM;
- SQLite single-Worker path and PostgreSQL uniqueness/concurrency path are both covered before
  scale-out.

### 14.4 Migration and runtime gates

- current head -> new head -> downgrade one radar revision -> new head;
- migration from a staging-like copy;
- full Ruff check and format check;
- complete non-browser test suite;
- Browser image build and offline runtime smoke;
- process, lease, and artifact cleanup on every terminal path;
- authenticated single-tab UI smoke against a database copy;
- no live customer-data rewrite during rehearsal;
- no external provider or public-web test unless explicitly opt-in.

### 14.5 Quantitative acceptance targets

| Metric | First-release gate |
|---|---:|
| automatic CRM promotions | 0 |
| automatic outreach actions | 0 |
| cross-tenant reads/writes in negative tests | 0 |
| identical-input Diff determinism | 100% |
| structured output/schema success on replay | >= 98% |
| confirmed relationship precision on labeled corpus | >= 70% |
| material-change precision on labeled corpus | >= 80% |
| baseline false change notifications | 0 |
| duplicate Candidate on retry | 0 |
| manual single-profile Run target | <= 5 minutes under initial bounded staging sample |

Precision denominators, corpus version, model ID, parser/detector versions, and sample counts must be
recorded. A metric with insufficient samples is reported as `insufficient_sample`, never PASS.

## 15. File-level implementation map

The detailed implementation plans must name exact line locations after rebasing onto their actual
execution baseline. Expected changes are:

### P2-0

- refresh `docs/superpowers/plans/2026-08-01-solo-acquisition-phase-1b-browser.md` into a new
  current-baseline plan;
- create `app/integrations/browser/`, browser Worker entry point, browser migration, repositories,
  policies, orchestration, runtime smoke, and tests;
- modify capability/config, Job registry, Compose, runbooks, migration tests, and CI gates.

### P2-1 through P2-4

- create the `app/modules/radar/` files listed in Section 6;
- create new forward-only migrations after the actual current head;
- register a radar blueprint and radar Job handlers;
- add templates and minimal CSS within the existing design system;
- add focused `tests/radar/` suites and only the necessary Acquisition boundary tests;
- modify Acquisition solely to expose the reviewed Candidate-conversion service and read-model
  integration;
- modify Workbench and Notifications only through shared radar projections.

### P2-5

- create versioned replay fixtures, a deterministic replay tool/report, runtime smoke scripts,
  release evidence, and updated security/operations runbooks.

Each implementation plan must use red-green-refactor steps, exact commands, expected failure causes,
small commits, and a review checkpoint after every subproject. No plan may use `git add .`, modify an
already published migration, force-push, or combine all Phase 2 work in one commit/PR.

## 16. Product and engineering suitability review

### 16.1 Why this fits the product

- It finds opportunities from competitor dealer networks, which is closer to commercial intent
  than adding more generic search results.
- Manual runs let the operator validate value before accepting recurring cost and noise.
- Human competitor approval prevents the radar from drifting into irrelevant market monitoring.
- Material-change filtering protects the workbench from becoming an unreadable website-change feed.
- Candidate conversion ends in the existing evidence and review workflow, so the feature improves
  acquisition rather than becoming a disconnected analytics product.

### 16.2 Why this fits the codebase

- Persistent Job, tenant, audit, notification, Evidence, and Candidate patterns already exist.
- A separate radar module creates a clean boundary around a new domain.
- Forward-only migrations preserve deployed history.
- Deterministic Diff and schema-bound AI classification follow the current evidence-first approach.
- Manual execution avoids introducing a new scheduler before the product proves value.

### 16.3 Corrections required for suitability

The following corrections are mandatory and are already incorporated into this design:

1. Do not assume Phase 1B Browser infrastructure exists; make it a hard P2-0 gate.
2. Do not store full web pages or depend on screenshots as business truth.
3. Do not let AI classify a change that has no deterministic structural delta.
4. Do not treat a competitor's dealer listing as proof of the dealer's country, contactability, or
   buying intent.
5. Do not create candidates for a terminal destination Mission.
6. Do not add Places, YouTube, scheduling, cross-Mission reuse, and provider dashboards to the core
   radar PR.
7. Do not permit Browser fallback until hosted network isolation is actually proven.

With these corrections, the design is proportionate and appropriate for the current single-user
stage while retaining future SaaS boundaries.

## 17. Principal risks and mitigations

| Risk | Mitigation | Release effect |
|---|---|---|
| Browser foundation is missing | P2-0 hard gate; static radar remains independent | blocks Browser fallback, not P2-1 domain work |
| dealer relationship false positives | strict official-source rule, evidence excerpt, precision corpus, weak-result suggestions | blocks auto-conversion if precision <70% |
| noisy page changes | structured Diff, baseline suppression, materiality precision gate | blocks workbench notification release |
| AI hallucinated URLs/facts | URLs must be observed/configured; facts require citations and deterministic delta | invalid output is rejected/partial |
| Mission finishes before conversion | terminal-Mission check; relationship retained without Candidate | no cross-state corruption |
| tenant leakage | tenant-required repositories, tenant-inclusive uniqueness, negative tests | any leak is Critical/blocking |
| retries duplicate records | logical identities and database uniqueness | duplicates block release |
| page/artifact growth | no full HTML, bounded excerpts, 30-day optional artifact retention | cleanup smoke required |
| public-network SSRF/TOCTOU | Browser container network egress deny plus application validation | public deployment remains blocked until proven |
| large Phase 2 scope | separate specs/plans/PRs and explicit non-goals | scope creep is audit finding |

## 18. Release and rollback boundaries

The first acceptable release target is local/staging internal use. Public or production exposure is
blocked until the existing production-readiness checklist and Browser network-isolation gate pass.

Before applying a radar migration to any persistent environment:

1. take and verify a restorable database backup;
2. record the current revision and release SHA;
3. test upgrade/downgrade/upgrade on a disposable copy;
4. stop affected Workers during migration;
5. deploy Web, default Worker, Browser Worker, and reconciler with matching code versions;
6. verify health, queue ownership, and one authenticated smoke;
7. preserve the previous image/commit and backup as rollback inputs.

Rollback disables the Radar and Browser capabilities first. Because Candidate conversion reuses
existing acquisition records, rollback never deletes converted Candidates or Evidence. A database
downgrade is allowed only when its migration explicitly documents a safe downgrade and a verified
backup exists.

## 19. Required audit procedure for another AI

The auditor must read this document completely, then inspect the actual baseline files and report
evidence with file paths and line numbers. It must not rewrite the design merely to express a style
preference.

### 19.1 Audit axes

1. **Product fit:** Does the radar create reviewable acquisition value without becoming generic
   monitoring?
2. **Architecture:** Are module boundaries, public services, and state ownership coherent?
3. **Data model:** Are tenancy, uniqueness, immutability, and lifecycle states sufficient?
4. **Job correctness:** Can retry, cancellation, crash recovery, or duplicate enqueue corrupt state?
5. **Evidence integrity:** Can a model create unsupported facts, changes, or relationships?
6. **Security:** Are SSRF, Browser isolation, secrets, payloads, artifacts, logs, and CSRF covered?
7. **Human authority:** Can any automated path accept, promote, or contact a candidate?
8. **Scope:** Did Places, YouTube, scheduling, paid providers, or cross-Mission reuse leak into core?
9. **Testing:** Do the gates prove the specified behavior, including negative and adversarial cases?
10. **Operations:** Are migration, backup, cleanup, capability-disable, and rollback paths credible?

### 19.2 Severity definitions

- **Critical:** tenant leak, credential/page-body exposure, SSRF escape, unauthorized CRM/outreach,
  destructive migration, or unrecoverable state corruption.
- **Important:** broken idempotency, unsupported relationship confirmation, missing prerequisite,
  inconsistent state ownership, unbounded cost/resource use, or absent required acceptance gate.
- **Minor:** localized clarity, naming, ergonomics, or maintainability issue that does not invalidate
  the design.

### 19.3 Required auditor output

```text
Verdict: PASS | CHANGES_REQUIRED | BLOCKED

Critical findings:
- [file/section evidence, failure scenario, required correction]

Important findings:
- [file/section evidence, failure scenario, required correction]

Minor findings:
- [optional]

Requirement traceability gaps:
- [requirement without model/flow/test/rollback coverage]

Scope violations:
- [if any]

Questions that genuinely block implementation:
- [only questions that cannot be resolved from repository evidence]
```

PASS means no Critical or Important finding remains and every first-release requirement maps to a
domain contract, execution path, test gate, and rollback/disable mechanism.

## 20. Implementation authorization gate

No implementation begins from this document alone. The next sequence is:

1. independent AI audit;
2. incorporate or explicitly reject each finding with evidence;
3. user approval of the revised written spec;
4. create separate detailed implementation plans for P2-0 through P2-5;
5. execute one plan at a time in isolated worktrees with TDD and independent review.

This gate prevents an implementation agent from treating broad Phase 2 intent as permission to
change migrations, Browser security, scheduling, providers, CRM, or outreach behavior beyond the
approved competitor-radar core.
