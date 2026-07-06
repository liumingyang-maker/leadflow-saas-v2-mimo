from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_crypto import SecretCryptoError, decrypt_secret, encrypt_secret, last4
from app.extensions import get_engine
from app.integrations.ai.base import AIGenerationRequest, AIProvider
from app.integrations.ai.disabled import DisabledProvider
from app.integrations.ai.fake import FakeAIProvider
from app.integrations.ai.openai_compatible import OpenAICompatibleProvider
from app.integrations.ai.prompts import (
    build_basic_search_strategy_prompt,
    build_candidate_company_research_prompt,
    build_candidate_outreach_draft_prompt,
    build_outreach_draft_prompt,
    build_pasted_search_results_prompt,
    build_product_profile_extraction_prompt,
    build_search_intent_query_matrix_prompt,
    build_search_result_paste_parser_v2_prompt,
    build_target_customer_candidate_prompt,
    build_target_customer_plan_prompt,
)
from app.modules.accounts.models import Tenant
from app.modules.ai.ledger import record_ai_usage, usage_summary
from app.modules.ai.models import AIProviderSettings
from app.modules.ai.quota import (
    DEFAULT_DISABLED_CREDITS,
    save_tenant_quota,
    summarize_quota,
)
from app.modules.leads.models import Lead

OUTREACH_DRAFT_FEATURE = "outreach_draft"
OUTREACH_DRAFT_CREDITS = 5
PRODUCT_PROFILE_EXTRACTION_FEATURE = "product_profile_extraction"
PRODUCT_PROFILE_EXTRACTION_CREDITS = 0
PRODUCT_PROFILE_ARRAY_FIELDS = (
    "product_keywords_cn",
    "product_keywords_en",
    "product_categories",
    "selling_points_cn",
    "selling_points_en",
    "target_industries",
    "buyer_types",
    "target_countries",
    "search_keywords",
    "negative_keywords",
    "outreach_angles",
    "certificates",
)
PRODUCT_PROFILE_TEXT_FIELDS = (
    "suggested_email_tone",
    "product_summary_en",
    "moq_summary",
    "delivery_capacity",
    "factory_type",
    "ideal_buyer_profile",
    "oem_odm_capability",
    "price_positioning",
)
TARGET_CUSTOMER_PLAN_FEATURE = "target_customer_plan_generation"
TARGET_CUSTOMER_MATCH_FEATURE = "target_customer_candidate_matching"
TARGET_CUSTOMER_PLAN_CREDITS = 0
TARGET_CUSTOMER_MATCH_CREDITS = 0
BASIC_SEARCH_STRATEGY_FEATURE = "basic_search_strategy_generation"
SEARCH_INTENT_QUERY_MATRIX_FEATURE = "search_intent_query_matrix"
SEARCH_RESULT_PASTE_PARSER_V2_FEATURE = "search_result_paste_parser_v2"
PASTED_SEARCH_PARSE_FEATURE = "pasted_search_result_parsing"
CANDIDATE_FIT_SCORING_FEATURE = "candidate_fit_scoring"
BASIC_SEARCH_STRATEGY_CREDITS = 0
SEARCH_INTENT_QUERY_MATRIX_REQUIRED_CREDITS = 1
SEARCH_INTENT_QUERY_MATRIX_CREDITS = 0
SEARCH_RESULT_PASTE_PARSER_V2_REQUIRED_CREDITS = 1
SEARCH_RESULT_PASTE_PARSER_V2_CREDITS = 0
PASTED_SEARCH_PARSE_CREDITS = 0
CANDIDATE_COMPANY_RESEARCH_FEATURE = "candidate_company_research"
CANDIDATE_COMPANY_RESEARCH_REQUIRED_CREDITS = 5
CANDIDATE_COMPANY_RESEARCH_CREDITS = 0
CANDIDATE_OUTREACH_DRAFT_FEATURE = "candidate_outreach_draft"
CANDIDATE_OUTREACH_DRAFT_REQUIRED_CREDITS = 3
CANDIDATE_OUTREACH_DRAFT_CREDITS = 0
TARGET_CUSTOMER_PLAN_ARRAY_FIELDS = (
    "ideal_buyer_types",
    "target_industries",
    "recommended_countries",
    "search_keywords",
    "negative_keywords",
    "channel_recommendations",
    "buyer_pain_points",
    "match_scoring_rules",
    "disqualification_rules",
)
TARGET_CUSTOMER_PLAN_TEXT_FIELDS = ("first_batch_strategy",)
TARGET_CUSTOMER_CANDIDATE_FIELDS = (
    "company_name",
    "country",
    "website",
    "industry",
    "buyer_type",
    "source_channel",
    "match_reason",
    "suggested_next_action",
)
BASIC_SEARCH_STRATEGY_ARRAY_FIELDS = (
    "buyer_types",
    "target_countries",
    "search_keywords",
    "negative_keywords",
    "query_templates",
    "query_rationale",
    "match_scoring_hints",
)
SEARCH_INTENT_QUERY_MATRIX_ARRAY_FIELDS = (
    "product_keywords",
    "product_synonyms",
    "use_cases",
    "target_industries",
    "buyer_roles",
    "buyer_company_types",
    "target_countries",
    "negative_keywords",
    "supplier_exclusion_terms",
    "marketplace_exclusion_terms",
    "directory_noise_terms",
    "next_search_steps",
)
CANDIDATE_COMPANY_RESEARCH_ARRAY_FIELDS = (
    "possible_use_cases",
    "positive_signals",
    "risk_signals",
)
CANDIDATE_OUTREACH_DRAFT_ARRAY_FIELDS = ("personalization_notes",)


class AIServiceError(ValueError):
    pass


@dataclass(frozen=True)
class ProviderSettingsView:
    provider: str
    enabled: bool
    base_url: str
    model: str
    api_key_masked: str
    timeout_seconds: int
    max_output_tokens: int


@dataclass(frozen=True)
class OutreachDraftResult:
    success: bool
    subject: str = ""
    body_text: str = ""
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class ProductProfileExtractionResult:
    success: bool
    profile: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class TargetCustomerPlanResult:
    success: bool
    plan: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class TargetCustomerCandidateResult:
    success: bool
    candidates: list[dict[str, object]] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class BasicSearchStrategyResult:
    success: bool
    strategy: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class SearchIntentQueryMatrixResult:
    success: bool
    strategy: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class PastedSearchResultParseResult:
    success: bool
    candidates: list[dict[str, object]] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class SearchResultPasteParserV2Result:
    success: bool
    parse_result: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0


@dataclass(frozen=True)
class CandidateCompanyResearchResult:
    success: bool
    report: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0
    ledger_id: str = ""
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class CandidateOutreachDraftResult:
    success: bool
    draft: dict[str, object] | None = None
    error_code: str = ""
    quota_remaining: int = 0
    ledger_id: str = ""
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class TenantQuotaAdminView:
    tenant_id: str
    company_name: str
    enabled: bool
    included: int
    used: int
    remaining: int


def get_provider_settings(app: Flask) -> ProviderSettingsView:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        return _settings_view(settings)


def save_provider_settings(
    app: Flask,
    *,
    provider: str,
    enabled: bool,
    base_url: str,
    model: str,
    api_key: str,
    timeout_seconds: int,
    max_output_tokens: int,
) -> ProviderSettingsView:
    if provider not in {"disabled", "fake", "openai_compatible"}:
        raise AIServiceError("Unsupported AI provider")
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        settings.provider = provider
        settings.enabled = bool(enabled)
        settings.base_url = (base_url or "").strip()[:500]
        settings.model = (model or "").strip()[:120]
        settings.timeout_seconds = max(1, min(int(timeout_seconds or 25), 60))
        settings.max_output_tokens = max(64, min(int(max_output_tokens or 800), 8000))
        clean_key = (api_key or "").strip()
        if clean_key:
            settings.api_key_encrypted = encrypt_secret(clean_key)
            settings.api_key_last4 = last4(clean_key)
        session.commit()
        return _settings_view(settings)


def test_provider_connection(app: Flask) -> tuple[bool, str]:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider = _provider_from_settings(settings)
        result = provider.test_connection()
    return result.success, result.error_code or result.error_summary


def quota_summary(app: Flask, *, tenant_id: str):
    with _session(app) as session:
        summary = summarize_quota(session, tenant_id=tenant_id)
        session.commit()
        return summary


def admin_ai_overview(app: Flask) -> dict[str, object]:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        quota_rows = _tenant_quota_admin_rows(session)
        usage = usage_summary(session)
        return {"settings": _settings_view(settings), "quotas": quota_rows, "usage": usage}


def save_tenant_ai_settings(
    app: Flask,
    *,
    tenant_id: str,
    enabled: bool,
    monthly_included_credits: int,
) -> None:
    with _session(app) as session:
        save_tenant_quota(
            session,
            tenant_id=tenant_id,
            enabled=enabled,
            monthly_included_credits=monthly_included_credits,
        )
        session.commit()


def generate_outreach_draft(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    lead_id: str,
    locale: str,
    notes: str = "",
) -> OutreachDraftResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return OutreachDraftResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return OutreachDraftResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        if summary.remaining < OUTREACH_DRAFT_CREDITS:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="blocked_quota",
                error_code="insufficient_credits",
            )
            session.commit()
            return OutreachDraftResult(
                success=False,
                error_code="insufficient_credits",
                quota_remaining=summary.remaining,
            )

        lead = session.get(Lead, lead_id)
        if lead is None or lead.tenant_id != tenant_id:
            raise AIServiceError("Lead not found")

        prompt = build_outreach_draft_prompt(
            locale=locale,
            company=getattr(lead.company, "name", "") if getattr(lead, "company", None) else "",
            contact_name=f"{lead.first_name} {lead.last_name}".strip(),
            title=lead.title,
            industry=lead.industry,
            website=lead.website,
            source=lead.source,
            notes=notes,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(64, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            subject, body_text = _split_subject_body(result.text, locale=locale)
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=OUTREACH_DRAFT_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=OUTREACH_DRAFT_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return OutreachDraftResult(
                success=True,
                subject=subject,
                body_text=body_text,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=OUTREACH_DRAFT_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return OutreachDraftResult(success=False, error_code=result.error_code or "provider_error")


def extract_product_profile(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    raw_fields: dict[str, str],
) -> ProductProfileExtractionResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PRODUCT_PROFILE_EXTRACTION_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return ProductProfileExtractionResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PRODUCT_PROFILE_EXTRACTION_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return ProductProfileExtractionResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        prompt = build_product_profile_extraction_prompt(locale=locale, raw_fields=raw_fields)
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(256, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                profile = _parse_product_profile_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=PRODUCT_PROFILE_EXTRACTION_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return ProductProfileExtractionResult(success=False, error_code="malformed_json")

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PRODUCT_PROFILE_EXTRACTION_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=PRODUCT_PROFILE_EXTRACTION_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return ProductProfileExtractionResult(
                success=True,
                profile=profile,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=PRODUCT_PROFILE_EXTRACTION_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return ProductProfileExtractionResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def generate_target_customer_plan(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
) -> TargetCustomerPlanResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_PLAN_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return TargetCustomerPlanResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_PLAN_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return TargetCustomerPlanResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        prompt = build_target_customer_plan_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(256, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                plan = _parse_target_customer_plan_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=TARGET_CUSTOMER_PLAN_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return TargetCustomerPlanResult(success=False, error_code="malformed_json")

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_PLAN_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=TARGET_CUSTOMER_PLAN_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return TargetCustomerPlanResult(success=True, plan=plan, quota_remaining=remaining)

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=TARGET_CUSTOMER_PLAN_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return TargetCustomerPlanResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def generate_target_customer_candidates(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
    target_plan_json: str,
    filters: dict[str, object],
    count: int,
) -> TargetCustomerCandidateResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_MATCH_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return TargetCustomerCandidateResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_MATCH_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return TargetCustomerCandidateResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        prompt = build_target_customer_candidate_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
            target_plan_json=target_plan_json,
            filters=filters,
            count=count,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(512, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                candidates = _parse_target_customer_candidates_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=TARGET_CUSTOMER_MATCH_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return TargetCustomerCandidateResult(success=False, error_code="malformed_json")

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=TARGET_CUSTOMER_MATCH_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=TARGET_CUSTOMER_MATCH_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return TargetCustomerCandidateResult(
                success=True,
                candidates=candidates,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=TARGET_CUSTOMER_MATCH_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return TargetCustomerCandidateResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def generate_basic_search_strategy(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
    filters: dict[str, object],
    count: int,
) -> BasicSearchStrategyResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=BASIC_SEARCH_STRATEGY_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return BasicSearchStrategyResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=BASIC_SEARCH_STRATEGY_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return BasicSearchStrategyResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        prompt = build_basic_search_strategy_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
            filters=filters,
            count=count,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(256, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                strategy = _parse_basic_search_strategy_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=BASIC_SEARCH_STRATEGY_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return BasicSearchStrategyResult(success=False, error_code="malformed_json")

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=BASIC_SEARCH_STRATEGY_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=BASIC_SEARCH_STRATEGY_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return BasicSearchStrategyResult(
                success=True,
                strategy=strategy,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=BASIC_SEARCH_STRATEGY_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return BasicSearchStrategyResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def generate_search_intent_query_matrix(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
    filters: dict[str, object],
    count: int,
) -> SearchIntentQueryMatrixResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return SearchIntentQueryMatrixResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return SearchIntentQueryMatrixResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        if summary.remaining < SEARCH_INTENT_QUERY_MATRIX_REQUIRED_CREDITS:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="blocked_quota",
                error_code="insufficient_credits",
            )
            session.commit()
            return SearchIntentQueryMatrixResult(
                success=False,
                error_code="insufficient_credits",
                quota_remaining=summary.remaining,
            )

        prompt = build_search_intent_query_matrix_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
            filters=filters,
            count=count,
            product_family=_detect_search_product_family(product_profile_json),
            forbidden_cross_industry_terms=_forbidden_cross_industry_terms(product_profile_json),
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(4000, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                strategy = _parse_search_intent_query_matrix_json(
                    result.text,
                    product_profile_json=product_profile_json,
                )
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return SearchIntentQueryMatrixResult(
                    success=False,
                    error_code="malformed_json",
                )

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=SEARCH_INTENT_QUERY_MATRIX_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return SearchIntentQueryMatrixResult(
                success=True,
                strategy=strategy,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=SEARCH_INTENT_QUERY_MATRIX_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return SearchIntentQueryMatrixResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def parse_pasted_search_results(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
    strategy_json: str,
    pasted_results: str,
    filters: dict[str, object],
    count: int,
) -> PastedSearchResultParseResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PASTED_SEARCH_PARSE_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return PastedSearchResultParseResult(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PASTED_SEARCH_PARSE_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return PastedSearchResultParseResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        prompt = build_pasted_search_results_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
            strategy_json=strategy_json,
            pasted_results=pasted_results[:10000],
            filters=filters,
            count=count,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(512, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                candidates = _parse_target_customer_candidates_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=PASTED_SEARCH_PARSE_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return PastedSearchResultParseResult(success=False, error_code="malformed_json")

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=PASTED_SEARCH_PARSE_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=PASTED_SEARCH_PARSE_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return PastedSearchResultParseResult(
                success=True,
                candidates=candidates,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=PASTED_SEARCH_PARSE_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return PastedSearchResultParseResult(
            success=False, error_code=result.error_code or "provider_error"
        )


def parse_search_result_paste_parser_v2(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    product_profile_json: str,
    product_profile_hash: str,
    strategy_json: str,
    pasted_text: str,
    source_type: str,
    user_note: str,
    filters: dict[str, object],
    count: int,
) -> SearchResultPasteParserV2Result:
    sanitized_paste = _sanitize_pasted_text_for_prompt(pasted_text, max_length=30_000)
    sanitized_note = _sanitize_paste_parser_text(user_note, max_length=1000)
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.commit()
            return SearchResultPasteParserV2Result(success=False, error_code="ai_disabled")

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.commit()
            return SearchResultPasteParserV2Result(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
            )

        if summary.remaining < SEARCH_RESULT_PASTE_PARSER_V2_REQUIRED_CREDITS:
            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="blocked_quota",
                error_code="insufficient_credits",
            )
            session.commit()
            return SearchResultPasteParserV2Result(
                success=False,
                error_code="insufficient_credits",
                quota_remaining=summary.remaining,
            )

        prompt = build_search_result_paste_parser_v2_prompt(
            locale=locale,
            product_profile_json=product_profile_json,
            product_profile_hash=product_profile_hash,
            strategy_json=strategy_json,
            pasted_text=sanitized_paste,
            source_type=source_type,
            user_note=sanitized_note,
            filters=filters,
            count=count,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(3000, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                parse_result = _parse_search_result_paste_parser_v2_json(result.text)
            except AIServiceError:
                record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.commit()
                return SearchResultPasteParserV2Result(
                    success=False,
                    error_code="malformed_json",
                )

            record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=SEARCH_RESULT_PASTE_PARSER_V2_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return SearchResultPasteParserV2Result(
                success=True,
                parse_result=parse_result,
                quota_remaining=remaining,
            )

        record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=SEARCH_RESULT_PASTE_PARSER_V2_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.commit()
        return SearchResultPasteParserV2Result(
            success=False,
            error_code=result.error_code or "provider_error",
        )


def generate_candidate_company_research(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    candidate_context_json: str,
    product_profile_json: str,
) -> CandidateCompanyResearchResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateCompanyResearchResult(
                success=False,
                error_code="ai_disabled",
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateCompanyResearchResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        if summary.remaining < CANDIDATE_COMPANY_RESEARCH_REQUIRED_CREDITS:
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="blocked_quota",
                error_code="insufficient_credits",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateCompanyResearchResult(
                success=False,
                error_code="insufficient_credits",
                quota_remaining=summary.remaining,
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        prompt = build_candidate_company_research_prompt(
            locale=locale,
            candidate_context_json=candidate_context_json,
            product_profile_json=product_profile_json,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(512, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                report = _parse_candidate_company_research_json(result.text)
            except AIServiceError:
                ledger = record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.flush()
                ledger_id = ledger.id
                session.commit()
                return CandidateCompanyResearchResult(
                    success=False,
                    error_code="malformed_json",
                    ledger_id=ledger_id,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                )

            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=CANDIDATE_COMPANY_RESEARCH_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            session.flush()
            ledger_id = ledger.id
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return CandidateCompanyResearchResult(
                success=True,
                report=report,
                quota_remaining=remaining,
                ledger_id=ledger_id,
                provider=result.provider or provider_name,
                model=result.model or model,
            )

        ledger = record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=CANDIDATE_COMPANY_RESEARCH_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.flush()
        ledger_id = ledger.id
        session.commit()
        return CandidateCompanyResearchResult(
            success=False,
            error_code=result.error_code or "provider_error",
            ledger_id=ledger_id,
            provider=result.provider or provider_name,
            model=result.model or model,
        )


def generate_candidate_outreach_draft(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    candidate_context_json: str,
    research_report_json: str,
    product_profile_json: str,
    sources_json: str,
    language: str = "en",
    tone: str = "professional_concise",
) -> CandidateOutreachDraftResult:
    with _session(app) as session:
        settings = _get_or_create_settings(session)
        provider_name = settings.provider
        model = settings.model
        if not settings.enabled or settings.provider == "disabled":
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="ai_disabled",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateOutreachDraftResult(
                success=False,
                error_code="ai_disabled",
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        summary = summarize_quota(session, tenant_id=tenant_id)
        if not summary.enabled:
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="disabled",
                error_code="tenant_ai_disabled",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateOutreachDraftResult(
                success=False,
                error_code="tenant_ai_disabled",
                quota_remaining=summary.remaining,
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        if summary.remaining < CANDIDATE_OUTREACH_DRAFT_REQUIRED_CREDITS:
            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
                provider=provider_name,
                model=model,
                credits_charged=0,
                input_tokens=0,
                output_tokens=0,
                status="blocked_quota",
                error_code="insufficient_credits",
            )
            session.flush()
            ledger_id = ledger.id
            session.commit()
            return CandidateOutreachDraftResult(
                success=False,
                error_code="insufficient_credits",
                quota_remaining=summary.remaining,
                ledger_id=ledger_id,
                provider=provider_name,
                model=model,
            )

        prompt = build_candidate_outreach_draft_prompt(
            locale=locale,
            candidate_context_json=candidate_context_json,
            research_report_json=research_report_json,
            product_profile_json=product_profile_json,
            sources_json=sources_json,
            language=language,
            tone=tone,
        )
        provider = _provider_from_settings(settings)

    start = time.monotonic()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale=locale,
            max_output_tokens=max(512, settings.max_output_tokens),
        )
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    with _session(app) as session:
        if result.success:
            try:
                draft = _parse_candidate_outreach_draft_json(result.text)
            except AIServiceError:
                ledger = record_ai_usage(
                    session,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                    credits_charged=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    status="failed",
                    error_code="malformed_json",
                    latency_ms=latency_ms,
                )
                session.flush()
                ledger_id = ledger.id
                session.commit()
                return CandidateOutreachDraftResult(
                    success=False,
                    error_code="malformed_json",
                    ledger_id=ledger_id,
                    provider=result.provider or provider_name,
                    model=result.model or model,
                )

            ledger = record_ai_usage(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
                provider=result.provider or provider_name,
                model=result.model or model,
                credits_charged=CANDIDATE_OUTREACH_DRAFT_CREDITS,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                status="success",
                latency_ms=latency_ms,
            )
            session.flush()
            ledger_id = ledger.id
            remaining = summarize_quota(session, tenant_id=tenant_id).remaining
            session.commit()
            return CandidateOutreachDraftResult(
                success=True,
                draft=draft,
                quota_remaining=remaining,
                ledger_id=ledger_id,
                provider=result.provider or provider_name,
                model=result.model or model,
            )

        ledger = record_ai_usage(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            feature_name=CANDIDATE_OUTREACH_DRAFT_FEATURE,
            provider=result.provider or provider_name,
            model=result.model or model,
            credits_charged=0,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            status="failed",
            error_code=result.error_code or "provider_error",
            latency_ms=latency_ms,
        )
        session.flush()
        ledger_id = ledger.id
        session.commit()
        return CandidateOutreachDraftResult(
            success=False,
            error_code=result.error_code or "provider_error",
            ledger_id=ledger_id,
            provider=result.provider or provider_name,
            model=result.model or model,
        )


def _session(app: Flask) -> Session:
    session = Session(get_engine(app))
    session.expire_on_commit = False
    return session


def _get_or_create_settings(session: Session) -> AIProviderSettings:
    settings = session.scalar(select(AIProviderSettings).order_by(AIProviderSettings.created_at))
    if settings is None:
        settings = AIProviderSettings(provider="disabled", enabled=False)
        session.add(settings)
        session.flush()
    return settings


def _settings_view(settings: AIProviderSettings) -> ProviderSettingsView:
    masked = ""
    if settings.api_key_last4:
        masked = f"****{settings.api_key_last4}"
    return ProviderSettingsView(
        provider=settings.provider,
        enabled=settings.enabled,
        base_url=settings.base_url,
        model=settings.model,
        api_key_masked=masked,
        timeout_seconds=settings.timeout_seconds,
        max_output_tokens=settings.max_output_tokens,
    )


def _tenant_quota_admin_rows(session: Session) -> list[TenantQuotaAdminView]:
    tenants = list(session.scalars(select(Tenant).order_by(Tenant.company_name, Tenant.created_at)))
    rows: list[TenantQuotaAdminView] = []
    for tenant in tenants:
        summary = summarize_quota(session, tenant_id=tenant.id)
        rows.append(
            TenantQuotaAdminView(
                tenant_id=tenant.id,
                company_name=tenant.company_name or tenant.id,
                enabled=summary.enabled,
                included=summary.included or DEFAULT_DISABLED_CREDITS,
                used=summary.used,
                remaining=summary.remaining,
            )
        )
    return rows


def _provider_from_settings(settings: AIProviderSettings) -> AIProvider:
    if not settings.enabled or settings.provider == "disabled":
        return DisabledProvider()
    if settings.provider == "fake":
        return FakeAIProvider(model=settings.model or "fake-ai")
    if settings.provider == "openai_compatible":
        api_key = ""
        if settings.api_key_encrypted:
            try:
                api_key = decrypt_secret(settings.api_key_encrypted)
            except SecretCryptoError:
                api_key = ""
        return OpenAICompatibleProvider(
            base_url=settings.base_url,
            model=settings.model,
            api_key=api_key,
            timeout_seconds=settings.timeout_seconds,
        )
    return DisabledProvider()


def _split_subject_body(text: str, *, locale: str) -> tuple[str, str]:
    clean = (text or "").strip()
    subject_prefixes = ("Subject:", "主题：", "主题:")
    for prefix in subject_prefixes:
        if clean.startswith(prefix):
            remainder = clean[len(prefix) :].strip()
            if "\n" in remainder:
                subject, body = remainder.split("\n", 1)
                return subject.strip()[:500], body.strip()[:10000]
            return remainder[:500], ""
    fallback = "AI generated outreach draft" if locale == "en-US" else "AI 生成外联草稿"
    return fallback, clean[:10000]


def _parse_product_profile_json(text: str) -> dict[str, object]:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.removeprefix("```json").removeprefix("```").strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AIServiceError("Malformed product profile JSON") from exc
    if not isinstance(data, dict):
        raise AIServiceError("Product profile JSON must be an object")

    normalized: dict[str, object] = {}
    for key in PRODUCT_PROFILE_ARRAY_FIELDS:
        normalized[key] = _normalize_list(data.get(key))
    for key in PRODUCT_PROFILE_TEXT_FIELDS:
        normalized[key] = _normalize_text(data.get(key))
    return normalized


def _parse_target_customer_plan_json(text: str) -> dict[str, object]:
    data = _load_json_object(text)
    normalized: dict[str, object] = {}
    for key in TARGET_CUSTOMER_PLAN_ARRAY_FIELDS:
        normalized[key] = _normalize_list(data.get(key))
    for key in TARGET_CUSTOMER_PLAN_TEXT_FIELDS:
        normalized[key] = _normalize_text(data.get(key))
    return normalized


def _parse_basic_search_strategy_json(text: str) -> dict[str, object]:
    data = _load_json_object(text)
    normalized: dict[str, object] = {}
    for key in BASIC_SEARCH_STRATEGY_ARRAY_FIELDS:
        normalized[key] = _normalize_list(data.get(key))
    return normalized


def _parse_search_intent_query_matrix_json(
    text: str,
    *,
    product_profile_json: str,
) -> dict[str, object]:
    data = _load_json_object(text)
    product_family = _detect_search_product_family(product_profile_json)
    normalized: dict[str, object] = {
        "intent_summary": _sanitize_search_intent_text(
            data.get("intent_summary", ""),
            max_length=1000,
        ),
        "product_context_check": _normalize_product_context_check(
            data.get("product_context_check"),
            fallback_family=product_family,
            product_profile_json=product_profile_json,
        ),
    }
    for key in SEARCH_INTENT_QUERY_MATRIX_ARRAY_FIELDS:
        normalized[key] = _normalize_public_list(data.get(key), limit=20)
    normalized["multilingual_terms"] = _normalize_multilingual_terms(data.get("multilingual_terms"))
    normalized = _filter_search_intent_for_current_product(
        normalized,
        product_family=product_family,
        product_profile_json=product_profile_json,
    )
    normalized["query_matrix"] = _filter_cross_industry_query_rows(
        _normalize_query_matrix(data.get("query_matrix")),
        product_family=product_family,
        product_profile_json=product_profile_json,
    )
    normalized["query_self_check"] = _filter_cross_industry_query_self_check(
        _normalize_query_self_check(data.get("query_self_check")),
        product_family=product_family,
        product_profile_json=product_profile_json,
    )
    if not normalized["intent_summary"]:
        normalized["intent_summary"] = "AI 搜索策略仅供参考，请人工确认搜索结果。"
    if not normalized["query_matrix"]:
        normalized["query_matrix"] = _fallback_query_matrix_for_product(product_profile_json)
        normalized["query_self_check"] = normalized["query_self_check"] or [
            {
                "query": "",
                "risk": "wrong product category",
                "improved_query": "已移除跨行业搜索词，并生成保守 fallback query。",
            }
        ]
        normalized["product_context_check"]["excluded_unrelated_terms"] = sorted(
            set(normalized["product_context_check"].get("excluded_unrelated_terms", []))
            | set(_forbidden_cross_industry_terms(product_profile_json))
        )
    return normalized


def _parse_target_customer_candidates_json(text: str) -> list[dict[str, object]]:
    data = _load_json_object(text)
    raw_candidates = data.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raise AIServiceError("Target customer candidates must be a list")

    candidates: list[dict[str, object]] = []
    for raw_candidate in raw_candidates[:25]:
        if not isinstance(raw_candidate, dict):
            continue
        candidate = {
            key: _sanitize_public_text(raw_candidate.get(key, ""), max_length=500)
            for key in TARGET_CUSTOMER_CANDIDATE_FIELDS
        }
        candidate["company_name"] = candidate["company_name"][:300]
        candidate["country"] = candidate["country"][:120]
        candidate["industry"] = candidate["industry"][:120]
        candidate["buyer_type"] = candidate["buyer_type"][:120]
        candidate["source_channel"] = candidate["source_channel"][:80]
        candidate["confidence_score"] = _normalize_score(raw_candidate.get("confidence_score"))
        if candidate["company_name"]:
            candidates.append(candidate)
    if not candidates:
        raise AIServiceError("No target customer candidates returned")
    return candidates


def _parse_search_result_paste_parser_v2_json(text: str) -> dict[str, object]:
    data = _load_json_object(text)
    candidates = _normalize_paste_parser_candidates(data.get("candidates"))
    rejected_items = _normalize_rejected_paste_items(data.get("rejected_items"))
    parse_summary = _normalize_paste_parse_summary(
        data.get("parse_summary"),
        candidate_count=len(candidates),
        rejected_count=len(rejected_items),
    )
    query_feedback = _normalize_paste_query_feedback(data.get("query_feedback"))
    return {
        "parse_summary": parse_summary,
        "candidates": candidates,
        "rejected_items": rejected_items,
        "query_feedback": query_feedback,
    }


def _parse_candidate_company_research_json(text: str) -> dict[str, object]:
    data = _load_json_object(text)
    report: dict[str, object] = {
        "summary": _sanitize_public_text(data.get("summary", ""), max_length=1500),
        "why_potential_buyer": _sanitize_public_text(
            data.get("why_potential_buyer", data.get("why_fit", "")),
            max_length=1500,
        ),
        "product_fit": _sanitize_public_text(data.get("product_fit", ""), max_length=1500),
        "buyer_type": _sanitize_public_text(
            data.get("buyer_type", data.get("buyer_type_judgment", "")),
            max_length=120,
        ),
        "country_region": _sanitize_public_text(data.get("country_region", ""), max_length=120),
        "fit_score": _normalize_score(data.get("fit_score")),
        "confidence_score": _normalize_score(data.get("confidence_score")),
        "suggested_next_action": _sanitize_public_text(
            data.get("suggested_next_action", ""),
            max_length=1000,
        ),
        "suggested_outreach_angle": _sanitize_public_text(
            data.get("suggested_outreach_angle", ""),
            max_length=1000,
        ),
        "disclaimer": _sanitize_public_text(
            data.get("disclaimer", "未验证，需要人工确认"),
            max_length=300,
        )
        or "未验证，需要人工确认",
    }
    for key in CANDIDATE_COMPANY_RESEARCH_ARRAY_FIELDS:
        report[key] = _normalize_signal_list(data.get(key), key=key)
    if not report["summary"]:
        raise AIServiceError("Candidate research summary is required")
    return report


def _parse_candidate_outreach_draft_json(text: str) -> dict[str, object]:
    data = _load_json_object(text)
    draft: dict[str, object] = {
        "subject": _sanitize_public_text(data.get("subject", ""), max_length=500),
        "body": _sanitize_public_text(data.get("body", ""), max_length=5000),
        "short_body": _sanitize_public_text(data.get("short_body", ""), max_length=1500),
        "follow_up_angle": _sanitize_public_text(
            data.get("follow_up_angle", ""),
            max_length=1000,
        ),
        "confidence_note": _sanitize_public_text(
            data.get("confidence_note", ""),
            max_length=1000,
        ),
        "disclaimer": _sanitize_public_text(
            data.get(
                "disclaimer",
                "Draft only. Not sent. Please verify before sending.",
            ),
            max_length=500,
        )
        or "Draft only. Not sent. Please verify before sending.",
    }
    for key in CANDIDATE_OUTREACH_DRAFT_ARRAY_FIELDS:
        draft[key] = _normalize_list(data.get(key))[:8]
    if not draft["subject"] or not draft["body"]:
        raise AIServiceError("Candidate outreach draft subject and body are required")
    return draft


def _normalize_paste_parse_summary(
    value: object,
    *,
    candidate_count: int,
    rejected_count: int,
) -> dict[str, object]:
    data = value if isinstance(value, dict) else {}
    return {
        "source_type": _sanitize_paste_parser_text(data.get("source_type", ""), max_length=80),
        "total_items_seen": _safe_int(data.get("total_items_seen"), 0, 500),
        "candidate_count": _safe_int(data.get("candidate_count"), candidate_count, 50),
        "rejected_count": _safe_int(data.get("rejected_count"), rejected_count, 100),
        "duplicate_hint_count": _safe_int(data.get("duplicate_hint_count"), 0, 100),
        "safety_warnings": _normalize_paste_public_list(data.get("safety_warnings"), limit=8),
    }


def _normalize_paste_parser_candidates(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value[:50]:
        if not isinstance(item, dict):
            continue
        classification = _normalize_classification(item.get("classification"))
        raw_text = json.dumps(item, ensure_ascii=False)
        candidate = {
            "source_item_id": _sanitize_paste_parser_text(
                item.get("source_item_id", ""),
                max_length=80,
            ),
            "company_name": _sanitize_paste_parser_text(
                item.get("company_name", ""),
                max_length=300,
            ),
            "domain": _sanitize_domain_like(item.get("domain", "")),
            "source_url": _sanitize_source_url(item.get("source_url", "")),
            "country": _sanitize_paste_parser_text(item.get("country", ""), max_length=120),
            "buyer_type": _sanitize_paste_parser_text(item.get("buyer_type", ""), max_length=120),
            "classification": classification,
            "product_fit": _normalize_enum(
                item.get("product_fit"),
                allowed={"high", "medium", "low", "irrelevant"},
                default="low",
            ),
            "source_quality": _normalize_enum(
                item.get("source_quality"),
                allowed={
                    "official_site",
                    "company_profile",
                    "directory",
                    "marketplace",
                    "article",
                    "unknown",
                },
                default="unknown",
            ),
            "fit_score": _normalize_score(item.get("fit_score")),
            "confidence_score": _normalize_score(item.get("confidence_score")),
            "match_reason": _sanitize_paste_parser_text(
                item.get("match_reason", ""),
                max_length=1000,
            ),
            "risk_reason": _sanitize_paste_parser_text(
                item.get("risk_reason", ""),
                max_length=700,
            ),
            "next_action": _sanitize_paste_parser_text(
                item.get("next_action", ""),
                max_length=500,
            ),
            "sanitized_snippet": _sanitize_paste_parser_text(
                item.get("sanitized_snippet", ""),
                max_length=500,
            ),
            "ai_safety_risk_score": _paste_safety_risk_score(raw_text),
            "ai_scoring_v2": _normalize_ai_scoring_v2(item.get("scoring_v2")),
        }
        if candidate["company_name"] or candidate["domain"]:
            rows.append(candidate)
    return rows


def _normalize_rejected_paste_items(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:50]:
        if not isinstance(item, dict):
            continue
        source_item_id = _sanitize_paste_parser_text(item.get("source_item_id", ""), max_length=80)
        reason = _sanitize_paste_parser_text(item.get("reason", ""), max_length=240)
        if source_item_id or reason:
            rows.append({"source_item_id": source_item_id, "reason": reason})
    return rows


def _normalize_paste_query_feedback(value: object) -> dict[str, object]:
    data = value if isinstance(value, dict) else {}
    return {
        "suggested_negative_keywords": _normalize_paste_public_list(
            data.get("suggested_negative_keywords"),
            limit=12,
        ),
        "suggested_better_queries": _normalize_paste_public_list(
            data.get("suggested_better_queries"),
            limit=12,
        ),
        "domain_blacklist_suggestions": _normalize_paste_public_list(
            data.get("domain_blacklist_suggestions"),
            limit=12,
        ),
        "notes": _normalize_paste_public_list(data.get("notes"), limit=8),
    }


def _normalize_ai_scoring_v2(value: object) -> dict[str, object]:
    data = value if isinstance(value, dict) else {}
    return {
        "buyer_score": _safe_int(data.get("buyer_score"), 0, 100),
        "product_fit_score": _safe_int(data.get("product_fit_score"), 0, 100),
        "confidence_score": _normalize_score_from_any(data.get("confidence_score")),
        "supplier_risk_score": _safe_int(data.get("supplier_risk_score"), 0, 100),
        "directory_risk_score": _safe_int(data.get("directory_risk_score"), 0, 100),
        "marketplace_risk_score": _safe_int(data.get("marketplace_risk_score"), 0, 100),
        "safety_risk_score": _safe_int(data.get("safety_risk_score"), 0, 100),
        "positive_signals": _normalize_paste_public_list(data.get("positive_signals"), limit=8),
        "risk_flags": _normalize_paste_public_list(data.get("risk_flags"), limit=8),
        "classification_v2": _sanitize_paste_parser_text(
            data.get("classification_v2", ""),
            max_length=40,
        ),
        "score_band": _sanitize_paste_parser_text(data.get("score_band", ""), max_length=20),
        "recommended_action": _sanitize_paste_parser_text(
            data.get("recommended_action", ""),
            max_length=40,
        ),
    }


def _normalize_score_from_any(value: object) -> int:
    try:
        score = float(value or 0)
    except (TypeError, ValueError):
        return 0
    if 0 < score <= 1:
        score *= 100
    elif 1 < score <= 5:
        score *= 20
    return max(0, min(int(round(score)), 100))


def _paste_safety_risk_score(value: str) -> int:
    text = value.lower()
    score = 0
    if re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", value):
        score += 50
    if re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", value):
        score += 40
    if "whatsapp" in text or "telegram" in text:
        score += 50
    if "linkedin.com/in/" in text or "facebook.com/" in text:
        score += 30
    if "crawl" in text or "scrape" in text or "scraping" in text:
        score += 80
    if "automatic email" in text or "send email" in text or "email campaign" in text:
        score += 80
    if "verified buyer" in text or "purchase intent" in text or "confirmed purchasing" in text:
        score += 60
    return max(0, min(score, 100))


def _normalize_paste_public_list(value: object, *, limit: int) -> list[str]:
    if value is None:
        return []
    raw_values: list[object]
    if isinstance(value, str):
        raw_values = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_values = value
    else:
        return []
    rows: list[str] = []
    for item in raw_values:
        clean = _sanitize_paste_parser_text(item, max_length=220)
        if clean:
            rows.append(clean)
        if len(rows) >= limit:
            break
    return rows


def _normalize_classification(value: object) -> str:
    allowed = {
        "buyer",
        "maybe_buyer",
        "supplier",
        "directory",
        "marketplace",
        "article",
        "irrelevant",
        "unsafe",
    }
    clean = str(value or "").strip().lower().replace(" ", "_")
    return clean if clean in allowed else "unsafe"


def _normalize_enum(value: object, *, allowed: set[str], default: str) -> str:
    clean = str(value or "").strip().lower()
    return clean if clean in allowed else default


def _safe_int(value: object, default: int, maximum: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(0, min(parsed, maximum))


def _normalize_signal_list(value: object, *, key: str) -> list[dict[str, str]]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:8]:
        if isinstance(item, dict):
            label_key = "risk" if key == "risk_signals" else "signal"
            label = _sanitize_public_text(
                item.get(label_key, item.get("value", item.get("text", ""))),
                max_length=300,
            )
            source = _sanitize_public_text(item.get("source", "candidate_metadata"), max_length=120)
            confidence = _sanitize_public_text(
                item.get("confidence", item.get("severity", "medium")),
                max_length=40,
            )
        else:
            label_key = "risk" if key == "risk_signals" else "signal"
            label = _sanitize_public_text(item, max_length=300)
            source = "candidate_metadata"
            confidence = "medium"
        if not label:
            continue
        rows.append({label_key: label, "source": source, "confidence": confidence})
    return rows


def _load_json_object(text: str) -> dict[str, object]:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.removeprefix("```json").removeprefix("```").strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise AIServiceError("Malformed JSON") from exc
    if not isinstance(data, dict):
        raise AIServiceError("JSON must be an object")
    return data


def _normalize_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(",", "\n").splitlines()]
        return [part[:200] for part in parts if part]
    if isinstance(value, list):
        return [str(item).strip()[:200] for item in value if str(item).strip()]
    return []


def _normalize_public_list(value: object, *, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_values = value.replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_values = value
    else:
        return []
    rows: list[str] = []
    for item in raw_values:
        clean = _sanitize_search_intent_text(item, max_length=200)
        if clean:
            rows.append(clean)
        if len(rows) >= limit:
            break
    return rows


def _normalize_multilingual_terms(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, object]] = []
    for item in value[:5]:
        if not isinstance(item, dict):
            continue
        row = {
            "country": _sanitize_search_intent_text(item.get("country", ""), max_length=120),
            "language": _sanitize_search_intent_text(item.get("language", ""), max_length=80),
            "buyer_terms": _normalize_public_list(item.get("buyer_terms"), limit=10),
            "query_terms": _normalize_public_list(item.get("query_terms"), limit=10),
            "negative_terms": _normalize_public_list(item.get("negative_terms"), limit=10),
        }
        if row["country"] or row["language"] or row["buyer_terms"] or row["query_terms"]:
            rows.append(row)
    return rows


def _normalize_product_context_check(
    value: object,
    *,
    fallback_family: str,
    product_profile_json: str,
) -> dict[str, object]:
    data = value if isinstance(value, dict) else {}
    detected = _sanitize_search_intent_text(
        data.get("detected_product_family", fallback_family),
        max_length=80,
    )
    core_products = _normalize_public_list(data.get("core_products_used"), limit=10)
    if not core_products:
        core_products = _profile_seed_terms(product_profile_json)[:5]
    excluded = _normalize_public_list(data.get("excluded_unrelated_terms"), limit=20)
    try:
        confidence = int(data.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0
    return {
        "detected_product_family": detected or fallback_family,
        "core_products_used": core_products,
        "excluded_unrelated_terms": excluded,
        "confidence": max(0, min(confidence, 100)),
    }


def _normalize_query_matrix(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        query = _sanitize_search_intent_text(item.get("query", ""), max_length=220)
        if not query:
            continue
        rows.append(
            {
                "group": _sanitize_search_intent_text(item.get("group", ""), max_length=80),
                "query": query,
                "target_country": _sanitize_search_intent_text(
                    item.get("target_country", ""),
                    max_length=120,
                ),
                "buyer_type": _sanitize_search_intent_text(
                    item.get("buyer_type", ""),
                    max_length=120,
                ),
                "why_useful": _sanitize_search_intent_text(
                    item.get("why_useful", ""),
                    max_length=400,
                ),
                "risk": _sanitize_search_intent_text(item.get("risk", ""), max_length=300),
                "copy_label": _sanitize_search_intent_text(
                    item.get("copy_label", ""),
                    max_length=120,
                ),
                "product_terms_used": ", ".join(
                    _normalize_public_list(item.get("product_terms_used"), limit=6)
                ),
                "buyer_terms_used": ", ".join(
                    _normalize_public_list(item.get("buyer_terms_used"), limit=6)
                ),
                "country_terms_used": ", ".join(
                    _normalize_public_list(item.get("country_terms_used"), limit=6)
                ),
                "negative_terms_used": ", ".join(
                    _normalize_public_list(item.get("negative_terms_used"), limit=8)
                ),
                "relevance_to_current_product": _sanitize_search_intent_text(
                    item.get("relevance_to_current_product", ""),
                    max_length=160,
                ),
                "cross_industry_risk": _sanitize_search_intent_text(
                    item.get("cross_industry_risk", "none"),
                    max_length=80,
                )
                or "none",
            }
        )
    return rows


def _normalize_query_self_check(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        query = _sanitize_search_intent_text(item.get("query", ""), max_length=220)
        improved_query = _sanitize_search_intent_text(
            item.get("improved_query", ""),
            max_length=220,
        )
        if not query and not improved_query:
            continue
        rows.append(
            {
                "query": query,
                "risk": _sanitize_search_intent_text(item.get("risk", ""), max_length=120),
                "improved_query": improved_query,
            }
        )
    return rows


def _filter_search_intent_for_current_product(
    normalized: dict[str, object],
    *,
    product_family: str,
    product_profile_json: str,
) -> dict[str, object]:
    if product_family not in {"packaging", "led_lighting"}:
        return normalized
    for key in (
        "product_keywords",
        "product_synonyms",
        "use_cases",
        "target_industries",
        "buyer_roles",
        "buyer_company_types",
        "target_countries",
        "negative_keywords",
        "supplier_exclusion_terms",
        "marketplace_exclusion_terms",
        "directory_noise_terms",
        "next_search_steps",
    ):
        value = normalized.get(key)
        if isinstance(value, list):
            normalized[key] = [
                item
                for item in value
                if not _has_forbidden_cross_industry_term(
                    str(item),
                    product_family=product_family,
                    product_profile_json=product_profile_json,
                )
            ]
    multilingual_terms = normalized.get("multilingual_terms")
    if isinstance(multilingual_terms, list):
        filtered_terms: list[dict[str, object]] = []
        for row in multilingual_terms:
            text = json.dumps(row, ensure_ascii=False)
            if not _has_forbidden_cross_industry_term(
                text,
                product_family=product_family,
                product_profile_json=product_profile_json,
            ):
                filtered_terms.append(row)
        normalized["multilingual_terms"] = filtered_terms
    return normalized


def _filter_cross_industry_query_rows(
    rows: list[dict[str, str]],
    *,
    product_family: str,
    product_profile_json: str,
) -> list[dict[str, str]]:
    if product_family not in {"packaging", "led_lighting"}:
        return rows
    filtered: list[dict[str, str]] = []
    for row in rows:
        row_text = json.dumps(row, ensure_ascii=False)
        risk = row.get("cross_industry_risk", "none").strip().lower()
        if risk and risk != "none":
            continue
        if _has_forbidden_cross_industry_term(
            row_text,
            product_family=product_family,
            product_profile_json=product_profile_json,
        ):
            continue
        filtered.append(row)
    return filtered[:30]


def _filter_cross_industry_query_self_check(
    rows: list[dict[str, str]],
    *,
    product_family: str,
    product_profile_json: str,
) -> list[dict[str, str]]:
    if product_family not in {"packaging", "led_lighting"}:
        return rows
    return [
        row
        for row in rows
        if not _has_forbidden_cross_industry_term(
            json.dumps(row, ensure_ascii=False),
            product_family=product_family,
            product_profile_json=product_profile_json,
        )
    ][:30]


def _fallback_query_matrix_for_product(product_profile_json: str) -> list[dict[str, str]]:
    family = _detect_search_product_family(product_profile_json)
    seed_terms = _profile_seed_terms(product_profile_json)
    product_term = seed_terms[0] if seed_terms else "export product"
    if family == "led_lighting":
        product_term = _first_matching_seed(
            seed_terms,
            ("led", "lighting", "lamp", "fixture"),
            fallback=product_term,
        )
        rows = [
            (
                "buyer_type",
                f"{product_term} distributor -manufacturer -factory -supplier",
                "Distributor",
            ),
            (
                "procurement",
                f"{product_term} electrical wholesaler -manufacturer -factory -supplier",
                "Electrical wholesaler",
            ),
            (
                "use_case",
                f"{product_term} project supplier -manufacturer -marketplace",
                "Project supplier",
            ),
        ]
    elif family == "packaging":
        product_term = _first_matching_seed(
            seed_terms,
            ("packaging", "bag", "mailer", "kraft", "compostable"),
            fallback=product_term,
        )
        rows = [
            (
                "buyer_type",
                f"{product_term} importer -manufacturer -factory -supplier",
                "Importer",
            ),
            (
                "country",
                f"{product_term} distributor Germany -manufacturer -factory",
                "Distributor",
            ),
            (
                "private_label",
                f"{product_term} private label brand -supplier -marketplace",
                "Private label brand",
            ),
        ]
    else:
        rows = [
            (
                "buyer_type",
                f"{product_term} importer -manufacturer -factory -supplier",
                "Importer",
            ),
            (
                "distributor",
                f"{product_term} distributor -manufacturer -factory -supplier",
                "Distributor",
            ),
        ]
    return [
        {
            "group": group,
            "query": query[:220],
            "target_country": "",
            "buyer_type": buyer_type,
            "why_useful": "AI 输出被跨行业过滤后，系统用当前产品关键词生成保守搜索词。",
            "risk": "fallback query，需要人工确认。",
            "copy_label": buyer_type,
            "product_terms_used": product_term,
            "buyer_terms_used": buyer_type,
            "country_terms_used": "",
            "negative_terms_used": "manufacturer, factory, supplier",
            "relevance_to_current_product": "fallback_high",
            "cross_industry_risk": "none",
        }
        for group, query, buyer_type in rows
    ]


def _detect_search_product_family(product_profile_json: str) -> str:
    text = _profile_text(product_profile_json)
    packaging_score = sum(1 for term in _PACKAGING_TERMS if term in text)
    lighting_score = sum(1 for term in _LED_LIGHTING_TERMS if term in text)
    if packaging_score and lighting_score:
        if packaging_score > lighting_score:
            return "packaging"
        if lighting_score > packaging_score:
            return "led_lighting"
        return "mixed"
    if packaging_score:
        return "packaging"
    if lighting_score:
        return "led_lighting"
    return "unknown"


def _forbidden_cross_industry_terms(product_profile_json: str) -> list[str]:
    family = _detect_search_product_family(product_profile_json)
    if family == "packaging":
        return [
            "LED",
            "lighting",
            "lamp",
            "fixture",
            "electrical wholesaler",
            "contractor lighting",
            "commercial LED",
        ]
    if family == "led_lighting":
        return [
            "packaging",
            "packaging bags",
            "compostable bags",
            "mailer bags",
            "kraft paper bags",
            "cosmetic packaging",
            "food packaging",
        ]
    return []


def _has_forbidden_cross_industry_term(
    value: str,
    *,
    product_family: str,
    product_profile_json: str,
) -> bool:
    if product_family not in {"packaging", "led_lighting"}:
        return False
    profile_text = _profile_text(product_profile_json)
    text = value.lower()
    for term in _forbidden_cross_industry_terms(product_profile_json):
        lowered = term.lower()
        if lowered in text and lowered not in profile_text:
            return True
    return False


def _profile_seed_terms(product_profile_json: str) -> list[str]:
    try:
        data = json.loads(product_profile_json or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        return []
    seeds: list[str] = []
    for key in (
        "product_keywords_en",
        "product_keywords_cn",
        "product_categories",
        "search_keywords",
        "target_industries",
    ):
        value = data.get(key)
        if isinstance(value, list):
            seeds.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            seeds.append(value.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for seed in seeds:
        normalized = seed.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(_sanitize_search_intent_text(seed, max_length=120))
    return [seed for seed in deduped if seed][:10]


def _first_matching_seed(
    seeds: list[str],
    terms: tuple[str, ...],
    *,
    fallback: str,
) -> str:
    for seed in seeds:
        lower = seed.lower()
        if any(term in lower for term in terms):
            return seed
    return fallback


def _profile_text(product_profile_json: str) -> str:
    try:
        data = json.loads(product_profile_json or "{}")
    except json.JSONDecodeError:
        return product_profile_json.lower()
    return json.dumps(data, ensure_ascii=False).lower()


_PACKAGING_TERMS = (
    "packaging",
    "package",
    "bag",
    "bags",
    "mailer",
    "pouch",
    "kraft",
    "compostable",
    "biodegradable",
    "cosmetic packaging",
    "food packaging",
)
_LED_LIGHTING_TERMS = (
    "led",
    "lighting",
    "lamp",
    "fixture",
    "fixtures",
    "luminaire",
    "electrical wholesaler",
    "decorative lighting",
    "commercial led",
)


def _sanitize_search_intent_text(value: object, *, max_length: int) -> str:
    clean = _sanitize_public_text(value, max_length=max_length)
    lower = clean.lower()
    blocked_terms = (
        "linkedin",
        "facebook",
        "whatsapp",
        "telegram",
        "scrape",
        "scraping",
        "crawl",
        "crawling",
        "smtp",
        "send email",
        "auto email",
        "private email",
        "phone enrichment",
        "verified buyer",
        "purchase intent",
    )
    if any(term in lower for term in blocked_terms):
        return ""
    return clean


def _sanitize_pasted_text_for_prompt(value: object, *, max_length: int) -> str:
    clean_lines: list[str] = []
    total_length = 0
    for line in str(value or "").replace("\r", "\n").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(term in lowered for term in ("whatsapp", "telegram")):
            continue
        if "linkedin.com/in/" in lowered:
            continue
        if "facebook.com/" in lowered and "company" not in lowered:
            continue
        clean = _sanitize_paste_parser_text(stripped, max_length=800)
        if clean:
            clean_lines.append(clean)
            total_length += len(clean)
        if total_length >= max_length:
            break
    return "\n".join(clean_lines)[:max_length]


def _sanitize_paste_parser_text(value: object, *, max_length: int) -> str:
    clean = _sanitize_public_text(value, max_length=max_length)
    blocked_terms = (
        "verified buyer",
        "verified importer",
        "purchase intent",
        "confirmed purchasing",
        "confirmed buyer",
        "confirmed contact",
        "automatic email",
        "send email",
        "email campaign",
        "smtp",
        "crawl",
        "scrape",
        "scraping",
        "phone enrichment",
        "private email",
        "private phone",
        "linkedin",
        "facebook",
        "whatsapp",
        "telegram",
    )
    for term in blocked_terms:
        clean = re.sub(re.escape(term), "", clean, flags=re.IGNORECASE)
    return " ".join(clean.split())[:max_length].strip()


def _sanitize_domain_like(value: object) -> str:
    clean = _sanitize_paste_parser_text(value, max_length=253).lower()
    clean = clean.replace("https://", "").replace("http://", "").split("/", 1)[0]
    if "@" in clean or " " in clean:
        return ""
    return clean[:253]


def _sanitize_source_url(value: object) -> str:
    clean = _sanitize_paste_parser_text(value, max_length=500)
    if "@" in clean:
        return ""
    return clean


def _normalize_text(value: object) -> str:
    if value is None:
        return "unknown"
    clean = str(value).strip()
    return clean[:1000] if clean else "unknown"


def _normalize_score(value: object) -> int:
    try:
        score = int(value or 0)
    except (TypeError, ValueError):
        score = 0
    return max(0, min(score, 100))


def _sanitize_public_text(value: object, *, max_length: int) -> str:
    clean = str(value or "").strip()
    clean = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", "", clean)
    clean = re.sub(r"(?:\+?\d[\d\s().-]{7,}\d)", "", clean)
    return clean[:max_length].strip()
