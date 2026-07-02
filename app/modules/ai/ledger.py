from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.ai.models import AIUsageLedger


def record_ai_usage(
    session: Session,
    *,
    tenant_id: str,
    user_id: str,
    feature_name: str,
    provider: str,
    model: str,
    credits_charged: int,
    input_tokens: int,
    output_tokens: int,
    status: str,
    error_code: str = "",
    latency_ms: int = 0,
) -> AIUsageLedger:
    row = AIUsageLedger(
        tenant_id=tenant_id,
        user_id=user_id,
        feature_name=feature_name,
        provider=provider,
        model=model,
        credits_charged=credits_charged,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        status=status,
        error_code=error_code[:80],
        latency_ms=latency_ms,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    return row


def used_credits_for_period(
    session: Session, *, tenant_id: str, period_start: datetime, period_end: datetime
) -> int:
    return int(
        session.scalar(
            select(func.coalesce(func.sum(AIUsageLedger.credits_charged), 0)).where(
                AIUsageLedger.tenant_id == tenant_id,
                AIUsageLedger.status == "success",
                AIUsageLedger.created_at >= period_start,
                AIUsageLedger.created_at < period_end,
            )
        )
        or 0
    )


def usage_summary(session: Session) -> dict[str, int]:
    total_calls = int(session.scalar(select(func.count(AIUsageLedger.id))) or 0)
    credits = int(
        session.scalar(select(func.coalesce(func.sum(AIUsageLedger.credits_charged), 0))) or 0
    )
    failed = int(
        session.scalar(select(func.count(AIUsageLedger.id)).where(AIUsageLedger.status == "failed"))
        or 0
    )
    blocked = int(
        session.scalar(
            select(func.count(AIUsageLedger.id)).where(AIUsageLedger.status == "blocked_quota")
        )
        or 0
    )
    return {
        "total_calls": total_calls,
        "credits": credits,
        "failed": failed,
        "blocked": blocked,
    }
