"""Persistent background handlers and mission reconciliation for acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.ai.contracts import CountryResearchPlan
from app.integrations.ai.mimo import ProviderError, build_mimo_provider
from app.integrations.web.fetcher import FetchError, StaticFetcher
from app.modules.acquisition.assessment import compute_candidate_assessment
from app.modules.acquisition.country_contacts import (
    extract_deterministic_evidence,
    merge_contact_paths,
)
from app.modules.acquisition.entity_triage import classify_discovery_entity
from app.modules.acquisition.source_identity import classify_source_identity
from app.modules.acquisition.mission_results import job_outcome_key, resolve_mission_result
from app.modules.acquisition.models import (
    AcquisitionCandidate,
    AcquisitionMission,
    CandidateAssessment,
    CandidateEvidence,
    Notification,
    ProviderStatus,
)
from app.modules.acquisition.policies import canonical_json
from app.modules.acquisition.repository import (
    AssessmentRepository,
    CandidateRepository,
    EvidenceRepository,
    MissionRepository,
    NotificationRepository,
    ProductKnowledgeRepository,
    ProviderStatusRepository,
)
from app.modules.acquisition.states import (
    TERMINAL_JOB_OUTCOME_STATUSES,
    USABLE_CANDIDATE_STATUSES,
    update_assessment_state_if_mutable,
)
from app.modules.acquisition.versions import (
    ELIGIBILITY_POLICY_VERSION,
    PRIORITY_SCORE_VERSION,
)
from app.modules.audit.service import add_event
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JobServiceError, create_and_enqueue, create_and_schedule

_ACTIVE_JOB_STATUSES = {"queued", "running", "retrying"}
_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
_BUSINESS_RESULT_CODES = {
    "ready",
    "needs_review",
    "partial",
    "no_results",
    "failed",
    "cancelled",
}
_ACQUISITION_JOB_TYPES = {
    "acquisition_plan",
    "web_discovery",
    "website_verify",
    "candidate_assess",
}
_TRANSIENT_CODES = {
    "rate_limit",
    "rate_limited",
    "timeout",
    "provider_timeout",
    "provider_unavailable",
    "transient",
    "source_timeout",
    "source_unreachable",
}
_FETCH_ERROR_EXCERPTS = {
    "response_too_large": "Website exceeded the safe download size limit",
    "source_timeout": "Website did not respond within the safe time limit",
    "source_unreachable": "Website could not be reached by the static verifier",
    "unsupported_content_type": "Website returned an unsupported evidence type",
    "policy_url_blocked": "Website URL was blocked by the public-evidence safety policy",
    "dns_changed": "Website DNS changed during verification and was blocked",
    "invalid_redirect": "Website returned an invalid redirect",
    "too_many_redirects": "Website exceeded the safe redirect limit",
}


class AcquisitionJobError(RuntimeError):
    def __init__(self, code: str, safe_summary: str, *, retryable: bool | None = None) -> None:
        super().__init__(f"{code}: {safe_summary}")
        self.code = code
        self.safe_summary = safe_summary
        self.retryable = code in _TRANSIENT_CODES if retryable is None else retryable


def _required_id(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError(f"{name} is required")
    return value.strip()


def validate_handler_payload(
    payload: dict[str, object], *, allowed: set[str], required: set[str]
) -> None:
    extra = set(payload) - allowed
    if extra:
        raise ValueError(f"unexpected payload fields: {sorted(extra)}")
    for name in required:
        _required_id(payload, name)


def _heartbeat(app, job: Job, progress: int, message: str) -> None:
    with Session(get_engine(app)) as session:
        stored = session.scalar(select(Job).where(Job.id == job.id, Job.tenant_id == job.tenant_id))
        if stored is not None:
            stored.heartbeat_at = datetime.now(UTC)
            stored.progress = progress
            stored.progress_message = message[:500]
            session.commit()


def _provider_success(app, tenant_id: str) -> None:
    with Session(get_engine(app)) as session:
        statuses = ProviderStatusRepository(session)
        previous = statuses.get("mimo", tenant_id=tenant_id)
        recovered = bool(previous and previous.consecutive_failures > 0)
        statuses.record_success("mimo", datetime.now(UTC), tenant_id=tenant_id)
        if recovered:
            add_event(
                session,
                tenant_id=tenant_id,
                actor_type="system",
                action="provider.recovered",
                target_type="provider",
                target_id="mimo",
                safe_summary="MiMo provider recovered",
            )
        session.commit()


def _provider_failure(app, tenant_id: str, error_code: str) -> None:
    with Session(get_engine(app)) as session:
        status = ProviderStatusRepository(session).record_failure(
            "mimo", error_code, datetime.now(UTC), tenant_id=tenant_id
        )
        _ensure_provider_failure_notification(session, status)
        session.commit()


def _ensure_provider_failure_notification(session: Session, status: ProviderStatus) -> None:
    if status.consecutive_failures < 3:
        return
    incident_anchor = status.last_success_at.isoformat() if status.last_success_at else "initial"
    dedupe_key = f"provider-failed:mimo:{incident_anchor}"
    notifications = NotificationRepository(session)
    if notifications.find_by_dedupe_key(dedupe_key, tenant_id=status.tenant_id) is None:
        try:
            with session.begin_nested():
                notifications.add(
                    Notification(
                        kind="provider_failed",
                        title="MiMo research is temporarily unavailable",
                        body="Use manual URL research while the provider is recovering.",
                        target_url="/settings",
                        dedupe_key=dedupe_key,
                    ),
                    tenant_id=status.tenant_id,
                )
                session.flush()
        except IntegrityError:
            # Worker and reconciler can observe the same incident concurrently.
            # The tenant-scoped unique key is authoritative; the savepoint keeps
            # the surrounding provider status transaction usable.
            pass


def handle_acquisition_plan(app, job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    validate_handler_payload(payload, allowed={"mission_id"}, required={"mission_id"})
    mission_id = _required_id(payload, "mission_id")
    tenant_id = job.tenant_id

    with Session(get_engine(app)) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionJobError("mission_not_found", "Mission was not found", retryable=False)
        product = ProductKnowledgeRepository(session).get(
            mission.product_snapshot_id, tenant_id=tenant_id
        )
        if product is None:
            raise AcquisitionJobError(
                "product_not_found", "Product snapshot was not found", retryable=False
            )
        target_profile = _json_object(mission.target_profile_json)
        product_summary = product.summary

    _heartbeat(app, job, 10, "Planning country research")
    started = perf_counter()
    try:
        provider = build_mimo_provider(app, tenant_id=tenant_id)
        plan = provider.plan_mission(product_summary=product_summary, target_profile=target_profile)
    except ProviderError as exc:
        _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
        _provider_failure(app, tenant_id, exc.code)
        raise AcquisitionJobError(exc.code, exc.safe_summary, retryable=exc.retryable) from None
    _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
    _provider_success(app, tenant_id)
    _heartbeat(app, job, 60, "Saving research plan")

    with Session(get_engine(app)) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionJobError("mission_not_found", "Mission was not found", retryable=False)
        mission.plan_json = canonical_json(plan.model_dump(mode="json"))
        mission.status = "running"
        session.commit()

    for country_run in plan.country_runs:
        create_and_enqueue(
            app,
            tenant_id=tenant_id,
            job_type="web_discovery",
            payload={"mission_id": mission_id, "country_code": country_run.country_code},
        )
    _heartbeat(app, job, 90, "Country research queued")
    return {
        "mission_id": mission_id,
        "country_run_count": len(plan.country_runs),
        "stage": "planned",
    }


def handle_web_discovery(app, job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    validate_handler_payload(
        payload,
        allowed={"mission_id", "country_code"},
        required={"mission_id", "country_code"},
    )
    mission_id = _required_id(payload, "mission_id")
    country_code = _required_id(payload, "country_code").upper()
    tenant_id = job.tenant_id

    with Session(get_engine(app)) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionJobError("mission_not_found", "Mission was not found", retryable=False)
        plan_json = _json_object(mission.plan_json)
        runs = plan_json.get("country_runs", [])
        matching = [item for item in runs if item.get("country_code") == country_code]
        if len(matching) != 1:
            raise AcquisitionJobError(
                "plan_invalid", "Country plan is unavailable", retryable=False
            )
        country_plan = CountryResearchPlan.model_validate(matching[0])
        budget = _json_object(mission.budget_json)
        max_candidates = int(
            budget.get("max_candidates", app.config.get("ACQUISITION_MAX_CANDIDATES", 30))
        )
        max_verify = int(budget.get("max_verify", app.config.get("ACQUISITION_MAX_VERIFY", 10)))

    _heartbeat(app, job, 10, f"Searching {country_code}")
    started = perf_counter()
    try:
        hits = build_mimo_provider(app, tenant_id=tenant_id).discover_companies(
            country_plan=country_plan
        )
    except ProviderError as exc:
        _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
        _provider_failure(app, tenant_id, exc.code)
        raise AcquisitionJobError(exc.code, exc.safe_summary, retryable=exc.retryable) from None
    _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
    _provider_success(app, tenant_id)

    hits_received = len(hits)
    valid_hits = 0
    domain_skipped = 0
    created = 0
    deduped = 0
    entity_triaged = 0
    verify_ids: list[str] = []
    with Session(get_engine(app)) as session:
        candidates = CandidateRepository(session)
        evidence = EvidenceRepository(session)
        for index, hit in enumerate(hits[:max_candidates], start=1):
            url = str(hit.url)
            domain = _canonical_domain(url)
            if not domain:
                domain_skipped += 1
                continue
            valid_hits += 1
            entity_type = classify_discovery_entity(
                url=url,
                title=hit.title,
                excerpt=hit.excerpt,
            )
            dedupe_key = f"domain:{domain}"
            candidate = candidates.find_by_dedupe_key(mission_id, dedupe_key, tenant_id=tenant_id)
            if candidate is None:
                candidate = candidates.add(
                    AcquisitionCandidate(
                        mission_id=mission_id,
                        status="discovered" if entity_type == "company" else "needs_evidence",
                        entity_type=entity_type,
                        company_name=hit.title[:300],
                        domain=domain,
                        website=url[:1000],
                        opportunity_country_code=country_code,
                        country_resolution_status="unknown",
                        source_channel="mimo_web",
                        source_provider="mimo",
                        eligibility_code=(
                            "" if entity_type == "company" else "entity_triage_noncompany"
                        ),
                        unknowns_json=(
                            "[]"
                            if entity_type == "company"
                            else canonical_json([f"entity_triage:{entity_type}"])
                        ),
                        dedupe_key=dedupe_key,
                    ),
                    tenant_id=tenant_id,
                )
                session.flush()
                created += 1
                if entity_type != "company":
                    entity_triaged += 1
            else:
                deduped += 1

            content_hash = _hash_json(
                {"url": url, "title": hit.title, "excerpt": hit.excerpt, "query": hit.query}
            )
            if evidence.find_content(candidate.id, url, content_hash, tenant_id=tenant_id) is None:
                evidence.add(
                    CandidateEvidence(
                        candidate_id=candidate.id,
                        job_id=job.id,
                        provider="mimo",
                        source_type="web_search",
                        trust_tier="D",
                        source_url=url,
                        canonical_url=url,
                        title=hit.title[:500],
                        excerpt=hit.excerpt[:4000],
                        content_hash=content_hash,
                        validation_status="unverified",
                    ),
                    tenant_id=tenant_id,
                )
            if (
                len(verify_ids) < max_verify
                and candidate.status == "discovered"
                and candidate.entity_type == "company"
            ):
                candidate.status = "verifying"
                verify_ids.append(candidate.id)
            if index % 10 == 0:
                session.flush()
        session.commit()

    _heartbeat(app, job, 70, "Queueing website verification")
    for candidate_id in verify_ids:
        if not _job_exists(
            app, tenant_id=tenant_id, job_type="website_verify", entity_id=candidate_id
        ):
            create_and_enqueue(
                app,
                tenant_id=tenant_id,
                job_type="website_verify",
                payload={"candidate_id": candidate_id},
            )
    return {
        "mission_id": mission_id,
        "country_code": country_code,
        "hits_received": hits_received,
        "valid_hits": valid_hits,
        "domain_skipped": domain_skipped,
        "query_count": len(country_plan.queries),
        "created": created,
        "deduped": deduped,
        "entity_triaged": entity_triaged,
        "stage": "discovered",
    }


def handle_website_verify(app, job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    validate_handler_payload(
        payload,
        allowed={"candidate_id", "analysis_retry"},
        required={"candidate_id"},
    )
    candidate_id = _required_id(payload, "candidate_id")
    analysis_retry = payload.get("analysis_retry", False)
    if not isinstance(analysis_retry, bool):
        raise ValueError("analysis_retry must be a boolean")
    tenant_id = job.tenant_id

    with Session(get_engine(app)) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionJobError(
                "candidate_not_found", "Candidate was not found", retryable=False
            )
        website = candidate.website
        mission_id = candidate.mission_id
        if not website:
            raise AcquisitionJobError(
                "source_unreachable", "Candidate website is unavailable", retryable=False
            )

    _heartbeat(app, job, 10, "Fetching public website evidence")
    started = perf_counter()
    try:
        snapshot = StaticFetcher.from_app(app).fetch(website)
    except FetchError as exc:
        _record_cost(app, tenant_id, mission_id, "static_fetcher", started, requests=1)
        _save_error_evidence(app, job, candidate_id, website, exc.code)
        _enqueue_candidate_assessment_if_inactive(
            app,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
        )
        raise AcquisitionJobError(
            exc.code,
            exc.safe_summary,
            retryable=exc.code in {"source_timeout", "source_unreachable"},
        ) from None
    _record_cost(
        app,
        tenant_id,
        mission_id,
        "static_fetcher",
        started,
        requests=1,
        pages=1,
    )

    if snapshot.detected_prompt_injection:
        _save_snapshot_evidence(
            app,
            job,
            candidate_id,
            snapshot,
            trust_tier="E",
            validation_status="contradicted",
            excerpt="Page rejected by prompt-injection policy",
            source_type="security_rejection",
        )
        raise AcquisitionJobError(
            "prompt_injection_detected",
            "Website evidence was rejected by safety policy",
            retryable=False,
        )

    source_identity = classify_source_identity(candidate.company_name, snapshot)
    _save_snapshot_evidence(
        app,
        job,
        candidate_id,
        snapshot,
        trust_tier=source_identity.trust_tier,
        validation_status=source_identity.validation_status,
        excerpt=snapshot.text[:4000],
        source_type=source_identity.source_type,
    )
    if not source_identity.is_confirmed:
        with Session(get_engine(app)) as session:
            candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
            if candidate is not None:
                candidate.entity_type = "source_identity_unverified"
                session.commit()
        _enqueue_candidate_assessment_if_inactive(
            app,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
        )
        return {
            "candidate_id": candidate_id,
            "evidence_count": 1,
            "stage": "source_identity_unverified",
        }
    deterministic = extract_deterministic_evidence(
        snapshot,
        target_country_code=candidate.opportunity_country_code,
    )
    with Session(get_engine(app)) as session:
        stored = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if stored is not None:
            stored.contact_json = canonical_json(
                merge_contact_paths(_json_object(stored.contact_json), deterministic.contact_paths)
            )
            if deterministic.country_confirmed:
                stored.hq_country_code = deterministic.country_code
                stored.opportunity_country_code = deterministic.country_code
                stored.country_resolution_status = "confirmed"
            elif deterministic.country_note:
                unknowns = _json_list(stored.unknowns_json)
                if deterministic.country_note not in unknowns:
                    unknowns.append(deterministic.country_note)
                stored.unknowns_json = canonical_json(unknowns)
            session.commit()
    _heartbeat(app, job, 55, "Extracting company facts")
    started = perf_counter()
    try:
        facts = build_mimo_provider(app, tenant_id=tenant_id).extract(snapshot)
    except ProviderError as exc:
        _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
        _provider_failure(app, tenant_id, exc.code)
        delayed_reanalysis_scheduled = (
            exc.code == "invalid_response"
            and not analysis_retry
            and _schedule_delayed_reanalysis_if_allowed(
                app,
                tenant_id=tenant_id,
                mission_id=mission_id,
                candidate_id=candidate_id,
            )
        )
        if not delayed_reanalysis_scheduled:
            _enqueue_candidate_assessment_if_inactive(
                app,
                tenant_id=tenant_id,
                candidate_id=candidate_id,
            )
        raise AcquisitionJobError(exc.code, exc.safe_summary, retryable=exc.retryable) from None
    _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
    _provider_success(app, tenant_id)

    with Session(get_engine(app)) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionJobError(
                "candidate_not_found", "Candidate was not found", retryable=False
            )
        existing_contacts = _json_object(candidate.contact_json)
        previous_country_confirmed = candidate.country_resolution_status == "confirmed"
        candidate.company_name = facts.company_name
        candidate.domain = facts.canonical_domain.lower()
        candidate.website = snapshot.final_url
        candidate.hq_country_code = facts.hq_country_code or candidate.hq_country_code
        candidate.opportunity_country_code = (
            facts.opportunity_country_code or candidate.opportunity_country_code
        )
        if facts.opportunity_country_code or previous_country_confirmed:
            candidate.country_resolution_status = "confirmed"
        candidate.contact_json = canonical_json(
            merge_contact_paths(existing_contacts, facts.contact_paths)
        )
        candidate.observed_facts_json = canonical_json(
            {
                "buyer_type": facts.buyer_type,
                "product_terms": facts.product_terms,
                "claims": [claim.model_dump(mode="json") for claim in facts.observed_claims],
            }
        )
        candidate.inferences_json = canonical_json(facts.inferences)
        candidate.unknowns_json = canonical_json(facts.unknowns)
        session.commit()

    _enqueue_candidate_assessment_if_inactive(
        app,
        tenant_id=tenant_id,
        candidate_id=candidate_id,
    )
    return {"candidate_id": candidate_id, "evidence_count": 1, "stage": "verified"}


def _enqueue_candidate_assessment_if_inactive(
    app,
    *,
    tenant_id: str,
    candidate_id: str,
) -> None:
    with Session(get_engine(app)) as session:
        assessment_active = JobRepository(session).has_active_for_candidate(
            candidate_id,
            job_type="candidate_assess",
            tenant_id=tenant_id,
        )
    if assessment_active:
        return
    create_and_enqueue(
        app,
        tenant_id=tenant_id,
        job_type="candidate_assess",
        payload={"candidate_id": candidate_id},
    )


def handle_candidate_assess(app, job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    validate_handler_payload(payload, allowed={"candidate_id"}, required={"candidate_id"})
    candidate_id = _required_id(payload, "candidate_id")
    tenant_id = job.tenant_id
    _heartbeat(app, job, 10, "Assessing verified evidence")

    with Session(get_engine(app)) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionJobError(
                "candidate_not_found", "Candidate was not found", retryable=False
            )
        mission = MissionRepository(session).get(candidate.mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionJobError("mission_not_found", "Mission was not found", retryable=False)
        evidence_items = list(
            EvidenceRepository(session).list_for_candidate(candidate_id, tenant_id=tenant_id)
        )
        computation = compute_candidate_assessment(
            candidate,
            mission,
            evidence_items,
            mimo_model_id=str(app.config.get("MIMO_MODEL", "mimo-v2.5")),
        )
        assessments = AssessmentRepository(session)
        existing = assessments.find_input_version(
            candidate_id,
            computation.evidence_bundle_hash,
            ELIGIBILITY_POLICY_VERSION,
            PRIORITY_SCORE_VERSION,
            computation.prompt_version,
            computation.model_id,
            tenant_id=tenant_id,
        )
        if existing is None:
            assessments.add(
                CandidateAssessment(
                    candidate_id=candidate_id,
                    evidence_bundle_hash=computation.evidence_bundle_hash,
                    policy_version=ELIGIBILITY_POLICY_VERSION,
                    score_version=PRIORITY_SCORE_VERSION,
                    prompt_version=computation.prompt_version,
                    model_provider=computation.model_provider,
                    model_id=computation.model_id,
                    input_json=canonical_json(computation.score_input.__dict__),
                    hard_gate_json=canonical_json(computation.gate.__dict__),
                    score_breakdown_json=canonical_json(computation.score.__dict__),
                    signal_coverage=computation.score.signal_coverage,
                    priority_mode=computation.score.priority_mode,
                    explanation=computation.explanation,
                ),
                tenant_id=tenant_id,
            )
        candidate.priority_score = computation.score.priority_score
        candidate.priority_band = computation.score.priority_band
        candidate.signal_coverage = computation.score.signal_coverage
        candidate.ai_confidence = computation.score.data_quality_score or 0
        candidate_status = update_assessment_state_if_mutable(
            session,
            candidate,
            tenant_id=tenant_id,
            status=computation.gate.disposition,
            eligibility_code=(
                computation.gate.reason_codes[0] if computation.gate.reason_codes else "eligible"
            ),
        )
        session.commit()

    return {
        "candidate_id": candidate_id,
        "disposition": computation.gate.disposition,
        "candidate_status": candidate_status,
        "priority": computation.score.priority_score,
        "coverage": computation.score.signal_coverage,
        "stage": "assessed",
    }


def handle_acquisition_reconcile(app, job: Job, payload: dict[str, object]) -> dict[str, object]:
    """Run reconciliation only for the tenant that owns the persisted Job."""

    validate_handler_payload(
        payload,
        allowed={"mission_id", "enforce_timeout"},
        required=set(),
    )
    mission_id = payload.get("mission_id")
    enforce_timeout = payload.get("enforce_timeout")
    if mission_id is not None:
        _required_id(payload, "mission_id")
        if enforce_timeout is not True:
            raise ValueError("mission reconciliation watchdog must enforce its timeout")
    elif enforce_timeout is not None:
        raise ValueError("timeout enforcement requires mission_id")

    now = datetime.now(UTC)
    timed_out = (
        enforce_mission_timeout(app, tenant_id=job.tenant_id, mission_id=str(mission_id), now=now)
        if mission_id is not None
        else 0
    )
    changed = reconcile_missions(app, tenant_id=job.tenant_id, now=now)
    return {"stage": "reconciled", "changed": changed, "timed_out": timed_out}


def _schedule_delayed_reanalysis_if_allowed(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    candidate_id: str,
) -> bool:
    """Give one malformed AI response a bounded second chance within a Mission."""

    with Session(get_engine(app)) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None or mission.status == "cancelled":
            return False
        deadline_value = _json_object(mission.retrospective_json).get("execution_deadline_at")
        if isinstance(deadline_value, str):
            try:
                deadline = datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
            except ValueError:
                return False
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=UTC)
            if deadline - datetime.now(UTC) <= timedelta(seconds=45):
                return False
        prior_jobs = session.scalars(
            select(Job).where(
                Job.tenant_id == tenant_id,
                Job.job_type == "website_verify",
            )
        )
        for prior_job in prior_jobs:
            prior_payload = _json_object(prior_job.payload_json)
            if (
                prior_payload.get("candidate_id") == candidate_id
                and prior_payload.get("analysis_retry") is True
            ):
                return False
    try:
        create_and_schedule(
            app,
            tenant_id=tenant_id,
            job_type="website_verify",
            payload={"candidate_id": candidate_id, "analysis_retry": True},
            delay=timedelta(seconds=45),
        )
    except JobServiceError:
        return False
    return True


ACQUISITION_HANDLERS = {
    "acquisition_plan": handle_acquisition_plan,
    "web_discovery": handle_web_discovery,
    "website_verify": handle_website_verify,
    "candidate_assess": handle_candidate_assess,
    "acquisition_reconcile": handle_acquisition_reconcile,
}


def enqueue_mission_reconciliations(app) -> int:
    """Persist one reconciliation Job for each non-deleted control-plane tenant."""

    from app.modules.accounts.models import Tenant

    with Session(get_engine(app)) as session:
        tenant_ids = tuple(
            session.scalars(select(Tenant.id).where(Tenant.status != "deleted").order_by(Tenant.id))
        )

    queued = 0
    for tenant_id in tenant_ids:
        with Session(get_engine(app)) as session:
            active_job_id = session.scalar(
                select(Job.id)
                .where(
                    Job.tenant_id == tenant_id,
                    Job.job_type == "acquisition_reconcile",
                    Job.status.in_(_ACTIVE_JOB_STATUSES),
                )
                .limit(1)
            )
        if active_job_id is not None:
            continue
        create_and_enqueue(
            app,
            tenant_id=tenant_id,
            job_type="acquisition_reconcile",
            payload={},
        )
        queued += 1
    return queued


def enforce_mission_timeout(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    now: datetime,
) -> int:
    """Fail only the active children of a manually started overdue Mission.

    The deadline is written when the user starts the Mission and this function
    runs from its one-shot watchdog.  It never scans for or starts new work.
    """

    with Session(get_engine(app)) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None or mission.status not in {"queued", "running"}:
            return 0
        retrospective = _json_object(mission.retrospective_json)
        deadline_value = retrospective.get("execution_deadline_at")
        if not isinstance(deadline_value, str):
            return 0
        try:
            deadline = datetime.fromisoformat(deadline_value.replace("Z", "+00:00"))
        except ValueError:
            return 0
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=UTC)
        if now < deadline:
            return 0

        candidates = list(
            session.scalars(
                select(AcquisitionCandidate).where(
                    AcquisitionCandidate.tenant_id == tenant_id,
                    AcquisitionCandidate.mission_id == mission_id,
                )
            )
        )
        candidate_missions = {candidate.id: candidate.mission_id for candidate in candidates}
        jobs = list(
            session.scalars(
                select(Job).where(
                    Job.tenant_id == tenant_id,
                    Job.job_type.in_(_ACQUISITION_JOB_TYPES),
                )
            )
        )
        timed_out = 0
        for child in jobs:
            if child.status not in _ACTIVE_JOB_STATUSES or not _job_belongs_to_mission(
                child, mission_id, candidate_missions
            ):
                continue
            child.status = "failed"
            child.error_code = "mission_timeout"
            child.error_summary = "Mission execution time budget expired"
            child.progress_message = "Stopped because mission time budget expired"
            child.next_retry_at = None
            child.finished_at = now
            timed_out += 1
        if timed_out:
            session.commit()
        return timed_out


def reconcile_missions(
    app,
    *,
    tenant_id: str,
    now: datetime,
) -> int:
    """Derive Mission status and notifications inside one explicit tenant scope."""

    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("tenant_id is required")
    changed = 0
    with Session(get_engine(app)) as session:
        provider_query = select(ProviderStatus).where(
            ProviderStatus.provider == "mimo",
            ProviderStatus.status == "failed",
            ProviderStatus.consecutive_failures >= 3,
            ProviderStatus.tenant_id == tenant_id,
        )
        for provider_status in session.scalars(provider_query):
            _ensure_provider_failure_notification(session, provider_status)

        job_query = select(Job).where(
            Job.job_type.in_(_ACQUISITION_JOB_TYPES),
            Job.tenant_id == tenant_id,
        )
        candidate_query = select(AcquisitionCandidate).where(
            AcquisitionCandidate.tenant_id == tenant_id
        )
        all_jobs = list(session.scalars(job_query))
        candidates = list(session.scalars(candidate_query))
        candidate_by_id = {item.id: item for item in candidates}
        failed_verification_candidates = _failed_verification_candidates(
            all_jobs,
            candidate_by_id=candidate_by_id,
        )
        repairable_terminal_ids = {
            candidate.mission_id
            for candidate in failed_verification_candidates
            if candidate.status in {"discovered", "verifying"}
        }
        mission_query = select(AcquisitionMission).where(
            AcquisitionMission.status.in_(["queued", "running", "completed", "failed"]),
            AcquisitionMission.tenant_id == tenant_id,
        )
        missions = [
            mission
            for mission in session.scalars(mission_query)
            if mission.status in {"queued", "running"}
            or mission.id in repairable_terminal_ids
            or _mission_needs_result_backfill(mission)
        ]
        candidate_missions = {item.id: item.mission_id for item in candidate_by_id.values()}

        for mission in missions:
            mission_jobs = [
                item
                for item in all_jobs
                if item.tenant_id == mission.tenant_id
                and _job_belongs_to_mission(item, mission.id, candidate_missions)
            ]
            backfill_without_jobs = (
                not mission_jobs
                and mission.status in {"completed", "failed"}
                and _mission_needs_result_backfill(mission)
            )
            if not mission_jobs and not backfill_without_jobs:
                continue
            if any(item.status in _ACTIVE_JOB_STATUSES for item in mission_jobs):
                has_usable_result = any(
                    item.tenant_id == mission.tenant_id
                    and item.mission_id == mission.id
                    and item.status in USABLE_CANDIDATE_STATUSES
                    for item in candidates
                )
                if mission.status != "completed" or not has_usable_result:
                    mission.status = "running"
                continue
            if any(item.status not in _TERMINAL_JOB_STATUSES for item in mission_jobs):
                continue

            _reconcile_failed_verification_candidates(
                failed_verification_candidates,
                mission_id=mission.id,
                tenant_id=mission.tenant_id,
            )
            mission_candidates = [
                item
                for item in candidates
                if item.tenant_id == mission.tenant_id and item.mission_id == mission.id
            ]
            from app.modules.acquisition.service import mission_retrospective_payload

            retrospective = _json_object(mission.retrospective_json)
            previous_execution_status = mission.status
            previous_business_result = retrospective.get("business_result")
            previous_result_code = (
                previous_business_result.get("code")
                if isinstance(previous_business_result, dict)
                else None
            )
            result = resolve_mission_result(
                session,
                mission,
                tenant_id=mission.tenant_id,
                candidates=mission_candidates,
                jobs=mission_jobs,
            )
            next_status = (
                mission.status
                if backfill_without_jobs
                else ("failed" if result.counts.failed_jobs else "completed")
            )
            if mission.status != next_status:
                mission.status = next_status
                result = resolve_mission_result(
                    session,
                    mission,
                    tenant_id=mission.tenant_id,
                    candidates=mission_candidates,
                    jobs=mission_jobs,
                )
            retrospective.pop("business_result_pending_reconcile", None)
            retrospective.update(mission_retrospective_payload(result, mission_candidates))
            mission.retrospective_json = canonical_json(retrospective)
            mission.finished_at = now
            changed += 1

            if previous_execution_status != next_status or previous_result_code != result.code:
                add_event(
                    session,
                    tenant_id=mission.tenant_id,
                    actor_type="system",
                    action="acquisition_mission.result_resolved",
                    target_type="acquisition_mission",
                    target_id=mission.id,
                    safe_summary=(
                        f"execution={next_status}; result={result.code}; "
                        f"discovered={result.counts.discovered}; "
                        f"failed_jobs={result.counts.failed_jobs}"
                    ),
                )

            notification_key = f"mission-terminal:{mission.id}:{next_status}"
            notifications = NotificationRepository(session)
            stale_status = "failed" if next_status == "completed" else "completed"
            stale_notification = notifications.find_by_dedupe_key(
                f"mission-terminal:{mission.id}:{stale_status}",
                tenant_id=mission.tenant_id,
            )
            if stale_notification is not None:
                stale_notification.status = "archived"
            kind = {
                "partial": "mission_partial",
                "failed": "mission_failed",
            }.get(result.code, "mission_completed")
            title = f"找客户任务{result.label}"
            body = f"{mission.name}：{result.summary}。下一步：{result.action_label}。"
            target_url = f"/acquisition/missions/{mission.id}"
            current_notification = notifications.find_by_dedupe_key(
                notification_key,
                tenant_id=mission.tenant_id,
            )
            if current_notification is None:
                notifications.add(
                    Notification(
                        kind=kind,
                        title=title,
                        body=body,
                        target_url=target_url,
                        dedupe_key=notification_key,
                    ),
                    tenant_id=mission.tenant_id,
                )
            else:
                current_notification.kind = kind
                current_notification.title = title
                current_notification.body = body
                current_notification.target_url = target_url
                current_notification.status = "unread"
                current_notification.read_at = None
        session.commit()
    return changed


def _failed_verification_candidates(
    jobs: list[Job],
    *,
    candidate_by_id: dict[str, AcquisitionCandidate],
) -> list[AcquisitionCandidate]:
    latest_jobs: dict[str, Job] = {}
    for job in jobs:
        if job.job_type != "website_verify" or job.status not in TERMINAL_JOB_OUTCOME_STATUSES:
            continue
        candidate_id = _json_object(job.payload_json).get("candidate_id")
        if not isinstance(candidate_id, str):
            continue
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None or candidate.tenant_id != job.tenant_id:
            continue
        current = latest_jobs.get(candidate_id)
        if current is None or job_outcome_key(job) > job_outcome_key(current):
            latest_jobs[candidate_id] = job
    return [
        candidate_by_id[candidate_id]
        for candidate_id, job in latest_jobs.items()
        if job.status in {"failed", "cancelled"}
    ]


def _reconcile_failed_verification_candidates(
    candidates: list[AcquisitionCandidate],
    *,
    mission_id: str,
    tenant_id: str,
) -> None:
    for candidate in candidates:
        if (
            candidate.tenant_id == tenant_id
            and candidate.mission_id == mission_id
            and candidate.status in {"discovered", "verifying"}
        ):
            candidate.status = "needs_evidence"


def _mission_needs_result_backfill(mission: AcquisitionMission) -> bool:
    retrospective = _json_object(mission.retrospective_json)
    if retrospective.get("business_result_pending_reconcile") is True:
        return True
    business_result = retrospective.get("business_result")
    return not (
        isinstance(business_result, dict) and business_result.get("code") in _BUSINESS_RESULT_CODES
    )


def _job_belongs_to_mission(job: Job, mission_id: str, candidate_missions: dict[str, str]) -> bool:
    payload = _json_object(job.payload_json)
    if payload.get("mission_id") == mission_id:
        return True
    candidate_id = payload.get("candidate_id")
    return isinstance(candidate_id, str) and candidate_missions.get(candidate_id) == mission_id


def _job_exists(app, *, tenant_id: str, job_type: str, entity_id: str) -> bool:
    key = "candidate_id" if job_type in {"website_verify", "candidate_assess"} else "mission_id"
    with Session(get_engine(app)) as session:
        jobs = session.scalars(
            select(Job).where(Job.tenant_id == tenant_id, Job.job_type == job_type)
        )
        return any(_json_object(job.payload_json).get(key) == entity_id for job in jobs)


def _save_snapshot_evidence(
    app,
    job: Job,
    candidate_id: str,
    snapshot,
    *,
    trust_tier: str,
    validation_status: str,
    excerpt: str,
    source_type: str,
) -> None:
    with Session(get_engine(app)) as session:
        repo = EvidenceRepository(session)
        if (
            repo.find_content(
                candidate_id,
                snapshot.final_url,
                snapshot.content_hash,
                tenant_id=job.tenant_id,
            )
            is None
        ):
            repo.add(
                CandidateEvidence(
                    candidate_id=candidate_id,
                    job_id=job.id,
                    provider="static_fetcher",
                    source_type=source_type,
                    trust_tier=trust_tier,
                    source_url=snapshot.requested_url,
                    canonical_url=snapshot.final_url,
                    title=snapshot.title[:500],
                    excerpt=excerpt[:4000],
                    retrieved_at=snapshot.retrieved_at,
                    content_hash=snapshot.content_hash,
                    validation_status=validation_status,
                ),
                tenant_id=job.tenant_id,
            )
            session.commit()


def _save_error_evidence(
    app, job: Job, candidate_id: str, source_url: str, error_code: str
) -> None:
    content_hash = _hash_json({"source_url": source_url, "error_code": error_code})
    with Session(get_engine(app)) as session:
        repo = EvidenceRepository(session)
        if (
            repo.find_content(candidate_id, source_url, content_hash, tenant_id=job.tenant_id)
            is None
        ):
            repo.add(
                CandidateEvidence(
                    candidate_id=candidate_id,
                    job_id=job.id,
                    provider="static_fetcher",
                    source_type="fetch_error",
                    trust_tier="E",
                    source_url=source_url,
                    canonical_url=source_url,
                    excerpt=_FETCH_ERROR_EXCERPTS.get(
                        error_code,
                        "Website evidence could not be retrieved",
                    ),
                    content_hash=content_hash,
                    validation_status="unreachable",
                ),
                tenant_id=job.tenant_id,
            )
            session.commit()


def _canonical_domain(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        return parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return ""


def _hash_json(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _record_cost(
    app,
    tenant_id: str,
    mission_id: str,
    provider: str,
    started: float,
    *,
    requests: int,
    pages: int | None = None,
) -> None:
    from app.modules.acquisition.service import record_mission_cost

    record_mission_cost(
        app,
        tenant_id=tenant_id,
        mission_id=mission_id,
        provider=provider,
        requests=requests,
        pages=pages,
        tokens=None,
        estimated_cost=None,
        duration_ms=max(0, round((perf_counter() - started) * 1000)),
    )


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _main() -> int:
    parser = argparse.ArgumentParser(description="Acquisition background operations")
    parser.add_argument("command", choices=["reconcile"])
    parser.add_argument("--tenant-id", default=None)
    args = parser.parse_args()
    from app import create_app

    app = create_app()
    if args.tenant_id:
        changed = reconcile_missions(app, tenant_id=args.tenant_id, now=datetime.now(UTC))
        print(f"Reconciled {changed} acquisition mission(s)")
    else:
        queued = enqueue_mission_reconciliations(app)
        print(f"Queued {queued} tenant reconciliation job(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
