from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import Flask
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.i18n import get_locale, localized_email_text
from app.modules.accounts.models import EmailToken, Tenant, TenantMembership, User
from app.modules.accounts.repository import session_scope
from app.modules.outreach.mailer import get_mailer

LOGGER = logging.getLogger(__name__)
VERIFY_TOKEN_TTL = timedelta(hours=24)


class AccountError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LoginIdentity:
    user_id: str
    tenant_id: str
    email: str


def register_account(app: Flask, *, email: str, password: str, company_name: str) -> EmailToken:
    clean_email = _normalize_email(email)
    clean_company = (company_name or "").strip()[:200]
    _validate_registration(clean_email, password)

    with session_scope(app) as session:
        if session.scalar(select(User.id).where(User.email == clean_email)):
            raise AccountError("email_exists", "Email is already registered")

        tenant = Tenant(company_name=clean_company)
        user = User(email=clean_email, password_hash=generate_password_hash(password))
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        token = EmailToken(
            tenant=tenant,
            email=clean_email,
            token_type="verify",
            expires_at=_verification_token_expires_at(),
        )
        session.add(token)
        session.flush()
        session.expunge(token)
    _send_verification_email(app, email=clean_email, token=token.token)
    return token


def verify_email(app: Flask, token: str) -> None:
    if not token or len(token) > 128:
        raise AccountError("invalid_token", "Verification link is invalid")

    with session_scope(app) as session:
        email_token = session.get(EmailToken, token)
        if (
            email_token is None
            or email_token.token_type != "verify"
            or email_token.used_at is not None
            or _is_expired(email_token.expires_at)
        ):
            raise AccountError("invalid_token", "Verification link is invalid")

        user = session.scalar(select(User).where(User.email == email_token.email))
        if user is None:
            raise AccountError("invalid_token", "Verification link is invalid")

        now = _now()
        user.email_verified_at = now
        email_token.used_at = now


def request_password_reset(app: Flask, *, email: str) -> EmailToken | None:
    clean_email = _normalize_email(email)
    with session_scope(app) as session:
        user = session.scalar(select(User).where(User.email == clean_email))
        if user is None:
            return None
        membership = session.scalar(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        if membership is None:
            return None
        token = EmailToken(tenant_id=membership.tenant_id, email=user.email, token_type="reset")
        session.add(token)
        session.flush()
        session.expunge(token)
    _send_password_reset_email(app, email=clean_email, token=token.token)
    return token


def resend_verification_email(app: Flask, *, email: str) -> EmailToken | None:
    clean_email = _normalize_email(email)
    if not clean_email:
        return None

    with session_scope(app) as session:
        user = session.scalar(select(User).where(User.email == clean_email))
        if user is None or user.email_verified_at is not None:
            return None
        membership = session.scalar(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        if membership is None:
            return None

        now = _now()
        old_tokens = session.scalars(
            select(EmailToken).where(
                EmailToken.email == clean_email,
                EmailToken.token_type == "verify",
                EmailToken.used_at.is_(None),
            )
        ).all()
        for old_token in old_tokens:
            old_token.used_at = now
            old_token.expires_at = now

        token = EmailToken(
            tenant_id=membership.tenant_id,
            email=clean_email,
            token_type="verify",
            expires_at=_verification_token_expires_at(),
        )
        session.add(token)
        session.flush()
        session.expunge(token)

    try:
        _send_verification_email(app, email=clean_email, token=token.token)
    except AccountError:
        LOGGER.warning("Verification email resend failed")
        raise
    return token


def reset_password(app: Flask, *, token: str, password: str) -> None:
    if not token or len(token) > 128:
        raise AccountError("invalid_token", "Reset link is invalid")
    if len(password or "") < 8:
        raise AccountError("weak_password", "Password must be at least 8 characters")

    with session_scope(app) as session:
        email_token = session.get(EmailToken, token)
        if (
            email_token is None
            or email_token.token_type != "reset"
            or email_token.used_at is not None
            or _is_expired(email_token.expires_at)
        ):
            raise AccountError("invalid_token", "Reset link is invalid")

        user = session.scalar(select(User).where(User.email == email_token.email))
        if user is None:
            raise AccountError("invalid_token", "Reset link is invalid")

        user.password_hash = generate_password_hash(password)
        email_token.used_at = _now()


def authenticate(app: Flask, *, email: str, password: str) -> LoginIdentity:
    clean_email = _normalize_email(email)
    with session_scope(app) as session:
        user = session.scalar(select(User).where(User.email == clean_email))
        if user is None or not check_password_hash(user.password_hash, password or ""):
            raise AccountError("invalid_credentials", "Email or password is incorrect")
        if user.email_verified_at is None:
            raise AccountError("verification_required", "Email verification required")
        membership = session.scalar(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        if membership is None or membership.tenant.status == "suspended":
            raise AccountError("account_unavailable", "Account is unavailable")

        now = _now()
        user.last_login_at = now
        membership.tenant.last_activity_at = now
        session.flush()
        return LoginIdentity(user_id=user.id, tenant_id=membership.tenant_id, email=user.email)


def complete_onboarding(app: Flask, *, tenant_id: str, industry: str) -> None:
    clean_industry = (industry or "").strip()[:120]
    if not clean_industry:
        raise AccountError("industry_required", "Industry is required to complete onboarding")
    with session_scope(app) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise AccountError("not_found", "Tenant not found")
        tenant.industry = clean_industry
        tenant.onboarding_done = True
        tenant.trial_ends_at = _now() + timedelta(days=14)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()[:320]


def _validate_registration(email: str, password: str) -> None:
    if not email or "@" not in email:
        raise AccountError("invalid_email", "A valid email is required")
    if len(password or "") < 8:
        raise AccountError("weak_password", "Password must be at least 8 characters")


def _send_verification_email(app: Flask, *, email: str, token: str) -> None:
    link = _account_url(app, f"/verify-email/{token}")
    locale = get_locale()
    result = get_mailer().send(
        to_email=email,
        subject=localized_email_text("Verify your LeadFlow email", locale),
        body_text=localized_email_text(
            "verification_email_body",
            locale,
            link=link,
        ),
        body_html="",
    )
    if not result.success:
        raise AccountError("email_send_failed", "Verification email could not be sent")


def _send_password_reset_email(app: Flask, *, email: str, token: str) -> None:
    link = _account_url(app, f"/reset-password/{token}")
    locale = get_locale()
    result = get_mailer().send(
        to_email=email,
        subject=localized_email_text("Reset your LeadFlow password", locale),
        body_text=localized_email_text(
            "password_reset_email_body",
            locale,
            link=link,
        ),
        body_html="",
    )
    if not result.success:
        raise AccountError("email_send_failed", "Password reset email could not be sent")


def _account_url(app: Flask, path: str) -> str:
    base_url = str(app.config.get("ACCOUNT_EMAIL_BASE_URL") or "").rstrip("/")
    if not base_url:
        server_name = app.config.get("SERVER_NAME")
        base_url = f"https://{server_name}" if server_name else "http://localhost"
    return f"{base_url}{path}"


def _now() -> datetime:
    return datetime.now(UTC)


def _verification_token_expires_at() -> datetime:
    return _now() + VERIFY_TOKEN_TTL


def _is_expired(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= _now()
