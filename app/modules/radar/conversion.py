"""Radar-to-Acquisition boundary adapter with no direct Candidate writes."""

from __future__ import annotations


def convert_confirmed_relationship(
    app,
    *,
    tenant_id: str,
    actor_id: str,
    mission_id: str,
    relationship_id: str,
    expected_domain: str,
):
    from app.modules.acquisition.service import create_candidate_from_radar_relationship

    return create_candidate_from_radar_relationship(
        app,
        tenant_id=tenant_id,
        actor_id=actor_id,
        mission_id=mission_id,
        relationship_id=relationship_id,
        expected_domain=expected_domain,
    )
