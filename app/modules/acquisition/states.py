"""State invariants shared by acquisition services and workers."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.acquisition.models import AcquisitionCandidate

HUMAN_TERMINAL_STATUSES = frozenset({"accepted", "promoted", "rejected"})
USABLE_CANDIDATE_STATUSES = frozenset({"eligible", "accepted", "promoted"})
_HUMAN_DECISION_FIELDS = (
    "status",
    "eligibility_code",
    "decision_reason_code",
    "decided_by",
    "decided_at",
)


def update_assessment_state_if_mutable(
    session: Session,
    candidate: AcquisitionCandidate,
    *,
    tenant_id: str,
    status: str,
    eligibility_code: str,
) -> str:
    """Atomically apply an automated decision unless a human decision already won."""
    session.flush()
    result = session.execute(
        update(AcquisitionCandidate)
        .where(
            AcquisitionCandidate.id == candidate.id,
            AcquisitionCandidate.tenant_id == tenant_id,
            AcquisitionCandidate.status.not_in(HUMAN_TERMINAL_STATUSES),
        )
        .values(status=status, eligibility_code=eligibility_code),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount not in {0, 1}:
        raise RuntimeError("candidate assessment state update affected unexpected rows")
    session.refresh(candidate, attribute_names=list(_HUMAN_DECISION_FIELDS))
    return candidate.status
