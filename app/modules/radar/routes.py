from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Flask, abort, redirect, render_template, session, url_for
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.extensions import get_engine
from app.integrations.ai.mimo import ProviderError
from app.modules.accounts.guards import tenant_required
from app.modules.acquisition.repository import MissionRepository
from app.modules.radar.models import RadarRun, RadarSnapshot
from app.modules.radar.policies import RadarPolicyError
from app.modules.radar.repository import CompetitorProfileRepository, RadarSuggestionRepository
from app.modules.radar.service import (
    RadarNotFoundError,
    RadarServiceError,
    cancel_manual_run,
    decide_competitor_suggestion,
    request_competitor_suggestions,
    request_manual_run,
)
from app.modules.radar.views import profile_view, run_view, snapshot_view, suggestion_view


def register_radar_routes(app: Flask) -> None:
    def radar_required(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def guarded(*args: Any, **kwargs: Any):
            require_capability(app, Capability.COMPETITOR_RADAR)
            return view(*args, **kwargs)

        return tenant_required(app)(guarded)

    @app.get("/radar")
    @radar_required
    def radar_overview():
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            profiles = [
                profile_view(item)
                for item in CompetitorProfileRepository(db_session).list_for_tenant(
                    tenant_id=tenant_id
                )
            ]
            missions = MissionRepository(db_session).list_by_status(
                ("queued", "running", "paused"),
                tenant_id=tenant_id,
            )
        return render_template("radar/overview.html", profiles=profiles, missions=missions)

    @app.get("/radar/missions/<mission_id>/suggestions")
    @radar_required
    def radar_suggestions(mission_id: str):
        return _render_suggestions(app, mission_id=mission_id)

    @app.post("/radar/missions/<mission_id>/suggestions/request")
    @radar_required
    def radar_request_suggestions(mission_id: str):
        tenant_id, actor_id = _identity()
        try:
            request_competitor_suggestions(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                mission_id=mission_id,
            )
        except RadarNotFoundError:
            abort(404)
        except ProviderError:
            return _render_suggestions(
                app,
                mission_id=mission_id,
                error="The research provider is unavailable. Try again later.",
                status_code=503,
            )
        except (RadarPolicyError, RadarServiceError):
            return _render_suggestions(
                app,
                mission_id=mission_id,
                error="Suggestions could not be safely stored for this mission.",
                status_code=400,
            )
        return redirect(url_for("radar_suggestions", mission_id=mission_id))

    @app.post("/radar/suggestions/<suggestion_id>/approve")
    @radar_required
    def radar_approve_suggestion(suggestion_id: str):
        tenant_id, actor_id = _identity()
        try:
            profile = decide_competitor_suggestion(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                suggestion_id=suggestion_id,
                action="approve",
            )
        except RadarNotFoundError:
            abort(404)
        except (RadarPolicyError, RadarServiceError):
            abort(400)
        if profile is None:
            abort(409)
        return redirect(url_for("radar_profile_detail", profile_id=profile.id))

    @app.post("/radar/suggestions/<suggestion_id>/dismiss")
    @radar_required
    def radar_dismiss_suggestion(suggestion_id: str):
        tenant_id, actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            suggestion = RadarSuggestionRepository(db_session).get(
                suggestion_id,
                tenant_id=tenant_id,
            )
            if suggestion is None:
                abort(404)
            mission_id = suggestion.mission_id
        try:
            decide_competitor_suggestion(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                suggestion_id=suggestion_id,
                action="dismiss",
            )
        except RadarNotFoundError:
            abort(404)
        except (RadarPolicyError, RadarServiceError):
            abort(400)
        return redirect(url_for("radar_suggestions", mission_id=mission_id))

    @app.get("/radar/profiles/<profile_id>")
    @radar_required
    def radar_profile_detail(profile_id: str):
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            profile = CompetitorProfileRepository(db_session).get(profile_id, tenant_id=tenant_id)
            if profile is None:
                abort(404)
            view = profile_view(profile)
            runs = list(
                db_session.scalars(
                    select(RadarRun)
                    .where(RadarRun.profile_id == profile.id, RadarRun.tenant_id == tenant_id)
                    .order_by(RadarRun.created_at.desc())
                    .limit(20)
                )
            )
        return render_template(
            "radar/profile_detail.html",
            profile=view,
            runs=[run_view(item) for item in runs],
        )

    @app.post("/radar/profiles/<profile_id>/runs")
    @radar_required
    def radar_request_manual_run(profile_id: str):
        tenant_id, actor_id = _identity()
        try:
            run = request_manual_run(
                app,
                tenant_id=tenant_id,
                actor_id=actor_id,
                profile_id=profile_id,
            )
        except RadarNotFoundError:
            abort(404)
        except RadarServiceError:
            abort(400)
        return redirect(url_for("radar_run_detail", run_id=run.id))

    @app.get("/radar/runs/<run_id>")
    @radar_required
    def radar_run_detail(run_id: str):
        tenant_id, _actor_id = _identity()
        with Session(get_engine(app)) as db_session:
            run = db_session.scalar(
                select(RadarRun).where(RadarRun.id == run_id, RadarRun.tenant_id == tenant_id)
            )
            if run is None:
                abort(404)
            profile = CompetitorProfileRepository(db_session).get(
                run.profile_id,
                tenant_id=tenant_id,
            )
            if profile is None:
                abort(404)
            snapshots = list(
                db_session.scalars(
                    select(RadarSnapshot)
                    .where(RadarSnapshot.run_id == run.id, RadarSnapshot.tenant_id == tenant_id)
                    .order_by(RadarSnapshot.created_at.asc(), RadarSnapshot.id.asc())
                )
            )
            view = run_view(run)
            profile_data = profile_view(profile)
        return render_template(
            "radar/run_detail.html",
            run=view,
            profile=profile_data,
            snapshots=[snapshot_view(item) for item in snapshots],
        )

    @app.post("/radar/runs/<run_id>/cancel")
    @radar_required
    def radar_cancel_manual_run(run_id: str):
        tenant_id, actor_id = _identity()
        try:
            cancel_manual_run(app, tenant_id=tenant_id, actor_id=actor_id, run_id=run_id)
        except RadarNotFoundError:
            abort(404)
        return redirect(url_for("radar_run_detail", run_id=run_id))


def _render_suggestions(
    app: Flask,
    *,
    mission_id: str,
    error: str = "",
    status_code: int = 200,
):
    tenant_id, _actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        mission = MissionRepository(db_session).get(mission_id, tenant_id=tenant_id)
        if mission is None:
            abort(404)
        suggestions = [
            suggestion_view(item)
            for item in RadarSuggestionRepository(db_session).list_for_mission(
                mission_id,
                tenant_id=tenant_id,
            )
        ]
    return (
        render_template(
            "radar/suggestions.html",
            mission=mission,
            suggestions=suggestions,
            error=error,
        ),
        status_code,
    )


def _identity() -> tuple[str, str]:
    return str(session.get("tenant_id", "")), str(session.get("user_id", ""))
