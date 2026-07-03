from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.ai.service import generate_candidate_company_research
from app.modules.jobs.target_discovery import raw_candidate_data
from app.modules.jobs.target_models import CandidateResearchReport, TargetCustomerCandidate
from app.modules.onboarding.models import TenantProductProfile


@dataclass(frozen=True)
class CandidateResearchContext:
    candidate: TargetCustomerCandidate
    latest_report: CandidateResearchReport | None
    candidate_extra: dict[str, object]
    candidate_view: dict[str, object]
    report_view: dict[str, object]


@dataclass(frozen=True)
class CandidateResearchActionResult:
    success: bool
    error_code: str = ""
    report_id: str = ""


def candidate_research_context(
    app: Flask, *, tenant_id: str, candidate_id: str
) -> CandidateResearchContext | None:
    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return None
        latest_report = _latest_report(session, tenant_id=tenant_id, candidate_id=candidate_id)
        return CandidateResearchContext(
            candidate=candidate,
            latest_report=latest_report,
            candidate_extra=raw_candidate_data(candidate),
            candidate_view=_candidate_context(candidate),
            report_view=report_view(latest_report),
        )


def generate_candidate_research_report(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    candidate_id: str,
    locale: str,
) -> CandidateResearchActionResult:
    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return CandidateResearchActionResult(success=False, error_code="candidate_not_found")
        existing = _latest_report(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            status="completed",
        )
        if existing is not None:
            return CandidateResearchActionResult(success=True, report_id=existing.id)
        profile = _confirmed_product_profile(session, tenant_id=tenant_id)
        product_profile_json = profile.extracted_profile_json if profile is not None else "{}"
        candidate_context = _candidate_context(candidate)
        sources = _candidate_sources(candidate)
        domain = _domain_from_url(candidate.website)

    ai_result = generate_candidate_company_research(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        candidate_context_json=json.dumps(candidate_context, ensure_ascii=False, sort_keys=True),
        product_profile_json=product_profile_json,
    )

    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return CandidateResearchActionResult(success=False, error_code="candidate_not_found")
        if ai_result.success and ai_result.report is not None:
            report = _completed_report(
                tenant_id=tenant_id,
                candidate=candidate,
                data=ai_result.report,
                sources=sources,
                domain=domain,
                provider=ai_result.provider,
                model=ai_result.model,
                ledger_id=ai_result.ledger_id,
            )
            session.add(report)
            session.commit()
            return CandidateResearchActionResult(success=True, report_id=report.id)

        report = CandidateResearchReport(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            status="failed",
            provider=ai_result.provider,
            search_provider="none",
            company_name=_public_text(candidate.company_name, 300),
            company_domain=domain,
            country=_public_text(candidate.country, 120),
            buyer_type=_public_text(candidate.buyer_type, 120),
            ai_model=ai_result.model,
            ai_usage_ledger_id=ai_result.ledger_id or None,
            error_code=(ai_result.error_code or "provider_error")[:80],
        )
        session.add(report)
        session.commit()
        return CandidateResearchActionResult(
            success=False,
            error_code=ai_result.error_code or "provider_error",
            report_id=report.id,
        )


def report_view(report: CandidateResearchReport | None) -> dict[str, object]:
    if report is None:
        return {}
    return {
        "possible_use_cases": _json_list(report.possible_use_cases_json),
        "buyer_signals": _json_list(report.buyer_signals_json),
        "risk_signals": _json_list(report.risk_signals_json),
        "sources": _json_list(report.sources_json),
    }


def _completed_report(
    *,
    tenant_id: str,
    candidate: TargetCustomerCandidate,
    data: dict[str, object],
    sources: list[dict[str, str]],
    domain: str,
    provider: str,
    model: str,
    ledger_id: str,
) -> CandidateResearchReport:
    confidence = _score(data.get("confidence_score"))
    risk_signals = _list_of_dicts(data.get("risk_signals"))
    if not domain:
        confidence = min(confidence, 45)
        risk_signals.append(
            {
                "risk": "该候选缺少官网，背调结果可信度较低。",
                "source": "candidate_metadata",
                "confidence": "medium",
            }
        )
    return CandidateResearchReport(
        tenant_id=tenant_id,
        candidate_id=candidate.id,
        status="completed",
        provider=provider,
        search_provider=_search_provider(candidate),
        company_name=_public_text(candidate.company_name, 300),
        company_domain=domain,
        country=_public_text(candidate.country or str(data.get("country_region", "")), 120),
        buyer_type=_public_text(candidate.buyer_type or str(data.get("buyer_type", "")), 120),
        fit_score=_score(data.get("fit_score")),
        confidence_score=confidence,
        summary=_public_text(data.get("summary", ""), 1500),
        why_potential_buyer=_public_text(data.get("why_potential_buyer", ""), 1500),
        product_fit=_public_text(data.get("product_fit", ""), 1500),
        possible_use_cases_json=json.dumps(
            _string_list(data.get("possible_use_cases")),
            ensure_ascii=False,
        ),
        buyer_signals_json=json.dumps(
            _list_of_dicts(data.get("positive_signals")),
            ensure_ascii=False,
        ),
        risk_signals_json=json.dumps(risk_signals, ensure_ascii=False),
        suggested_next_action=_public_text(data.get("suggested_next_action", ""), 1000),
        suggested_outreach_angle=_public_text(data.get("suggested_outreach_angle", ""), 1000),
        sources_json=json.dumps(sources, ensure_ascii=False),
        ai_model=model,
        ai_usage_ledger_id=ledger_id or None,
        error_code="",
    )


def _candidate_context(candidate: TargetCustomerCandidate) -> dict[str, object]:
    extra = raw_candidate_data(candidate)
    return {
        "company_name": _public_text(candidate.company_name, 300),
        "website": _public_text(candidate.website, 500),
        "domain": _domain_from_url(candidate.website),
        "country": _public_text(candidate.country, 120),
        "industry": _public_text(candidate.industry, 120),
        "buyer_type": _public_text(candidate.buyer_type, 120),
        "source_channel": _public_text(candidate.source_channel, 80),
        "source_provider": _public_text(extra.get("source_provider", ""), 80),
        "match_reason": _public_text(candidate.match_reason, 1000),
        "confidence_score": _score(candidate.confidence_score),
        "source_snippet": _public_text(candidate.match_reason, 700),
        "unverified": True,
    }


def _candidate_sources(candidate: TargetCustomerCandidate) -> list[dict[str, str]]:
    extra = raw_candidate_data(candidate)
    url = _public_text(candidate.website, 500)
    source_provider = _public_text(extra.get("source_provider", candidate.source_channel), 80)
    source = {
        "title": _public_text(candidate.company_name or "Candidate source", 200),
        "url": url,
        "snippet": _public_text(candidate.match_reason, 500),
        "source_provider": source_provider or "candidate_metadata",
    }
    return [source]


def _latest_report(
    session: Session, *, tenant_id: str, candidate_id: str, status: str = ""
) -> CandidateResearchReport | None:
    query = select(CandidateResearchReport).where(
        CandidateResearchReport.tenant_id == tenant_id,
        CandidateResearchReport.candidate_id == candidate_id,
    )
    if status:
        query = query.where(CandidateResearchReport.status == status)
    return session.scalar(query.order_by(CandidateResearchReport.created_at.desc()))


def _confirmed_product_profile(session: Session, *, tenant_id: str) -> TenantProductProfile | None:
    return session.scalar(
        select(TenantProductProfile).where(
            TenantProductProfile.tenant_id == tenant_id,
            TenantProductProfile.status == "confirmed",
        )
    )


def _search_provider(candidate: TargetCustomerCandidate) -> str:
    extra = raw_candidate_data(candidate)
    provider = str(extra.get("source_provider", "") or "").lower()
    if provider in {"brave", "fake"}:
        return provider
    return "none"


def _json_list(value: str) -> list[object]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [_public_text(item, 300) for item in value[:8] if _public_text(item, 300)]


def _list_of_dicts(value: object) -> list[dict[str, str]]:
    if isinstance(value, str):
        value = [{"signal": value, "source": "candidate_metadata", "confidence": "medium"}]
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:8]:
        if isinstance(item, dict):
            rows.append(
                {
                    str(key)[:40]: _public_text(val, 300)
                    for key, val in item.items()
                    if _public_text(val, 300)
                }
            )
        else:
            rows.append(
                {
                    "signal": _public_text(item, 300),
                    "source": "candidate_metadata",
                    "confidence": "medium",
                }
            )
    return [row for row in rows if row]


def _domain_from_url(value: str) -> str:
    clean = (value or "").strip()
    if not clean:
        return ""
    parsed = urlsplit(clean if "://" in clean else f"https://{clean}")
    domain = (parsed.netloc or parsed.path).split("/")[0].lower()
    return domain.removeprefix("www.")[:255]


def _score(value: object) -> int:
    try:
        score = int(value or 0)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(score, 100))


def _public_text(value: object, max_length: int) -> str:
    clean = str(value or "").strip()
    clean = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "", clean)
    clean = re.sub(r"(?:\+?\d[\d\s().-]{7,}\d)", "", clean)
    return clean[:max_length].strip()
