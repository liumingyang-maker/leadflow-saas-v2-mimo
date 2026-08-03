from __future__ import annotations

import hashlib
import json
from typing import Any

from app.integrations.web.url_safety import Resolver, SafeUrl, validate_public_url
from app.modules.acquisition.models import AcquisitionMission, ProductKnowledgeSnapshot

ACTIVE_MISSION_STATUSES = frozenset({"queued", "running", "paused"})


class RadarPolicyError(ValueError):
    """A proposal or state transition does not satisfy Radar policy."""


def require_active_mission(mission: AcquisitionMission) -> AcquisitionMission:
    if mission.status not in ACTIVE_MISSION_STATUSES:
        raise RadarPolicyError("Mission must be active for competitor radar")
    return mission


def require_matching_product_snapshot(
    mission: AcquisitionMission, snapshot: ProductKnowledgeSnapshot
) -> ProductKnowledgeSnapshot:
    if snapshot.tenant_id != mission.tenant_id or snapshot.id != mission.product_snapshot_id:
        raise RadarPolicyError("Mission product snapshot does not match")
    return snapshot


def canonical_public_url(url: str, *, resolver: Resolver) -> SafeUrl:
    return validate_public_url(url, resolver=resolver)


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise RadarPolicyError("Radar value must be JSON serializable") from exc


def evidence_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
