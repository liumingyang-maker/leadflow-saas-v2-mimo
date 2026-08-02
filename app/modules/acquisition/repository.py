from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.acquisition.models import (
    AcquisitionCandidate,
    AcquisitionMission,
    CandidateAssessment,
    CandidateEvidence,
    MissionSuggestion,
    Notification,
    ProductKnowledgeSnapshot,
    ProviderStatus,
)


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise ValueError("tenant_id is required")
    return clean


def _add_tenant_owned(session: Session, value, *, tenant_id: str):
    tenant_id = _require_tenant(tenant_id)
    if value.tenant_id and value.tenant_id != tenant_id:
        raise ValueError("tenant_id mismatch")
    value.tenant_id = tenant_id
    session.add(value)
    return value


class ProductKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, snapshot_id: str, *, tenant_id: str) -> ProductKnowledgeSnapshot | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(ProductKnowledgeSnapshot).where(
                ProductKnowledgeSnapshot.id == snapshot_id,
                ProductKnowledgeSnapshot.tenant_id == tenant_id,
            )
        )

    def list_latest(self, *, tenant_id: str) -> Sequence[ProductKnowledgeSnapshot]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(ProductKnowledgeSnapshot)
            .where(ProductKnowledgeSnapshot.tenant_id == tenant_id)
            .order_by(
                ProductKnowledgeSnapshot.product_name,
                ProductKnowledgeSnapshot.created_at.desc(),
                ProductKnowledgeSnapshot.version.desc(),
            )
        )
        latest: list[ProductKnowledgeSnapshot] = []
        seen_products: set[str] = set()
        for snapshot in self.session.scalars(query):
            if snapshot.product_name in seen_products:
                continue
            seen_products.add(snapshot.product_name)
            latest.append(snapshot)
        return latest

    def add(
        self, snapshot: ProductKnowledgeSnapshot, *, tenant_id: str
    ) -> ProductKnowledgeSnapshot:
        return _add_tenant_owned(self.session, snapshot, tenant_id=tenant_id)


class MissionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, mission_id: str, *, tenant_id: str) -> AcquisitionMission | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(AcquisitionMission).where(
                AcquisitionMission.id == mission_id,
                AcquisitionMission.tenant_id == tenant_id,
            )
        )

    def list_by_status(
        self, statuses: Sequence[str], *, tenant_id: str
    ) -> Sequence[AcquisitionMission]:
        tenant_id = _require_tenant(tenant_id)
        if not statuses:
            return []
        query = (
            select(AcquisitionMission)
            .where(
                AcquisitionMission.tenant_id == tenant_id,
                AcquisitionMission.status.in_(statuses),
            )
            .order_by(AcquisitionMission.created_at.desc())
        )
        return list(self.session.scalars(query))

    def oldest_id_with_candidate_status(self, status: str, *, tenant_id: str) -> str | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(AcquisitionMission.id)
            .join(
                AcquisitionCandidate,
                AcquisitionCandidate.mission_id == AcquisitionMission.id,
            )
            .where(
                AcquisitionMission.tenant_id == tenant_id,
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.status == status,
            )
            .order_by(AcquisitionMission.created_at.asc(), AcquisitionMission.id.asc())
            .limit(1)
        )

    def add(self, mission: AcquisitionMission, *, tenant_id: str) -> AcquisitionMission:
        return _add_tenant_owned(self.session, mission, tenant_id=tenant_id)

    def update_status(
        self, mission_id: str, status: str, *, tenant_id: str
    ) -> AcquisitionMission | None:
        mission = self.get(mission_id, tenant_id=tenant_id)
        if mission is not None:
            mission.status = status
        return mission


class CandidateRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, candidate_id: str, *, tenant_id: str) -> AcquisitionCandidate | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(AcquisitionCandidate).where(
                AcquisitionCandidate.id == candidate_id,
                AcquisitionCandidate.tenant_id == tenant_id,
            )
        )

    def list_for_mission(
        self, mission_id: str, *, tenant_id: str
    ) -> Sequence[AcquisitionCandidate]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.mission_id == mission_id,
                AcquisitionCandidate.tenant_id == tenant_id,
            )
            .order_by(AcquisitionCandidate.created_at.desc())
        )
        return list(self.session.scalars(query))

    def list_by_status(
        self, statuses: Sequence[str], *, tenant_id: str
    ) -> Sequence[AcquisitionCandidate]:
        tenant_id = _require_tenant(tenant_id)
        if not statuses:
            return []
        query = (
            select(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.status.in_(statuses),
            )
            .order_by(AcquisitionCandidate.created_at.desc())
        )
        return list(self.session.scalars(query))

    def statuses_by_ids(self, candidate_ids: Sequence[str], *, tenant_id: str) -> dict[str, str]:
        tenant_id = _require_tenant(tenant_id)
        if not candidate_ids:
            return {}
        rows = self.session.execute(
            select(AcquisitionCandidate.id, AcquisitionCandidate.status).where(
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.id.in_(candidate_ids),
            )
        ).all()
        return dict(rows)

    def mark_verifying_if_needs_evidence(self, candidate_id: str, *, tenant_id: str) -> bool:
        """Atomically claim one candidate for a user-requested verification retry."""

        tenant_id = _require_tenant(tenant_id)
        result = self.session.execute(
            update(AcquisitionCandidate)
            .where(
                AcquisitionCandidate.id == candidate_id,
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.status == "needs_evidence",
            )
            .values(status="verifying")
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1

    def find_by_dedupe_key(
        self, mission_id: str, dedupe_key: str, *, tenant_id: str
    ) -> AcquisitionCandidate | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(AcquisitionCandidate).where(
                AcquisitionCandidate.mission_id == mission_id,
                AcquisitionCandidate.dedupe_key == dedupe_key,
                AcquisitionCandidate.tenant_id == tenant_id,
            )
        )

    def add(self, candidate: AcquisitionCandidate, *, tenant_id: str) -> AcquisitionCandidate:
        return _add_tenant_owned(self.session, candidate, tenant_id=tenant_id)


class EvidenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_candidate(
        self, candidate_id: str, *, tenant_id: str
    ) -> Sequence[CandidateEvidence]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(CandidateEvidence)
            .where(
                CandidateEvidence.candidate_id == candidate_id,
                CandidateEvidence.tenant_id == tenant_id,
            )
            .order_by(CandidateEvidence.retrieved_at.desc())
        )
        return list(self.session.scalars(query))

    def find_content(
        self,
        candidate_id: str,
        canonical_url: str,
        content_hash: str,
        *,
        tenant_id: str,
    ) -> CandidateEvidence | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(CandidateEvidence).where(
                CandidateEvidence.candidate_id == candidate_id,
                CandidateEvidence.canonical_url == canonical_url,
                CandidateEvidence.content_hash == content_hash,
                CandidateEvidence.tenant_id == tenant_id,
            )
        )

    def add(self, evidence: CandidateEvidence, *, tenant_id: str) -> CandidateEvidence:
        return _add_tenant_owned(self.session, evidence, tenant_id=tenant_id)


class AssessmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def latest_for_candidate(
        self, candidate_id: str, *, tenant_id: str
    ) -> CandidateAssessment | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(CandidateAssessment)
            .where(
                CandidateAssessment.candidate_id == candidate_id,
                CandidateAssessment.tenant_id == tenant_id,
            )
            .order_by(CandidateAssessment.created_at.desc())
            .limit(1)
        )

    def find_input_version(
        self,
        candidate_id: str,
        evidence_bundle_hash: str,
        policy_version: str,
        score_version: str,
        prompt_version: str,
        model_id: str,
        *,
        tenant_id: str,
    ) -> CandidateAssessment | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(CandidateAssessment).where(
                CandidateAssessment.candidate_id == candidate_id,
                CandidateAssessment.evidence_bundle_hash == evidence_bundle_hash,
                CandidateAssessment.policy_version == policy_version,
                CandidateAssessment.score_version == score_version,
                CandidateAssessment.prompt_version == prompt_version,
                CandidateAssessment.model_id == model_id,
                CandidateAssessment.tenant_id == tenant_id,
            )
        )

    def add(self, assessment: CandidateAssessment, *, tenant_id: str) -> CandidateAssessment:
        return _add_tenant_owned(self.session, assessment, tenant_id=tenant_id)


class SuggestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_mission(self, mission_id: str, *, tenant_id: str) -> Sequence[MissionSuggestion]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(MissionSuggestion)
            .where(
                MissionSuggestion.mission_id == mission_id,
                MissionSuggestion.tenant_id == tenant_id,
            )
            .order_by(MissionSuggestion.created_at.desc())
        )
        return list(self.session.scalars(query))

    def find_by_dedupe_key(self, dedupe_key: str, *, tenant_id: str) -> MissionSuggestion | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(MissionSuggestion).where(
                MissionSuggestion.dedupe_key == dedupe_key,
                MissionSuggestion.tenant_id == tenant_id,
            )
        )

    def add(self, suggestion: MissionSuggestion, *, tenant_id: str) -> MissionSuggestion:
        return _add_tenant_owned(self.session, suggestion, tenant_id=tenant_id)

    def set_status(
        self, suggestion_id: str, status: str, *, tenant_id: str
    ) -> MissionSuggestion | None:
        tenant_id = _require_tenant(tenant_id)
        suggestion = self.session.scalar(
            select(MissionSuggestion).where(
                MissionSuggestion.id == suggestion_id,
                MissionSuggestion.tenant_id == tenant_id,
            )
        )
        if suggestion is not None:
            suggestion.status = status
        return suggestion


class NotificationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, notification_id: str, *, tenant_id: str) -> Notification | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
                Notification.tenant_id == tenant_id,
            )
        )

    def list_unread(self, *, tenant_id: str) -> Sequence[Notification]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(Notification)
            .where(
                Notification.tenant_id == tenant_id,
                Notification.status == "unread",
            )
            .order_by(Notification.created_at.desc())
        )
        return list(self.session.scalars(query))

    def find_by_dedupe_key(self, dedupe_key: str, *, tenant_id: str) -> Notification | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(Notification).where(
                Notification.dedupe_key == dedupe_key,
                Notification.tenant_id == tenant_id,
            )
        )

    def add(self, notification: Notification, *, tenant_id: str) -> Notification:
        return _add_tenant_owned(self.session, notification, tenant_id=tenant_id)

    def mark_read(self, notification_id: str, *, tenant_id: str) -> Notification | None:
        notification = self.get(notification_id, tenant_id=tenant_id)
        if notification is not None:
            notification.status = "read"
            notification.read_at = datetime.now(UTC)
        return notification


class ProviderStatusRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, provider: str, *, tenant_id: str) -> ProviderStatus | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(ProviderStatus).where(
                ProviderStatus.provider == provider,
                ProviderStatus.tenant_id == tenant_id,
            )
        )

    def record_success(self, provider: str, now: datetime, *, tenant_id: str) -> ProviderStatus:
        status = self.get(provider, tenant_id=tenant_id)
        if status is None:
            status = self.add(ProviderStatus(provider=provider), tenant_id=tenant_id)
        status.status = "healthy"
        status.consecutive_failures = 0
        status.error_code = ""
        status.last_checked_at = now
        status.last_success_at = now
        return status

    def record_failure(
        self, provider: str, error_code: str, now: datetime, *, tenant_id: str
    ) -> ProviderStatus:
        status = self.get(provider, tenant_id=tenant_id)
        if status is None:
            status = self.add(
                ProviderStatus(provider=provider, consecutive_failures=0),
                tenant_id=tenant_id,
            )
        status.consecutive_failures = (status.consecutive_failures or 0) + 1
        status.status = "failed" if status.consecutive_failures >= 3 else "degraded"
        status.error_code = error_code
        status.last_checked_at = now
        return status

    def add(self, status: ProviderStatus, *, tenant_id: str) -> ProviderStatus:
        return _add_tenant_owned(self.session, status, tenant_id=tenant_id)
