from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session


def _seed_workbench(
    app,
    *,
    mission_t1: str,
    mission_t2: str,
    tenant_t1: str = "t1",
    tenant_t2: str = "t2",
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate, Notification
    from app.modules.jobs.models import Job
    from app.modules.leads.models import Activity, Lead

    now = datetime.now(UTC)
    with Session(get_engine(app)) as db_session:
        reply_lead = Lead(
            tenant_id=tenant_t1,
            email="reply@example.com",
            status="accepted",
            follow_up_at=now - timedelta(hours=1),
        )
        private_lead = Lead(
            tenant_id=tenant_t2,
            email="private@example.com",
            status="accepted",
            follow_up_at=now - timedelta(hours=1),
        )
        db_session.add_all([reply_lead, private_lead])
        db_session.flush()
        db_session.add_all(
            [
                AcquisitionCandidate(
                    tenant_id=tenant_t1,
                    mission_id=mission_t1,
                    status="eligible",
                    dedupe_key="domain:a.example",
                ),
                AcquisitionCandidate(
                    tenant_id=tenant_t1,
                    mission_id=mission_t1,
                    status="eligible",
                    dedupe_key="domain:b.example",
                ),
                AcquisitionCandidate(
                    tenant_id=tenant_t1,
                    mission_id=mission_t1,
                    status="needs_evidence",
                    dedupe_key="domain:needs-evidence.example",
                ),
                AcquisitionCandidate(
                    tenant_id=tenant_t2,
                    mission_id=mission_t2,
                    status="eligible",
                    dedupe_key="domain:private.example",
                ),
                Job(tenant_id=tenant_t1, job_type="candidate_assess", status="running"),
                Job(tenant_id=tenant_t1, job_type="website_verify", status="failed"),
                Job(tenant_id=tenant_t2, job_type="candidate_assess", status="running"),
                Notification(
                    tenant_id=tenant_t1,
                    kind="mission_failed",
                    title="任务失败",
                    dedupe_key="mission:m1:failed",
                ),
                Notification(
                    tenant_id=tenant_t2,
                    kind="mission_failed",
                    title="私有通知",
                    dedupe_key="mission:m2:failed",
                ),
                Activity(
                    tenant_id=tenant_t1,
                    lead_id=reply_lead.id,
                    action="inbound_received",
                ),
                Activity(
                    tenant_id=tenant_t1,
                    lead_id=reply_lead.id,
                    action="inbound_received",
                ),
                Activity(
                    tenant_id=tenant_t2,
                    lead_id=private_lead.id,
                    action="inbound_received",
                ),
            ]
        )
        db_session.commit()


def test_workbench_uses_tenant_scoped_real_counts(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.modules.acquisition.workbench import load_workbench

    mission_t1 = seed_acquisition_mission(tenant_id="t1", suffix="workbench")
    mission_t2 = seed_acquisition_mission(tenant_id="t2", suffix="workbench")
    _seed_workbench(acquisition_app, mission_t1=mission_t1, mission_t2=mission_t2)

    view = load_workbench(acquisition_app, tenant_id="t1")
    private_view = load_workbench(acquisition_app, tenant_id="t2")

    assert view.candidates_to_review == 2
    assert view.jobs_running == 1
    assert view.jobs_failed == 1
    assert view.needs_evidence == 1
    assert view.notifications_unread == 1
    assert view.replies_to_handle == 1
    assert view.follow_ups_due == 1
    assert view.next_action_url == "/workbench#unresolved-job-failures"
    assert view.review_url.startswith("/acquisition/candidates/")
    assert view.attention_url == "/workbench#unresolved-job-failures"
    assert len(view.current_jobs) == 1
    assert {job.status for job in view.current_jobs} == {"running"}
    assert len(view.failed_jobs) == 1
    assert {job.status for job in view.failed_jobs} == {"failed"}
    assert private_view.candidates_to_review == 1
    assert private_view.needs_evidence == 0


def test_needs_evidence_resolves_verification_failure_and_becomes_next_action(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    oldest_mission = seed_acquisition_mission(tenant_id="t1", suffix="needs-oldest")
    newer_mission = seed_acquisition_mission(tenant_id="t1", suffix="needs-newer")
    now = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as db_session:
        resolved_candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=oldest_mission,
            status="needs_evidence",
            dedupe_key="domain:resolved-failure.example",
            created_at=now - timedelta(hours=2),
        )
        newer_candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=newer_mission,
            status="needs_evidence",
            dedupe_key="domain:newer-failure.example",
            created_at=now - timedelta(hours=1),
        )
        review_candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=newer_mission,
            status="eligible",
            dedupe_key="domain:review.example",
        )
        db_session.add_all([resolved_candidate, newer_candidate, review_candidate])
        db_session.flush()
        db_session.add(
            Job(
                tenant_id="t1",
                job_type="website_verify",
                status="failed",
                payload_json=json.dumps({"candidate_id": resolved_candidate.id}),
            )
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 0
    assert view.failed_jobs == ()
    assert view.current_jobs == ()
    assert view.needs_evidence == 2
    assert view.next_action_url == f"/acquisition/missions/{oldest_mission}"
    assert view.attention_url == f"/acquisition/missions/{oldest_mission}"


def test_candidate_state_does_not_hide_unrelated_job_failure(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="assess-failure")
    with Session(get_engine(acquisition_app)) as db_session:
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=mission_id,
            status="needs_evidence",
            dedupe_key="domain:assessment-failure.example",
        )
        db_session.add(candidate)
        db_session.flush()
        db_session.add(
            Job(
                tenant_id="t1",
                job_type="candidate_assess",
                status="failed",
                payload_json=json.dumps({"candidate_id": candidate.id}),
            )
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 1
    assert len(view.failed_jobs) == 1


@pytest.mark.parametrize("candidate_status", ["accepted", "promoted", "rejected"])
def test_terminal_review_state_hides_obsolete_candidate_assessment_failure(
    acquisition_app, seed_acquisition_mission, candidate_status: str
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix=f"terminal-{candidate_status}")
    with Session(get_engine(acquisition_app)) as db_session:
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=mission_id,
            status=candidate_status,
            dedupe_key=f"domain:{candidate_status}-assessment.example",
        )
        db_session.add(candidate)
        db_session.flush()
        db_session.add(
            Job(
                tenant_id="t1",
                job_type="candidate_assess",
                status="failed",
                payload_json=json.dumps({"candidate_id": candidate.id}),
            )
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 0
    assert view.failed_jobs == ()


def test_accepted_candidate_keeps_failed_promotion_actionable(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="accepted-promote")
    with Session(get_engine(acquisition_app)) as db_session:
        candidate = AcquisitionCandidate(
            tenant_id="t1",
            mission_id=mission_id,
            status="accepted",
            dedupe_key="domain:accepted-promotion.example",
        )
        db_session.add(candidate)
        db_session.flush()
        db_session.add(
            Job(
                tenant_id="t1",
                job_type="candidate_promote",
                status="failed",
                payload_json=json.dumps({"candidate_id": candidate.id}),
            )
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 1
    assert len(view.failed_jobs) == 1


def test_oldest_needs_evidence_action_uses_mission_creation_time(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import AcquisitionCandidate, AcquisitionMission
    from app.modules.acquisition.workbench import load_workbench

    older_mission_id = seed_acquisition_mission(tenant_id="t1", suffix="mission-older")
    newer_mission_id = seed_acquisition_mission(tenant_id="t1", suffix="mission-newer")
    now = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as db_session:
        older_mission = db_session.get(AcquisitionMission, older_mission_id)
        newer_mission = db_session.get(AcquisitionMission, newer_mission_id)
        assert older_mission is not None
        assert newer_mission is not None
        older_mission.created_at = now - timedelta(days=2)
        newer_mission.created_at = now - timedelta(days=1)
        db_session.add_all(
            [
                AcquisitionCandidate(
                    tenant_id="t1",
                    mission_id=older_mission_id,
                    status="needs_evidence",
                    dedupe_key="domain:older-mission-late-candidate.example",
                    created_at=now,
                ),
                AcquisitionCandidate(
                    tenant_id="t1",
                    mission_id=newer_mission_id,
                    status="needs_evidence",
                    dedupe_key="domain:newer-mission-early-candidate.example",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.next_action_url == f"/acquisition/missions/{older_mission_id}"
    assert view.attention_url == f"/acquisition/missions/{older_mission_id}"


def test_later_success_supersedes_failure_for_same_logical_job(
    acquisition_app, seed_acquisition_mission
) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="superseded")
    now = datetime.now(UTC)
    payload = json.dumps({"mission_id": mission_id})
    with Session(get_engine(acquisition_app)) as db_session:
        db_session.add_all(
            [
                Job(
                    tenant_id="t1",
                    job_type="web_discovery",
                    status="failed",
                    payload_json=payload,
                    created_at=now - timedelta(minutes=2),
                    updated_at=now - timedelta(minutes=2),
                ),
                Job(
                    tenant_id="t1",
                    job_type="web_discovery",
                    status="succeeded",
                    payload_json=payload,
                    created_at=now - timedelta(minutes=1),
                    updated_at=now - timedelta(minutes=1),
                ),
            ]
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 0
    assert view.failed_jobs == ()


def test_unresolved_failure_count_is_not_truncated_with_display_list(acquisition_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.workbench import load_workbench
    from app.modules.jobs.models import Job

    with Session(get_engine(acquisition_app)) as db_session:
        db_session.add_all(
            [
                Job(
                    tenant_id="t1",
                    job_type="web_discovery",
                    status="failed",
                    payload_json=json.dumps({"mission_id": f"mission-{index}"}),
                )
                for index in range(10)
            ]
        )
        db_session.commit()

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.jobs_failed == 10
    assert len(view.failed_jobs) == 8


def test_workbench_live_is_tenant_guarded_polling_partial(
    acquisition_app, logged_in_client
) -> None:
    client, _tenant_id = logged_in_client

    response = client.get("/workbench/live")
    html = response.get_data(as_text=True)
    anonymous = acquisition_app.test_client().get("/workbench/live")

    assert response.status_code == 200
    assert '<section id="workbench-live"' in html
    assert 'hx-get="/workbench/live"' in html
    assert 'hx-trigger="load, every 5s"' in html
    assert 'hx-swap="outerHTML"' in html
    assert 'id="active-jobs"' in html
    assert 'id="unresolved-job-failures"' in html
    assert "<!doctype html>" not in html.lower()
    assert anonymous.status_code in {302, 303}
    assert anonymous.headers["Location"].endswith("/login")


def test_main_workbench_includes_live_polling_projection(logged_in_client) -> None:
    client, _tenant_id = logged_in_client

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert html.count('id="workbench-live"') == 1
    assert 'hx-get="/workbench/live"' in html
    assert 'id="active-jobs"' in html
    assert 'id="unresolved-job-failures"' in html


def test_empty_workbench_without_product_points_to_product_knowledge(acquisition_app) -> None:
    from app.modules.acquisition.workbench import load_workbench

    view = load_workbench(acquisition_app, tenant_id="new-tenant")

    assert view.next_action_url == "/acquisition/products"
    assert view.review_url == "/acquisition/products"
    assert view.has_product_knowledge is False
    assert view.attention_url == "/workbench#active-jobs"
    assert view.current_jobs == ()


def test_empty_workbench_with_product_points_to_new_mission(acquisition_app) -> None:
    from app.modules.acquisition.service import create_product_snapshot
    from app.modules.acquisition.workbench import load_workbench

    create_product_snapshot(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        product_name="Engine",
        summary="Motorcycle engine",
        facts=[{"name": "product", "value": "engine"}],
        prohibited_claims=[],
    )

    view = load_workbench(acquisition_app, tenant_id="t1")

    assert view.next_action_url == "/acquisition/missions/new"
    assert view.review_url == "/acquisition/missions/new"
    assert view.has_product_knowledge is True


def test_other_tenant_product_does_not_unlock_new_mission(acquisition_app) -> None:
    from app.modules.acquisition.service import create_product_snapshot
    from app.modules.acquisition.workbench import load_workbench

    create_product_snapshot(
        acquisition_app,
        tenant_id="other-tenant",
        actor_id="u1",
        product_name="Private engine",
        summary="Other tenant product",
        facts=[{"name": "product", "value": "engine"}],
        prohibited_claims=[],
    )

    view = load_workbench(acquisition_app, tenant_id="current-tenant")

    assert view.has_product_knowledge is False
    assert view.next_action_url == "/acquisition/products"
    assert view.review_url == "/acquisition/products"


def test_empty_workbench_route_prompts_for_product_knowledge(
    logged_in_client,
) -> None:
    client, _tenant_id = logged_in_client

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    top_nav = html.split('<nav class="lf-top-nav"', 1)[1].split("</nav>", 1)[0]
    page_header = html.split('<header class="lf-page-header">', 1)[1].split("</header>", 1)[0]
    empty_state = html.split('<div class="lf-empty-state">', 1)[1].split("</div>", 1)[0]
    assert '<a href="/acquisition/products">先添加产品知识</a>' in top_nav
    assert 'href="/acquisition/products"' in page_header
    assert "先添加产品知识" in page_header
    assert 'href="/acquisition/products"' in empty_state
    assert "先添加产品知识" in empty_state


def test_empty_workbench_route_with_product_offers_new_mission(logged_in_client) -> None:
    from app.modules.acquisition.service import create_product_snapshot

    client, tenant_id = logged_in_client
    create_product_snapshot(
        client.application,
        tenant_id=tenant_id,
        actor_id="u1",
        product_name="Engine",
        summary="Motorcycle engine",
        facts=[{"name": "product", "value": "engine"}],
        prohibited_claims=[],
    )

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    top_nav = html.split('<nav class="lf-top-nav"', 1)[1].split("</nav>", 1)[0]
    page_header = html.split('<header class="lf-page-header">', 1)[1].split("</header>", 1)[0]
    empty_state = html.split('<div class="lf-empty-state">', 1)[1].split("</div>", 1)[0]
    assert '<a href="/acquisition/missions/new">创建找客户任务</a>' in top_nav
    assert 'href="/acquisition/missions/new"' in page_header
    assert "创建找客户任务" in page_header
    assert 'href="/acquisition/missions/new"' in empty_state
    assert "创建找客户任务" in empty_state


def test_notification_dedupe_is_exactly_once(acquisition_app) -> None:
    from app.modules.acquisition.workbench import notify_once

    first = notify_once(
        acquisition_app,
        tenant_id="t1",
        kind="mission_completed",
        dedupe_key="mission:m1:completed",
        title="任务完成",
        target_url="/acquisition/missions/m1",
    )
    second = notify_once(
        acquisition_app,
        tenant_id="t1",
        kind="mission_completed",
        dedupe_key="mission:m1:completed",
        title="不同标题不会覆盖",
        target_url="/workbench",
    )

    assert first.id == second.id
    assert second.title == "任务完成"


@pytest.mark.parametrize(
    "kind,target_url",
    [
        ("not_allowed", "/workbench"),
        ("mission_completed", "https://evil.example/path"),
        ("mission_completed", "//evil.example/path"),
        ("mission_completed", "/\\evil.example/path"),
        ("mission_completed", "workbench"),
    ],
)
def test_notification_rejects_unknown_kind_or_external_target(
    acquisition_app, kind: str, target_url: str
) -> None:
    from app.modules.acquisition.workbench import WorkbenchError, notify_once

    with pytest.raises(WorkbenchError):
        notify_once(
            acquisition_app,
            tenant_id="t1",
            kind=kind,
            dedupe_key=f"test:{kind}:{target_url}",
            title="Test",
            target_url=target_url,
        )


def test_mark_notification_read_is_tenant_scoped(acquisition_app) -> None:
    from app.modules.acquisition.workbench import mark_notification_read, notify_once

    notification = notify_once(
        acquisition_app,
        tenant_id="t1",
        kind="mission_completed",
        dedupe_key="mission:m1:read",
        title="任务完成",
        target_url="/workbench",
    )

    assert (
        mark_notification_read(acquisition_app, tenant_id="t2", notification_id=notification.id)
        is None
    )
    updated = mark_notification_read(
        acquisition_app, tenant_id="t1", notification_id=notification.id
    )
    assert updated is not None
    assert updated.status == "read"


def test_mark_all_notifications_read_and_sanitize_stored_targets(acquisition_app) -> None:
    from app.extensions import get_engine
    from app.modules.acquisition.models import Notification
    from app.modules.acquisition.workbench import (
        list_notifications,
        mark_all_notifications_read,
        notify_once,
    )

    notify_once(
        acquisition_app,
        tenant_id="t1",
        kind="mission_completed",
        dedupe_key="mission:m1:all",
        title="任务一完成",
        target_url="/workbench",
    )
    with Session(get_engine(acquisition_app)) as db_session:
        db_session.add(
            Notification(
                tenant_id="t1",
                kind="mission_failed",
                title="遗留通知",
                target_url="//evil.example/path",
                dedupe_key="legacy:unsafe-target",
            )
        )
        db_session.commit()

    notifications = list_notifications(acquisition_app, tenant_id="t1")
    assert {item.target_url for item in notifications} == {"/workbench"}
    assert mark_all_notifications_read(acquisition_app, tenant_id="t1") == 2
    assert all(
        item.status == "read" for item in list_notifications(acquisition_app, tenant_id="t1")
    )


def test_workbench_route_renders_real_counts(
    acquisition_app, logged_in_client, seed_acquisition_mission
) -> None:
    client, tenant_id = logged_in_client
    other_mission = seed_acquisition_mission(tenant_id="other", suffix="route")
    own_mission = seed_acquisition_mission(tenant_id=tenant_id, suffix="route")
    _seed_workbench(
        acquisition_app,
        mission_t1=own_mission,
        mission_t2=other_mission,
        tenant_t1=tenant_id,
        tenant_t2="other",
    )

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "待审核候选" in html
    assert ">2<" in html
    assert "处理失败任务" in html
    assert "35%" not in html
    assert "Connect the data layer" not in html
    assert 'href="/leads?has_reply=1"' in html
    assert 'href="/leads?follow_up_due=1"' in html


def test_notification_routes_hide_other_tenants(acquisition_app, logged_in_client) -> None:
    from app.modules.acquisition.workbench import notify_once

    client, tenant_id = logged_in_client
    own = notify_once(
        acquisition_app,
        tenant_id=tenant_id,
        kind="mission_completed",
        dedupe_key="mission:own:completed",
        title="我的任务完成",
        target_url="/workbench",
    )
    other = notify_once(
        acquisition_app,
        tenant_id="other-tenant",
        kind="mission_failed",
        dedupe_key="mission:other:failed",
        title="其他租户通知",
        target_url="/workbench",
    )

    listing = client.get("/notifications")
    cross_tenant_read = client.post(f"/notifications/{other.id}/read")
    own_read = client.post(f"/notifications/{own.id}/read")

    html = listing.get_data(as_text=True)
    assert listing.status_code == 200
    assert "我的任务完成" in html
    assert "其他租户通知" not in html
    assert cross_tenant_read.status_code == 404
    assert own_read.status_code in {302, 303}


def test_lead_route_applies_acquisition_filters(acquisition_app, logged_in_client) -> None:
    from app.extensions import get_engine
    from app.modules.leads.models import Lead

    client, tenant_id = logged_in_client
    with Session(get_engine(acquisition_app)) as db_session:
        db_session.add_all(
            [
                Lead(
                    tenant_id=tenant_id,
                    email="top@example.com",
                    source="acquisition",
                    status="accepted",
                    opportunity_country_code="MX",
                    priority_score=90,
                    priority_band="A",
                ),
                Lead(
                    tenant_id=tenant_id,
                    email="other@example.com",
                    source="acquisition",
                    status="accepted",
                    opportunity_country_code="BR",
                    priority_score=55,
                    priority_band="C",
                ),
                Lead(
                    tenant_id="other-tenant",
                    email="private@example.com",
                    source="acquisition",
                    status="accepted",
                    opportunity_country_code="MX",
                    priority_score=95,
                    priority_band="A",
                ),
            ]
        )
        db_session.commit()

    response = client.get(
        "/leads?opportunity_country_code=MX&priority_band=A&"
        "priority_min=80&acquisition_source=1&has_contact=1"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "top@example.com" in html
    assert "other@example.com" not in html
    assert "private@example.com" not in html
    assert 'value="MX"' in html
