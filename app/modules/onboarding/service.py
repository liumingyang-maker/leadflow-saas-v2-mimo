from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.ai.service import (
    PRODUCT_PROFILE_ARRAY_FIELDS,
    PRODUCT_PROFILE_TEXT_FIELDS,
    ProductProfileExtractionResult,
    extract_product_profile,
)
from app.modules.onboarding.models import TenantProductProfile

RAW_FIELDS = (
    "raw_company_intro",
    "raw_products",
    "raw_website_url",
    "raw_target_markets",
    "raw_advantages",
    "raw_certificates",
    "raw_moq",
    "raw_delivery_capacity",
    "raw_customer_countries",
)
RAW_FIELD_LIMITS = {
    "raw_company_intro": 3000,
    "raw_products": 3000,
    "raw_website_url": 500,
    "raw_target_markets": 1000,
    "raw_advantages": 2000,
    "raw_certificates": 1000,
    "raw_moq": 1000,
    "raw_delivery_capacity": 1000,
    "raw_customer_countries": 1000,
}
TOTAL_INPUT_LIMIT = 9000


@dataclass(frozen=True)
class ProductProfileFormData:
    raw_fields: dict[str, str]
    extracted_profile: dict[str, object]
    website_warning: bool = False


def get_product_profile(app: Flask, *, tenant_id: str) -> TenantProductProfile | None:
    with Session(get_engine(app)) as session:
        return session.scalar(
            select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
        )


def has_confirmed_product_profile(app: Flask, *, tenant_id: str) -> bool:
    profile = get_product_profile(app, tenant_id=tenant_id)
    return profile is not None and profile.status == "confirmed"


def form_data_from_profile(profile: TenantProductProfile | None) -> ProductProfileFormData:
    if profile is None:
        return ProductProfileFormData(
            raw_fields=_empty_raw_fields(), extracted_profile=_empty_profile()
        )
    raw_fields = {key: getattr(profile, key, "") for key in RAW_FIELDS}
    return ProductProfileFormData(
        raw_fields=raw_fields,
        extracted_profile=parse_profile_json(profile.extracted_profile_json),
        website_warning=website_needs_warning(raw_fields.get("raw_website_url", "")),
    )


def extract_and_save_profile(
    app: Flask,
    *,
    tenant_id: str,
    user_id: str,
    locale: str,
    form: Any,
) -> ProductProfileExtractionResult:
    raw_fields = raw_fields_from_form(form)
    with Session(get_engine(app)) as session:
        profile = _get_or_create_profile(session, tenant_id=tenant_id)
        _apply_raw_fields(profile, raw_fields)
        profile.status = "draft"
        session.commit()

    result = extract_product_profile(
        app,
        tenant_id=tenant_id,
        user_id=user_id,
        locale=locale,
        raw_fields=raw_fields,
    )

    with Session(get_engine(app)) as session:
        profile = _get_or_create_profile(session, tenant_id=tenant_id)
        _apply_raw_fields(profile, raw_fields)
        profile.version = max(1, profile.version + 1)
        if result.success and result.profile is not None:
            profile.extracted_profile_json = json.dumps(result.profile, ensure_ascii=False)
            profile.status = "extracted"
            profile.last_extracted_at = datetime.now(UTC)
        else:
            profile.status = "failed"
        session.commit()
    return result


def confirm_profile(app: Flask, *, tenant_id: str, form: Any) -> TenantProductProfile:
    raw_fields = raw_fields_from_form(form)
    extracted_profile = extracted_profile_from_form(form)
    with Session(get_engine(app)) as session:
        profile = _get_or_create_profile(session, tenant_id=tenant_id)
        _apply_raw_fields(profile, raw_fields)
        profile.extracted_profile_json = json.dumps(extracted_profile, ensure_ascii=False)
        profile.status = "confirmed"
        profile.confirmed_at = datetime.now(UTC)
        profile.version = max(1, profile.version + 1)
        session.commit()
        return profile


def save_draft_profile(app: Flask, *, tenant_id: str, form: Any) -> TenantProductProfile:
    raw_fields = raw_fields_from_form(form)
    extracted_profile = extracted_profile_from_form(form)
    with Session(get_engine(app)) as session:
        profile = _get_or_create_profile(session, tenant_id=tenant_id)
        _apply_raw_fields(profile, raw_fields)
        profile.extracted_profile_json = json.dumps(extracted_profile, ensure_ascii=False)
        profile.status = "draft" if profile.status == "failed" else profile.status
        session.commit()
        return profile


def raw_fields_from_form(form: Any) -> dict[str, str]:
    raw = {key: _limit(str(form.get(key, "") or ""), RAW_FIELD_LIMITS[key]) for key in RAW_FIELDS}
    total = sum(len(value) for value in raw.values())
    if total <= TOTAL_INPUT_LIMIT:
        return raw

    overflow = total - TOTAL_INPUT_LIMIT
    for key in reversed(RAW_FIELDS):
        value = raw[key]
        if overflow <= 0:
            break
        trim = min(len(value), overflow)
        raw[key] = value[: len(value) - trim]
        overflow -= trim
    return raw


def extracted_profile_from_form(form: Any) -> dict[str, object]:
    profile: dict[str, object] = {}
    for key in PRODUCT_PROFILE_ARRAY_FIELDS:
        profile[key] = _textarea_to_list(str(form.get(key, "") or ""))
    for key in PRODUCT_PROFILE_TEXT_FIELDS:
        profile[key] = _limit(str(form.get(key, "") or "").strip() or "unknown", 1000)
    return profile


def parse_profile_json(value: str) -> dict[str, object]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    profile: dict[str, object] = {}
    for key in PRODUCT_PROFILE_ARRAY_FIELDS:
        raw_value = data.get(key, [])
        if isinstance(raw_value, list):
            profile[key] = [str(item) for item in raw_value]
        elif isinstance(raw_value, str):
            profile[key] = _textarea_to_list(raw_value)
        else:
            profile[key] = []
    for key in PRODUCT_PROFILE_TEXT_FIELDS:
        profile[key] = str(data.get(key, "") or "unknown")
    return profile


def profile_field_text(profile: dict[str, object], key: str) -> str:
    value = profile.get(key, [] if key in PRODUCT_PROFILE_ARRAY_FIELDS else "")
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def website_needs_warning(value: str) -> bool:
    clean = (value or "").strip().lower()
    return bool(clean) and not (clean.startswith("http://") or clean.startswith("https://"))


def _get_or_create_profile(session: Session, *, tenant_id: str) -> TenantProductProfile:
    profile = session.scalar(
        select(TenantProductProfile).where(TenantProductProfile.tenant_id == tenant_id)
    )
    if profile is None:
        profile = TenantProductProfile(tenant_id=tenant_id)
        session.add(profile)
        session.flush()
    return profile


def _apply_raw_fields(profile: TenantProductProfile, raw_fields: dict[str, str]) -> None:
    for key in RAW_FIELDS:
        setattr(profile, key, raw_fields.get(key, ""))


def _empty_raw_fields() -> dict[str, str]:
    return {key: "" for key in RAW_FIELDS}


def _empty_profile() -> dict[str, object]:
    profile: dict[str, object] = {}
    for key in PRODUCT_PROFILE_ARRAY_FIELDS:
        profile[key] = []
    for key in PRODUCT_PROFILE_TEXT_FIELDS:
        profile[key] = "unknown"
    return profile


def _textarea_to_list(value: str) -> list[str]:
    return [_limit(line.strip(), 200) for line in value.splitlines() if line.strip()]


def _limit(value: str, max_length: int) -> str:
    return value.strip()[:max_length]
