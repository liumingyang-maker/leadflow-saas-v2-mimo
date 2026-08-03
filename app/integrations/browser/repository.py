from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.integrations.browser.models import BrowserResearchRun, BrowserSitePolicy, redact_url_query


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise ValueError("tenant_id is required")
    return clean


class BrowserSitePolicyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, policy_id: str, *, tenant_id: str) -> BrowserSitePolicy | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(BrowserSitePolicy).where(
                BrowserSitePolicy.id == policy_id,
                BrowserSitePolicy.tenant_id == tenant_id,
            )
        )

    def get_by_domain(self, canonical_domain: str, *, tenant_id: str) -> BrowserSitePolicy | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(BrowserSitePolicy).where(
                BrowserSitePolicy.canonical_domain == canonical_domain,
                BrowserSitePolicy.tenant_id == tenant_id,
            )
        )


class BrowserRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, run_id: str, *, tenant_id: str) -> BrowserResearchRun | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(BrowserResearchRun).where(
                BrowserResearchRun.id == run_id,
                BrowserResearchRun.tenant_id == tenant_id,
            )
        )

    def list_for_owner(
        self, *, tenant_id: str, owner_type: str, owner_id: str
    ) -> Sequence[BrowserResearchRun]:
        tenant_id = _require_tenant(tenant_id)
        return list(
            self.session.scalars(
                select(BrowserResearchRun)
                .where(
                    BrowserResearchRun.tenant_id == tenant_id,
                    BrowserResearchRun.owner_type == owner_type,
                    BrowserResearchRun.owner_id == owner_id,
                )
                .order_by(BrowserResearchRun.created_at.desc(), BrowserResearchRun.id.desc())
            )
        )

    def claim(self, run_id: str, *, tenant_id: str, lease_seconds: int) -> int | None:
        tenant_id = _require_tenant(tenant_id)
        bounded_lease = max(1, min(int(lease_seconds), 600))
        now = datetime.now(UTC)
        result = self.session.execute(
            update(BrowserResearchRun)
            .where(
                BrowserResearchRun.id == run_id,
                BrowserResearchRun.tenant_id == tenant_id,
                BrowserResearchRun.status == "queued",
                or_(
                    BrowserResearchRun.lease_expires_at.is_(None),
                    BrowserResearchRun.lease_expires_at < now,
                ),
            )
            .values(
                status="running",
                attempt=BrowserResearchRun.attempt + 1,
                started_at=now,
                heartbeat_at=now,
                lease_expires_at=now + timedelta(seconds=bounded_lease),
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount != 1:
            return None
        run = self.get(run_id, tenant_id=tenant_id)
        return None if run is None else run.attempt

    def complete(
        self,
        run_id: str,
        *,
        tenant_id: str,
        attempt: int,
        run_token_digest: str,
        status: str,
        result_json: str,
        artifact_manifest_json: str,
        final_url: str = "",
    ) -> bool:
        tenant_id = _require_tenant(tenant_id)
        if status not in {"completed", "partial", "blocked", "failed"}:
            raise ValueError("invalid terminal Browser Run status")
        if len(result_json) > 100_000 or len(artifact_manifest_json) > 100_000:
            raise ValueError("browser result exceeds storage limit")
        now = datetime.now(UTC)
        result = self.session.execute(
            update(BrowserResearchRun)
            .where(
                BrowserResearchRun.id == run_id,
                BrowserResearchRun.tenant_id == tenant_id,
                BrowserResearchRun.status == "running",
                BrowserResearchRun.attempt == attempt,
                BrowserResearchRun.run_token_digest == run_token_digest,
            )
            .values(
                status=status,
                result_json=result_json,
                artifact_manifest_json=artifact_manifest_json,
                final_url=redact_url_query(final_url),
                finished_at=now,
                lease_expires_at=None,
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    def mark_enqueue_failed(self, run_id: str, *, tenant_id: str) -> bool:
        tenant_id = _require_tenant(tenant_id)
        now = datetime.now(UTC)
        result = self.session.execute(
            update(BrowserResearchRun)
            .where(
                BrowserResearchRun.id == run_id,
                BrowserResearchRun.tenant_id == tenant_id,
                BrowserResearchRun.status.in_(("queued", "running")),
            )
            .values(
                status="failed",
                error_code="browser_transport_unavailable",
                error_summary="Browser transport was unavailable after persistence.",
                finished_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    def cancel(self, run_id: str, *, tenant_id: str) -> BrowserResearchRun | None:
        tenant_id = _require_tenant(tenant_id)
        run = self.get(run_id, tenant_id=tenant_id)
        if run is None or run.status not in {"queued", "running"}:
            return None
        now = datetime.now(UTC)
        result = self.session.execute(
            update(BrowserResearchRun)
            .where(
                BrowserResearchRun.id == run_id,
                BrowserResearchRun.tenant_id == tenant_id,
                BrowserResearchRun.status.in_(("queued", "running")),
            )
            .values(
                status="cancelled",
                error_code="cancelled",
                error_summary="Browser research was cancelled.",
                finished_at=now,
                lease_expires_at=None,
                updated_at=now,
            )
            .execution_options(synchronize_session="fetch")
        )
        return run if result.rowcount == 1 else None
