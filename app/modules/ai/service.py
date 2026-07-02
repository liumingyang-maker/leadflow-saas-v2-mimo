from __future__ import annotations

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
from app.integrations.ai.prompts import build_outreach_draft_prompt
from app.modules.ai.ledger import record_ai_usage, usage_summary
from app.modules.ai.models import AIProviderSettings, TenantAIQuota
from app.modules.ai.quota import has_credits, summarize_quota
from app.modules.leads.models import Lead

OUTREACH_DRAFT_FEATURE = "outreach_draft"
OUTREACH_DRAFT_CREDITS = 5


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
        quotas = list(session.scalars(select(TenantAIQuota).order_by(TenantAIQuota.created_at)))
        usage = usage_summary(session)
        return {"settings": _settings_view(settings), "quotas": quotas, "usage": usage}


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
        if not has_credits(session, tenant_id=tenant_id, required=OUTREACH_DRAFT_CREDITS):
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
