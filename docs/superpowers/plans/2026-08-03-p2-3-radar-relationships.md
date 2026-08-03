# P2-3 Radar Relationships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` task-by-task with tests first.

**Goal:** Turn cited, confirmed competitor dealer/distributor observations into review-only Acquisition Candidates without automatic CRM, verification, assessment, or outreach.

**Architecture:** `RadarRelationship` is tenant-owned evidence derived only from a completed static Snapshot. The Radar extractor may propose relationships but cannot write Acquisition tables. The Acquisition public service re-checks all ownership, Mission state, relationship evidence, drift and type gates in one transaction before creating an idempotent B-tier candidate.

**Tech Stack:** Flask, SQLAlchemy/Alembic, deterministic extraction, pytest, Ruff.

---

### Task 1: Persist and deterministically extract relationships

**Files:**
- Modify: `app/modules/radar/models.py`, `app/modules/radar/snapshots.py`, `app/modules/radar/jobs.py`
- Create: `app/modules/radar/relationships.py`, `migrations/versions/0018_radar_relationships.py`, `tests/radar/test_relationships.py`

- [ ] Write failing fixtures for confirmed dealer/distributor, partner, likely and unknown observations; run and observe the missing extractor failure.
- [ ] Add immutable-source, tenant/profile/run/snapshot-owned `RadarRelationship` rows with unique profile/domain/type identity and decision state.
- [ ] Extract only a bounded claim excerpt plus a separately observed public outbound URL; classify by versioned multilingual phrase rules. Missing official-source, target identity, outbound URL or claim yields likely/unknown, never confirmed.
- [ ] Re-run relationship tests and commit `feat(radar): add cited relationship proposals`.

### Task 2: Add the Acquisition conversion boundary

**Files:**
- Create: `app/modules/radar/conversion.py`, `tests/radar/test_conversion.py`, `tests/acquisition/test_radar_candidate_boundary.py`
- Modify: `app/modules/acquisition/service.py`, `app/modules/acquisition/routes.py`

- [ ] Write failing tests for confirmed dealer/distributor conversion, partner/likely rejection, terminal Mission rejection, domain dedupe and cross-tenant non-disclosure.
- [ ] Implement `create_candidate_from_radar_relationship(...)` in Acquisition, which re-reads all Radar rows inside its own transaction and creates only `needs_evidence` plus B-tier `competitor_dealer_network` evidence.
- [ ] Record safe provenance that explicitly does not prove target country, contactability, intent or own-site identity. Do not enqueue any Job or write Lead/CRM rows.
- [ ] Re-run boundary tests and commit `feat(acquisition): convert confirmed radar dealers for review`.

### Task 3: Present proposals and enforce the no-automation boundary

**Files:**
- Modify: `app/modules/radar/routes.py`, `app/modules/radar/views.py`, `app/templates/radar/run_detail.html`, `app/templates/radar/profile_detail.html`, `app/templates/acquisition/_candidate_card.html`
- Test: `tests/radar/test_routes.py`

- [ ] Write failing tenant/CSRF UI tests for relationship review and manual conversion.
- [ ] Add only explicit review/conversion POST actions; show relationship evidence and candidate limitations without raw snapshot content.
- [ ] Run Radar/Acquisition suites, migration tests, Ruff and diff check; commit `feat(radar): show review-only relationships`.
