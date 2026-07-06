from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.acquisition.basic_ai_search import build_search_links
from app.integrations.acquisition.search_api.base import SearchProviderError, SearchResult
from app.integrations.acquisition.search_api.brave import BraveSearchProvider
from app.integrations.acquisition.search_api.fake import FakeSearchProvider
from app.modules.acquisition.service import (
    acquisition_provider_secret,
    advanced_search_queries_used_today,
    daily_query_limit,
    get_acquisition_settings,
)
from app.modules.ai.ledger import record_ai_usage
from app.modules.ai.quota import summarize_quota
from app.modules.ai.service import (
    generate_basic_search_strategy,
    generate_search_intent_query_matrix,
    generate_target_customer_candidates,
    generate_target_customer_plan,
    get_provider_settings,
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
ADVANCED_WEB_SEARCH_FEATURE = "advanced_web_search"
SEARCH_INTENT_QUERY_MATRIX_CHANNEL = "search_intent_query_matrix"
SEARCH_INTENT_QUERY_MATRIX_PROMPT_VERSION = "alpha13a_v2_product_specific"
ADVANCED_SEARCH_NEGATIVE_KEYWORDS = (
    "manufacturer",
    "factory",
    "supplier",
    "producer",
    "oem manufacturer",
    "wholesale supplier",
    "made in china",
    "alibaba",
    "temu",
    "amazon",
    "ebay",
    "blog",
    "article",
    "news",
    "directory",
    "marketplace",
    "b2b directory",
    "europages",
    "ensun",
)
ADVANCED_SEARCH_STRONG_NEGATIVE_TERMS = (
    "manufacturer",
    "factory",
    "supplier",
    "producer",
    "marketplace",
    "directory",
    "blog",
    "news",
    "article",
)
ADVANCED_SEARCH_POSITIVE_TERMS = (
    "importer",
    "distributor",
    "reseller",
    "retailer",
    "brand",
    "procurement",
    "sourcing",
    "purchasing",
    "buyer",
    "private label",
    "wholesale buyer",
)
ADVANCED_SEARCH_NOISE_DOMAINS = (
    "europages.",
    "ensun.io",
    "alibaba.",
    "made-in-china.",
    "amazon.",
    "ebay.",
    "temu.",
    "pinterest.",
    "wikipedia.",
    "youtube.",
    "facebook.",
    "linkedin.",
    "medium.",
    "blogspot.",
    "wordpress.",
)
COUNTRY_QUERY_FALLBACKS = {
    "ae": "UAE",
    "uae": "UAE",
    "united arab emirates": "UAE",
}


@dataclass(frozen=True)
class TargetDiscoveryContext:
    product_profile: TenantProductProfile | None
    product_profile_summary: dict[str, object]
    product_profile_hash: str
    product_family: str
    latest_run: TargetCustomerDiscoveryRun | None
    latest_search_intent_run: TargetCustomerDiscoveryRun | None
    stale_search_intent_available: bool
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
        recent_runs = list(
            session.scalars(
                select(TargetCustomerDiscoveryRun)
                .where(TargetCustomerDiscoveryRun.tenant_id == tenant_id)
                .order_by(TargetCustomerDiscoveryRun.created_at.desc())
                .limit(20)
            )
        )
        product_profile_hash = (
            build_product_profile_fingerprint(product_profile)
            if product_profile is not None
            else ""
        )
        latest_search_intent_run = _latest_search_intent_run_for_profile(
            recent_runs,
            product_profile_hash=product_profile_hash,
        )
        stale_search_intent_available = (
            product_profile is not None
            and latest_search_intent_run is None
            and _latest_run_for_channel(
                recent_runs,
                channel_key=SEARCH_INTENT_QUERY_MATRIX_CHANNEL,
            )
            is not None
        )
        latest_run = _latest_non_search_intent_run(recent_runs)
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
            product_profile_hash=product_profile_hash,
            product_family=_detect_product_family_from_profile(product_profile),
            latest_run=latest_run,
            latest_search_intent_run=latest_search_intent_run,
            stale_search_intent_available=stale_search_intent_available,
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


def generate_search_intent_query_matrix_for_collection(
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
        product_profile_hash = build_product_profile_fingerprint(profile)
        product_family = _detect_product_family_from_profile(profile)

    result = generate_search_intent_query_matrix(
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
        product_context_check = strategy.get("product_context_check")
        detected_family = ""
        if isinstance(product_context_check, dict):
            detected_family = str(product_context_check.get("detected_product_family", "") or "")
        strategy["metadata"] = {
            "feature": SEARCH_INTENT_QUERY_MATRIX_CHANNEL,
            "prompt_version": SEARCH_INTENT_QUERY_MATRIX_PROMPT_VERSION,
            "product_profile_id": product_profile_id,
            "product_profile_hash": product_profile_hash,
            "product_family": product_family,
            "detected_product_family": detected_family or product_family,
            "generated_at": datetime.now(UTC).isoformat(),
        }
        strategy["source_channel"] = SEARCH_INTENT_QUERY_MATRIX_CHANNEL
        strategy["test_phase_free"] = True
        strategy["safety_notes"] = [
            "这些搜索词不是已验证客户，只是获客线索搜索建议。",
            "系统不会自动爬网页。",
            "系统不会自动发送邮件。",
            "不会生成或保存私人邮箱/手机号。",
        ]

    with Session(get_engine(app)) as session:
        run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=product_profile_id,
            filters_json=json.dumps(
                {**filters, "channel_key": SEARCH_INTENT_QUERY_MATRIX_CHANNEL},
                ensure_ascii=False,
            ),
            generated_plan_json=json.dumps(strategy, ensure_ascii=False),
            status="planned" if result.success else "failed",
            requested_count=int(filters["result_count"]),
            generated_count=0,
            credits_estimated=1,
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


def run_advanced_web_search_for_collection(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    form,
) -> TargetDiscoveryResult:
    del locale
    filters = filters_from_form(form)
    settings = get_acquisition_settings(app)
    ai_settings = get_provider_settings(app)
    if not ai_settings.enabled or ai_settings.provider == "disabled":
        _record_advanced_search_ledger(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            provider=settings.provider,
            status="disabled",
            error_code="ai_disabled",
        )
        return TargetDiscoveryResult(success=False, error_code="ai_disabled")
    with Session(get_engine(app)) as session:
        profile = _confirmed_product_profile(session, tenant_id=tenant_id)
        if profile is None:
            return TargetDiscoveryResult(success=False, error_code="missing_product_profile")
        quota = summarize_quota(session, tenant_id=tenant_id)
        if not quota.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=ADVANCED_WEB_SEARCH_FEATURE,
                provider=settings.provider,
                model="acquisition_search",
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return TargetDiscoveryResult(success=False, error_code="tenant_ai_disabled")
        product_profile_id = profile.id
        product_profile_summary = parse_profile_json(profile.extracted_profile_json)

    if not settings.enabled or settings.provider == "disabled":
        _record_advanced_search_ledger(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            provider=settings.provider,
            status="disabled",
            error_code="acquisition_provider_disabled",
        )
        return TargetDiscoveryResult(success=False, error_code="acquisition_provider_disabled")
    if settings.provider == "brave" and not settings.configured:
        _record_advanced_search_ledger(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            provider=settings.provider,
            status="disabled",
            error_code="acquisition_provider_unconfigured",
        )
        return TargetDiscoveryResult(success=False, error_code="acquisition_provider_unconfigured")

    query_limit = min(int(settings.query_limit_per_run), 3)
    result_count = min(int(filters["result_count"]), int(settings.result_limit_per_run), 10)
    if advanced_search_queries_used_today(app) + query_limit > daily_query_limit(settings):
        _record_advanced_search_ledger(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            provider=settings.provider,
            status="blocked_quota",
            error_code="daily_spend_cap_reached",
        )
        return TargetDiscoveryResult(success=False, error_code="daily_spend_cap_reached")

    queries = _advanced_search_queries(
        product_profile_summary,
        filters=filters,
        limit=query_limit,
    )
    provider = _advanced_search_provider(app, settings_provider=settings.provider)
    try:
        search_results: list[SearchResult] = []
        per_query_limit = max(1, min(result_count, 10))
        executed_queries: list[str] = []
        fallback_used = False
        for query in queries:
            if len(executed_queries) >= query_limit:
                break
            provider_results = provider.search(
                query,
                country=str(filters.get("country", "")) or None,
                language="en",
                limit=per_query_limit,
            )
            search_results.extend(provider_results)
            executed_queries.append(query)
            if not provider_results and not fallback_used and len(executed_queries) < query_limit:
                fallback_query = _country_fallback_query(
                    query,
                    country=str(filters.get("country", "")),
                )
                if fallback_query:
                    search_results.extend(
                        provider.search(
                            fallback_query,
                            country=None,
                            language="en",
                            limit=per_query_limit,
                        )
                    )
                    executed_queries.append(fallback_query)
                    fallback_used = True
    except SearchProviderError as exc:
        _record_advanced_search_ledger(
            app,
            tenant_id=tenant_id,
            user_id=user_id,
            provider=settings.provider,
            status="failed",
            error_code=exc.code,
        )
        return TargetDiscoveryResult(success=False, error_code=exc.code)

    with Session(get_engine(app)) as session:
        run = TargetCustomerDiscoveryRun(
            tenant_id=tenant_id,
            product_profile_id=product_profile_id,
            filters_json=json.dumps(
                {
                    **filters,
                    "channel_key": "advanced_web_search",
                    "provider": settings.provider,
                    "query_count": len(executed_queries),
                    "fallback_used": fallback_used,
                },
                ensure_ascii=False,
            ),
            generated_plan_json=json.dumps(
                {
                    "source_channel": "advanced_web_search",
                    "source_provider": settings.provider,
                    "queries": executed_queries,
                    "query_count": len(executed_queries),
                    "fallback_used": fallback_used,
                    "requested_count": result_count,
                    "credits_estimated": 0,
                    "credits_charged": 0,
                    "test_phase_free": True,
                },
                ensure_ascii=False,
            ),
            status="matched",
            requested_count=result_count,
            generated_count=0,
            credits_estimated=0,
            credits_charged=0,
        )
        session.add(run)
        session.flush()
        saved = 0
        duplicates = 0
        invalid = 0
        for result in search_results:
            if saved >= result_count:
                break
            candidate_data = _candidate_from_search_result(result, filters=filters)
            if _is_filtered_advanced_search_candidate(candidate_data):
                invalid += 1
                continue
            if not candidate_data.get("company_name") and not candidate_data.get("website"):
                invalid += 1
                continue
            if _candidate_duplicate_exists(
                session,
                tenant_id=tenant_id,
                run_id=run.id,
                data=candidate_data,
            ):
                duplicates += 1
                continue
            session.add(_candidate_from_ai(tenant_id=tenant_id, run_id=run.id, data=candidate_data))
            saved += 1
        run.generated_count = saved
        run.generated_plan_json = _add_advanced_search_summary(
            run.generated_plan_json,
            generated_count=saved,
            duplicate_count=duplicates,
            invalid_count=invalid,
        )
        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=ADVANCED_WEB_SEARCH_FEATURE,
            provider=settings.provider,
            model="acquisition_search",
            credits_charged=0,
            input_tokens=0,
            output_tokens=0,
            status="success",
        )
        session.commit()
        return TargetDiscoveryResult(success=True, run_id=run.id)


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


def build_product_profile_fingerprint(product_profile: TenantProductProfile) -> str:
    summary = parse_profile_json(product_profile.extracted_profile_json)
    payload = {
        "id": product_profile.id,
        "version": product_profile.version,
        "products": summary.get("product_keywords_en", []),
        "product_keywords_cn": summary.get("product_keywords_cn", []),
        "product_categories": summary.get("product_categories", []),
        "target_markets": summary.get("target_countries", []),
        "advantages": summary.get("selling_points_en", []),
        "raw_products": (product_profile.raw_products or "")[:1000],
        "raw_company_intro": (product_profile.raw_company_intro or "")[:1000],
        "raw_target_markets": (product_profile.raw_target_markets or "")[:500],
        "updated_at": product_profile.updated_at.isoformat()
        if product_profile.updated_at is not None
        else "",
    }
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _latest_search_intent_run_for_profile(
    runs: list[TargetCustomerDiscoveryRun],
    *,
    product_profile_hash: str,
) -> TargetCustomerDiscoveryRun | None:
    if not product_profile_hash:
        return None
    for run in runs:
        if _run_channel(run) != SEARCH_INTENT_QUERY_MATRIX_CHANNEL:
            continue
        data = plan_json(run)
        metadata = data.get("metadata")
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("product_profile_hash", "") or "") == product_profile_hash:
            return run
    return None


def _latest_run_for_channel(
    runs: list[TargetCustomerDiscoveryRun], *, channel_key: str
) -> TargetCustomerDiscoveryRun | None:
    for run in runs:
        if _run_channel(run) == channel_key:
            return run
    return None


def _latest_non_search_intent_run(
    runs: list[TargetCustomerDiscoveryRun],
) -> TargetCustomerDiscoveryRun | None:
    for run in runs:
        if _run_channel(run) != SEARCH_INTENT_QUERY_MATRIX_CHANNEL:
            return run
    return None


def _run_channel(run: TargetCustomerDiscoveryRun) -> str:
    try:
        filters = json.loads(run.filters_json or "{}")
    except json.JSONDecodeError:
        return ""
    if not isinstance(filters, dict):
        return ""
    return str(filters.get("channel_key", "") or "")


def _confirmed_product_profile(session: Session, *, tenant_id: str) -> TenantProductProfile | None:
    return session.scalar(
        select(TenantProductProfile).where(
            TenantProductProfile.tenant_id == tenant_id,
            TenantProductProfile.status == "confirmed",
        )
    )


def _detect_product_family_from_profile(product_profile: TenantProductProfile | None) -> str:
    if product_profile is None:
        return "unknown"
    summary = parse_profile_json(product_profile.extracted_profile_json)
    text = json.dumps(
        {
            "summary": summary,
            "raw_products": product_profile.raw_products,
            "raw_company_intro": product_profile.raw_company_intro,
            "raw_target_markets": product_profile.raw_target_markets,
        },
        ensure_ascii=False,
    ).lower()
    packaging_terms = (
        "packaging",
        "package",
        "bag",
        "bags",
        "mailer",
        "kraft",
        "compostable",
        "cosmetic packaging",
        "food packaging",
    )
    led_terms = (
        "led",
        "lighting",
        "lamp",
        "fixture",
        "electrical wholesaler",
        "decorative lighting",
        "commercial led",
    )
    packaging_score = sum(1 for term in packaging_terms if term in text)
    led_score = sum(1 for term in led_terms if term in text)
    if packaging_score and led_score:
        if packaging_score > led_score:
            return "packaging"
        if led_score > packaging_score:
            return "led_lighting"
        return "mixed"
    if packaging_score:
        return "packaging"
    if led_score:
        return "led_lighting"
    return "unknown"


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
    extra_raw = data.get("raw_data")
    if isinstance(extra_raw, dict):
        for key in ("source_provider", "rank", "domain"):
            if key in extra_raw:
                raw_data[key] = _public_text(extra_raw.get(key, ""), 120)
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


def _advanced_search_provider(app: Flask, *, settings_provider: str):
    if settings_provider == "fake":
        return FakeSearchProvider()
    if settings_provider == "brave":
        settings = get_acquisition_settings(app)
        return BraveSearchProvider(
            api_key=acquisition_provider_secret(app),
            timeout_seconds=settings.timeout_seconds,
        )
    raise SearchProviderError("unsupported_provider")


def _advanced_search_queries(
    product_profile: dict[str, object],
    *,
    filters: dict[str, object],
    limit: int,
) -> list[str]:
    keywords = _list_values(product_profile.get("product_keywords_en")) or _list_values(
        product_profile.get("search_keywords")
    )
    buyer_types = _list_values(product_profile.get("buyer_types")) or ["importer", "distributor"]
    country = str(filters.get("country", "") or "").strip()
    filtered_buyer = str(filters.get("buyer_type", "") or "").strip()
    base_keyword = keywords[0] if keywords else "product"
    profile_terms: list[str] = []
    for key in ("product_keywords_en", "product_categories", "target_industries", "buyer_types"):
        profile_terms.extend(_list_values(product_profile.get(key)))
    profile_text = " ".join(profile_terms).lower()
    is_hardware_oem = any(
        term in profile_text
        for term in ("hardware", "metal", "fitting", "component", "oem", "industrial")
    )
    buyers = [filtered_buyer] if filtered_buyer else buyer_types
    queries: list[str] = []
    if country:
        queries.append(f"{base_keyword} buyer {country}")
        queries.append(f"{base_keyword} import company {country}")
    for buyer in buyers:
        normalized_buyer = buyer.lower()
        if any(term in normalized_buyer for term in ("manufacturer", "factory", "supplier")):
            continue
        if normalized_buyer in {"distributor", "wholesaler"}:
            queries.append(f"{base_keyword} {normalized_buyer} company")
        elif normalized_buyer:
            queries.append(f"{base_keyword} {normalized_buyer} list")
    if is_hardware_oem:
        queries.extend(
            [
                f"{base_keyword} procurement company",
                f"{base_keyword} industrial distributor",
                f"{base_keyword} sourcing company",
                f"{base_keyword} parts buyer",
                f"{base_keyword} assembly company",
                f"{base_keyword} maintenance supplies buyer",
            ]
        )
    else:
        queries.extend(
            [
                f"{base_keyword} importer list",
                f"{base_keyword} wholesale buyer",
                f"{base_keyword} purchasing company",
                f"{base_keyword} sourcing company",
                f"{base_keyword} private label brand",
                f"{base_keyword} distributor company",
                f"{base_keyword} retail chain",
                f"{base_keyword} B2B buyer",
                f"{base_keyword} procurement company",
                f"{base_keyword} supplier wanted",
            ]
        )
    negative_suffix = "-manufacturer -factory -supplier -alibaba -amazon -ebay"
    deduped: list[str] = []
    for query in queries:
        clean = " ".join(f"{query} {negative_suffix}".split())[:180]
        if clean and clean not in deduped:
            deduped.append(clean)
    return deduped[: max(1, min(limit, 3))]


def _candidate_from_search_result(
    result: SearchResult, *, filters: dict[str, object]
) -> dict[str, object]:
    domain = _domain_from_url(result.url)
    company_name = _company_from_title_or_domain(result.title, domain)
    country = str(filters.get("country", "") or result.country or "")
    industry = str(filters.get("industry", "") or "")
    buyer_type = str(filters.get("buyer_type", "") or "")
    combined = f"{result.title} {result.snippet} {result.url}"
    quality_flags = _advanced_search_quality_flags(combined=combined, domain=domain)
    data = {
        "company_name": company_name,
        "website": result.url,
        "country": country,
        "industry": industry,
        "buyer_type": buyer_type,
        "source_channel": "advanced_web_search",
        "match_reason": _public_text(
            f"Search result matched the advanced web search query. {result.snippet}",
            1000,
        ),
        "confidence_score": _score_advanced_search_candidate(
            {
                "company_name": company_name,
                "website": result.url,
                "country": country,
                "industry": industry,
                "buyer_type": buyer_type,
                "match_reason": result.snippet,
                "quality_flags": quality_flags,
            },
            filters=filters,
        ),
        "suggested_next_action": "Review the website before adding outreach context.",
        "raw_data": {
            "source_provider": result.source_provider,
            "rank": result.rank,
            "domain": domain,
            "quality_flags": ",".join(quality_flags),
            "unverified": True,
        },
    }
    return data


def _add_advanced_search_summary(
    plan_json_text: str,
    *,
    generated_count: int,
    duplicate_count: int,
    invalid_count: int,
) -> str:
    try:
        parsed = json.loads(plan_json_text or "{}")
        data = parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        data = {}
    data["generated_count"] = generated_count
    data["duplicate_count"] = duplicate_count
    data["invalid_count"] = invalid_count
    return json.dumps(data, ensure_ascii=False)


def _record_advanced_search_ledger(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    provider: str,
    status: str,
    error_code: str = "",
) -> None:
    with Session(get_engine(app)) as session:
        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=ADVANCED_WEB_SEARCH_FEATURE,
            provider=provider,
            model="acquisition_search",
            credits_charged=0,
            input_tokens=0,
            output_tokens=0,
            status=status,
            error_code=error_code,
        )
        session.commit()


def _score_candidate(data: dict[str, object], *, filters: dict[str, object]) -> int:
    score = _int_in_range(data.get("confidence_score", 65), 0, 100)
    website = str(data.get("website", "")).lower()
    combined = _strip_negated_search_terms(
        " ".join(
            str(data.get(key, ""))
            for key in (
                "company_name",
                "industry",
                "buyer_type",
                "match_reason",
                "suggested_next_action",
            )
        ).lower()
    )
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


def _score_advanced_search_candidate(data: dict[str, object], *, filters: dict[str, object]) -> int:
    score = _int_in_range(data.get("confidence_score", 60), 0, 100)
    website = str(data.get("website", "")).lower()
    domain = _domain_from_url(website)
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
    flags = data.get("quality_flags", [])
    if isinstance(flags, list):
        quality_flags = {str(flag) for flag in flags}
    else:
        quality_flags = set()

    if website and "." in website and not _is_noise_domain(domain):
        score += 12
    if any(term in combined for term in ADVANCED_SEARCH_POSITIVE_TERMS):
        score += 18
    if "official_company_site" in quality_flags:
        score += 10
    for field in ("country", "buyer_type", "industry"):
        value = str(filters.get(field, "")).strip().lower()
        if value and value in combined:
            score += 6

    strong_negative_hits = sum(
        1 for term in ADVANCED_SEARCH_STRONG_NEGATIVE_TERMS if term in combined
    )
    score -= strong_negative_hits * 18
    if "noise_domain" in quality_flags:
        score -= 55
    if "marketplace_or_directory" in quality_flags:
        score -= 35
    if "supplier_like" in quality_flags:
        score -= 30
    if not website or "." not in website:
        score -= 25
    country_filter = str(filters.get("country", "")).strip().lower()
    country_value = str(data.get("country", "")).strip().lower()
    if country_filter and country_value and country_filter != country_value:
        score -= 10
    return max(0, min(score, 100))


def _advanced_search_quality_flags(*, combined: str, domain: str) -> list[str]:
    text = _strip_negated_search_terms(combined.lower())
    flags: list[str] = []
    if _is_noise_domain(domain):
        flags.append("noise_domain")
    if any(term in text for term in ("directory", "marketplace", "europages", "ensun")):
        flags.append("marketplace_or_directory")
    if any(term in text for term in ("manufacturer", "factory", "supplier", "producer")):
        flags.append("supplier_like")
    if any(term in text for term in ADVANCED_SEARCH_POSITIVE_TERMS):
        flags.append("buyer_like")
    if domain and not _is_noise_domain(domain):
        flags.append("official_company_site")
    return flags


def _is_filtered_advanced_search_candidate(data: dict[str, object]) -> bool:
    domain = _domain_from_url(str(data.get("website", "")))
    if _is_noise_domain(domain):
        return True
    score = _int_in_range(data.get("confidence_score", 0), 0, 100)
    raw_data = data.get("raw_data")
    flags = ""
    if isinstance(raw_data, dict):
        flags = str(raw_data.get("quality_flags", ""))
    if score <= 15 and any(
        flag in flags for flag in ("marketplace_or_directory", "supplier_like", "noise_domain")
    ):
        return True
    if score <= 35 and "supplier_like" in flags:
        return True
    return False


def _is_noise_domain(domain: str) -> bool:
    clean = domain.lower()
    if clean.startswith("www."):
        clean = clean[4:]
    return any(pattern.replace("*", "") in clean for pattern in ADVANCED_SEARCH_NOISE_DOMAINS)


def _country_fallback_query(query: str, *, country: str) -> str:
    clean_country = country.strip().lower()
    fallback_name = COUNTRY_QUERY_FALLBACKS.get(clean_country, "")
    if not fallback_name:
        return ""
    if fallback_name.lower() in query.lower():
        return ""
    return " ".join(f"{query} {fallback_name}".split())[:180]


def _strip_negated_search_terms(value: str) -> str:
    text = value
    for term in ADVANCED_SEARCH_NEGATIVE_KEYWORDS:
        normalized = term.lower().replace(" ", r"\s+")
        # Avoid penalizing candidates because our own query contained negative operators.
        import re

        text = re.sub(rf"-{normalized}", "", text)
    return text


def _list_values(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _company_from_title_or_domain(title: str, domain: str) -> str:
    clean_title = _public_text(title, 160)
    for separator in (" - ", " | ", " – ", ":"):
        if separator in clean_title:
            clean_title = clean_title.split(separator, 1)[0].strip()
    if clean_title:
        return clean_title[:160]
    if domain:
        root = domain.split(".")[0].replace("-", " ").title()
        return root[:160]
    return ""


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
