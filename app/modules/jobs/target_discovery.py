from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.ai.service import (
    generate_target_customer_candidates,
    generate_target_customer_plan,
)
from app.modules.jobs.target_models import (
    TargetCustomerCandidate,
    TargetCustomerDiscoveryRun,
)
from app.modules.leads.models import Activity, Company, Lead
from app.modules.onboarding.models import TenantProductProfile
from app.modules.onboarding.service import parse_profile_json

DEFAULT_MATCH_COUNT = 10
MAX_MATCH_COUNT = 25


@dataclass(frozen=True)
class TargetDiscoveryContext:
    product_profile: TenantProductProfile | None
    product_profile_summary: dict[str, object]
    latest_run: TargetCustomerDiscoveryRun | None
    candidates: list[TargetCustomerCandidate]


@dataclass(frozen=True)
class TargetDiscoveryResult:
    success: bool
    error_code: str = ""
    run_id: str = ""


@dataclass(frozen=True)
class AddCandidateResult:
    success: bool
    error_code: str = ""
    lead_id: str = ""


def collection_target_context(app: Flask, *, tenant_id: str) -> TargetDiscoveryContext:
    with Session(get_engine(app)) as session:
        product_profile = _confirmed_product_profile(session, tenant_id=tenant_id)
        latest_run = session.scalar(
            select(TargetCustomerDiscoveryRun)
            .where(TargetCustomerDiscoveryRun.tenant_id == tenant_id)
            .order_by(TargetCustomerDiscoveryRun.created_at.desc())
        )
        candidates: list[TargetCustomerCandidate] = []
        if latest_run is not None:
            candidates = list(
                session.scalars(
                    select(TargetCustomerCandidate)
                    .where(
                        TargetCustomerCandidate.tenant_id == tenant_id,
                        TargetCustomerCandidate.run_id == latest_run.id,
                    )
                    .order_by(TargetCustomerCandidate.created_at)
                )
            )
        summary = (
            parse_profile_json(product_profile.extracted_profile_json)
            if product_profile is not None
            else {}
        )
        return TargetDiscoveryContext(
            product_profile=product_profile,
            product_profile_summary=summary,
            latest_run=latest_run,
            candidates=candidates,
        )


def generate_collection_target_plan(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    form,
) -> TargetDiscoveryResult:
    filters = filters_from_form(form)
    with Session(get_engine(app)) as session:
        profile = _confirmed_product_profile(session, tenant_id=tenant_id)
        if profile is None:
            return TargetDiscoveryResult(success=False, error_code="missing_product_profile")
        product_profile_id = profile.id
        product_profile_json = profile.extracted_profile_json

    result = generate_target_customer_plan(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        product_profile_json=product_profile_json,
    )

    with Session(get_engine(app)) as session:
        run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=product_profile_id,
            filters_json=json.dumps(filters, ensure_ascii=False),
            generated_plan_json=json.dumps(result.plan or {}, ensure_ascii=False),
            status="planned" if result.success else "failed",
            requested_count=int(filters["result_count"]),
            generated_count=0,
            credits_estimated=int(filters["result_count"]),
            credits_charged=0,
        )
        session.add(run)
        session.commit()
        return TargetDiscoveryResult(
            success=result.success,
            error_code=result.error_code,
            run_id=run.id,
        )


def match_collection_target_candidates(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    form,
) -> TargetDiscoveryResult:
    filters = filters_from_form(form)
    with Session(get_engine(app)) as session:
        run = _run_for_match(session, tenant_id=tenant_id, run_id=str(form.get("run_id", "") or ""))
        if run is None:
            return TargetDiscoveryResult(success=False, error_code="missing_target_plan")
        profile = session.get(TenantProductProfile, run.product_profile_id)
        if profile is None or profile.tenant_id != tenant_id or profile.status != "confirmed":
            return TargetDiscoveryResult(success=False, error_code="missing_product_profile")
        run_id = run.id
        product_profile_json = profile.extracted_profile_json
        target_plan_json = run.generated_plan_json

    result = generate_target_customer_candidates(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        product_profile_json=product_profile_json,
        target_plan_json=target_plan_json,
        filters=filters,
        count=int(filters["result_count"]),
    )

    with Session(get_engine(app)) as session:
        run = session.get(TargetCustomerDiscoveryRun, run_id)
        if run is None or run.tenant_id != tenant_id:
            return TargetDiscoveryResult(success=False, error_code="missing_target_plan")
        if result.success and result.candidates is not None:
            _clear_pending_candidates(session, tenant_id=tenant_id, run_id=run_id)
            for candidate in result.candidates[: int(filters["result_count"])]:
                session.add(_candidate_from_ai(tenant_id=tenant_id, run_id=run_id, data=candidate))
            run.status = "matched"
            run.generated_count = min(len(result.candidates), int(filters["result_count"]))
            run.credits_charged = 0
        else:
            run.status = "failed"
            run.generated_count = 0
        session.commit()
        return TargetDiscoveryResult(
            success=result.success,
            error_code=result.error_code,
            run_id=run_id,
        )


def add_candidate_to_crm(
    app: Flask, *, tenant_id: str, user_id: str, candidate_id: str
) -> AddCandidateResult:
    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return AddCandidateResult(success=False, error_code="candidate_not_found")
        if candidate.status == "added_to_crm" and candidate.added_lead_id:
            return AddCandidateResult(success=True, lead_id=candidate.added_lead_id)

        domain = _domain_from_url(candidate.website)
        duplicate = _find_duplicate(
            session,
            tenant_id=tenant_id,
            domain=domain,
            name=candidate.company_name,
        )
        if duplicate is not None:
            candidate.status = "duplicate"
            session.commit()
            return AddCandidateResult(success=False, error_code="duplicate_candidate")

        company = Company(
            tenant_id=tenant_id,
            name=candidate.company_name[:300],
            domain=domain or f"candidate-{candidate.id}",
            industry=candidate.industry[:120],
            country=candidate.country[:120],
            notes=_company_notes(candidate),
        )
        lead = Lead(
            tenant_id=tenant_id,
            company=company,
            website=candidate.website[:500],
            industry=candidate.industry[:120],
            source="collection",
            status="pending_review",
            stage="new",
            confidence_score=max(0, min(candidate.confidence_score, 100)),
            notes=_lead_notes(candidate),
        )
        session.add(lead)
        session.flush()
        session.add(
            Activity(
                tenant_id=tenant_id,
                lead_id=lead.id,
                action="created",
                description="Added from AI target customer candidate",
                metadata_json=json.dumps(
                    {"candidate_id": candidate.id, "run_id": candidate.run_id},
                    ensure_ascii=False,
                ),
                performed_by=user_id,
            )
        )
        candidate.status = "added_to_crm"
        candidate.added_lead_id = lead.id
        session.commit()
        return AddCandidateResult(success=True, lead_id=lead.id)


def filters_from_form(form) -> dict[str, object]:
    result_count = _int_in_range(form.get("result_count", DEFAULT_MATCH_COUNT), 1, MAX_MATCH_COUNT)
    return {
        "country": _limit(form.get("country", ""), 120),
        "buyer_type": _limit(form.get("buyer_type", ""), 120),
        "industry": _limit(form.get("industry", ""), 120),
        "result_count": result_count,
    }


def plan_json(run: TargetCustomerDiscoveryRun | None) -> dict[str, object]:
    if run is None:
        return {}
    try:
        data = json.loads(run.generated_plan_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def raw_candidate_data(candidate: TargetCustomerCandidate) -> dict[str, object]:
    try:
        data = json.loads(candidate.raw_data_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _confirmed_product_profile(session: Session, *, tenant_id: str) -> TenantProductProfile | None:
    return session.scalar(
        select(TenantProductProfile).where(
            TenantProductProfile.tenant_id == tenant_id,
            TenantProductProfile.status == "confirmed",
        )
    )


def _run_for_match(
    session: Session, *, tenant_id: str, run_id: str
) -> TargetCustomerDiscoveryRun | None:
    if run_id:
        run = session.get(TargetCustomerDiscoveryRun, run_id)
        if run is not None and run.tenant_id == tenant_id:
            return run
        return None
    return session.scalar(
        select(TargetCustomerDiscoveryRun)
        .where(
            TargetCustomerDiscoveryRun.tenant_id == tenant_id,
            TargetCustomerDiscoveryRun.status.in_(("planned", "matched")),
        )
        .order_by(TargetCustomerDiscoveryRun.created_at.desc())
    )


def _candidate_from_ai(
    *, tenant_id: str, run_id: str, data: dict[str, object]
) -> TargetCustomerCandidate:
    raw_data = {"suggested_next_action": str(data.get("suggested_next_action", ""))[:500]}
    return TargetCustomerCandidate(
        tenant_id=tenant_id,
        run_id=run_id,
        company_name=str(data.get("company_name", ""))[:300],
        website=str(data.get("website", ""))[:500],
        country=str(data.get("country", ""))[:120],
        industry=str(data.get("industry", ""))[:120],
        buyer_type=str(data.get("buyer_type", ""))[:120],
        source_channel=str(data.get("source_channel", ""))[:80],
        match_reason=str(data.get("match_reason", ""))[:1000],
        confidence_score=int(data.get("confidence_score", 0) or 0),
        raw_data_json=json.dumps(raw_data, ensure_ascii=False),
        status="pending_review",
    )


def _clear_pending_candidates(session: Session, *, tenant_id: str, run_id: str) -> None:
    candidates = session.scalars(
        select(TargetCustomerCandidate).where(
            TargetCustomerCandidate.tenant_id == tenant_id,
            TargetCustomerCandidate.run_id == run_id,
            TargetCustomerCandidate.status == "pending_review",
        )
    )
    for candidate in candidates:
        session.delete(candidate)


def _find_duplicate(session: Session, *, tenant_id: str, domain: str, name: str) -> Lead | None:
    query = select(Lead).where(Lead.tenant_id == tenant_id)
    if domain:
        query = query.join(Company).where(Company.domain == domain)
    else:
        query = query.join(Company).where(Company.name == name)
    return session.scalar(query)


def _domain_from_url(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""
    parsed = urlsplit(clean if "://" in clean else f"https://{clean}")
    return parsed.netloc.lower()[:253]


def _company_notes(candidate: TargetCustomerCandidate) -> str:
    return (
        f"Source: {candidate.source_channel}\n"
        f"Buyer type: {candidate.buyer_type}\n"
        f"Match reason: {candidate.match_reason}"
    )[:2000]


def _lead_notes(candidate: TargetCustomerCandidate) -> str:
    extra = raw_candidate_data(candidate)
    next_action = str(extra.get("suggested_next_action", ""))
    return (
        f"AI target discovery candidate\n"
        f"Run: {candidate.run_id}\n"
        f"Candidate: {candidate.id}\n"
        f"Source: {candidate.source_channel}\n"
        f"Buyer type: {candidate.buyer_type}\n"
        f"Match reason: {candidate.match_reason}\n"
        f"Suggested next action: {next_action}"
    )[:4000]


def _int_in_range(value: object, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value or DEFAULT_MATCH_COUNT)
    except (TypeError, ValueError):
        parsed = DEFAULT_MATCH_COUNT
    return max(minimum, min(parsed, maximum))


def _limit(value: object, max_length: int) -> str:
    return str(value or "").strip()[:max_length]
