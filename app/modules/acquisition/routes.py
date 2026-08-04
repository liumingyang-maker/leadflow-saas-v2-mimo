"""Tenant-scoped routes for the solo acquisition workflow."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Flask, abort, make_response, redirect, render_template, request, session, url_for
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.ai.mimo import ProviderError, build_mimo_provider
from app.integrations.web.fetcher import FetchError, StaticFetcher
from app.modules.accounts.guards import tenant_required
from app.modules.acquisition.contracts import (
    DEFAULT_LANGUAGES,
    CountryEvidenceInput,
    ManualCompanyFactsInput,
    MissionCreateInput,
)
from app.modules.acquisition.manual_evidence import ManualEvidenceError
from app.modules.acquisition.mission_results import (
    list_mission_result_summaries,
    resolve_mission_result,
)
from app.modules.acquisition.models import AcquisitionCandidate
from app.modules.acquisition.repository import (
    AssessmentRepository,
    CandidateRepository,
    EvidenceRepository,
    MissionRepository,
    ProductKnowledgeRepository,
)
from app.modules.acquisition.policies import canonical_json
from app.modules.acquisition.service import (
    AcquisitionActiveJobError,
    AcquisitionError,
    AcquisitionNotFoundError,
    AcquisitionQueueError,
    AcquisitionRetryConflictError,
    AcquisitionStateError,
    bulk_review_candidates,
    create_mission,
    create_product_snapshot,
    override_candidate_country,
    process_manual_facts,
    process_manual_url,
    retry_candidate_verification,
    review_candidate,
)
from app.modules.acquisition.workbench import (
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
)
from app.modules.audit.service import add_event
from app.modules.jobs import service as job_service
from app.modules.jobs.models import Job

COUNTRY_CHOICES = (
    ("MX", "墨西哥"),
    ("BR", "巴西"),
    ("CO", "哥伦比亚"),
    ("PE", "秘鲁"),
    ("US", "美国"),
    ("GB", "英国"),
    ("DE", "德国"),
    ("FR", "法国"),
    ("ES", "西班牙"),
    ("IT", "意大利"),
    ("ZA", "南非"),
    ("AE", "阿联酋"),
)

BUYER_TYPE_CHOICES = (
    ("importer", "进口商"),
    ("distributor", "经销商"),
    ("wholesaler", "批发商"),
    ("assembler", "装配商"),
    ("repair_network", "维修网络"),
)

REJECTION_REASONS = (
    ("wrong_buyer_type", "买家类型不匹配"),
    ("excluded_business", "属于排除业务"),
    ("missing_identity", "公司身份不清楚"),
    ("missing_product_evidence", "缺少产品相关证据"),
    ("missing_contact_path", "缺少有效联系路径"),
    ("duplicate", "重复客户"),
    ("other", "其他"),
)

TERMINAL_MISSION_STATUSES = frozenset({"completed", "failed", "cancelled"})
BUSINESS_RESULT_REASON_LABELS = {
    "planning_failed": "研究计划生成失败",
    "search_failed": "部分市场搜索失败",
    "verification_failed": "部分官网验证失败",
    "ai_analysis_failed": "部分候选分析失败",
    "execution_failed": "部分执行步骤失败",
    "legacy_failed_with_results": "旧任务虽标记失败，但已保留可用结果",
    "search_no_valid_hits": "搜索已完成，但没有返回可用的企业候选。",
    "completed_without_candidates": "搜索已完成，但没有发现候选客户",
    "all_candidates_excluded": "发现的候选均已排除",
}


def register_acquisition_routes(app: Flask) -> None:
    @app.route("/acquisition/products", methods=["GET", "POST"])
    @tenant_required(app)
    def acquisition_products():
        tenant_id, actor_id = _identity()
        error = ""
        form_values = _product_form_values()
        if request.method == "POST":
            try:
                create_product_snapshot(
                    app,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    product_name=request.form.get("product_name", ""),
                    summary=request.form.get("summary", ""),
                    facts=_parse_facts(request.form.get("facts", "")),
                    prohibited_claims=_lines(request.form.get("prohibited_claims", "")),
                )
                return redirect(url_for("acquisition_products", saved="1"))
            except AcquisitionError as exc:
                error = _friendly_error(exc)

        with Session(get_engine(app)) as db_session:
            products = list(ProductKnowledgeRepository(db_session).list_latest(tenant_id=tenant_id))
        return (
            render_template(
                "acquisition/product_knowledge.html",
                products=products,
                error=error,
                saved=request.args.get("saved") == "1",
                form_values=form_values,
            ),
            400 if error else 200,
        )

    @app.get("/acquisition/missions")
    @tenant_required(app)
    def acquisition_mission_list():
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            missions = list_mission_result_summaries(
                db_session,
                tenant_id=tenant_id,
                limit=50,
            )
        return render_template("acquisition/mission_list.html", missions=missions)

    @app.route("/acquisition/missions/new", methods=["GET", "POST"])
    @tenant_required(app)
    def acquisition_mission_new():
        tenant_id, actor_id = _identity()
        form_values = _mission_form_values()
        error = ""
        if request.method == "POST":
            try:
                value = MissionCreateInput(
                    product_snapshot_id=request.form.get("product_snapshot_id", ""),
                    country_codes=request.form.getlist("country_codes"),
                    buyer_types=request.form.getlist("buyer_types"),
                    industries=_lines(request.form.get("industries", "")),
                    company_sizes=_lines(request.form.get("company_sizes", "")),
                    include_terms=_lines(request.form.get("include_terms", "")),
                    exclude_terms=_lines(request.form.get("exclude_terms", "")),
                    allowed_channels=(
                        request.form.getlist("allowed_channels") or ["mimo_web", "manual_url"]
                    ),
                    max_candidates=_form_int("max_candidates", 30),
                    max_verify=_form_int("max_verify", 10),
                    max_search_actions=_form_int("max_search_actions", 5),
                    max_seconds=_form_int("max_seconds", 900),
                )
                mission = create_mission(
                    app,
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    value=value,
                )
                return redirect(url_for("acquisition_mission_detail", mission_id=mission.id))
            except (AcquisitionError, ValidationError, ValueError) as exc:
                error = _friendly_error(exc)

        with Session(get_engine(app)) as db_session:
            products = list(ProductKnowledgeRepository(db_session).list_latest(tenant_id=tenant_id))
        return (
            render_template(
                "acquisition/mission_form.html",
                products=products,
                countries=COUNTRY_CHOICES,
                extra_countries=[
                    code
                    for code in form_values["country_codes"]
                    if code not in dict(COUNTRY_CHOICES)
                ],
                buyer_types=BUYER_TYPE_CHOICES,
                languages=DEFAULT_LANGUAGES,
                form_values=form_values,
                error=error,
            ),
            400 if error else 200,
        )

    @app.get("/acquisition/missions/<mission_id>")
    @tenant_required(app)
    def acquisition_mission_detail(mission_id: str):
        return _render_mission(app, mission_id=mission_id)

    @app.post("/acquisition/missions/<mission_id>/manual-url")
    @tenant_required(app)
    def acquisition_mission_manual_url(mission_id: str):
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
            if mission is None:
                abort(404)
            channel_policy = _json_value(mission.channel_policy_json, {})
            if mission.status == "cancelled" or not _manual_url_policy_allows(channel_policy):
                return _render_mission(
                    app,
                    mission_id=mission_id,
                    error="这个任务当前不能补充企业网址。",
                    status_code=409,
                )

        mode = request.form.get("mode", "").strip()
        if mode not in {"ai_extract", "manual_facts"}:
            return _render_mission(
                app,
                mission_id=mission_id,
                error="请选择有效的网址补充方式。",
                status_code=400,
            )

        manual_url_values = _manual_url_form_values()
        manual_url_form = _bounded_manual_url_form(manual_url_values)
        if mode == "ai_extract" and len(manual_url_values["url"]) > 1000:
            return _render_mission(
                app,
                mission_id=mission_id,
                error="企业网址不能超过 1000 个字符。",
                status_code=400,
                manual_url_form=manual_url_form,
            )

        fetcher = None
        provider = None
        try:
            if mode == "ai_extract":
                provider = build_mimo_provider(app, tenant_id=tenant_id)
                fetcher = StaticFetcher.from_app(app)
                candidate = process_manual_url(
                    app,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    url=manual_url_values["url"],
                    fetcher=fetcher,
                    extractor=provider,
                )
            else:
                value = ManualCompanyFactsInput(**manual_url_values)
                fetcher = StaticFetcher.from_app(app)
                candidate = process_manual_facts(
                    app,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    value=value,
                    fetcher=fetcher,
                )
        except AcquisitionStateError:
            return _render_mission(
                app,
                mission_id=mission_id,
                error="这个任务当前不能补充企业网址。",
                status_code=409,
                manual_url_form=manual_url_form,
                manual_mode_open=mode == "manual_facts",
            )
        except ProviderError:
            return _render_mission(
                app,
                mission_id=mission_id,
                error="MiMo 暂时不可用。你可以手工填写公开网页中的企业证据，或稍后重试。",
                status_code=503,
                manual_url_form=manual_url_form,
                manual_mode_open=True,
            )
        except FetchError as exc:
            status_code = 503 if exc.code in {"source_timeout", "source_unreachable"} else 400
            return _render_mission(
                app,
                mission_id=mission_id,
                error=exc.safe_summary,
                status_code=status_code,
                manual_url_form=manual_url_form,
                manual_mode_open=mode == "manual_facts",
            )
        except ValidationError as exc:
            return _render_mission(
                app,
                mission_id=mission_id,
                error=_friendly_error(exc),
                status_code=400,
                manual_url_form=manual_url_form,
                manual_mode_open=mode == "manual_facts",
            )
        except (AcquisitionError, ManualEvidenceError):
            return _render_mission(
                app,
                mission_id=mission_id,
                error="无法处理这份企业证据，请检查填写内容后重试。",
                status_code=400,
                manual_url_form=manual_url_form,
                manual_mode_open=mode == "manual_facts",
            )
        finally:
            _close_adapter(fetcher)
            _close_adapter(provider)
        return redirect(url_for("acquisition_candidate_detail", candidate_id=candidate.id))

    @app.post("/acquisition/missions/<mission_id>/start")
    @tenant_required(app)
    def acquisition_mission_start(mission_id: str):
        tenant_id, actor_id = _identity()
        previous_status = ""
        max_seconds = 900
        with Session(get_engine(app)) as db_session:
            mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
            if mission is None:
                abort(404)
            if mission.status not in {"draft", "paused", "failed"}:
                return _render_mission(
                    app,
                    mission_id=mission_id,
                    error="这个任务当前不能启动。",
                    status_code=409,
                )
            previous_status = mission.status
            mission.status = "queued"
            try:
                budget = json.loads(mission.budget_json or "{}")
            except (TypeError, ValueError):
                budget = {}
            configured_seconds = budget.get("max_seconds") if isinstance(budget, dict) else None
            if isinstance(configured_seconds, int) and configured_seconds > 0:
                max_seconds = configured_seconds
            try:
                retrospective = json.loads(mission.retrospective_json or "{}")
            except (TypeError, ValueError):
                retrospective = {}
            if not isinstance(retrospective, dict):
                retrospective = {}
            retrospective["execution_deadline_at"] = (
                datetime.now(UTC) + timedelta(seconds=max_seconds)
            ).isoformat()
            mission.retrospective_json = canonical_json(retrospective)
            add_event(
                db_session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action="acquisition_mission.started",
                target_type="acquisition_mission",
                target_id=mission.id,
                safe_summary="Acquisition mission queued",
            )
            db_session.commit()
        try:
            job_service.create_and_schedule(
                app,
                tenant_id=tenant_id,
                job_type="acquisition_reconcile",
                payload={"mission_id": mission_id, "enforce_timeout": True},
                delay=timedelta(seconds=max_seconds),
            )
            job_service.create_and_enqueue(
                app,
                tenant_id=tenant_id,
                job_type="acquisition_plan",
                payload={"mission_id": mission_id},
            )
        except job_service.JobServiceError:
            with Session(get_engine(app)) as db_session:
                mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
                if mission is not None and mission.status == "queued":
                    mission.status = previous_status
                    db_session.commit()
            return _render_mission(
                app,
                mission_id=mission_id,
                error="任务暂时无法加入队列，请稍后重试。",
                status_code=503,
            )
        return redirect(url_for("acquisition_mission_detail", mission_id=mission_id))

    @app.post("/acquisition/missions/<mission_id>/pause")
    @tenant_required(app)
    def acquisition_mission_pause(mission_id: str):
        return _change_mission_status(
            app,
            mission_id=mission_id,
            allowed={"queued", "running"},
            next_status="paused",
            action="acquisition_mission.paused",
        )

    @app.post("/acquisition/missions/<mission_id>/cancel")
    @tenant_required(app)
    def acquisition_mission_cancel(mission_id: str):
        return _change_mission_status(
            app,
            mission_id=mission_id,
            allowed={"draft", "queued", "running", "paused", "failed"},
            next_status="cancelled",
            action="acquisition_mission.cancelled",
        )

    @app.get("/acquisition/missions/<mission_id>/status")
    @tenant_required(app)
    def acquisition_mission_status(mission_id: str):
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
            if mission is None:
                abort(404)
            business_result = (
                resolve_mission_result(db_session, mission, tenant_id=tenant_id)
                if mission.status in TERMINAL_MISSION_STATUSES
                else None
            )
        return render_template(
            "acquisition/_mission_status.html",
            mission=mission,
            business_result=business_result,
        )

    @app.get("/acquisition/candidates/<candidate_id>")
    @tenant_required(app)
    def acquisition_candidate_detail(candidate_id: str):
        return _render_candidate(app, candidate_id=candidate_id)

    @app.post("/acquisition/candidates/<candidate_id>/retry-verification")
    @tenant_required(app)
    def acquisition_candidate_retry_verification(candidate_id: str):
        tenant_id, actor_id = _identity()
        try:
            result = retry_candidate_verification(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate_id=candidate_id,
            )
        except AcquisitionNotFoundError:
            abort(404)
        except AcquisitionActiveJobError:
            return _render_retry_verification_error(
                app,
                candidate_id=candidate_id,
                error="这个候选已经在验证队列中。",
                status_code=409,
            )
        except AcquisitionRetryConflictError:
            return _render_retry_verification_error(
                app,
                candidate_id=candidate_id,
                error="候选状态已经改变，未重新验证。",
                status_code=409,
            )
        except AcquisitionStateError:
            return _render_retry_verification_error(
                app,
                candidate_id=candidate_id,
                error="这个候选当前不能重新验证。",
                status_code=409,
            )
        except AcquisitionQueueError:
            return _render_retry_verification_error(
                app,
                candidate_id=candidate_id,
                error="验证任务暂时无法加入队列，请稍后重试。",
                status_code=503,
            )
        if _is_htmx():
            return _render_candidate_card(
                app,
                result.candidate_id,
                verification_retried=True,
            )
        return redirect(
            url_for(
                "acquisition_candidate_detail",
                candidate_id=result.candidate_id,
                verification_retried=1,
            )
        )

    @app.post("/acquisition/candidates/<candidate_id>/country-evidence")
    @tenant_required(app)
    def acquisition_candidate_country_evidence(candidate_id: str):
        tenant_id, actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            candidate = CandidateRepository(db_session).get(candidate_id, tenant_id=tenant_id)
            if candidate is None:
                abort(404)
            country_evidence_form = _country_evidence_form_values()
            if not _candidate_accepts_country_evidence(candidate):
                return _render_country_evidence_error(
                    app,
                    candidate_id=candidate_id,
                    error="这个候选当前不需要确认国家证据。",
                    status_code=409,
                    country_evidence_form=country_evidence_form,
                )

        try:
            value = CountryEvidenceInput(**country_evidence_form)
        except ValidationError as exc:
            return _render_country_evidence_error(
                app,
                candidate_id=candidate_id,
                error=_friendly_error(exc),
                status_code=400,
                country_evidence_form=_bounded_country_evidence_form(country_evidence_form),
            )
        country_evidence_form = value.model_dump()

        fetcher = None
        try:
            fetcher = StaticFetcher.from_app(app)
            candidate = override_candidate_country(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate_id=candidate_id,
                value=value,
                fetcher=fetcher,
            )
        except AcquisitionStateError:
            return _render_country_evidence_error(
                app,
                candidate_id=candidate_id,
                error="这个候选当前不需要确认国家证据。",
                status_code=409,
                country_evidence_form=country_evidence_form,
            )
        except FetchError as exc:
            status_code = 503 if exc.code in {"source_timeout", "source_unreachable"} else 400
            return _render_country_evidence_error(
                app,
                candidate_id=candidate_id,
                error=exc.safe_summary,
                status_code=status_code,
                country_evidence_form=country_evidence_form,
            )
        except (AcquisitionError, ManualEvidenceError):
            return _render_country_evidence_error(
                app,
                candidate_id=candidate_id,
                error="无法确认这份国家证据，请检查公开页面和证据句子后重试。",
                status_code=400,
                country_evidence_form=country_evidence_form,
            )
        finally:
            _close_adapter(fetcher)
        if _is_htmx():
            return _render_candidate_card(app, candidate.id)
        return redirect(url_for("acquisition_candidate_detail", candidate_id=candidate.id))

    @app.post("/acquisition/candidates/<candidate_id>/review")
    @tenant_required(app)
    def acquisition_candidate_review(candidate_id: str):
        tenant_id, actor_id = _identity()
        try:
            candidate = review_candidate(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate_id=candidate_id,
                action=request.form.get("action", ""),
                reason_code=request.form.get("reason_code", ""),
                note=request.form.get("note", ""),
            )
        except AcquisitionError as exc:
            return _render_candidate(
                app,
                candidate_id=candidate_id,
                error=_friendly_error(exc),
                status_code=400,
            )
        if _is_htmx():
            return _render_candidate_card(app, candidate.id)
        return redirect(url_for("acquisition_candidate_detail", candidate_id=candidate.id))

    @app.post("/acquisition/candidates/bulk/reject")
    @tenant_required(app)
    def acquisition_candidates_bulk_reject():
        tenant_id, actor_id = _identity()
        candidate_ids = request.form.getlist("candidate_ids")
        mission_id = request.form.get("mission_id", "")
        try:
            reviewed = bulk_review_candidates(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate_ids=candidate_ids,
                action="reject",
                reason_code=request.form.get("reason_code", ""),
                note=request.form.get("note", ""),
            )
        except AcquisitionError as exc:
            return _bulk_error(app, mission_id, exc)
        return _bulk_success(app, mission_id, reviewed)

    @app.post("/acquisition/candidates/bulk/accept")
    @tenant_required(app)
    def acquisition_candidates_bulk_accept():
        tenant_id, actor_id = _identity()
        candidate_ids = request.form.getlist("candidate_ids")
        mission_id = request.form.get("mission_id", "")
        try:
            candidates = _validate_bulk_accept(
                app,
                tenant_id=tenant_id,
                candidate_ids=candidate_ids,
            )
            if request.form.get("confirm") != "yes":
                return _render_mission(
                    app,
                    mission_id=mission_id,
                    bulk_confirmation=candidates,
                )
            reviewed = bulk_review_candidates(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                candidate_ids=candidate_ids,
                action="accept",
            )
        except AcquisitionError as exc:
            return _bulk_error(app, mission_id, exc)
        return _bulk_success(app, mission_id, reviewed)

    @app.get("/notifications")
    @tenant_required(app)
    def acquisition_notifications():
        tenant_id, _actor_id = _identity()
        return render_template(
            "acquisition/notifications.html",
            notifications=list_notifications(app, tenant_id=tenant_id),
        )

    @app.post("/notifications/<notification_id>/read")
    @tenant_required(app)
    def acquisition_notification_read(notification_id: str):
        tenant_id, _actor_id = _identity()
        notification = mark_notification_read(
            app,
            tenant_id=tenant_id,
            notification_id=notification_id,
        )
        if notification is None:
            abort(404)
        return redirect(url_for("acquisition_notifications"))

    @app.post("/notifications/read-all")
    @tenant_required(app)
    def acquisition_notifications_read_all():
        tenant_id, _actor_id = _identity()
        mark_all_notifications_read(app, tenant_id=tenant_id)
        return redirect(url_for("acquisition_notifications"))


def _identity() -> tuple[str, str]:
    return str(session.get("tenant_id", "")), str(session.get("user_id", ""))


def _change_mission_status(
    app: Flask,
    *,
    mission_id: str,
    allowed: set[str],
    next_status: str,
    action: str,
):
    tenant_id, actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            abort(404)
        if mission.status not in allowed:
            return _render_mission(
                app,
                mission_id=mission_id,
                error="任务当前状态不允许这个操作。",
                status_code=409,
            )
        mission.status = next_status
        add_event(
            db_session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action=action,
            target_type="acquisition_mission",
            target_id=mission.id,
            safe_summary=f"Acquisition mission changed to {next_status}",
        )
        db_session.commit()
    return redirect(url_for("acquisition_mission_detail", mission_id=mission_id))


def _render_mission(
    app: Flask,
    *,
    mission_id: str,
    error: str = "",
    status_code: int = 200,
    bulk_confirmation: list[AcquisitionCandidate] | None = None,
    manual_url_form: dict[str, str] | None = None,
    manual_mode_open: bool = False,
):
    tenant_id, _actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            abort(404)
        product = ProductKnowledgeRepository(db_session).get(
            mission.product_snapshot_id, tenant_id=tenant_id
        )
        candidates = CandidateRepository(db_session).list_for_mission(
            mission_id, tenant_id=tenant_id
        )
        candidate_views = [
            _candidate_view(db_session, item, tenant_id=tenant_id) for item in candidates
        ]
        channel_policy = _json_value(mission.channel_policy_json, {})
        view = {
            "target": _json_value(mission.target_profile_json, {}),
            "channels": channel_policy,
            "budget": _json_value(mission.budget_json, {}),
            "plan": _json_value(mission.plan_json, {}),
        }
        manual_url_available = mission.status != "cancelled" and _manual_url_policy_allows(
            channel_policy
        )
        business_result = (
            resolve_mission_result(
                db_session,
                mission,
                tenant_id=tenant_id,
                candidates=candidates,
            )
            if mission.status in TERMINAL_MISSION_STATUSES
            else None
        )
        business_result_reasons = (
            tuple(
                BUSINESS_RESULT_REASON_LABELS.get(code, "部分执行步骤未完成")
                for code in business_result.reason_codes
            )
            if business_result is not None
            else ()
        )
    return (
        render_template(
            "acquisition/mission_detail.html",
            mission=mission,
            product=product,
            candidate_views=candidate_views,
            view=view,
            rejection_reasons=REJECTION_REASONS,
            error=error,
            bulk_confirmation=bulk_confirmation or [],
            manual_url_form=manual_url_form or _empty_manual_url_form(),
            manual_mode_open=manual_mode_open,
            manual_url_available=manual_url_available,
            business_result=business_result,
            business_result_reasons=business_result_reasons,
        ),
        status_code,
    )


def _render_candidate(
    app: Flask,
    *,
    candidate_id: str,
    error: str = "",
    status_code: int = 200,
    country_evidence_form: dict[str, str] | None = None,
):
    tenant_id, _actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        candidate = CandidateRepository(db_session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            abort(404)
        mission = MissionRepository(db_session).get(candidate.mission_id, tenant_id=tenant_id)
        candidate_view = _candidate_view(db_session, candidate, tenant_id=tenant_id)
    return (
        render_template(
            "acquisition/candidate_detail.html",
            mission=mission,
            view=candidate_view,
            rejection_reasons=REJECTION_REASONS,
            error=error,
            verification_retried=(
                request.method == "GET" and request.args.get("verification_retried") == "1"
            ),
            country_evidence_form=country_evidence_form or {},
        ),
        status_code,
    )


def _render_candidate_card(
    app: Flask,
    candidate_id: str,
    *,
    error: str = "",
    country_evidence_form: dict[str, str] | None = None,
    verification_retried: bool = False,
):
    tenant_id, _actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        candidate = CandidateRepository(db_session).get(candidate_id, tenant_id=tenant_id)
        if candidate is None:
            abort(404)
        view = _candidate_view(db_session, candidate, tenant_id=tenant_id)
    return render_template(
        "acquisition/_candidate_card.html",
        view=view,
        rejection_reasons=REJECTION_REASONS,
        card_error=error,
        verification_retried=verification_retried,
        country_evidence_form=country_evidence_form or {},
    )


def _render_country_evidence_error(
    app: Flask,
    *,
    candidate_id: str,
    error: str,
    status_code: int,
    country_evidence_form: dict[str, str],
):
    bounded_form = _bounded_country_evidence_form(country_evidence_form)
    if _is_htmx():
        response = make_response(
            _render_candidate_card(
                app,
                candidate_id,
                error=error,
                country_evidence_form=bounded_form,
            ),
            status_code,
        )
        response.headers["HX-LeadFlow-Swap-Error"] = "true"
        response.headers["HX-Retarget"] = f"#candidate-{candidate_id}"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return _render_candidate(
        app,
        candidate_id=candidate_id,
        error=error,
        status_code=status_code,
        country_evidence_form=bounded_form,
    )


def _render_retry_verification_error(
    app: Flask,
    *,
    candidate_id: str,
    error: str,
    status_code: int,
):
    if _is_htmx():
        response = make_response(
            _render_candidate_card(app, candidate_id, error=error),
            status_code,
        )
        response.headers["HX-LeadFlow-Swap-Error"] = "true"
        response.headers["HX-Retarget"] = f"#candidate-{candidate_id}"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return _render_candidate(
        app,
        candidate_id=candidate_id,
        error=error,
        status_code=status_code,
    )


def _candidate_view(
    db_session: Session,
    candidate: AcquisitionCandidate,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    evidence = list(
        EvidenceRepository(db_session).list_for_candidate(candidate.id, tenant_id=tenant_id)
    )
    assessment = AssessmentRepository(db_session).latest_for_candidate(
        candidate.id, tenant_id=tenant_id
    )
    has_assessment = assessment is not None
    priority_mode = assessment.priority_mode if assessment else ""
    is_provisional = bool(assessment and priority_mode != "full_v1")
    score_breakdown = _json_value(assessment.score_breakdown_json, {}) if assessment else {}
    display_band = candidate.priority_band or ""
    if is_provisional and display_band in {"S", "A"}:
        display_band = "B"
    if candidate.status == "rejected":
        priority_label = "已拒绝"
        display_priority = None
    elif not assessment:
        priority_label = "待评估"
        display_priority = None
    elif priority_mode == "evidence_only_provisional_v1":
        priority_label = "待补充匹配证据"
        display_priority = None
    elif is_provisional:
        priority_label = f"暂定 {display_band or '待评估'}"
        display_priority = display_band or None
    else:
        priority_label = f"{display_band or '待评估'} 优先级"
        display_priority = display_band or None
    reason = assessment.explanation if assessment and assessment.explanation else ""
    reason_by_code = {
        "eligible": "国家和买家类型证据符合当前目标。",
        "country_confirmed": "目标国家已经确认，建议进一步审核。",
        "missing_contact_path": "基础匹配，但仍需补充联系路径。",
        "country_unknown": "目标国家仍需确认。",
        "country_conflicting": "国家证据存在冲突。",
        "buyer_type_unknown": "买家类型仍需公开证据确认。",
        "product_evidence_unknown": "目标产品相关性仍需公开证据确认。",
        "contact_path_unknown": "公开联系方式仍需确认。",
        "wrong_country": "公开证据显示目标国家不匹配。",
        "wrong_buyer_type": "公开证据显示该企业不是目标买家类型。",
        "excluded_business": "公开证据命中了排除业务类型。",
    }
    if candidate.status == "rejected" and candidate.eligibility_code in reason_by_code:
        reason = reason_by_code[candidate.eligibility_code]
    elif not reason:
        reason = reason_by_code.get(
            candidate.eligibility_code,
            "根据现有公开信息值得进一步审核。",
        )
    processing_note = ""
    if priority_mode == "evidence_only_provisional_v1":
        processing_note = "官网验证或结构化分析尚未完成；当前为临时评估，请重新验证。"
    elif priority_mode == "fit_quality_provisional_v1":
        processing_note = "尚未观察到采购意向信号；当前优先级仅依据匹配度和证据质量。"
    verification_jobs = list(
        db_session.query(Job)
        .filter(
            Job.tenant_id == tenant_id,
            Job.job_type == "website_verify",
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
    )
    latest_verification = next(
        (
            item
            for item in verification_jobs
            if _job_payload(item).get("candidate_id") == candidate.id
        ),
        None,
    )
    if candidate.entity_type == "source_identity_unverified":
        processing_note = "当前网页与公司域名不一致，已按第三方页面保存，需提供公司官网后再验证。"
    elif latest_verification is not None and latest_verification.status == "retrying":
        processing_note = "官网暂时不可访问，系统正在执行本任务内的有限退避重试。"
    elif (
        latest_verification is not None
        and _job_payload(latest_verification).get("analysis_retry") is True
        and latest_verification.status in {"queued", "running"}
    ):
        processing_note = "AI 结构化分析未通过校验，已安排一次延迟重分析。"
    elif latest_verification is not None and latest_verification.error_code == "invalid_response":
        processing_note = "AI 结构化分析未通过校验；本次有限重分析已结束，可手动重新验证公开网页。"
    observed_facts = _candidate_observed_facts(candidate.observed_facts_json)
    inferences = _json_value(candidate.inferences_json, [])
    analysis_items: list[object] = [reason]
    if isinstance(inferences, list):
        analysis_items.extend(item for item in inferences if item != reason)
    unknowns = _json_value(candidate.unknowns_json, [])
    if not unknowns and priority_mode == "evidence_only_provisional_v1":
        unknowns = ["官网结构化事实、目标国家、买家角色和联系方式仍可能需要确认。"]
    elif not unknowns and priority_mode == "fit_quality_provisional_v1":
        unknowns = ["尚未观察到明确采购意向信号。"]
    score_rows = _candidate_score_rows(score_breakdown)
    if candidate.status == "rejected":
        score_rows = [row for row in score_rows if row[0] != "综合优先级"]
    company_country_label = "待确认"
    if candidate.country_resolution_status == "confirmed":
        country_code = candidate.hq_country_code or candidate.opportunity_country_code
        company_country_label = f"已确认（{country_code or '—'}）"
    elif candidate.country_resolution_status == "conflicting":
        company_country_label = "证据冲突，待确认"
    country_signal_note = ""
    if isinstance(unknowns, list):
        for item in unknowns:
            if isinstance(item, str) and item.startswith("likely:"):
                parts = item.split(":", 2)
                country_code = parts[1] if len(parts) > 1 else ""
                country_signal_note = (
                    f"国家域名信号：可能在 {country_code}；仍需官方地址或注册信息确认。"
                )
                break
    return {
        "candidate": candidate,
        "primary_reason": reason,
        "contacts": _json_value(candidate.contact_json, {}),
        "observed_facts": observed_facts,
        "inferences": inferences,
        "analysis_items": analysis_items,
        "unknowns": unknowns,
        "evidence": evidence,
        "assessment": assessment,
        "has_assessment": has_assessment,
        "priority_mode": priority_mode,
        "is_provisional": is_provisional,
        "priority_label": priority_label,
        "display_priority": display_priority,
        "processing_note": processing_note,
        "score_breakdown": score_breakdown,
        "score_rows": score_rows,
        "company_country_label": company_country_label,
        "country_signal_note": country_signal_note,
    }


def _candidate_observed_facts(value: str) -> list[object]:
    observed = _json_value(value, [])
    if isinstance(observed, list):
        return observed
    if not isinstance(observed, dict):
        return []
    facts: list[object] = []
    if observed.get("buyer_type"):
        facts.append(f"买家类型：{observed['buyer_type']}")
    product_terms = observed.get("product_terms", [])
    if isinstance(product_terms, list) and product_terms:
        facts.append(f"相关产品：{', '.join(map(str, product_terms))}")
    claims = observed.get("claims", [])
    if isinstance(claims, list):
        facts.extend(claims)
    return facts


def _job_payload(job: Job) -> dict[str, Any]:
    value = _json_value(job.payload_json, {})
    return value if isinstance(value, dict) else {}


def _candidate_score_rows(score_breakdown: object) -> list[tuple[str, object]]:
    if not isinstance(score_breakdown, dict):
        return []
    fields = (
        ("fit_score", "匹配度", "fit"),
        ("intent_score", "采购意向", "intent"),
        ("data_quality_score", "证据质量", "data_quality"),
        ("priority_score", "综合优先级", "priority"),
        ("signal_coverage", "信号覆盖", "coverage"),
    )
    rows: list[tuple[str, object]] = []
    for key, label, legacy_key in fields:
        if key in score_breakdown:
            value = score_breakdown[key]
        elif legacy_key in score_breakdown:
            value = score_breakdown[legacy_key]
        else:
            continue
        if value is None:
            display_value: object = "未观察到" if key == "intent_score" else "待补充"
        elif key == "signal_coverage":
            display_value = f"{value}%"
        else:
            display_value = value
        rows.append((label, display_value))
    return rows


def _validate_bulk_accept(
    app: Flask,
    *,
    tenant_id: str,
    candidate_ids: list[str],
) -> list[AcquisitionCandidate]:
    unique_ids = list(dict.fromkeys(item.strip() for item in candidate_ids if item.strip()))
    if not unique_ids:
        raise AcquisitionError("at least one candidate is required")
    if len(unique_ids) > 20:
        raise AcquisitionError("bulk accept is limited to 20 candidates")
    with Session(get_engine(app)) as db_session:
        rows = list(
            db_session.query(AcquisitionCandidate).filter(
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.id.in_(unique_ids),
            )
        )
        by_id = {item.id: item for item in rows}
        if len(by_id) != len(unique_ids):
            raise AcquisitionError("one or more candidates were not found")
        candidates = [by_id[item_id] for item_id in unique_ids]
        if any(
            item.status != "eligible"
            or item.country_resolution_status != "confirmed"
            or item.eligibility_code in {"country_unknown", "country_conflicting"}
            for item in candidates
        ):
            raise AcquisitionError(
                "all candidates must be eligible with confirmed country evidence"
            )
        return candidates


def _bulk_error(app: Flask, mission_id: str, exc: AcquisitionError):
    if not mission_id:
        abort(400)
    return _render_mission(
        app,
        mission_id=mission_id,
        error=_friendly_error(exc),
        status_code=400,
    )


def _bulk_success(
    app: Flask,
    mission_id: str,
    reviewed: list[AcquisitionCandidate],
):
    if _is_htmx():
        return "\n".join(_render_candidate_card(app, item.id) for item in reviewed)
    return redirect(url_for("acquisition_mission_detail", mission_id=mission_id))


def _is_htmx() -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def _parse_facts(value: str) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    for line in _lines(value):
        separator = ":" if ":" in line else "=" if "=" in line else ""
        if separator:
            key, fact_value = line.split(separator, 1)
            if key.strip() and fact_value.strip():
                facts.append({key.strip(): fact_value.strip()})
        else:
            facts.append({"fact": line})
    return facts


def _form_int(name: str, default: int) -> int:
    raw = request.form.get(name, "").strip()
    return default if not raw else int(raw)


def _product_form_values() -> dict[str, str]:
    return {
        "product_name": request.form.get("product_name", ""),
        "summary": request.form.get("summary", ""),
        "facts": request.form.get("facts", ""),
        "prohibited_claims": request.form.get("prohibited_claims", ""),
    }


def _mission_form_values() -> dict[str, Any]:
    return {
        "product_snapshot_id": request.form.get("product_snapshot_id", ""),
        "country_codes": request.form.getlist("country_codes"),
        "buyer_types": request.form.getlist("buyer_types"),
        "industries": request.form.get("industries", ""),
        "company_sizes": request.form.get("company_sizes", ""),
        "include_terms": request.form.get("include_terms", ""),
        "exclude_terms": request.form.get("exclude_terms", ""),
        "allowed_channels": request.form.getlist("allowed_channels") or ["mimo_web", "manual_url"],
        "max_candidates": request.form.get("max_candidates", "30"),
        "max_verify": request.form.get("max_verify", "10"),
        "max_search_actions": request.form.get("max_search_actions", "5"),
        "max_seconds": request.form.get("max_seconds", "900"),
    }


def _manual_url_policy_allows(policy: Any) -> bool:
    if not isinstance(policy, dict):
        return False
    allowed_channels = policy.get("allowed_channels")
    return isinstance(allowed_channels, list) and "manual_url" in allowed_channels


def _candidate_accepts_country_evidence(candidate: AcquisitionCandidate) -> bool:
    return candidate.status == "needs_evidence" and candidate.eligibility_code in {
        "country_unknown",
        "country_conflicting",
    }


def _country_evidence_form_values() -> dict[str, str]:
    return {
        "country_code": request.form.get("country_code", "").strip().upper(),
        "source_url": request.form.get("source_url", "").strip(),
        "evidence_text": request.form.get("evidence_text", "").strip(),
        "reason_code": request.form.get("reason_code", "").strip(),
    }


def _bounded_country_evidence_form(values: dict[str, str]) -> dict[str, str]:
    limits = {
        "country_code": 2,
        "source_url": 1000,
        "evidence_text": 1000,
        "reason_code": 40,
    }
    return {name: values.get(name, "")[:limit] for name, limit in limits.items()}


def _close_adapter(adapter: Any | None) -> None:
    close = getattr(adapter, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        return


def _empty_manual_url_form() -> dict[str, str]:
    return {
        "url": "",
        "company_name": "",
        "opportunity_country_code": "",
        "buyer_type": "",
        "evidence_text": "",
        "contact_path": "",
    }


def _manual_url_form_values() -> dict[str, str]:
    return {
        "url": request.form.get("url", "").strip(),
        "company_name": request.form.get("company_name", "").strip(),
        "opportunity_country_code": request.form.get("opportunity_country_code", "")
        .strip()
        .upper(),
        "buyer_type": request.form.get("buyer_type", "").strip().lower(),
        "evidence_text": request.form.get("evidence_text", "").strip(),
        "contact_path": request.form.get("contact_path", "").strip(),
    }


def _bounded_manual_url_form(values: dict[str, str]) -> dict[str, str]:
    limits = {
        "url": 1000,
        "company_name": 300,
        "opportunity_country_code": 2,
        "buyer_type": 120,
        "evidence_text": 1000,
        "contact_path": 1000,
    }
    return {name: values.get(name, "")[:limit] for name, limit in limits.items()}


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = [str(item.get("msg", "输入无效")) for item in exc.errors()[:3]]
        return "；".join(parts)
    known = {
        "product name, summary and facts are required": "产品名称、摘要和至少一条事实都是必填项。",
        "candidate review input is invalid": "请选择有效的审核动作和原因。",
        "at least one candidate is required": "请至少选择一个候选客户。",
        "one or more candidates were not found": "部分候选不存在或不属于当前工作区。",
        "bulk accept is limited to 20 candidates": "每次最多批量接受 20 个候选。",
        "bulk reject is limited to 100 candidates": "每次最多批量拒绝 100 个候选。",
        "all candidates must be eligible with confirmed country evidence": (
            "整批未执行：所有候选都必须通过筛选并确认目标国家。"
        ),
    }
    return known.get(str(exc), str(exc))


def _json_value(value: str, default: Any) -> Any:
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default
