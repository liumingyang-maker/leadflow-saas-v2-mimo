from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.radar.models import CompetitorProfile, RadarCompetitorSuggestion


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise ValueError("tenant_id is required")
    return clean


def _add_tenant_owned(
    session: Session,
    value: CompetitorProfile | RadarCompetitorSuggestion,
    *,
    tenant_id: str,
) -> CompetitorProfile | RadarCompetitorSuggestion:
    tenant_id = _require_tenant(tenant_id)
    if value.tenant_id and value.tenant_id != tenant_id:
        raise ValueError("tenant_id mismatch")
    value.tenant_id = tenant_id
    session.add(value)
    return value


class RadarSuggestionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, suggestion_id: str, *, tenant_id: str) -> RadarCompetitorSuggestion | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(RadarCompetitorSuggestion).where(
                RadarCompetitorSuggestion.id == suggestion_id,
                RadarCompetitorSuggestion.tenant_id == tenant_id,
            )
        )

    def get_by_mission_domain(
        self, mission_id: str, canonical_domain: str, *, tenant_id: str
    ) -> RadarCompetitorSuggestion | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(RadarCompetitorSuggestion).where(
                RadarCompetitorSuggestion.tenant_id == tenant_id,
                RadarCompetitorSuggestion.mission_id == mission_id,
                RadarCompetitorSuggestion.canonical_domain == canonical_domain,
            )
        )

    def list_for_mission(
        self, mission_id: str, *, tenant_id: str
    ) -> Sequence[RadarCompetitorSuggestion]:
        tenant_id = _require_tenant(tenant_id)
        return list(
            self.session.scalars(
                select(RadarCompetitorSuggestion)
                .where(
                    RadarCompetitorSuggestion.tenant_id == tenant_id,
                    RadarCompetitorSuggestion.mission_id == mission_id,
                )
                .order_by(
                    RadarCompetitorSuggestion.created_at.desc(),
                    RadarCompetitorSuggestion.id.desc(),
                )
            )
        )

    def add(
        self, suggestion: RadarCompetitorSuggestion, *, tenant_id: str
    ) -> RadarCompetitorSuggestion:
        return _add_tenant_owned(self.session, suggestion, tenant_id=tenant_id)


class CompetitorProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, profile_id: str, *, tenant_id: str) -> CompetitorProfile | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(CompetitorProfile).where(
                CompetitorProfile.id == profile_id,
                CompetitorProfile.tenant_id == tenant_id,
            )
        )

    def get_by_mission_domain(
        self, mission_id: str, canonical_domain: str, *, tenant_id: str
    ) -> CompetitorProfile | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(
            select(CompetitorProfile).where(
                CompetitorProfile.tenant_id == tenant_id,
                CompetitorProfile.mission_id == mission_id,
                CompetitorProfile.canonical_domain == canonical_domain,
            )
        )

    def list_for_tenant(self, *, tenant_id: str) -> Sequence[CompetitorProfile]:
        tenant_id = _require_tenant(tenant_id)
        return list(
            self.session.scalars(
                select(CompetitorProfile)
                .where(CompetitorProfile.tenant_id == tenant_id)
                .order_by(CompetitorProfile.created_at.desc(), CompetitorProfile.id.desc())
            )
        )

    def list_for_mission(self, mission_id: str, *, tenant_id: str) -> Sequence[CompetitorProfile]:
        tenant_id = _require_tenant(tenant_id)
        return list(
            self.session.scalars(
                select(CompetitorProfile)
                .where(
                    CompetitorProfile.tenant_id == tenant_id,
                    CompetitorProfile.mission_id == mission_id,
                )
                .order_by(CompetitorProfile.created_at.desc(), CompetitorProfile.id.desc())
            )
        )

    def add(self, profile: CompetitorProfile, *, tenant_id: str) -> CompetitorProfile:
        return _add_tenant_owned(self.session, profile, tenant_id=tenant_id)
