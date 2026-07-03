from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.acquisition.basic_ai_search import build_search_links
from app.modules.ai.service import (
    generate_basic_search_strategy,
    generate_target_customer_candidates,
    generate_target_customer_plan,
    parse_pasted_search_results,
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
MAX_PASTED_RESULTS_LENGTH = 10_000


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


def generate_basic_search_strategy_for_collection(
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

    result = generate_basic_search_strategy(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        product_profile_json=product_profile_json,
        filters=filters,
        count=int(filters["result_count"]),
    )

    strategy = dict(result.strategy or {})
    if result.success:
        strategy["search_links"] = build_search_links(
            keywords=[str(item) for item in strategy.get("search_keywords", [])],
            country=str(filters.get("country", "")),
        )
        strategy["source_channel"] = "basic_ai_search"
        strategy["test_phase_free"] = True

    with Session(get_engine(app)) as session:
        run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=product_profile_id,
            filters_json=json.dumps(
                {**filters, "channel_key": "ai_basic_search"},
                ensure_ascii=False,
            ),
            generated_plan_json=json.dumps(strategy, ensure_ascii=False),
            status="planned" if result.success else "failed",
            requested_count=int(filters["result_count"]),
            generated_count=0,
            credits_estimated=0,
            credits_charged=0,
        )
        session.add(run)
        session.commit()
        return TargetDiscoveryResult(
            success=result.success,
            error_code=result.error_code,
            run_id=run.id,
        )


def parse_basic_search_results_for_collection(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    form,
) -> TargetDiscoveryResult:
    filters = filters_from_form(form)
    pasted_results = _limit(form.get("pasted_results", ""), MAX_PASTED_RESULTS_LENGTH)
    if not pasted_results:
        return TargetDiscoveryResult(success=False, error_code="missing_search_results")

    with Session(get_engine(app)) as session:
        run = _run_for_match(session, tenant_id=tenant_id, run_id=str(form.get("run_id", "") or ""))
        if run is None:
            return TargetDiscoveryResult(success=False, error_code="missing_target_plan")
        profile = session.get(TenantProductProfile, run.product_profile_id)
        if profile is None or profile.tenant_id != tenant_id or profile.status != "confirmed":
            return TargetDiscoveryResult(success=False, error_code="missing_product_profile")
        run_id = run.id
        product_profile_json = profile.extracted_profile_json
        strategy_json = run.generated_plan_json

    result = parse_pasted_search_results(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        product_profile_json=product_profile_json,
        strategy_json=strategy_json,
        pasted_results=pasted_results,
        filters=filters,
        count=int(filters["result_count"]),
    )

    with Session(get_engine(app)) as session:
        run = session.get(TargetCustomerDiscoveryRun, run_id)
        if run is None or run.tenant_id != tenant_id:
            return TargetDiscoveryResult(success=False, error_code="missing_target_plan")
        if result.success and result.candidates is not None:
            _clear_pending_candidates(session, tenant_id=tenant_id, run_id=run_id)
            saved = 0
            for candidate in result.candidates[: int(filters["result_count"])]:
                normalized = _normalize_basic_search_candidate(candidate, filters=filters)
                if _candidate_duplicate_exists(
                    session,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    data=normalized,
                ):
                    normalized["status"] = "duplicate"
                session.add(_candidate_from_ai(tenant_id=tenant_id, run_id=run_id, data=normalized))
                saved += 1
            run.status = "matched"
            run.generated_count = saved
            run.credits_charged = 0
            run.generated_plan_json = _mark_pasted_result_parse(
                run.generated_plan_json,
                pasted_length=len(pasted_results),
            )
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
    confidence_score = _int_in_range(data.get("confidence_score", 0), 0, 100)
    raw_data = {
        "suggested_next_action": _public_text(data.get("suggested_next_action", ""), 500),
        "unverified": True,
    }
    return TargetCustomerCandidate(
        tenant_id=tenant_id,
        run_id=run_id,
        company_name=_public_text(data.get("company_name", ""), 300),
        website=_public_text(data.get("website", ""), 500),
        country=_public_text(data.get("country", ""), 120),
        industry=_public_text(data.get("industry", ""), 120),
        buyer_type=_public_text(data.get("buyer_type", ""), 120),
        source_channel=_public_text(data.get("source_channel", ""), 80),
        match_reason=_public_text(data.get("match_reason", ""), 1000),
        confidence_score=confidence_score,
        raw_data_json=json.dumps(raw_data, ensure_ascii=False),
        status=str(data.get("status", "pending_review"))[:24] or "pending_review",
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


def _candidate_duplicate_exists(
    session: Session, *, tenant_id: str, run_id: str, data: dict[str, object]
) -> bool:
    domain = _domain_from_url(str(data.get("website", "")))
    company_name = _normalize_company_name(str(data.get("company_name", "")))
    if not domain and not company_name:
        return False
    candidates = session.scalars(
        select(TargetCustomerCandidate).where(
            TargetCustomerCandidate.tenant_id == tenant_id,
            TargetCustomerCandidate.run_id == run_id,
        )
    )
    for candidate in candidates:
        if domain and _domain_from_url(candidate.website) == domain:
            return True
        if company_name and _normalize_company_name(candidate.company_name) == company_name:
            return True
    if _find_duplicate(
        session,
        tenant_id=tenant_id,
        domain=domain,
        name=str(data.get("company_name", "")),
    ):
        return True
    return False


def _normalize_basic_search_candidate(
    data: dict[str, object], *, filters: dict[str, object]
) -> dict[str, object]:
    normalized = dict(data)
    normalized["source_channel"] = str(normalized.get("source_channel") or "pasted_search_results")[
        :80
    ]
    normalized["confidence_score"] = _score_candidate(normalized, filters=filters)
    normalized.setdefault("suggested_next_action", "Review before adding to CRM.")
    return normalized


def _score_candidate(data: dict[str, object], *, filters: dict[str, object]) -> int:
    score = _int_in_range(data.get("confidence_score", 65), 0, 100)
    website = str(data.get("website", "")).lower()
    combined = " ".join(
        str(data.get(key, ""))
        for key in (
            "company_name",
            "industry",
            "buyer_type",
            "match_reason",
            "suggested_next_action",
        )
    ).lower()
    if website and "." in website:
        score += 5
    for field in ("country", "buyer_type", "industry"):
        value = str(filters.get(field, "")).strip().lower()
        if value and value in combined:
            score += 5
    penalty_terms = ("supplier", "factory", "manufacturer", "job", "career", "blog", "news")
    if any(term in combined for term in penalty_terms):
        score -= 10
    return max(0, min(score, 100))


def _mark_pasted_result_parse(plan_json_text: str, *, pasted_length: int) -> str:
    try:
        parsed = json.loads(plan_json_text or "{}")
        data = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        data = {}
    data["pasted_results_parsed"] = True
    data["pasted_results_length"] = pasted_length
    return json.dumps(data, ensure_ascii=False)


def _domain_from_url(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""
    parsed = urlsplit(clean if "://" in clean else f"https://{clean}")
    return parsed.netloc.lower()[:253]


def _normalize_company_name(value: str) -> str:
    return " ".join((value or "").lower().strip().split())


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


def _public_text(value: object, max_length: int) -> str:
    clean = str(value or "").strip()
    clean = clean.replace("\r", " ").replace("\n", " ")
    clean = " ".join(clean.split())
    # Search-result parsing must not persist private contact-like fields.
    import re

    clean = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "", clean)
    clean = re.sub(r"(?:\+?\d[\d\s().-]{7,}\d)", "", clean)
    return clean[:max_length].strip()
