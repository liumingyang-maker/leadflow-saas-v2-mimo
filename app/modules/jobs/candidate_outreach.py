from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.ai.service import generate_candidate_outreach_draft
from app.modules.jobs.target_discovery import raw_candidate_data
from app.modules.jobs.target_models import (
    CandidateOutreachDraft,
    CandidateResearchReport,
    TargetCustomerCandidate,
)
from app.modules.onboarding.models import TenantProductProfile


@dataclass(frozen=True)
class CandidateOutreachContext:
    latest_draft: CandidateOutreachDraft | None
    draft_view: dict[str, object]


@dataclass(frozen=True)
class CandidateOutreachActionResult:
    success: bool
    error_code: str = ""
    draft_id: str = ""


def candidate_outreach_context(
    app: Flask, *, tenant_id: str, candidate_id: str
) -> CandidateOutreachContext:
    with Session(get_engine(app)) as session:
        draft = _latest_draft(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            status="completed",
        )
        return CandidateOutreachContext(latest_draft=draft, draft_view=draft_view(draft))


def generate_candidate_outreach_draft_for_candidate(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    candidate_id: str,
    locale: str,
) -> CandidateOutreachActionResult:
    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return CandidateOutreachActionResult(
                success=False,
                error_code="candidate_not_found",
            )
        report = _latest_completed_report(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
        )
        if report is None:
            return CandidateOutreachActionResult(
                success=False,
                error_code="missing_research_report",
            )
        existing = _latest_draft(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            status="completed",
        )
        if existing is not None:
            return CandidateOutreachActionResult(success=True, draft_id=existing.id)
        profile = _confirmed_product_profile(session, tenant_id=tenant_id)
        product_profile_json = profile.extracted_profile_json if profile is not None else "{}"
        candidate_context = _candidate_context(candidate)
        report_context = _research_report_context(report)
        sources = _safe_sources(report.sources_json)

    ai_result = generate_candidate_outreach_draft(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        candidate_context_json=json.dumps(candidate_context, ensure_ascii=False, sort_keys=True),
        research_report_json=json.dumps(report_context, ensure_ascii=False, sort_keys=True),
        product_profile_json=product_profile_json,
        sources_json=json.dumps(sources, ensure_ascii=False, sort_keys=True),
        language="en",
        tone="professional_concise",
    )

    with Session(get_engine(app)) as session:
        candidate = session.get(TargetCustomerCandidate, candidate_id)
        if candidate is None or candidate.tenant_id != tenant_id:
            return CandidateOutreachActionResult(
                success=False,
                error_code="candidate_not_found",
            )
        report = _latest_completed_report(
            session,
            tenant_id=tenant_id,
            candidate_id=candidate_id,
        )
        if report is None:
            return CandidateOutreachActionResult(
                success=False,
                error_code="missing_research_report",
            )
        if ai_result.success and ai_result.draft is not None:
            draft = _completed_draft(
                tenant_id=tenant_id,
                candidate_id=candidate.id,
                report_id=report.id,
                data=ai_result.draft,
                sources=_safe_sources(report.sources_json),
                provider=ai_result.provider,
                model=ai_result.model,
                ledger_id=ai_result.ledger_id,
            )
            session.add(draft)
            session.commit()
            return CandidateOutreachActionResult(success=True, draft_id=draft.id)

        draft = CandidateOutreachDraft(
            tenant_id=tenant_id,
            candidate_id=candidate.id,
            research_report_id=report.id,
            status="failed",
            provider=ai_result.provider,
            ai_model=ai_result.model,
            language="en",
            tone="professional_concise",
            ai_usage_ledger_id=ai_result.ledger_id or None,
            error_code=(ai_result.error_code or "provider_error")[:80],
        )
        session.add(draft)
        session.commit()
        return CandidateOutreachActionResult(
            success=False,
            error_code=ai_result.error_code or "provider_error",
            draft_id=draft.id,
        )


def draft_view(draft: CandidateOutreachDraft | None) -> dict[str, object]:
    if draft is None:
        return {}
    return {
        "personalization_notes": _json_list(draft.personalization_notes_json),
        "sources": _json_list(draft.sources_json),
    }


def _completed_draft(
    *,
    tenant_id: str,
    candidate_id: str,
    report_id: str,
    data: dict[str, object],
    sources: list[dict[str, str]],
    provider: str,
    model: str,
    ledger_id: str,
) -> CandidateOutreachDraft:
    return CandidateOutreachDraft(
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        research_report_id=report_id,
        status="completed",
        provider=provider,
        ai_model=model,
        language="en",
        tone="professional_concise",
        subject=_public_text(data.get("subject", ""), 500),
        body=_public_text(data.get("body", ""), 5000),
        short_body=_public_text(data.get("short_body", ""), 1500),
        follow_up_angle=_public_text(data.get("follow_up_angle", ""), 1000),
        personalization_notes_json=json.dumps(
            _string_list(data.get("personalization_notes")),
            ensure_ascii=False,
        ),
        sources_json=json.dumps(sources, ensure_ascii=False),
        confidence_note=_public_text(data.get("confidence_note", ""), 1000),
        disclaimer=_public_text(
            data.get("disclaimer", "Draft only. Not sent. Please verify before sending."),
            500,
        )
        or "Draft only. Not sent. Please verify before sending.",
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
        "unverified": True,
    }


def _research_report_context(report: CandidateResearchReport) -> dict[str, object]:
    return {
        "summary": _public_text(report.summary, 1500),
        "why_potential_buyer": _public_text(report.why_potential_buyer, 1500),
        "buyer_type": _public_text(report.buyer_type, 120),
        "product_fit": _public_text(report.product_fit, 1500),
        "fit_score": _score(report.fit_score),
        "confidence_score": _score(report.confidence_score),
        "buyer_signals": _list_of_dicts(report.buyer_signals_json),
        "risk_signals": _list_of_dicts(report.risk_signals_json),
        "suggested_next_action": _public_text(report.suggested_next_action, 1000),
        "suggested_outreach_angle": _public_text(report.suggested_outreach_angle, 1000),
        "sources": _safe_sources(report.sources_json),
        "unverified": True,
    }


def _latest_completed_report(
    session: Session, *, tenant_id: str, candidate_id: str
) -> CandidateResearchReport | None:
    return session.scalar(
        select(CandidateResearchReport)
        .where(
            CandidateResearchReport.tenant_id == tenant_id,
            CandidateResearchReport.candidate_id == candidate_id,
            CandidateResearchReport.status == "completed",
        )
        .order_by(CandidateResearchReport.created_at.desc())
    )


def _latest_draft(
    session: Session, *, tenant_id: str, candidate_id: str, status: str = ""
) -> CandidateOutreachDraft | None:
    query = select(CandidateOutreachDraft).where(
        CandidateOutreachDraft.tenant_id == tenant_id,
        CandidateOutreachDraft.candidate_id == candidate_id,
    )
    if status:
        query = query.where(CandidateOutreachDraft.status == status)
    return session.scalar(query.order_by(CandidateOutreachDraft.created_at.desc()))


def _confirmed_product_profile(session: Session, *, tenant_id: str) -> TenantProductProfile | None:
    return session.scalar(
        select(TenantProductProfile).where(
            TenantProductProfile.tenant_id == tenant_id,
            TenantProductProfile.status == "confirmed",
        )
    )


def _safe_sources(value: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _json_list(value)[:8]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": _public_text(item.get("title", "Candidate source"), 200),
                "url": _public_text(item.get("url", ""), 500),
                "source_provider": _public_text(
                    item.get("source_provider", item.get("source", "candidate_metadata")),
                    80,
                )
                or "candidate_metadata",
                "snippet": _public_text(item.get("snippet", ""), 500),
            }
        )
    return [row for row in rows if row.get("title") or row.get("url")]


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


def _list_of_dicts(value: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in _json_list(value)[:8]:
        if not isinstance(item, dict):
            text = _public_text(item, 300)
            if text:
                rows.append({"signal": text, "source": "candidate_metadata"})
            continue
        row = {
            str(key)[:40]: _public_text(val, 300)
            for key, val in item.items()
            if _public_text(val, 300)
        }
        if row:
            rows.append(row)
    return rows


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
    clean = _remove_forbidden_claims(clean)
    return clean[:max_length].strip()


def _remove_forbidden_claims(value: str) -> str:
    clean = value
    replacements = (
        ("verified buyer", "potential buyer"),
        ("verified importer", "potential importer"),
        ("confirmed contact", "possible contact"),
        ("confirmed contact person", "possible contact person"),
        ("current purchase intent", "possible product interest"),
        ("currently buying", "may be reviewing suppliers"),
    )
    for bad, safe in replacements:
        clean = re.sub(re.escape(bad), safe, clean, flags=re.IGNORECASE)
    return clean
