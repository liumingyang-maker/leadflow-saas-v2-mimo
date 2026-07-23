from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app.modules.accounts.models import AdminUser, Tenant
from app.modules.accounts.repository import session_scope


class AdminAccountError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AdminIdentity:
    admin_id: str
    email: str
    must_change_password: bool
    auth_version: int


def create_admin(
    app: Flask, *, email: str, password: str, must_change_password: bool = True
) -> AdminUser:
    clean_email = _normalize_email(email)
    _validate_admin_password(clean_email, password)
    with session_scope(app) as session:
        if session.scalar(select(AdminUser.id).where(AdminUser.email == clean_email)):
            raise AdminAccountError("email_exists", "Admin email already exists")
        admin = AdminUser(
            email=clean_email,
            password_hash=generate_password_hash(password),
            must_change_password=must_change_password,
        )
        session.add(admin)
        session.flush()
        session.expunge(admin)
        return admin


def authenticate_admin(app: Flask, *, email: str, password: str) -> AdminIdentity:
    clean_email = _normalize_email(email)
    with session_scope(app) as session:
        admin = session.scalar(select(AdminUser).where(AdminUser.email == clean_email))
        if (
            admin is None
            or admin.disabled_at is not None
            or not check_password_hash(admin.password_hash, password or "")
        ):
            raise AdminAccountError("invalid_credentials", "Email or password is incorrect")
        return AdminIdentity(
            admin_id=admin.id,
            email=admin.email,
            must_change_password=admin.must_change_password,
            auth_version=admin.auth_version,
        )


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()[:320]


def _validate_admin_password(email: str, password: str) -> None:
    if not email or "@" not in email:
        raise AdminAccountError("invalid_email", "A valid email is required")
    if len(password or "") < 12:
        raise AdminAccountError("weak_password", "Admin password must be at least 12 characters")


def list_tenants_for_admin(app: Flask) -> list[dict[str, Any]]:
    with session_scope(app) as session:
        tenants = session.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
        return [
            {
                "id": t.id,
                "company_name": t.company_name,
                "industry": t.industry,
                "status": t.status,
                "plan": t.plan,
                "onboarding_done": t.onboarding_done,
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "last_activity_at": t.last_activity_at.isoformat() if t.last_activity_at else "",
            }
            for t in tenants
        ]
