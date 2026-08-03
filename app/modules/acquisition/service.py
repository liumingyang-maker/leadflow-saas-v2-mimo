"""Application services for solo acquisition review and CRM promotion."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.ai.contracts import CompanyExtractor, ExtractedCompanyFacts
from app.integrations.web.fetcher import FetchResult, StaticFetcher
from app.modules.acquisition.assessment import compute_candidate_assessment
from app.modules.acquisition.contracts import (
    CandidateDecisionInput,
    CountryEvidenceInput,
    ManualCompanyFactsInput,
    MissionCreateInput,
)
from app.modules.acquisition.manual_evidence import (
    ManualEvidenceError,
    build_manual_company_facts,
    contact_url,
    normalise_domain,
    require_supported_text,
)
from app.modules.acquisition.models import (
    AcquisitionCandidate,
    AcquisitionMission,
    CandidateAssessment,
    CandidateEvidence,
    MissionSuggestion,
    ProductKnowledgeSnapshot,
)
from app.modules.acquisition.policies import (
    build_budget,
    build_channel_policy,
    build_target_profile,
    canonical_json,
)
from app.modules.acquisition.repository import (
    AssessmentRepository,
    CandidateRepository,
    EvidenceRepository,
    MissionRepository,
    NotificationRepository,
    ProductKnowledgeRepository,
    SuggestionRepository,
)
from app.modules.acquisition.states import (
    BusinessResult,
    update_assessment_state_if_mutable,
)
from app.modules.acquisition.versions import (
    COUNTRY_EVIDENCE_PROMPT_VERSION,
    ELIGIBILITY_POLICY_VERSION,
    MANUAL_FACTS_PROMPT_VERSION,
    MIMO_EXTRACT_PROMPT_VERSION,
    PRIORITY_SCORE_VERSION,
)
from app.modules.audit.service import add_event
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JobServiceError, create_and_enqueue
from app.modules.leads.models import Activity, Company, Lead
from app.modules.leads.repository import CompanyRepository, LeadRepository


class AcquisitionError(ValueError):
    pass


class AcquisitionStateError(AcquisitionError):
    pass


class AcquisitionNotFoundError(AcquisitionError):
    pass


class AcquisitionQueueError(AcquisitionError):
    pass


class AcquisitionActiveJobError(AcquisitionStateError):
    pass


class AcquisitionRetryConflictError(AcquisitionStateError):
    pass


@dataclass(frozen=True)
class PromotionResult:
    candidate_id: str
    company_id: str
    lead_id: str
    created_company: bool
    created_lead: bool


@dataclass(frozen=True)
class AssessmentProvenance:
    provider: str
    model_id: str
    prompt_version: str


@dataclass(frozen=True)
class VerificationRetryResult:
    candidate_id: str
    mission_id: str


MIMO_PROVENANCE = AssessmentProvenance("mimo", "", MIMO_EXTRACT_PROMPT_VERSION)


def _session(app) -> Session:
    session = Session(get_engine(app))
    session.expire_on_commit = False
    return session


def _require_identity(tenant_id: str, actor_id: str) -> tuple[str, str]:
    tenant = (tenant_id or "").strip()
    actor = (actor_id or "").strip()
    if not tenant:
        raise AcquisitionError("tenant_id is required")
    if not actor:
        raise AcquisitionError("actor_id is required")
    return tenant, actor


def create_product_snapshot(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    product_name: str,
    summary: str,
    facts: list[dict[str, str]],
    prohibited_claims: list[str],
) -> ProductKnowledgeSnapshot:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    name = " ".join((product_name or "").split())
    clean_summary = " ".join((summary or "").split())
    clean_facts = [
        {
            str(key).strip(): " ".join(str(value).split())
            for key, value in fact.items()
            if str(key).strip() and str(value).strip()
        }
        for fact in facts
        if isinstance(fact, dict)
    ]
    clean_facts = [fact for fact in clean_facts if fact]
    if not name or not clean_summary or not clean_facts:
        raise AcquisitionError("product name, summary and facts are required")
    claims: list[str] = []
    seen_claims: set[str] = set()
    for claim in prohibited_claims:
        clean = " ".join(str(claim).split())
        if clean and clean.casefold() not in seen_claims:
            seen_claims.add(clean.casefold())
            claims.append(clean)

    content = {
        "product_name": name,
        "summary": clean_summary,
        "facts": clean_facts,
        "prohibited_claims": claims,
    }
    content_hash = hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()
    with _session(app) as session:
        existing = list(
            session.scalars(
                select(ProductKnowledgeSnapshot).where(
                    ProductKnowledgeSnapshot.tenant_id == tenant_id,
                    ProductKnowledgeSnapshot.product_name == name,
                )
            )
        )
        next_number = max((_version_number(item.version) for item in existing), default=0) + 1
        snapshot = ProductKnowledgeRepository(session).add(
            ProductKnowledgeSnapshot(
                version=f"v{next_number}",
                product_name=name,
                summary=clean_summary,
                source_revision=f"manual-v{next_number}",
                facts_json=canonical_json(clean_facts),
                prohibited_claims_json=canonical_json(claims),
                content_hash=content_hash,
                approved_by=actor_id,
            ),
            tenant_id=tenant_id,
        )
        session.commit()
        return snapshot


def create_mission(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    value: MissionCreateInput,
) -> AcquisitionMission:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    with _session(app) as session:
        product = ProductKnowledgeRepository(session).get(
            value.product_snapshot_id, tenant_id=tenant_id
        )
        if product is None:
            raise AcquisitionError("approved product snapshot was not found")
        countries = ", ".join(value.country_codes)
        mission = MissionRepository(session).add(
            AcquisitionMission(
                name=f"{product.product_name} — {countries}"[:200],
                status="draft",
                product_snapshot_id=product.id,
                target_profile_json=canonical_json(build_target_profile(value)),
                channel_policy_json=canonical_json(build_channel_policy(value)),
                budget_json=canonical_json(build_budget(value)),
                automation_level="research_only",
                created_by=actor_id,
            ),
            tenant_id=tenant_id,
        )
        session.commit()
        return mission


def process_manual_url(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    url: str,
    fetcher: StaticFetcher,
    extractor: CompanyExtractor,
) -> AcquisitionCandidate:
    tenant_id = (tenant_id or "").strip()
    if not tenant_id:
        raise AcquisitionError("tenant_id is required")
    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        _require_manual_url_active(mission)
        _require_manual_url_channel(mission)

    snapshot = fetcher.fetch(url)
    if snapshot.detected_prompt_injection:
        raise AcquisitionError("prompt injection detected in website evidence")
    facts = extractor.extract(snapshot)
    snapshots = (snapshot,)
    _validate_claim_sources(facts, snapshots)

    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        _require_manual_url_active(mission)
        _require_manual_url_channel(mission)
        candidate = _persist_url_candidate(
            session,
            app=app,
            tenant_id=tenant_id,
            mission=mission,
            facts=facts,
            snapshots=snapshots,
            provenance=MIMO_PROVENANCE,
        )
        session.commit()
        return candidate


def process_manual_facts(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    value: ManualCompanyFactsInput,
    fetcher: StaticFetcher,
) -> AcquisitionCandidate:
    tenant_id = (tenant_id or "").strip()
    if not tenant_id:
        raise AcquisitionError("tenant_id is required")
    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        _require_manual_url_active(mission)
        _require_manual_url_channel(mission)

    primary = fetcher.fetch(value.url)
    if primary.detected_prompt_injection:
        raise AcquisitionError("prompt injection detected in website evidence")

    contact_snapshot = None
    try:
        primary_domain = normalise_domain(primary.final_url)
        submitted_contact_url = contact_url(value.contact_path)
    except ManualEvidenceError as exc:
        raise AcquisitionError(
            "manual company facts are not supported by website evidence"
        ) from exc
    if not primary_domain:
        raise AcquisitionError("manual company facts are not supported by website evidence")
    if submitted_contact_url is not None:
        try:
            submitted_contact_domain = normalise_domain(submitted_contact_url)
            if not submitted_contact_domain or submitted_contact_domain != primary_domain:
                raise ManualEvidenceError("Contact URL must use the company domain")
        except ManualEvidenceError as exc:
            raise AcquisitionError(
                "manual company facts are not supported by website evidence"
            ) from exc
        contact_snapshot = fetcher.fetch(submitted_contact_url)
        if contact_snapshot.detected_prompt_injection:
            raise AcquisitionError("prompt injection detected in website evidence")
        try:
            if normalise_domain(contact_snapshot.final_url) != primary_domain:
                raise ManualEvidenceError("Contact URL redirected off the company domain")
        except ManualEvidenceError as exc:
            raise AcquisitionError(
                "manual company facts are not supported by website evidence"
            ) from exc

    try:
        facts = build_manual_company_facts(
            value,
            primary=primary,
            contact_snapshot=contact_snapshot,
        )
    except ManualEvidenceError as exc:
        raise AcquisitionError(
            "manual company facts are not supported by website evidence"
        ) from exc

    snapshots = (primary, contact_snapshot) if contact_snapshot is not None else (primary,)
    _validate_claim_sources(facts, snapshots)
    provenance = AssessmentProvenance(
        provider="manual",
        model_id="human-confirmed-v1",
        prompt_version=MANUAL_FACTS_PROMPT_VERSION,
    )
    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        _require_manual_url_active(mission)
        _require_manual_url_channel(mission)
        candidate = _persist_url_candidate(
            session,
            app=app,
            tenant_id=tenant_id,
            mission=mission,
            facts=facts,
            snapshots=snapshots,
            provenance=provenance,
        )
        session.commit()
        return candidate


def _persist_url_candidate(
    session: Session,
    *,
    app,
    tenant_id: str,
    mission: AcquisitionMission,
    facts: ExtractedCompanyFacts,
    snapshots: tuple[FetchResult, ...],
    provenance: AssessmentProvenance,
) -> AcquisitionCandidate:
    if not snapshots:
        raise AcquisitionError("website evidence is required")
    primary = snapshots[0]
    try:
        domain = normalise_domain(primary.final_url)
    except ManualEvidenceError as exc:
        raise AcquisitionError("company domain is required") from exc
    if not domain:
        raise AcquisitionError("company domain is required")
    _validate_claim_sources(facts, snapshots)

    candidates = CandidateRepository(session)
    candidate = candidates.find_by_dedupe_key(mission.id, f"domain:{domain}", tenant_id=tenant_id)
    if candidate is None:
        candidate = candidates.add(
            AcquisitionCandidate(
                mission_id=mission.id,
                status="verifying",
                source_channel="manual_url",
                source_provider="manual",
                dedupe_key=f"domain:{domain}",
            ),
            tenant_id=tenant_id,
        )
        session.flush()
    _apply_extracted_facts(
        candidate,
        facts,
        primary.final_url,
        domain=domain,
    )
    evidence = EvidenceRepository(session)
    for snapshot in snapshots:
        supported_claims = sorted(
            {
                claim.claim_id
                for claim in facts.observed_claims
                if _canonical_evidence_url(str(claim.source_url))
                == _canonical_evidence_url(snapshot.final_url)
            }
        )
        existing_evidence = evidence.find_content(
            candidate.id,
            snapshot.final_url,
            snapshot.content_hash,
            tenant_id=tenant_id,
        )
        if existing_evidence is not None:
            existing_supports = _validated_support_ids(existing_evidence.supports_json)
            existing_evidence.supports_json = canonical_json(
                sorted(existing_supports | set(supported_claims))
            )
            continue
        evidence.add(
            CandidateEvidence(
                candidate_id=candidate.id,
                provider="manual",
                source_type="manual_url",
                trust_tier="A",
                source_url=snapshot.requested_url,
                canonical_url=snapshot.final_url,
                title=snapshot.title[:500],
                excerpt=snapshot.text[:4000],
                retrieved_at=snapshot.retrieved_at,
                content_hash=snapshot.content_hash,
                supports_json=canonical_json(supported_claims),
                validation_status="valid",
            ),
            tenant_id=tenant_id,
        )
        session.flush()
    _assess_candidate_in_session(
        session,
        app=app,
        candidate=candidate,
        mission=mission,
        tenant_id=tenant_id,
        provenance=provenance,
    )
    return candidate


def _validate_claim_sources(
    facts: ExtractedCompanyFacts, snapshots: tuple[FetchResult, ...]
) -> None:
    supplied_urls = {_canonical_evidence_url(snapshot.final_url) for snapshot in snapshots}
    if any(
        _canonical_evidence_url(str(claim.source_url)) not in supplied_urls
        for claim in facts.observed_claims
    ):
        raise AcquisitionError("observed claim cites an unsupplied source URL")


def _canonical_evidence_url(value: str) -> str:
    return value.rstrip("/")


def _validated_support_ids(value: str) -> set[str]:
    try:
        supports = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        raise AcquisitionError("stored evidence support provenance is invalid") from None
    if not isinstance(supports, list) or any(
        not isinstance(item, str) or not item for item in supports
    ):
        raise AcquisitionError("stored evidence support provenance is invalid")
    return set(supports)


def _require_manual_url_channel(mission: AcquisitionMission) -> None:
    policy = _json_object(mission.channel_policy_json)
    allowed_channels = policy.get("allowed_channels", [])
    if not isinstance(allowed_channels, list) or "manual_url" not in allowed_channels:
        raise AcquisitionError("manual URL acquisition channel is not allowed")


def _require_manual_url_active(mission: AcquisitionMission) -> None:
    if mission.status == "cancelled":
        raise AcquisitionStateError("manual URL acquisition is unavailable for cancelled mission")


def review_candidate(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    candidate_id: str,
    action: str,
    reason_code: str,
    note: str,
) -> AcquisitionCandidate:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    try:
        decision = CandidateDecisionInput(action=action, reason_code=reason_code, note=note)
    except ValidationError as exc:
        raise AcquisitionError("candidate review input is invalid") from exc

    with _session(app) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionError("candidate was not found")
        now = datetime.now(UTC)
        if decision.action == "accept":
            if candidate.country_resolution_status in {
                "unknown",
                "conflicting",
            } or candidate.eligibility_code in {"country_unknown", "country_conflicting"}:
                raise AcquisitionError("country evidence must be resolved before accept")
            if candidate.status != "eligible":
                raise AcquisitionError("only eligible candidates can be accepted")
            candidate.status = "accepted"
            candidate.decision_reason_code = ""
            _audit_candidate(session, candidate, actor_id, "candidate.accepted")
            _promote_candidate_in_session(
                session,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate=candidate,
            )
        elif decision.action == "reject":
            if candidate.status not in {"eligible", "needs_evidence"}:
                raise AcquisitionError("candidate cannot be rejected from its current status")
            candidate.status = "rejected"
            candidate.decision_reason_code = decision.reason_code
            _audit_candidate(session, candidate, actor_id, "candidate.rejected")
        else:
            if candidate.status not in {"verifying", "eligible"}:
                raise AcquisitionError("candidate cannot request evidence from its current status")
            if not decision.reason_code:
                raise AcquisitionError("reason_code is required for needs_evidence")
            candidate.status = "needs_evidence"
            candidate.eligibility_code = decision.reason_code
            candidate.decision_reason_code = decision.reason_code
            _audit_candidate(session, candidate, actor_id, "candidate.needs_evidence")
        candidate.decision_note = decision.note
        candidate.decided_by = actor_id
        candidate.decided_at = now
        session.commit()
        return candidate


def retry_candidate_verification(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    candidate_id: str,
) -> VerificationRetryResult:
    """Queue one candidate retry and atomically claim its workflow state.

    The queue commit necessarily precedes the candidate transaction. If a concurrent
    decision wins, the newly created SQL Job is cancelled while still queued. If a
    worker already claimed it, the candidate transition still fails and human terminal
    state guards prevent later assessment from replacing that decision.
    """

    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    with _session(app) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionNotFoundError("candidate was not found")
        if candidate.status != "needs_evidence":
            raise AcquisitionStateError("candidate cannot be retried from its current status")
        if JobRepository(session).has_active_for_candidate(
            candidate_id,
            job_type="website_verify",
            tenant_id=tenant_id,
        ):
            raise AcquisitionActiveJobError("candidate verification is already active")
        mission_id = candidate.mission_id

    try:
        queued_job = create_and_enqueue(
            app,
            tenant_id=tenant_id,
            job_type="website_verify",
            payload={"candidate_id": candidate_id},
        )
    except JobServiceError as exc:
        raise AcquisitionQueueError("candidate verification could not be queued") from exc

    with _session(app) as session:
        jobs = JobRepository(session)
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            jobs.cancel_queued_for_tenant(queued_job.id, tenant_id=tenant_id)
            session.commit()
            raise AcquisitionNotFoundError("candidate mission was not found")
        transitioned = CandidateRepository(session).mark_verifying_if_needs_evidence(
            candidate_id,
            tenant_id=tenant_id,
        )
        if not transitioned:
            jobs.cancel_queued_for_tenant(queued_job.id, tenant_id=tenant_id)
            session.commit()
            raise AcquisitionRetryConflictError("candidate status changed before retry claim")

        now = datetime.now(UTC)
        notifications = NotificationRepository(session)
        for terminal_status in ("failed", "completed"):
            terminal_notification = notifications.find_by_dedupe_key(
                f"mission-terminal:{mission.id}:{terminal_status}",
                tenant_id=tenant_id,
            )
            if terminal_notification is not None:
                terminal_notification.status = "archived"
                terminal_notification.read_at = now
        if mission.status == "failed":
            mission.status = "running"
            mission.finished_at = None

        add_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="acquisition_candidate.verification_retried",
            target_type="acquisition_candidate",
            target_id=candidate_id,
            safe_summary="Candidate website verification retried",
        )
        session.commit()
    return VerificationRetryResult(candidate_id=candidate_id, mission_id=mission_id)


def bulk_review_candidates(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    candidate_ids: list[str],
    action: str,
    reason_code: str = "",
    note: str = "",
) -> list[AcquisitionCandidate]:
    """Review a bounded candidate set in one database transaction.

    Validation happens for the complete set before any row is changed.  This is
    especially important for bulk acceptance because promotion creates CRM rows;
    one ineligible candidate must leave the whole batch untouched.
    """

    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    unique_ids = list(dict.fromkeys(item.strip() for item in candidate_ids if item.strip()))
    limit = 20 if action == "accept" else 100
    if not unique_ids:
        raise AcquisitionError("at least one candidate is required")
    if len(unique_ids) > limit:
        raise AcquisitionError(f"bulk {action} is limited to {limit} candidates")
    try:
        decision = CandidateDecisionInput(
            action=action,
            reason_code=reason_code,
            note=note,
        )
    except ValidationError as exc:
        raise AcquisitionError("candidate review input is invalid") from exc
    if decision.action not in {"accept", "reject"}:
        raise AcquisitionError("bulk review supports accept or reject only")

    try:
        with _session(app) as session:
            rows = list(
                session.scalars(
                    select(AcquisitionCandidate).where(
                        AcquisitionCandidate.tenant_id == tenant_id,
                        AcquisitionCandidate.id.in_(unique_ids),
                    )
                )
            )
            by_id = {item.id: item for item in rows}
            if len(by_id) != len(unique_ids):
                raise AcquisitionError("one or more candidates were not found")
            candidates = [by_id[item_id] for item_id in unique_ids]

            if decision.action == "accept":
                invalid = [
                    item
                    for item in candidates
                    if item.status != "eligible"
                    or item.country_resolution_status != "confirmed"
                    or item.eligibility_code in {"country_unknown", "country_conflicting"}
                ]
                if invalid:
                    raise AcquisitionError(
                        "all candidates must be eligible with confirmed country evidence"
                    )
            else:
                invalid = [
                    item for item in candidates if item.status not in {"eligible", "needs_evidence"}
                ]
                if invalid:
                    raise AcquisitionError(
                        "all candidates must be reviewable before bulk rejection"
                    )

            now = datetime.now(UTC)
            for candidate in candidates:
                candidate.decision_note = decision.note
                candidate.decided_by = actor_id
                candidate.decided_at = now
                if decision.action == "accept":
                    candidate.status = "accepted"
                    candidate.decision_reason_code = ""
                    _audit_candidate(session, candidate, actor_id, "candidate.accepted")
                    _promote_candidate_in_session(
                        session,
                        tenant_id=tenant_id,
                        actor_id=actor_id,
                        candidate=candidate,
                    )
                else:
                    candidate.status = "rejected"
                    candidate.decision_reason_code = decision.reason_code
                    _audit_candidate(session, candidate, actor_id, "candidate.rejected")
            session.commit()
            return candidates
    except IntegrityError as exc:
        raise AcquisitionError("bulk candidate promotion conflicted; retry later") from exc


def promote_candidate(app, *, tenant_id: str, actor_id: str, candidate_id: str) -> PromotionResult:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    for attempt in range(2):
        try:
            with _session(app) as session:
                candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
                if candidate is None:
                    raise AcquisitionError("candidate was not found")
                result = _promote_candidate_in_session(
                    session,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    candidate=candidate,
                )
                session.commit()
                return result
        except IntegrityError:
            if attempt == 1:
                raise AcquisitionError("candidate promotion conflicted; retry later") from None
    raise AssertionError("unreachable")


def override_candidate_country(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    candidate_id: str,
    value: CountryEvidenceInput,
    fetcher: StaticFetcher,
) -> AcquisitionCandidate:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    allowed_states = {"country_unknown", "country_conflicting"}

    with _session(app) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionError("candidate was not found")
        if candidate.status != "needs_evidence" or candidate.eligibility_code not in allowed_states:
            raise AcquisitionStateError(
                "only country evidence candidates that need evidence can override country"
            )

    snapshot = fetcher.fetch(value.source_url)
    if snapshot.detected_prompt_injection:
        raise AcquisitionError("prompt injection detected in country evidence")
    try:
        evidence_text = require_supported_text(
            claim=value.evidence_text,
            page_text=snapshot.text,
        )
    except ManualEvidenceError as exc:
        raise AcquisitionError("country evidence is not supported by the fetched page") from exc

    with _session(app) as session:
        candidate = CandidateRepository(session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            raise AcquisitionError("candidate was not found")
        mission = MissionRepository(session).get(candidate.mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        result = session.execute(
            update(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.id == candidate_id,
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.status == "needs_evidence",
                AcquisitionCandidate.eligibility_code.in_(allowed_states),
            )
            .values(
                opportunity_country_code=value.country_code,
                country_resolution_status="confirmed",
                eligibility_code="country_confirmed",
                status="verifying",
                decision_reason_code="",
            ),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount != 1:
            raise AcquisitionStateError(
                "only country evidence candidates that need evidence can override country"
            )
        session.refresh(
            candidate,
            attribute_names=[
                "opportunity_country_code",
                "country_resolution_status",
                "eligibility_code",
                "status",
                "decision_reason_code",
            ],
        )
        evidence = EvidenceRepository(session)
        existing_evidence = evidence.find_content(
            candidate.id,
            snapshot.final_url,
            snapshot.content_hash,
            tenant_id=tenant_id,
        )
        if existing_evidence is None:
            evidence.add(
                CandidateEvidence(
                    candidate_id=candidate.id,
                    provider="manual",
                    source_type="country_evidence",
                    trust_tier="A",
                    source_url=snapshot.requested_url,
                    canonical_url=snapshot.final_url,
                    title=snapshot.title[:500],
                    excerpt=evidence_text[:4000],
                    retrieved_at=snapshot.retrieved_at,
                    content_hash=snapshot.content_hash,
                    supports_json=canonical_json(["country-evidence"]),
                    validation_status="valid",
                ),
                tenant_id=tenant_id,
            )
        else:
            existing_evidence.provider = "manual"
            existing_evidence.trust_tier = "A"
            existing_evidence.source_url = snapshot.requested_url
            existing_evidence.canonical_url = snapshot.final_url
            existing_evidence.title = snapshot.title[:500]
            existing_evidence.excerpt = evidence_text[:4000]
            existing_evidence.retrieved_at = snapshot.retrieved_at
            existing_evidence.validation_status = "valid"
            existing_evidence.supports_json = canonical_json(
                sorted(
                    _validated_support_ids(existing_evidence.supports_json) | {"country-evidence"}
                )
            )
        add_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="candidate.country_overridden",
            target_type="acquisition_candidate",
            target_id=candidate.id,
            safe_summary=f"Country set to {value.country_code}; reason={value.reason_code}",
        )
        _assess_candidate_in_session(
            session,
            app=app,
            candidate=candidate,
            mission=mission,
            tenant_id=tenant_id,
            provenance=AssessmentProvenance(
                "manual",
                "human-confirmed-v1",
                COUNTRY_EVIDENCE_PROMPT_VERSION,
            ),
        )
        session.commit()
        return candidate


def _promote_candidate_in_session(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str,
    candidate: AcquisitionCandidate,
) -> PromotionResult:
    if candidate.status not in {"eligible", "accepted", "promoted"}:
        raise AcquisitionError("candidate cannot be promoted from its current status")
    lead_repo = LeadRepository(session)
    company_repo = CompanyRepository(session)
    if candidate.promoted_lead_id:
        existing_lead = lead_repo.get(candidate.promoted_lead_id, tenant_id=tenant_id)
        if existing_lead is not None:
            return PromotionResult(
                candidate.id,
                existing_lead.company_id or "",
                existing_lead.id,
                False,
                False,
            )

    domain = _normalise_domain(candidate.domain or candidate.website)
    if not domain:
        raise AcquisitionError("candidate domain is required for promotion")
    company = company_repo.find_by_domain(domain, tenant_id=tenant_id)
    created_company = company is None
    if company is None:
        company = company_repo.add(
            Company(
                name=candidate.company_name,
                domain=domain,
                country_code=candidate.opportunity_country_code,
            ),
            tenant_id=tenant_id,
        )
        session.flush()

    email = _candidate_email(candidate)
    lead = (
        lead_repo.find_by_email(email, tenant_id=tenant_id)
        if email
        else lead_repo.find_by_acquisition_candidate_id(candidate.id, tenant_id=tenant_id)
    )
    created_lead = lead is None
    if lead is None:
        assessment = AssessmentRepository(session).latest_for_candidate(
            candidate.id, tenant_id=tenant_id
        )
        breakdown = _json_object(assessment.score_breakdown_json) if assessment else {}
        lead = lead_repo.add(
            Lead(
                company_id=company.id,
                email=email,
                website=candidate.website[:500],
                source="acquisition",
                status="accepted",
                stage="new",
                opportunity_country_code=candidate.opportunity_country_code,
                fit_score=breakdown.get("fit_score"),
                intent_score=breakdown.get("intent_score"),
                data_quality_score=breakdown.get("data_quality_score"),
                priority_score=candidate.priority_score,
                priority_band=candidate.priority_band,
                score_version=(assessment.score_version if assessment else PRIORITY_SCORE_VERSION),
                score_explanation_json=(
                    canonical_json(
                        {
                            "assessment_id": assessment.id,
                            "explanation": assessment.explanation,
                        }
                    )
                    if assessment
                    else "{}"
                ),
                acquisition_candidate_id=candidate.id,
            ),
            tenant_id=tenant_id,
        )
        session.flush()

    candidate.status = "promoted"
    candidate.promoted_lead_id = lead.id
    session.add(
        Activity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            action="accepted",
            description="Promoted from acquisition candidate",
            performed_by=actor_id,
            metadata_json=canonical_json({"candidate_id": candidate.id}),
        )
    )
    add_event(
        session,
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        action="candidate.promoted",
        target_type="acquisition_candidate",
        target_id=candidate.id,
        safe_summary="Candidate promoted to CRM lead",
    )
    session.flush()
    return PromotionResult(
        candidate.id,
        company.id,
        lead.id,
        created_company,
        created_lead,
    )


def summarize_feedback(app, *, tenant_id: str, mission_id: str) -> MissionSuggestion | None:
    tenant_id = (tenant_id or "").strip()
    if not tenant_id:
        raise AcquisitionError("tenant_id is required")
    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        candidates = list(
            CandidateRepository(session).list_for_mission(mission_id, tenant_id=tenant_id)
        )
        reviewed = [
            item
            for item in candidates
            if item.decided_at is not None or item.status in {"accepted", "promoted", "rejected"}
        ]
        reasons = Counter(
            item.decision_reason_code
            for item in reviewed
            if item.status == "rejected" and item.decision_reason_code
        )
        for reason, count in reasons.most_common():
            if count >= 5 or (reviewed and count / len(reviewed) >= 0.30):
                return _get_or_add_suggestion(
                    session,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    suggestion_type="add_exclusion",
                    reason_codes=[reason],
                    sample_size=count,
                    proposed_change={
                        "operation": "add_exclusion",
                        "reason_code": reason,
                    },
                )

        accepted_buyer_types = Counter()
        for item in reviewed:
            if item.status not in {"accepted", "promoted"}:
                continue
            buyer_type = str(_json_object(item.observed_facts_json).get("buyer_type", ""))
            if buyer_type:
                accepted_buyer_types[buyer_type] += 1
        for buyer_type, count in accepted_buyer_types.most_common():
            if count >= 10:
                return _get_or_add_suggestion(
                    session,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    suggestion_type="prefer_buyer_type",
                    reason_codes=[buyer_type],
                    sample_size=count,
                    proposed_change={
                        "operation": "prefer_buyer_type",
                        "buyer_type": buyer_type,
                    },
                )

        scored = [item for item in candidates if item.priority_score is not None]
        if len(scored) >= 30:
            return _get_or_add_suggestion(
                session,
                tenant_id=tenant_id,
                mission_id=mission_id,
                suggestion_type="score_weight_review",
                reason_codes=["review_outcomes_available"],
                sample_size=len(scored),
                proposed_change={"operation": "review_score_weights"},
            )
        return None


def _get_or_add_suggestion(
    session: Session,
    *,
    tenant_id: str,
    mission_id: str,
    suggestion_type: str,
    reason_codes: list[str],
    sample_size: int,
    proposed_change: dict[str, Any],
) -> MissionSuggestion:
    bucket = max(1, sample_size // 5)
    key = ":".join([mission_id, suggestion_type, ",".join(sorted(reason_codes)), str(bucket)])
    repo = SuggestionRepository(session)
    existing = repo.find_by_dedupe_key(key, tenant_id=tenant_id)
    if existing is not None:
        return existing
    suggestion = repo.add(
        MissionSuggestion(
            mission_id=mission_id,
            suggestion_type=suggestion_type,
            reason_codes_json=canonical_json(sorted(reason_codes)),
            sample_size=sample_size,
            proposed_change_json=canonical_json(proposed_change),
            status="proposed",
            dedupe_key=key,
        ),
        tenant_id=tenant_id,
    )
    session.commit()
    return suggestion


def apply_suggestion(app, *, tenant_id: str, actor_id: str, suggestion_id: str) -> str:
    tenant_id, actor_id = _require_identity(tenant_id, actor_id)
    with _session(app) as session:
        suggestion = session.scalar(
            select(MissionSuggestion).where(
                MissionSuggestion.id == suggestion_id,
                MissionSuggestion.tenant_id == tenant_id,
            )
        )
        if suggestion is None:
            raise AcquisitionError("suggestion was not found")
        if suggestion.status == "applied" and suggestion.applied_profile_version:
            return suggestion.applied_profile_version
        if suggestion.status != "proposed":
            raise AcquisitionError("suggestion cannot be applied from its current status")
        mission = MissionRepository(session).get(suggestion.mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        proposal = _json_object(suggestion.proposed_change_json)
        original_proposal = json.loads(canonical_json(proposal))
        next_profile = _json_object(mission.target_profile_json)
        operation = original_proposal.get("operation")
        if operation == "add_exclusion":
            reasons = list(next_profile.get("feedback_exclusion_reason_codes", []))
            reason = str(original_proposal.get("reason_code", ""))
            next_profile["feedback_exclusion_reason_codes"] = list(
                dict.fromkeys([*reasons, reason])
            )
        elif operation == "prefer_buyer_type":
            buyer_type = str(original_proposal.get("buyer_type", ""))
            buyers = [str(item) for item in next_profile.get("buyer_types", [])]
            next_profile["buyer_types"] = list(dict.fromkeys([buyer_type, *buyers]))
        elif operation == "review_score_weights":
            next_profile["score_weight_review_required"] = True
        version_payload = {
            "base_mission_id": mission.id,
            "base_target_profile": _json_object(mission.target_profile_json),
            "target_profile": next_profile,
            "proposed_change": original_proposal,
            "score_version": PRIORITY_SCORE_VERSION,
        }
        digest = hashlib.sha256(canonical_json(version_payload).encode("utf-8")).hexdigest()
        version = f"target-profile-{digest[:12]}"
        proposal["applied_version_json"] = version_payload
        suggestion.proposed_change_json = canonical_json(proposal)
        suggestion.applied_profile_version = version
        suggestion.status = "applied"
        add_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="mission.suggestion_applied",
            target_type="mission_suggestion",
            target_id=suggestion.id,
            safe_summary="Feedback suggestion applied as a new profile version",
        )
        session.commit()
        return version


def record_mission_cost(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    provider: str,
    requests: int = 0,
    tokens: int | None = None,
    pages: int | None = None,
    estimated_cost: float | None = None,
    duration_ms: int = 0,
) -> None:
    with _session(app) as session:
        mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            raise AcquisitionError("mission was not found")
        summary = _json_object(mission.cost_summary_json)
        providers = summary.setdefault("providers", {})
        current = providers.setdefault(
            provider,
            {
                "requests": 0,
                "tokens": None,
                "pages": None,
                "estimated_cost": None,
                "duration_ms": 0,
            },
        )
        current["requests"] += requests
        current["duration_ms"] += duration_ms
        current["tokens"] = _sum_optional(current.get("tokens"), tokens)
        current["pages"] = _sum_optional(current.get("pages"), pages)
        current["estimated_cost"] = _sum_optional(current.get("estimated_cost"), estimated_cost)
        mission.cost_summary_json = canonical_json(summary)
        session.commit()


def mission_retrospective_payload(
    result: BusinessResult,
    candidates: list[AcquisitionCandidate],
) -> dict[str, Any]:
    rejected = Counter(
        item.decision_reason_code or item.eligibility_code
        for item in candidates
        if item.status == "rejected"
    )
    return {
        "business_result": {
            "code": result.code,
            "label": result.label,
            "tone": result.tone,
            "action_code": result.action_code,
            "action_label": result.action_label,
            "summary": result.summary,
            "reason_codes": list(result.reason_codes),
            "counts": asdict(result.counts),
        },
        "discovered": result.counts.discovered,
        "eligible": result.counts.ready_to_review,
        "needs_evidence": result.counts.needs_review,
        "rejected": result.counts.excluded,
        "rejected_by_reason": dict(sorted(rejected.items())),
        "accepted": result.counts.crm_ready,
        "contactable": sum(bool(_candidate_email(item)) for item in candidates),
        "partial_failures": result.counts.failed_jobs,
        "partial_success": result.code == "partial",
        "candidate_count": result.counts.discovered,
    }


def _assess_candidate_in_session(
    session: Session,
    *,
    app,
    candidate: AcquisitionCandidate,
    mission: AcquisitionMission,
    tenant_id: str,
    provenance: AssessmentProvenance = MIMO_PROVENANCE,
) -> None:
    evidence = [
        item
        for item in EvidenceRepository(session).list_for_candidate(
            candidate.id, tenant_id=tenant_id
        )
    ]
    configured_model_id = str(app.config.get("MIMO_MODEL", "mimo-v2.5"))
    computation = compute_candidate_assessment(
        candidate,
        mission,
        evidence,
        mimo_model_id=configured_model_id,
    )
    if computation.extraction_complete:
        model_provider = provenance.provider
        model_id = provenance.model_id or configured_model_id
        prompt_version = provenance.prompt_version
    else:
        model_provider = computation.model_provider
        model_id = computation.model_id
        prompt_version = computation.prompt_version
    input_json = canonical_json(computation.score_input.__dict__)
    hard_gate_json = canonical_json(computation.gate.__dict__)
    score_breakdown_json = canonical_json(computation.score.__dict__)
    assessments = AssessmentRepository(session)
    existing_assessment = assessments.find_input_version(
        candidate.id,
        computation.evidence_bundle_hash,
        ELIGIBILITY_POLICY_VERSION,
        PRIORITY_SCORE_VERSION,
        prompt_version,
        model_id,
        tenant_id=tenant_id,
    )
    if existing_assessment is None:
        assessments.add(
            CandidateAssessment(
                candidate_id=candidate.id,
                evidence_bundle_hash=computation.evidence_bundle_hash,
                policy_version=ELIGIBILITY_POLICY_VERSION,
                score_version=PRIORITY_SCORE_VERSION,
                prompt_version=prompt_version,
                model_provider=model_provider,
                model_id=model_id,
                input_json=input_json,
                hard_gate_json=hard_gate_json,
                score_breakdown_json=score_breakdown_json,
                signal_coverage=computation.score.signal_coverage,
                priority_mode=computation.score.priority_mode,
                explanation=computation.explanation,
            ),
            tenant_id=tenant_id,
        )
    elif (
        existing_assessment.input_json != input_json
        or existing_assessment.hard_gate_json != hard_gate_json
        or existing_assessment.score_breakdown_json != score_breakdown_json
        or existing_assessment.signal_coverage != computation.score.signal_coverage
        or existing_assessment.priority_mode != computation.score.priority_mode
    ):
        raise AcquisitionError("assessment conflicts with existing evidence version")
    candidate.priority_score = computation.score.priority_score
    candidate.priority_band = computation.score.priority_band
    candidate.signal_coverage = computation.score.signal_coverage
    candidate.ai_confidence = computation.score.data_quality_score or 0
    update_assessment_state_if_mutable(
        session,
        candidate,
        tenant_id=tenant_id,
        status=computation.gate.disposition,
        eligibility_code=(
            computation.gate.reason_codes[0] if computation.gate.reason_codes else "eligible"
        ),
    )


def _apply_extracted_facts(
    candidate: AcquisitionCandidate,
    facts: ExtractedCompanyFacts,
    final_url: str,
    *,
    domain: str,
) -> None:
    candidate.company_name = facts.company_name
    candidate.domain = domain
    candidate.website = final_url
    candidate.hq_country_code = facts.hq_country_code
    candidate.opportunity_country_code = facts.opportunity_country_code
    candidate.country_resolution_status = (
        "confirmed" if facts.opportunity_country_code else "unknown"
    )
    emails = [path.removeprefix("mailto:") for path in facts.contact_paths if "@" in path]
    candidate.contact_json = canonical_json(
        {"paths": facts.contact_paths, "email": emails[0] if emails else ""}
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


def _audit_candidate(
    session: Session,
    candidate: AcquisitionCandidate,
    actor_id: str,
    action: str,
) -> None:
    add_event(
        session,
        tenant_id=candidate.tenant_id,
        actor_user_id=actor_id,
        action=action,
        target_type="acquisition_candidate",
        target_id=candidate.id,
        safe_summary=action.replace(".", " "),
    )


def _candidate_email(candidate: AcquisitionCandidate) -> str:
    contact = _json_object(candidate.contact_json)
    direct = str(contact.get("email", "")).strip().lower()
    if _looks_like_email(direct):
        return direct.removeprefix("mailto:")
    for value in contact.get("paths", []):
        candidate_value = str(value).strip().lower().removeprefix("mailto:")
        match = re.search(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+", candidate_value)
        if match:
            return match.group(0)
    return ""


def _looks_like_email(value: str) -> bool:
    return "@" in value and " " not in value


def _normalise_domain(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return ""
    labels = host.split(".")
    common_two_level_suffixes = {
        "co.uk",
        "com.au",
        "com.br",
        "com.cn",
        "com.co",
        "com.mx",
        "co.jp",
        "co.in",
    }
    if len(labels) >= 3 and ".".join(labels[-2:]) in common_two_level_suffixes:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _version_number(value: str) -> int:
    match = re.fullmatch(r"v(\d+)", value or "")
    return int(match.group(1)) if match else 0


def _sum_optional(current, added):
    if added is None:
        return current
    return (current or 0) + added
