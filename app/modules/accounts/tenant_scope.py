from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session


class TenantScopeError(ValueError):
    pass


@dataclass(frozen=True)
class TenantIdentity:
    tenant_id: str
    user_id: str
    email: str


class TenantScopedRepository:
    def __init__(self, session: Session, model: type[Any]) -> None:
        if not hasattr(model, "tenant_id"):
            raise TenantScopeError(f"{model.__name__} is not tenant scoped")
        if not hasattr(model, "id"):
            raise TenantScopeError(f"{model.__name__} must expose an id column")
        self.session = session
        self.model = model

    def get(self, item_id: str, *, tenant_id: str) -> Any | None:
        tenant_id = _require_tenant_id(tenant_id)
        return self.session.scalar(
            select(self.model).where(
                self.model.id == item_id,
                self.model.tenant_id == tenant_id,
            )
        )

    def list(self, *, tenant_id: str) -> list[Any]:
        tenant_id = _require_tenant_id(tenant_id)
        query = select(self.model).where(self.model.tenant_id == tenant_id)
        return list(self.session.scalars(query))

    def add(self, instance: Any, *, tenant_id: str) -> Any:
        tenant_id = _require_tenant_id(tenant_id)
        tenant_scoped = cast(Any, instance)
        instance_tenant_id = tenant_scoped.tenant_id
        if instance_tenant_id in {None, ""}:
            tenant_scoped.tenant_id = tenant_id
        elif instance_tenant_id != tenant_id:
            raise TenantScopeError("tenant_id mismatch")
        self.session.add(instance)
        return instance


def current_tenant_identity(session_data: dict[str, Any]) -> TenantIdentity:
    tenant_id = _require_tenant_id(str(session_data.get("tenant_id") or ""))
    user_id = str(session_data.get("user_id") or "")
    if not user_id:
        raise TenantScopeError("user_id is required")
    return TenantIdentity(
        tenant_id=tenant_id,
        user_id=user_id,
        email=str(session_data.get("tenant_email") or ""),
    )


def _require_tenant_id(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise TenantScopeError("tenant_id is required")
    return clean
