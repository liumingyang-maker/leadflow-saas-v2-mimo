"""Tenant-scoped routes for the solo acquisition workflow."""

from __future__ import annotations

import json
from typing import Any

from flask import Flask, abort, redirect, render_template, request, session, url_for
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.accounts.guards import tenant_required
from app.modules.acquisition.contracts import DEFAULT_LANGUAGES, MissionCreateInput
from app.modules.acquisition.models import AcquisitionCandidate
from app.modules.acquisition.repository import (
    AssessmentRepository,
    CandidateRepository,
    EvidenceRepository,
    MissionRepository,
    ProductKnowledgeRepository,
)
from app.modules.acquisition.service import (
    AcquisitionError,
    bulk_review_candidates,
    create_mission,
    create_product_snapshot,
    review_candidate,
)
from app.modules.audit.service import add_event
from app.modules.jobs.service import JobServiceError, create_and_enqueue

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

    @app.post("/acquisition/missions/<mission_id>/start")
    @tenant_required(app)
    def acquisition_mission_start(mission_id: str):
        tenant_id, actor_id = _identity()
        previous_status = ""
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
            create_and_enqueue(
                app,
                tenant_id=tenant_id,
                job_type="acquisition_plan",
                payload={"mission_id": mission_id},
            )
        except JobServiceError:
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
        return render_template("acquisition/_mission_status.html", mission=mission)

    @app.get("/acquisition/candidates/<candidate_id>")
    @tenant_required(app)
    def acquisition_candidate_detail(candidate_id: str):
        return _render_candidate(app, candidate_id=candidate_id)

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
        view = {
            "target": _json_value(mission.target_profile_json, {}),
            "channels": _json_value(mission.channel_policy_json, {}),
            "budget": _json_value(mission.budget_json, {}),
            "plan": _json_value(mission.plan_json, {}),
        }
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
        ),
        status_code,
    )


def _render_candidate(
    app: Flask,
    *,
    candidate_id: str,
    error: str = "",
    status_code: int = 200,
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
        ),
        status_code,
    )


def _render_candidate_card(app: Flask, candidate_id: str):
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
    reason = assessment.explanation if assessment and assessment.explanation else ""
    if not reason:
        reason = {
            "eligible": "国家和买家类型证据符合当前目标。",
            "country_confirmed": "目标国家已经确认，建议进一步审核。",
            "missing_contact_path": "基础匹配，但仍需补充联系路径。",
            "country_unknown": "目标国家仍需确认。",
            "country_conflicting": "国家证据存在冲突。",
        }.get(candidate.eligibility_code, "根据现有公开信息值得进一步审核。")
    return {
        "candidate": candidate,
        "primary_reason": reason,
        "contacts": _json_value(candidate.contact_json, {}),
        "observed_facts": _json_value(candidate.observed_facts_json, []),
        "inferences": _json_value(candidate.inferences_json, []),
        "unknowns": _json_value(candidate.unknowns_json, []),
        "evidence": evidence,
        "assessment": assessment,
        "score_breakdown": (_json_value(assessment.score_breakdown_json, {}) if assessment else {}),
    }


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
