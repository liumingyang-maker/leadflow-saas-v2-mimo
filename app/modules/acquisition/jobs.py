"""Persistent background handlers and mission reconciliation for acquisition."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
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
from app.modules.acquisition.scoring import (
    EligibilityFacts,
    ScoreInput,
    evaluate_gate,
    score_candidate,
)
from app.modules.audit.service import add_event
from app.modules.jobs.models import Job
from app.modules.jobs.service import create_and_enqueue

_ACTIVE_JOB_STATUSES = {"queued", "running", "retrying"}
_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
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

    created = 0
    deduped = 0
    verify_ids: list[str] = []
    with Session(get_engine(app)) as session:
        candidates = CandidateRepository(session)
        evidence = EvidenceRepository(session)
        for index, hit in enumerate(hits[:max_candidates], start=1):
            url = str(hit.url)
            domain = _canonical_domain(url)
            if not domain:
                continue
            dedupe_key = f"domain:{domain}"
            candidate = candidates.find_by_dedupe_key(mission_id, dedupe_key, tenant_id=tenant_id)
            if candidate is None:
                candidate = candidates.add(
                    AcquisitionCandidate(
                        mission_id=mission_id,
                        status="discovered",
                        company_name=hit.title[:300],
                        domain=domain,
                        website=url[:1000],
                        opportunity_country_code=country_code,
                        country_resolution_status="unknown",
                        source_channel="mimo_web",
                        source_provider="mimo",
                        dedupe_key=dedupe_key,
                    ),
                    tenant_id=tenant_id,
                )
                session.flush()
                created += 1
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
            if len(verify_ids) < max_verify and candidate.status == "discovered":
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
        "created": created,
        "deduped": deduped,
        "stage": "discovered",
    }


def handle_website_verify(app, job: Job, payload: dict[str, Any]) -> dict[str, Any]:
    validate_handler_payload(payload, allowed={"candidate_id"}, required={"candidate_id"})
    candidate_id = _required_id(payload, "candidate_id")
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
        raise AcquisitionJobError(
            "source_unreachable",
            "Candidate website could not be verified",
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

    _save_snapshot_evidence(
        app,
        job,
        candidate_id,
        snapshot,
        trust_tier="A",
        validation_status="valid",
        excerpt=snapshot.text[:4000],
        source_type="official_website",
    )
    _heartbeat(app, job, 55, "Extracting company facts")
    started = perf_counter()
    try:
        facts = build_mimo_provider(app, tenant_id=tenant_id).extract(snapshot)
    except ProviderError as exc:
        _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
        _provider_failure(app, tenant_id, exc.code)
        raise AcquisitionJobError(exc.code, exc.safe_summary, retryable=exc.retryable) from None
    _record_cost(app, tenant_id, mission_id, "mimo", started, requests=1)
    _provider_success(app, tenant_id)

    with Session(get_engine(app)) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionJobError(
                "candidate_not_found", "Candidate was not found", retryable=False
            )
        candidate.company_name = facts.company_name
        candidate.domain = facts.canonical_domain.lower()
        candidate.website = snapshot.final_url
        candidate.hq_country_code = facts.hq_country_code
        candidate.opportunity_country_code = facts.opportunity_country_code
        if facts.opportunity_country_code:
            candidate.country_resolution_status = "confirmed"
        candidate.contact_json = canonical_json({"paths": facts.contact_paths})
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

    if not _job_exists(
        app, tenant_id=tenant_id, job_type="candidate_assess", entity_id=candidate_id
    ):
        create_and_enqueue(
            app,
            tenant_id=tenant_id,
            job_type="candidate_assess",
            payload={"candidate_id": candidate_id},
        )
    return {"candidate_id": candidate_id, "evidence_count": 1, "stage": "verified"}


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
        target = _json_object(mission.target_profile_json)
        observed = _json_object(candidate.observed_facts_json)
        contact = _json_object(candidate.contact_json)

        countries = {str(value).upper() for value in target.get("country_codes", [])}
        country_status = candidate.country_resolution_status
        if (
            country_status == "confirmed"
            and countries
            and candidate.opportunity_country_code not in countries
        ):
            gate_country = "mismatch"
        else:
            gate_country = country_status
        buyer_type = str(observed.get("buyer_type", "")).lower()
        buyer_types = {str(value).lower() for value in target.get("buyer_types", [])}
        buyer_match = not buyer_type or not buyer_types or buyer_type in buyer_types
        product_terms = [str(value) for value in observed.get("product_terms", [])]
        claims = observed.get("claims", [])
        contact_paths = [str(value) for value in contact.get("paths", [])]
        combined = " ".join(
            [candidate.company_name, buyer_type, *product_terms, json.dumps(claims)]
        ).lower()
        excluded = any(str(term).lower() in combined for term in target.get("exclude_terms", []))
        gate = evaluate_gate(
            EligibilityFacts(
                country_status=gate_country,
                buyer_type_match=buyer_match,
                excluded_business=excluded,
                independent_identity=bool(candidate.company_name and candidate.domain),
                product_evidence=bool(product_terms or claims),
                contact_path=bool(contact_paths),
            )
        )
        trust_values = {"A": 100, "B": 80, "C": 60, "D": 40, "E": 20}
        best_trust = max(
            (trust_values.get(item.trust_tier, 0) for item in evidence_items), default=0
        )
        score_input = ScoreInput(
            product_relevance=85 if product_terms else None,
            buyer_role=85 if buyer_type and buyer_match else (0 if buyer_type else None),
            country_match=(
                100 if gate_country == "confirmed" else (0 if gate_country == "mismatch" else None)
            ),
            company_size=None,
            industry_match=70 if product_terms else None,
            direct_purchase=None,
            recent_activity=None,
            competitor_signal=None,
            signal_recency=None,
            identity_quality=90 if candidate.company_name and candidate.domain else None,
            source_trust=best_trust or None,
            contactability=80 if contact_paths else None,
            independent_evidence=80
            if len(evidence_items) >= 2
            else (50 if evidence_items else None),
            data_recency=90 if evidence_items else None,
        )
        score = score_candidate(score_input)
        bundle_hash = _hash_json(
            sorted(
                (item.canonical_url, item.content_hash, item.validation_status)
                for item in evidence_items
            )
        )
        assessments = AssessmentRepository(session)
        model_id = str(app.config.get("MIMO_MODEL", "mimo-v2.5"))
        existing = assessments.find_input_version(
            candidate_id,
            bundle_hash,
            "eligibility-v1",
            "priority-v1",
            "company-extract-v1",
            model_id,
            tenant_id=tenant_id,
        )
        if existing is None:
            assessments.add(
                CandidateAssessment(
                    candidate_id=candidate_id,
                    evidence_bundle_hash=bundle_hash,
                    policy_version="eligibility-v1",
                    score_version="priority-v1",
                    prompt_version="company-extract-v1",
                    model_provider="mimo",
                    model_id=model_id,
                    input_json=canonical_json(score_input.__dict__),
                    hard_gate_json=canonical_json(gate.__dict__),
                    score_breakdown_json=canonical_json(score.__dict__),
                    signal_coverage=score.signal_coverage,
                    priority_mode=score.priority_mode,
                    explanation="Deterministic evidence-aware assessment",
                ),
                tenant_id=tenant_id,
            )
        candidate.status = gate.disposition
        candidate.eligibility_code = gate.reason_codes[0] if gate.reason_codes else "eligible"
        candidate.priority_score = score.priority_score
        candidate.priority_band = score.priority_band
        candidate.signal_coverage = score.signal_coverage
        session.commit()

    return {
        "candidate_id": candidate_id,
        "disposition": gate.disposition,
        "priority": score.priority_score,
        "coverage": score.signal_coverage,
        "stage": "assessed",
    }


ACQUISITION_HANDLERS = {
    "acquisition_plan": handle_acquisition_plan,
    "web_discovery": handle_web_discovery,
    "website_verify": handle_website_verify,
    "candidate_assess": handle_candidate_assess,
}


def reconcile_missions(app, *, tenant_id: str | None = None, now: datetime) -> int:
    """Recover stale jobs, derive Mission status, and dedupe notifications."""

    from app.modules.jobs.worker import recover_stale_jobs

    recover_stale_jobs(app)
    changed = 0
    with Session(get_engine(app)) as session:
        provider_query = select(ProviderStatus).where(
            ProviderStatus.provider == "mimo",
            ProviderStatus.status == "failed",
            ProviderStatus.consecutive_failures >= 3,
        )
        if tenant_id is not None:
            provider_query = provider_query.where(ProviderStatus.tenant_id == tenant_id)
        for provider_status in session.scalars(provider_query):
            _ensure_provider_failure_notification(session, provider_status)

        mission_query = select(AcquisitionMission).where(
            AcquisitionMission.status.in_(["queued", "running"])
        )
        if tenant_id is not None:
            mission_query = mission_query.where(AcquisitionMission.tenant_id == tenant_id)
        missions = list(session.scalars(mission_query))
        all_jobs = list(
            session.scalars(select(Job).where(Job.job_type.in_(_ACQUISITION_JOB_TYPES)))
        )
        candidates = list(session.scalars(select(AcquisitionCandidate)))
        candidate_missions = {item.id: item.mission_id for item in candidates}

        for mission in missions:
            mission_jobs = [
                item
                for item in all_jobs
                if item.tenant_id == mission.tenant_id
                and _job_belongs_to_mission(item, mission.id, candidate_missions)
            ]
            if not mission_jobs:
                continue
            if any(item.status in _ACTIVE_JOB_STATUSES for item in mission_jobs):
                mission.status = "running"
                continue
            if any(item.status not in _TERMINAL_JOB_STATUSES for item in mission_jobs):
                continue

            mission_candidates = [
                item
                for item in candidates
                if item.tenant_id == mission.tenant_id and item.mission_id == mission.id
            ]
            usable = [item for item in mission_candidates if item.status != "rejected"]
            failed_count = sum(item.status in {"failed", "cancelled"} for item in mission_jobs)
            next_status = "completed" if usable else "failed"
            partial = bool(usable and failed_count)
            from app.modules.acquisition.service import mission_retrospective_payload

            retrospective = _json_object(mission.retrospective_json)
            retrospective.update(
                mission_retrospective_payload(mission_candidates, failed_job_count=failed_count)
            )
            mission.retrospective_json = canonical_json(retrospective)
            mission.status = next_status
            mission.finished_at = now
            changed += 1

            notification_key = f"mission-terminal:{mission.id}:{next_status}"
            notifications = NotificationRepository(session)
            if (
                notifications.find_by_dedupe_key(notification_key, tenant_id=mission.tenant_id)
                is None
            ):
                kind = (
                    "mission_partial"
                    if partial
                    else ("mission_completed" if next_status == "completed" else "mission_failed")
                )
                notifications.add(
                    Notification(
                        kind=kind,
                        title=(
                            "Acquisition mission completed"
                            if next_status == "completed"
                            else "Acquisition mission failed"
                        ),
                        body=f"{mission.name}: {len(usable)} usable candidates",
                        target_url=f"/acquisition/missions/{mission.id}",
                        dedupe_key=notification_key,
                    ),
                    tenant_id=mission.tenant_id,
                )
        session.commit()
    return changed


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
                    excerpt="Website evidence could not be retrieved",
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


def _main() -> int:
    parser = argparse.ArgumentParser(description="Acquisition background operations")
    parser.add_argument("command", choices=["reconcile"])
    parser.add_argument("--tenant-id", default=None)
    args = parser.parse_args()
    from app import create_app

    app = create_app()
    changed = reconcile_missions(app, tenant_id=args.tenant_id, now=datetime.now(UTC))
    print(f"Reconciled {changed} acquisition mission(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
