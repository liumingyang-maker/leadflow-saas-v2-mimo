from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, time

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.secret_crypto import decrypt_secret, encrypt_secret, last4
from app.extensions import get_engine
from app.modules.acquisition.models import ACQUISITION_PROVIDERS, AcquisitionProviderSettings
from app.modules.ai.models import AIUsageLedger
from app.modules.jobs.target_models import TargetCustomerDiscoveryRun


class AcquisitionProviderError(ValueError):
    pass


@dataclass(frozen=True)
class AcquisitionSettingsView:
    id: str
    enabled: bool
    provider: str
    api_key_masked: str
    configured: bool
    daily_spend_cap_cents: int
    query_limit_per_run: int
    result_limit_per_run: int
    timeout_seconds: int
    last_tested_at: datetime | None
    last_test_status: str
    last_error_code: str


def get_acquisition_settings(app: Flask) -> AcquisitionSettingsView:
    with Session(get_engine(app)) as session:
        settings = _get_or_create_settings(session)
        session.commit()
        return _settings_view(settings)


def acquisition_provider_secret(app: Flask) -> str:
    with Session(get_engine(app)) as session:
        settings = _get_or_create_settings(session)
        if not settings.api_key_encrypted:
            return ""
        return decrypt_secret(settings.api_key_encrypted)


def save_acquisition_settings(
    app: Flask,
    *,
    provider: str,
    enabled: bool,
    api_key: str,
    daily_spend_cap_cents: int,
    query_limit_per_run: int,
    result_limit_per_run: int,
    timeout_seconds: int,
) -> AcquisitionSettingsView:
    provider = (provider or "disabled").strip()
    if provider not in ACQUISITION_PROVIDERS:
        raise AcquisitionProviderError("unsupported_acquisition_provider")

    with Session(get_engine(app)) as session:
        settings = _get_or_create_settings(session)
        settings.enabled = bool(enabled) and provider != "disabled"
        settings.provider = provider
        settings.daily_spend_cap_cents = _clamp(daily_spend_cap_cents, 0, 100_000)
        settings.query_limit_per_run = _clamp(query_limit_per_run, 1, 3)
        settings.result_limit_per_run = _clamp(result_limit_per_run, 3, 10)
        settings.timeout_seconds = _clamp(timeout_seconds, 1, 30)
        clean_key = (api_key or "").strip()
        if clean_key:
            settings.api_key_encrypted = encrypt_secret(clean_key)
            settings.api_key_last4 = last4(clean_key)
        session.commit()
        return _settings_view(settings)


def mark_acquisition_test_result(app: Flask, *, ok: bool, error_code: str = "") -> None:
    with Session(get_engine(app)) as session:
        settings = _get_or_create_settings(session)
        settings.last_tested_at = datetime.now(UTC)
        settings.last_test_status = "success" if ok else "failed"
        settings.last_error_code = (error_code or "")[:80]
        session.commit()


def advanced_search_available(app: Flask) -> bool:
    settings = get_acquisition_settings(app)
    if not settings.enabled or settings.provider == "disabled":
        return False
    if settings.provider == "brave" and not settings.configured:
        return False
    return settings.provider in {"fake", "brave"}


def daily_query_limit(settings: AcquisitionSettingsView) -> int:
    if settings.daily_spend_cap_cents <= 0:
        return 0
    # Brave's paid search cost is request-based; keep local safety conservative.
    return max(1, settings.daily_spend_cap_cents * 2)


def advanced_search_queries_used_today(app: Flask) -> int:
    start = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    with Session(get_engine(app)) as session:
        runs = session.scalars(
            select(TargetCustomerDiscoveryRun)
            .where(TargetCustomerDiscoveryRun.created_at >= start)
            .order_by(TargetCustomerDiscoveryRun.created_at)
        )
        total = 0
        for run in runs:
            try:
                filters = json.loads(run.filters_json or "{}")
            except json.JSONDecodeError:
                continue
            if isinstance(filters, dict) and filters.get("channel_key") == "advanced_web_search":
                total += int(filters.get("query_count", 0) or 0)
        failed_attempts = session.scalars(
            select(AIUsageLedger).where(
                AIUsageLedger.created_at >= start,
                AIUsageLedger.feature_name == "advanced_web_search",
                AIUsageLedger.status == "failed",
            )
        )
        total += sum(3 for _row in failed_attempts)
        return total


def _get_or_create_settings(session: Session) -> AcquisitionProviderSettings:
    settings = session.scalar(
        select(AcquisitionProviderSettings).order_by(AcquisitionProviderSettings.created_at)
    )
    if settings is None:
        settings = AcquisitionProviderSettings()
        session.add(settings)
        session.flush()
    return settings


def _settings_view(settings: AcquisitionProviderSettings) -> AcquisitionSettingsView:
    masked = f"****{settings.api_key_last4}" if settings.api_key_last4 else ""
    return AcquisitionSettingsView(
        id=settings.id,
        enabled=settings.enabled,
        provider=settings.provider,
        api_key_masked=masked,
        configured=bool(settings.api_key_encrypted or settings.provider == "fake"),
        daily_spend_cap_cents=settings.daily_spend_cap_cents,
        query_limit_per_run=settings.query_limit_per_run,
        result_limit_per_run=settings.result_limit_per_run,
        timeout_seconds=settings.timeout_seconds,
        last_tested_at=settings.last_tested_at,
        last_test_status=settings.last_test_status,
        last_error_code=settings.last_error_code,
    )


def _clamp(value: object, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(parsed, maximum))
