from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
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


def _configure_mission(
    app,
    mission_id: str,
    *,
    allowed_channels: list[str] | None = None,
    status: str | None = None,
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission

    with Session(get_engine(app)) as db_session:
        mission = db_session.get(AcquisitionMission, mission_id)
        assert mission is not None
        if allowed_channels is not None:
            mission.channel_policy_json = json.dumps(
                {"allowed_channels": allowed_channels, "browser_research": False}
            )
        if status is not None:
            mission.status = status
        db_session.commit()


def _set_mission_policy_json(app, mission_id: str, policy_json: str) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionMission

    with Session(get_engine(app)) as db_session:
        mission = db_session.get(AcquisitionMission, mission_id)
        assert mission is not None
        mission.channel_policy_json = policy_json
        db_session.commit()


def _patch_manual_dependencies(monkeypatch, *, process_url, process_facts=None):
    from app.modules.acquisition import routes

    calls: dict[str, list[object]] = {"fetcher": [], "provider": []}
    fetcher = object()
    provider = object()

    class FakeStaticFetcher:
        @classmethod
        def from_app(cls, app):
            calls["fetcher"].append(app)
            return fetcher

    def fake_build_provider(app, *, tenant_id: str):
        calls["provider"].append((app, tenant_id))
        return provider

    monkeypatch.setattr(routes, "StaticFetcher", FakeStaticFetcher, raising=False)
    monkeypatch.setattr(routes, "build_mimo_provider", fake_build_provider, raising=False)
    monkeypatch.setattr(routes, "process_manual_url", process_url, raising=False)
    if process_facts is not None:
        monkeypatch.setattr(routes, "process_manual_facts", process_facts, raising=False)
    return calls, fetcher, provider


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


def test_mission_detail_shows_manual_url_only_when_allowed_and_not_cancelled(
    acquisition_app, logged_in_client
) -> None:
    client, tenant_id = logged_in_client
    actor_id = _actor_id(client)
    allowed = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=actor_id)
    disallowed = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=actor_id)
    cancelled = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=actor_id)
    _configure_mission(acquisition_app, disallowed.id, allowed_channels=["mimo_web"])
    _configure_mission(acquisition_app, cancelled.id, status="cancelled")

    allowed_html = client.get(f"/acquisition/missions/{allowed.id}").get_data(as_text=True)
    disallowed_html = client.get(f"/acquisition/missions/{disallowed.id}").get_data(as_text=True)
    cancelled_html = client.get(f"/acquisition/missions/{cancelled.id}").get_data(as_text=True)

    assert "补充企业网址" in allowed_html
    assert "用 MiMo 提取这个网址" in allowed_html
    assert "MiMo 不可用？手工填写证据" in allowed_html
    assert 'name="mode" value="ai_extract"' in allowed_html
    assert 'name="mode" value="manual_facts"' in allowed_html
    assert "不会发送任何消息" in allowed_html
    assert "ExtractedCompanyFacts" not in allowed_html
    assert "StaticFetcher" not in allowed_html
    assert "Assessment" not in allowed_html
    assert "补充企业网址" not in disallowed_html
    assert "补充企业网址" not in cancelled_html


@pytest.mark.parametrize(
    "policy_json",
    [
        "not-json",
        json.dumps("manual_url"),
        json.dumps(["manual_url"]),
        json.dumps({"allowed_channels": "manual_url"}),
        json.dumps({"allowed_channels": {"manual_url": True}}),
    ],
)
def test_malformed_manual_url_policy_hides_form_and_rejects_post_before_dependencies(
    acquisition_app,
    logged_in_client,
    monkeypatch,
    policy_json: str,
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    _set_mission_policy_json(acquisition_app, mission.id, policy_json)
    process_calls: list[object] = []

    def fake_process(*_args, **_kwargs):
        process_calls.append(object())
        return SimpleNamespace(id="must-not-exist")

    calls, _fetcher, _provider = _patch_manual_dependencies(monkeypatch, process_url=fake_process)

    detail = client.get(f"/acquisition/missions/{mission.id}")
    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "https://example.com"},
    )

    assert detail.status_code == 200
    assert "补充企业网址" not in detail.get_data(as_text=True)
    assert response.status_code == 409
    assert calls == {"fetcher": [], "provider": []}
    assert process_calls == []


def test_manual_url_post_requires_csrf_when_enabled(csrf_client) -> None:
    client, _tenant_id = csrf_client

    response = client.post(
        "/acquisition/missions/not-present/manual-url",
        data={"mode": "ai_extract", "url": "https://example.com"},
    )

    assert response.status_code == 400


def test_manual_url_post_hides_cross_tenant_mission_before_dependencies(
    acquisition_app, logged_in_client, seed_acquisition_mission, monkeypatch
) -> None:
    client, _tenant_id = logged_in_client
    mission_id = seed_acquisition_mission(tenant_id="other-tenant", suffix="manual-private")

    def unexpected_process(**_kwargs):
        raise AssertionError("manual processing must not run")

    calls, _fetcher, _provider = _patch_manual_dependencies(
        monkeypatch, process_url=unexpected_process
    )

    response = client.post(
        f"/acquisition/missions/{mission_id}/manual-url",
        data={"mode": "ai_extract", "url": "https://private.example"},
    )

    assert response.status_code == 404
    assert calls == {"fetcher": [], "provider": []}


def test_manual_url_ai_extract_builds_bounded_dependencies_and_redirects(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    process_calls: list[dict[str, object]] = []

    def fake_process(app, **kwargs):
        process_calls.append({"app": app, **kwargs})
        return SimpleNamespace(id="candidate-from-url")

    calls, fetcher, provider = _patch_manual_dependencies(monkeypatch, process_url=fake_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "  https://example.com/about  "},
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/acquisition/candidates/candidate-from-url")
    assert calls == {
        "fetcher": [acquisition_app],
        "provider": [(acquisition_app, tenant_id)],
    }
    assert process_calls == [
        {
            "app": acquisition_app,
            "tenant_id": tenant_id,
            "mission_id": mission.id,
            "url": "https://example.com/about",
            "fetcher": fetcher,
            "extractor": provider,
        }
    ]


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [("success", 302), ("fetch_error", 503), ("provider_error", 503)],
)
def test_ai_extract_builds_provider_first_and_closes_adapters(
    acquisition_app,
    logged_in_client,
    monkeypatch,
    outcome: str,
    expected_status: int,
) -> None:
    from app.integrations.ai.mimo import ProviderError
    from app.integrations.web.fetcher import FetchError
    from app.modules.acquisition import routes

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    constructed: list[str] = []
    closed: list[str] = []

    class Adapter:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            closed.append(self.name)

    fetcher = Adapter("fetcher")
    provider = Adapter("provider")

    class FakeStaticFetcher:
        @classmethod
        def from_app(cls, app):
            assert app is acquisition_app
            constructed.append("fetcher")
            return fetcher

    def fake_build_provider(app, *, tenant_id: str):
        assert app is acquisition_app
        assert tenant_id
        constructed.append("provider")
        return provider

    def fake_process(*_args, **_kwargs):
        if outcome == "fetch_error":
            raise FetchError("source_timeout", "Evidence page request timed out")
        if outcome == "provider_error":
            raise ProviderError("transient", "MiMo is unavailable", retryable=True)
        return SimpleNamespace(id="closed-candidate")

    monkeypatch.setattr(routes, "StaticFetcher", FakeStaticFetcher)
    monkeypatch.setattr(routes, "build_mimo_provider", fake_build_provider)
    monkeypatch.setattr(routes, "process_manual_url", fake_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "https://example.com/lifecycle"},
    )

    assert response.status_code == expected_status
    assert constructed == ["provider", "fetcher"]
    assert closed == ["fetcher", "provider"]


def test_manual_facts_closes_only_fetcher(acquisition_app, logged_in_client, monkeypatch) -> None:
    from app.modules.acquisition import routes

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    closed: list[str] = []
    provider_calls: list[object] = []

    class Fetcher:
        def close(self) -> None:
            closed.append("fetcher")

    class FakeStaticFetcher:
        @classmethod
        def from_app(cls, app):
            assert app is acquisition_app
            return Fetcher()

    def unexpected_provider(*_args, **_kwargs):
        provider_calls.append(object())
        return SimpleNamespace(close=lambda: closed.append("provider"))

    monkeypatch.setattr(routes, "StaticFetcher", FakeStaticFetcher)
    monkeypatch.setattr(routes, "build_mimo_provider", unexpected_provider)
    monkeypatch.setattr(
        routes,
        "process_manual_facts",
        lambda *_args, **_kwargs: SimpleNamespace(id="manual-closed-candidate"),
    )

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={
            "mode": "manual_facts",
            "url": "https://example.com/company",
            "company_name": "Example Co",
            "opportunity_country_code": "MX",
            "buyer_type": "distributor",
            "evidence_text": "Example distributor in Mexico",
            "contact_path": "sales@example.com",
        },
    )

    assert response.status_code == 302
    assert provider_calls == []
    assert closed == ["fetcher"]


def test_manual_url_provider_error_is_safe_and_preserves_normalized_url(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.integrations.ai.mimo import ProviderError
    from app.modules.acquisition import routes

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    submitted = "  https://example.com/provider-check  "
    expected_url = submitted.strip()

    def unexpected_process(**_kwargs):
        raise AssertionError("processing must not run when provider construction fails")

    calls, _fetcher, _provider = _patch_manual_dependencies(
        monkeypatch, process_url=unexpected_process
    )

    def fail_provider(_app, *, tenant_id: str):
        calls["provider"].append((_app, tenant_id))
        raise ProviderError(
            "provider_not_configured",
            "raw-provider-body; MiMo API key; MIMO_BASE_URL",
            retryable=False,
        )

    monkeypatch.setattr(routes, "build_mimo_provider", fail_provider)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": submitted},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 503
    assert calls["fetcher"] == []
    assert calls["provider"] == [(acquisition_app, tenant_id)]
    assert expected_url in html
    assert '<details class="lf-form-stack" open>' in html
    assert "raw-provider-body" not in html
    assert "API key" not in html
    assert "MIMO_BASE_URL" not in html


def test_manual_url_state_error_returns_safe_409_with_bounded_form(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.modules.acquisition import routes
    from app.modules.acquisition.service import AcquisitionError

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    class FakeStateError(AcquisitionError):
        pass

    def fail_process(*_args, **_kwargs):
        raise FakeStateError("RAW cancelled race Assessment API_CONFIG")

    monkeypatch.setattr(routes, "AcquisitionStateError", FakeStateError, raising=False)
    _patch_manual_dependencies(monkeypatch, process_url=fail_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "  https://example.com/state-race  "},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 409
    assert "这个任务当前不能补充企业网址。" in html
    assert "https://example.com/state-race" in html
    assert "RAW cancelled race" not in html
    assert "Assessment" not in html
    assert "API_CONFIG" not in html


def test_manual_url_acquisition_error_is_redacted_to_fixed_400(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.modules.acquisition.service import AcquisitionError

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    def fail_process(*_args, **_kwargs):
        raise AcquisitionError(
            "RAW_BODY Assessment MIMO_BASE_URL=private API key=secret internal-table"
        )

    _patch_manual_dependencies(monkeypatch, process_url=fail_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "https://example.com/redaction"},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "无法处理这份企业证据，请检查填写内容后重试。" in html
    assert "RAW_BODY" not in html
    assert "Assessment" not in html
    assert "MIMO_BASE_URL" not in html
    assert "API key" not in html
    assert "internal-table" not in html


def test_manual_facts_builds_normalized_valid_input_without_mimo(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    from app.modules.acquisition.contracts import ManualCompanyFactsInput

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    process_calls: list[dict[str, object]] = []

    def unexpected_url_process(**_kwargs):
        raise AssertionError("AI extraction must not run")

    def fake_facts_process(app, **kwargs):
        process_calls.append({"app": app, **kwargs})
        return SimpleNamespace(id="candidate-from-facts")

    calls, fetcher, _provider = _patch_manual_dependencies(
        monkeypatch,
        process_url=unexpected_url_process,
        process_facts=fake_facts_process,
    )
    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={
            "mode": "manual_facts",
            "url": "  https://example.com/company  ",
            "company_name": "  Acme Parts  ",
            "opportunity_country_code": " mx ",
            "buyer_type": " Distributor ",
            "evidence_text": "  Motorcycle parts distributor in Mexico.  ",
            "contact_path": "  buyer@example.com  ",
        },
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/acquisition/candidates/candidate-from-facts")
    assert calls == {"fetcher": [acquisition_app], "provider": []}
    assert len(process_calls) == 1
    value = process_calls[0]["value"]
    assert isinstance(value, ManualCompanyFactsInput)
    assert value.url == "https://example.com/company"
    assert value.company_name == "Acme Parts"
    assert value.opportunity_country_code == "MX"
    assert value.buyer_type == "distributor"
    assert value.evidence_text == "Motorcycle parts distributor in Mexico."
    assert value.contact_path == "buyer@example.com"
    assert process_calls[0] == {
        "app": acquisition_app,
        "tenant_id": tenant_id,
        "mission_id": mission.id,
        "value": value,
        "fetcher": fetcher,
    }


def test_ai_extract_rejects_overlong_url_before_dependencies(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    submitted_url = "  https://example.com/" + ("url-secret-" * 110) + "  "
    process_calls: list[object] = []

    def fake_process(*_args, **_kwargs):
        process_calls.append(object())
        return SimpleNamespace(id="must-not-exist")

    calls, _fetcher, _provider = _patch_manual_dependencies(monkeypatch, process_url=fake_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": submitted_url},
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert calls == {"fetcher": [], "provider": []}
    assert process_calls == []
    assert submitted_url.strip() not in html


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("url", "  https://example.com/" + ("url-secret-" * 110) + "  "),
        ("company_name", "  " + ("CompanySecret" * 30) + "  "),
        ("evidence_text", "  " + ("EvidenceSecret" * 80) + "  "),
        ("contact_path", "  " + ("contact-secret-" * 80) + "  "),
        ("opportunity_country_code", " MXX "),
        ("buyer_type", " retailer "),
    ],
)
def test_manual_facts_rejects_invalid_full_value_before_dependencies(
    acquisition_app,
    logged_in_client,
    monkeypatch,
    field: str,
    invalid_value: str,
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    form = {
        "mode": "manual_facts",
        "url": "https://example.com/company",
        "company_name": "Acme Parts",
        "opportunity_country_code": "MX",
        "buyer_type": "distributor",
        "evidence_text": "Motorcycle parts distributor in Mexico.",
        "contact_path": "buyer@example.com",
    }
    form[field] = invalid_value
    process_calls: list[object] = []

    def unexpected_url_process(*_args, **_kwargs):
        process_calls.append(object())
        return SimpleNamespace(id="must-not-exist")

    def fake_facts_process(*_args, **_kwargs):
        process_calls.append(object())
        return SimpleNamespace(id="must-not-exist")

    calls, _fetcher, _provider = _patch_manual_dependencies(
        monkeypatch,
        process_url=unexpected_url_process,
        process_facts=fake_facts_process,
    )

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data=form,
    )

    html = response.get_data(as_text=True)
    assert response.status_code == 400
    assert calls == {"fetcher": [], "provider": []}
    assert process_calls == []
    assert invalid_value.strip() not in html


@pytest.mark.parametrize(
    ("code", "safe_summary", "expected_status"),
    [
        ("policy_url_blocked", "Evidence URL was blocked by safety policy", 400),
        ("source_timeout", "Evidence page request timed out", 503),
        ("source_unreachable", "Evidence page request failed", 503),
    ],
)
def test_manual_url_fetch_error_uses_only_safe_summary_and_creates_no_candidate(
    acquisition_app,
    logged_in_client,
    monkeypatch,
    code: str,
    safe_summary: str,
    expected_status: int,
) -> None:
    from app.extensions import get_engine
    from app.integrations.web.fetcher import FetchError
    from app.modules.acquisition.models import AcquisitionCandidate

    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    class RawFetchError(FetchError):
        def __str__(self) -> str:
            return "RAW_EXCEPTION PAGE_TEXT_DO_NOT_ECHO"

    def fail_process(*_args, **_kwargs):
        raise RawFetchError(code, safe_summary)

    _patch_manual_dependencies(monkeypatch, process_url=fail_process)

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={
            "mode": "ai_extract",
            "url": "https://example.com",
            "page_text": "PAGE_TEXT_DO_NOT_ECHO",
        },
    )

    html = response.get_data(as_text=True)
    assert response.status_code == expected_status
    assert safe_summary in html
    assert "RAW_EXCEPTION" not in html
    assert "PAGE_TEXT_DO_NOT_ECHO" not in html
    with Session(get_engine(acquisition_app)) as db_session:
        candidates = list(
            db_session.scalars(
                select(AcquisitionCandidate).where(AcquisitionCandidate.tenant_id == tenant_id)
            )
        )
    assert candidates == []


@pytest.mark.parametrize(
    ("status", "allowed_channels"),
    [("cancelled", ["manual_url"]), ("draft", ["mimo_web"])],
)
def test_manual_url_rejects_cancelled_or_disallowed_before_dependencies(
    acquisition_app,
    logged_in_client,
    monkeypatch,
    status: str,
    allowed_channels: list[str],
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))
    _configure_mission(
        acquisition_app,
        mission.id,
        status=status,
        allowed_channels=allowed_channels,
    )

    def unexpected_process(**_kwargs):
        raise AssertionError("manual processing must not run")

    calls, _fetcher, _provider = _patch_manual_dependencies(
        monkeypatch, process_url=unexpected_process
    )

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "ai_extract", "url": "https://example.com"},
    )

    assert response.status_code == 409
    assert calls == {"fetcher": [], "provider": []}


def test_manual_url_rejects_invalid_mode_before_dependencies(
    acquisition_app, logged_in_client, monkeypatch
) -> None:
    client, tenant_id = logged_in_client
    mission = _seed_mission(acquisition_app, tenant_id=tenant_id, actor_id=_actor_id(client))

    def unexpected_process(**_kwargs):
        raise AssertionError("manual processing must not run")

    calls, _fetcher, _provider = _patch_manual_dependencies(
        monkeypatch, process_url=unexpected_process
    )

    response = client.post(
        f"/acquisition/missions/{mission.id}/manual-url",
        data={"mode": "unknown", "url": "https://example.com"},
    )

    assert response.status_code == 400
    assert calls == {"fetcher": [], "provider": []}


def test_acquisition_css_protects_mobile_width() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    css = (root / "app" / "static" / "css" / "components.css").read_text(encoding="utf-8")

    assert ".lf-acquisition-layout" in css
    assert "minmax(0, 1fr)" in css
    assert ".lf-candidate-card" in css
    assert "overflow-wrap: anywhere" in css
