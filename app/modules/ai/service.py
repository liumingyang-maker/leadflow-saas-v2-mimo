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
    build_outreach_draft_prompt,
    build_product_profile_extraction_prompt,
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
        settings.max_output_tokens = max(64, min(int(max_output_tokens or 800), 4000))
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
