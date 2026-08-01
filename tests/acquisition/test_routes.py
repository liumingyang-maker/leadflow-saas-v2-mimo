from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session


def _actor_id(client) -> str:
    with client.session_transaction() as browser_session:
        return str(browser_session["user_id"])


def _seed_product(app, *, tenant_id: str, actor_id: str, name: str = "Motor parts"):
    from app.modules.acquisition.service import create_product_snapshot

    return create_product_snapshot(
        app,
        tenant_id=tenant_id,
        actor_id=actor_id,
        product_name=name,
        summary="Replacement parts for motorcycle distributors.",
        facts=[{"category": "motorcycle replacement parts"}],
        prohibited_claims=["Do not claim an exclusive territory"],
    )


def _seed_mission(app, *, tenant_id: str, actor_id: str):
    from app.modules.acquisition.contracts import MissionCreateInput
    from app.modules.acquisition.service import create_mission

    product = _seed_product(app, tenant_id=tenant_id, actor_id=actor_id)
    return create_mission(
        app,
        tenant_id=tenant_id,
        actor_id=actor_id,
        value=MissionCreateInput(
            product_snapshot_id=product.id,
            country_codes=["MX"],
            buyer_types=["distributor"],
        ),
    )


def _seed_candidate(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    suffix: str,
    status: str = "eligible",
    country_status: str = "confirmed",
):
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate

    with Session(get_engine(app)) as db_session:
        candidate = AcquisitionCandidate(
            tenant_id=tenant_id,
            mission_id=mission_id,
            status=status,
            company_name=f"Distribuidora {suffix}",
            domain=f"{suffix}.example",
            website=f"https://{suffix}.example",
            opportunity_country_code="MX",
            country_resolution_status=country_status,
            source_channel="mimo_web",
            source_provider="mimo",
            priority_score=82,
            priority_band="A",
            signal_coverage=75,
            ai_confidence=78,
            eligibility_code=("eligible" if status == "eligible" else "missing_contact_path"),
            observed_facts_json=json.dumps(
                [{"claim_id": "claim-1", "field": "buyer_type", "value": "distributor"}]
            ),
            inferences_json=json.dumps([{"field": "fit", "value": "strong"}]),
            unknowns_json=json.dumps(["decision maker email"]),
            contact_json=json.dumps({"email": f"buyer@{suffix}.example"}),
            dedupe_key=f"domain:{suffix}.example",
        )
        db_session.add(candidate)
        db_session.commit()
        return SimpleNamespace(id=candidate.id)


def test_acquisition_routes_require_login(acquisition_app) -> None:
    client = acquisition_app.test_client()

    response = client.get("/acquisition/products")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_mission_form_exposes_three_required_business_fields(logged_in_client) -> None:
    client, _tenant_id = logged_in_client

    response = client.get("/acquisition/missions/new")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    first_layer = html.split('data-advanced="true"')[0]
    assert 'name="product_snapshot_id"' in first_layer
    assert 'name="country_codes"' in first_layer
    assert 'name="buyer_types"' in first_layer
    assert 'name="languages"' not in first_layer


def test_product_post_creates_append_only_snapshot(acquisition_app, logged_in_client) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import ProductKnowledgeSnapshot

    client, tenant_id = logged_in_client
    payload = {
        "product_name": "Motor parts",
        "summary": "Parts for independent motorcycle distributors",
        "facts": "category: replacement parts\nmaterial: aluminium",
        "prohibited_claims": "exclusive distributor\nguaranteed revenue",
    }

    first = client.post("/acquisition/products", data=payload)
    second = client.post("/acquisition/products", data=payload)

    assert first.status_code in {302, 303}
    assert second.status_code in {302, 303}
    with Session(get_engine(acquisition_app)) as db_session:
        snapshots = list(
            db_session.scalars(
                select(ProductKnowledgeSnapshot)
                .where(ProductKnowledgeSnapshot.tenant_id == tenant_id)
                .order_by(ProductKnowledgeSnapshot.version)
            )
        )
    assert [item.version for item in snapshots] == ["v1", "v2"]
    assert snapshots[0].id != snapshots[1].id


def test_mission_post_creates_draft_and_derives_languages(
    acquisition_app, logged_in_client
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission

    client, tenant_id = logged_in_client
    product = _seed_product(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    response = client.post(
        "/acquisition/missions/new",
        data={
            "product_snapshot_id": product.id,
            "country_codes": ["MX", "BR"],
            "buyer_types": ["distributor"],
        },
    )

    assert response.status_code in {302, 303}
    assert "/acquisition/missions/" in response.headers["Location"]
    with Session(get_engine(acquisition_app)) as db_session:
        mission = db_session.scalars(
            select(AcquisitionMission).where(AcquisitionMission.tenant_id == tenant_id)
        ).one()
        target_profile = json.loads(mission.target_profile_json)
    assert mission.status == "draft"
    assert target_profile["languages"] == {"BR": ["pt"], "MX": ["es"]}


def test_invalid_mission_preserves_values_and_shows_text_error(
    acquisition_app, logged_in_client
) -> None:
    client, tenant_id = logged_in_client
    product = _seed_product(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    response = client.post(
        "/acquisition/missions/new",
        data={
            "product_snapshot_id": product.id,
            "country_codes": "ZZ",
            "buyer_types": "distributor",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert 'id="form-errors"' in html
    assert 'value="ZZ"' in html
    assert "无法创建任务" in html


def test_start_queues_exact_mission_and_changes_status(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    calls: list[dict[str, object]] = []

    def fake_enqueue(_app, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="job-1")

    monkeypatch.setattr("app.modules.acquisition.routes.create_and_enqueue", fake_enqueue)

    response = client.post(f"/acquisition/missions/{mission.id}/start")

    assert response.status_code in {302, 303}
    assert calls == [
        {
            "tenant_id": tenant_id,
            "job_type": "acquisition_plan",
            "payload": {"mission_id": mission.id},
        }
    ]
    with Session(get_engine(acquisition_app)) as db_session:
        stored = db_session.get(AcquisitionMission, mission.id)
        assert stored is not None
        assert stored.status == "queued"


def test_tenant_cannot_view_other_candidate(
    acquisition_app, logged_in_client, seed_acquisition_mission
) -> None:
    client, _tenant_id = logged_in_client
    mission_id = seed_acquisition_mission(tenant_id="other-tenant", suffix="other")
    candidate = _seed_candidate(
        acquisition_app,
        tenant_id="other-tenant",
        mission_id=mission_id,
        suffix="private",
    )

    response = client.get(f"/acquisition/candidates/{candidate.id}")

    assert response.status_code == 404


def test_candidate_detail_uses_progressive_disclosure(acquisition_app, logged_in_client) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    candidate = _seed_candidate(
        acquisition_app,
        tenant_id=tenant_id,
        mission_id=mission.id,
        suffix="visible",
    )

    response = client.get(f"/acquisition/candidates/{candidate.id}")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    first_layer = html.split("证据、评分和未知项")[0]
    assert "Distribuidora visible" in first_layer
    assert "为什么推荐" in first_layer
    assert "TrustTier" not in first_layer
    assert "ScoreVersion" not in first_layer
    assert 'rel="noopener noreferrer"' in html


def test_reject_requires_csrf_when_enabled(csrf_client) -> None:
    client, _tenant_id = csrf_client

    response = client.post(
        "/acquisition/candidates/not-present/review",
        data={"action": "reject", "reason_code": "wrong_buyer_type"},
    )

    assert response.status_code == 400


def test_bulk_accept_is_atomic_when_any_candidate_is_ineligible(
    acquisition_app, logged_in_client
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.leads.models import Lead

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    eligible = _seed_candidate(
        acquisition_app,
        tenant_id=tenant_id,
        mission_id=mission.id,
        suffix="eligible",
    )
    blocked = _seed_candidate(
        acquisition_app,
        tenant_id=tenant_id,
        mission_id=mission.id,
        suffix="blocked",
        status="needs_evidence",
        country_status="unknown",
    )

    response = client.post(
        "/acquisition/candidates/bulk/accept",
        data={"candidate_ids": [eligible.id, blocked.id], "mission_id": mission.id},
    )

    assert response.status_code == 400
    with Session(get_engine(acquisition_app)) as db_session:
        assert db_session.get(AcquisitionCandidate, eligible.id).status == "eligible"
        assert db_session.get(AcquisitionCandidate, blocked.id).status == "needs_evidence"
        assert list(db_session.scalars(select(Lead))) == []


def test_confirmed_bulk_accept_promotes_to_crm_without_queuing_outreach(
    acquisition_app, logged_in_client
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.jobs.models import Job
    from app.modules.leads.models import Lead

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    candidates = [
        _seed_candidate(
            acquisition_app,
            tenant_id=tenant_id,
            mission_id=mission.id,
            suffix=suffix,
        )
        for suffix in ("accepted-one", "accepted-two")
    ]

    preview = client.post(
        "/acquisition/candidates/bulk/accept",
        data={
            "candidate_ids": [item.id for item in candidates],
            "mission_id": mission.id,
        },
    )
    confirmed = client.post(
        "/acquisition/candidates/bulk/accept",
        data={
            "candidate_ids": [item.id for item in candidates],
            "mission_id": mission.id,
            "confirm": "yes",
        },
    )

    assert preview.status_code == 200
    assert "不会生成开发信" in preview.get_data(as_text=True)
    assert confirmed.status_code in {302, 303}
    with Session(get_engine(acquisition_app)) as db_session:
        assert {db_session.get(AcquisitionCandidate, item.id).status for item in candidates} == {
            "promoted"
        }
        assert len(list(db_session.scalars(select(Lead)))) == 2
        assert len(list(db_session.scalars(select(Job)))) == 0


def test_enqueue_failure_restores_draft_status(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.jobs.service import JobServiceError

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    def fail_enqueue(_app, **_kwargs):
        raise JobServiceError("queue unavailable")

    monkeypatch.setattr("app.modules.acquisition.routes.create_and_enqueue", fail_enqueue)

    response = client.post(f"/acquisition/missions/{mission.id}/start")

    assert response.status_code == 503
    assert "暂时无法加入队列" in response.get_data(as_text=True)
    with Session(get_engine(acquisition_app)) as db_session:
        stored = db_session.get(AcquisitionMission, mission.id)
        assert stored is not None
        assert stored.status == "draft"


def test_bulk_reject_requires_common_reason_and_enforces_limit(
    acquisition_app, logged_in_client
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    missing_reason = client.post(
        "/acquisition/candidates/bulk/reject",
        data={"candidate_ids": ["candidate-1"], "mission_id": mission.id},
    )
    too_many = client.post(
        "/acquisition/candidates/bulk/reject",
        data={
            "candidate_ids": [f"candidate-{index}" for index in range(101)],
            "reason_code": "wrong_buyer_type",
            "mission_id": mission.id,
        },
    )

    assert missing_reason.status_code == 400
    assert too_many.status_code == 400


def test_acquisition_css_protects_mobile_width() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    css = (root / "app" / "static" / "css" / "components.css").read_text(encoding="utf-8")

    assert ".lf-acquisition-layout" in css
    assert "minmax(0, 1fr)" in css
    assert ".lf-candidate-card" in css
    assert "overflow-wrap: anywhere" in css
