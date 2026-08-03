from __future__ import annotations

import uuid
from datetime import UTC, datetime

from flask import Flask
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, require_capability
from app.extensions import get_engine
from app.integrations.ai.mimo import build_mimo_provider
from app.modules.acquisition.repository import MissionRepository, ProductKnowledgeRepository
from app.modules.audit.service import add_event
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JobServiceError, enqueue_existing_job
from app.modules.radar import suggestions as suggestion_policy
from app.modules.radar.models import (
    CompetitorProfile,
    RadarChangeSignal,
    RadarCompetitorSuggestion,
    RadarRun,
)
from app.modules.radar.policies import (
    RadarPolicyError,
    canonical_json,
    parse_bounded_json_object,
    require_active_mission,
    require_matching_product_snapshot,
)
from app.modules.radar.repository import CompetitorProfileRepository, RadarSuggestionRepository
from app.modules.radar.suggestions import RadarProposalError


class RadarServiceError(RuntimeError):
    """Safe application-level Radar failure."""


class RadarNotFoundError(RadarServiceError):
    """A tenant-scoped Radar resource does not exist."""


def _session(app: Flask) -> Session:
    session = Session(get_engine(app))
    session.expire_on_commit = False
    return session


def _load_mission_context(
    session: Session,
    *,
    tenant_id: str,
    mission_id: str,
) -> tuple[str, dict]:
    mission = MissionRepository(session).get(mission_id, tenant_id=tenant_id)
    if mission is None:
        raise RadarNotFoundError("Mission was not found")
    require_active_mission(mission)
    snapshot = ProductKnowledgeRepository(session).get(
        mission.product_snapshot_id,
        tenant_id=tenant_id,
    )
    if snapshot is None:
        raise RadarPolicyError("Mission product snapshot does not match")
    require_matching_product_snapshot(mission, snapshot)
    return snapshot.summary[:10_000], parse_bounded_json_object(mission.target_profile_json)


def request_competitor_suggestions(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    mission_id: str,
) -> tuple[str, ...]:
    """Manually request cited suggestions; does not fetch or schedule any Radar work."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    require_capability(app, Capability.AI_RESEARCH)
    with _session(app) as session:
        product_summary, target_profile = _load_mission_context(
            session,
            tenant_id=tenant_id,
            mission_id=mission_id,
        )

    provider = build_mimo_provider(app, tenant_id=tenant_id)
    try:
        proposal = provider.suggest_competitors(
            product_summary=product_summary,
            target_profile=target_profile,
        )
    finally:
        provider.close()
    try:
        validated = suggestion_policy.validate_competitor_suggestions(
            proposal,
            product_summary=product_summary,
            resolver=suggestion_policy.system_resolver,
        )
    except RadarProposalError as exc:
        raise RadarServiceError("Competitor suggestions could not be safely stored") from exc

    persisted_ids: list[str] = []
    with _session(app) as session:
        _load_mission_context(session, tenant_id=tenant_id, mission_id=mission_id)
        profiles = CompetitorProfileRepository(session)
        suggestions = RadarSuggestionRepository(session)
        for item in validated[:10]:
            if (
                profiles.get_by_mission_domain(
                    mission_id,
                    item.canonical_domain,
                    tenant_id=tenant_id,
                )
                is not None
            ):
                continue
            existing = suggestions.get_by_mission_domain(
                mission_id,
                item.canonical_domain,
                tenant_id=tenant_id,
            )
            if existing is None:
                created = RadarCompetitorSuggestion(
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    company_name=item.company_name,
                    canonical_domain=item.canonical_domain,
                    official_url=item.official_url,
                    reason_codes_json=item.reason_codes_json,
                    evidence_json=item.evidence_json,
                    evidence_hash=item.evidence_hash,
                )
                try:
                    with session.begin_nested():
                        suggestions.add(created, tenant_id=tenant_id)
                        session.flush()
                except IntegrityError:
                    existing = suggestions.get_by_mission_domain(
                        mission_id,
                        item.canonical_domain,
                        tenant_id=tenant_id,
                    )
                    if existing is None:
                        raise RadarServiceError(
                            "Competitor suggestion could not be stored"
                        ) from None
                else:
                    persisted_ids.append(created.id)
                    continue
            if existing.status == "dismissed" and existing.evidence_hash != item.evidence_hash:
                existing.company_name = item.company_name
                existing.official_url = item.official_url
                existing.reason_codes_json = item.reason_codes_json
                existing.evidence_json = item.evidence_json
                existing.evidence_hash = item.evidence_hash
                existing.status = "proposed"
                existing.decided_by = ""
                existing.decided_at = None
                persisted_ids.append(existing.id)

        add_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="radar.suggestions_requested",
            target_type="acquisition_mission",
            target_id=mission_id,
            safe_summary=f"Stored {len(persisted_ids)} competitor suggestions",
        )
        session.commit()
    return tuple(persisted_ids)


def decide_competitor_suggestion(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    suggestion_id: str,
    action: str,
) -> CompetitorProfile | None:
    """Approve or dismiss one tenant-owned suggestion in one transaction."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    if action not in {"approve", "dismiss"}:
        raise RadarServiceError("Unknown competitor suggestion decision")

    with _session(app) as session:
        suggestions = RadarSuggestionRepository(session)
        suggestion = suggestions.get(suggestion_id, tenant_id=tenant_id)
        if suggestion is None:
            raise RadarNotFoundError("Competitor suggestion was not found")
        profiles = CompetitorProfileRepository(session)
        profile = profiles.get_by_mission_domain(
            suggestion.mission_id,
            suggestion.canonical_domain,
            tenant_id=tenant_id,
        )

        if action == "dismiss":
            if suggestion.status == "approved":
                raise RadarServiceError("Approved suggestions cannot be dismissed")
            if suggestion.status == "dismissed":
                return None
        elif suggestion.status == "approved" and profile is not None:
            return profile

        _load_mission_context(session, tenant_id=tenant_id, mission_id=suggestion.mission_id)
        now = datetime.now(UTC)

        if action == "dismiss":
            suggestion.status = "dismissed"
            suggestion.decided_by = actor_id
            suggestion.decided_at = now
            add_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action="radar.suggestion_dismissed",
                target_type="radar_competitor_suggestion",
                target_id=suggestion.id,
                safe_summary="Dismissed competitor suggestion",
            )
            session.commit()
            return None

        if suggestion.status == "dismissed":
            raise RadarServiceError("Dismissed suggestions require new cited evidence")
        changed = suggestion.status != "approved" or profile is None
        if profile is None:
            mission = MissionRepository(session).get(suggestion.mission_id, tenant_id=tenant_id)
            if mission is None:
                raise RadarNotFoundError("Mission was not found")
            created = CompetitorProfile(
                tenant_id=tenant_id,
                mission_id=suggestion.mission_id,
                product_snapshot_id=mission.product_snapshot_id,
                source_suggestion_id=suggestion.id,
                company_name=suggestion.company_name,
                canonical_domain=suggestion.canonical_domain,
                official_url=suggestion.official_url,
                tracking_config_json=canonical_json(
                    {"seed_urls": [suggestion.official_url], "allowed_page_kinds": ["home"]}
                ),
                approved_by=actor_id,
                approved_at=now,
            )
            try:
                with session.begin_nested():
                    profiles.add(created, tenant_id=tenant_id)
                    session.flush()
            except IntegrityError:
                profile = profiles.get_by_mission_domain(
                    suggestion.mission_id,
                    suggestion.canonical_domain,
                    tenant_id=tenant_id,
                )
                if profile is None:
                    raise RadarServiceError("Competitor profile could not be approved") from None
            else:
                profile = created
        suggestion.status = "approved"
        suggestion.decided_by = actor_id
        suggestion.decided_at = now
        if changed:
            add_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action="radar.profile_approved",
                target_type="competitor_profile",
                target_id=profile.id,
                safe_summary="Approved competitor profile",
            )
        session.commit()
        return profile


_ACTIVE_RUN_STATUSES = ("queued", "running")
_DEFAULT_RUN_BUDGET = {
    "pages": 10,
    "browser_pages": 3,
    "wall_seconds": 300,
    "excerpt_chars": 4000,
    "artifacts": 10,
    "material_signals": 50,
    "automatic_conversions": 10,
}


def request_manual_run(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    profile_id: str,
) -> RadarRun:
    """Persist and enqueue exactly one explicitly requested manual Radar Run."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    with _session(app) as session:
        profile = CompetitorProfileRepository(session).get(profile_id, tenant_id=tenant_id)
        if profile is None:
            raise RadarNotFoundError("Competitor profile was not found")
        if profile.status != "active":
            raise RadarServiceError("Only active competitor profiles can run")
        try:
            _load_mission_context(session, tenant_id=tenant_id, mission_id=profile.mission_id)
        except RadarPolicyError as exc:
            raise RadarServiceError("Mission must be active for competitor Radar") from exc
        existing = session.scalar(
            select(RadarRun).where(
                RadarRun.tenant_id == tenant_id,
                RadarRun.profile_id == profile.id,
                RadarRun.active_key == "active",
            )
        )
        if existing is not None:
            return existing

        run_id = uuid.uuid4().hex
        job_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        run = RadarRun(
            id=run_id,
            tenant_id=tenant_id,
            profile_id=profile.id,
            root_job_id=job_id,
            requested_by=actor_id,
            active_key="active",
            budget_json=canonical_json(_DEFAULT_RUN_BUDGET),
            created_at=now,
        )
        job = Job(
            id=job_id,
            tenant_id=tenant_id,
            job_type="radar_scan",
            status="queued",
            payload_json=canonical_json({"run_id": run_id}),
            queue_name="default",
            created_at=now,
            queued_at=now,
        )
        try:
            with session.begin_nested():
                session.add(run)
                JobRepository(session).create_for_tenant(job, tenant_id=tenant_id)
                session.flush()
        except IntegrityError:
            existing = session.scalar(
                select(RadarRun).where(
                    RadarRun.tenant_id == tenant_id,
                    RadarRun.profile_id == profile.id,
                    RadarRun.active_key == "active",
                )
            )
            if existing is None:
                raise RadarServiceError("Manual Radar Run could not be created") from None
            return existing
        add_event(
            session,
            tenant_id=tenant_id,
            actor_user_id=actor_id,
            action="radar.run_requested",
            target_type="radar_run",
            target_id=run.id,
            safe_summary="Requested manual competitor Radar run",
        )
        session.commit()

    try:
        enqueue_existing_job(app, job_id=job.id, tenant_id=tenant_id)
    except JobServiceError:
        with _session(app) as session:
            stored = session.get(RadarRun, run.id)
            if stored is not None and stored.status == "queued":
                stored.status = "failed"
                stored.stage = "enqueue_failed"
                stored.active_key = None
                stored.result_summary_json = canonical_json({"reason_codes": ["enqueue_failed"]})
                stored.finished_at = datetime.now(UTC)
                session.commit()
                return stored
        raise RadarServiceError("Manual Radar Run could not be queued") from None
    return run


def cancel_manual_run(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    run_id: str,
) -> RadarRun:
    """Cancel a caller-owned active Run while retaining completed snapshots."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    with _session(app) as session:
        run = session.scalar(
            select(RadarRun).where(RadarRun.id == run_id, RadarRun.tenant_id == tenant_id)
        )
        if run is None:
            raise RadarNotFoundError("Radar Run was not found")
        if run.status in _ACTIVE_RUN_STATUSES:
            run.status = "cancelled"
            run.stage = "cancelled"
            run.active_key = None
            run.finished_at = datetime.now(UTC)
            job = JobRepository(session).get_for_tenant(run.root_job_id, tenant_id=tenant_id)
            if job is not None and job.status in {"queued", "running", "retrying"}:
                job.status = "cancelled"
                job.finished_at = run.finished_at
            from app.modules.acquisition.models import Notification

            session.execute(
                update(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.dedupe_key == f"radar-run:{run.profile_id}:{run.id}",
                    Notification.status != "archived",
                )
                .values(status="archived")
            )
            add_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action="radar.run_cancelled",
                target_type="radar_run",
                target_id=run.id,
                safe_summary="Cancelled manual competitor Radar run",
            )
            session.commit()
        return run


def decide_change_signal(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    signal_id: str,
    action: str,
) -> RadarChangeSignal:
    """Record an idempotent, tenant-scoped decision for a Radar signal."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    target_status = {"acknowledge": "acknowledged", "dismiss": "dismissed"}.get(action)
    if target_status is None:
        raise RadarServiceError("Radar signal action is invalid")
    with _session(app) as session:
        signal = session.scalar(
            select(RadarChangeSignal).where(
                RadarChangeSignal.id == signal_id,
                RadarChangeSignal.tenant_id == tenant_id,
            )
        )
        if signal is None:
            raise RadarNotFoundError("Radar change signal was not found")
        now = datetime.now(UTC)
        transitioned = session.execute(
            update(RadarChangeSignal)
            .where(
                RadarChangeSignal.id == signal.id,
                RadarChangeSignal.tenant_id == tenant_id,
                RadarChangeSignal.status == "open",
            )
            .values(status=target_status, decided_by=actor_id, decided_at=now)
        )
        if transitioned.rowcount == 1:
            add_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action=f"radar.signal_{target_status}",
                target_type="radar_change_signal",
                target_id=signal.id,
                safe_summary=f"Radar change signal marked {target_status}",
            )
            session.commit()
            session.refresh(signal)
        else:
            session.refresh(signal)
        return signal


def accept_run_baseline(
    app: Flask,
    *,
    tenant_id: str,
    actor_id: str,
    run_id: str,
) -> RadarRun:
    """Make an inspected drifted Run eligible as the next comparison baseline."""

    require_capability(app, Capability.COMPETITOR_RADAR)
    with _session(app) as session:
        run = session.scalar(
            select(RadarRun).where(RadarRun.id == run_id, RadarRun.tenant_id == tenant_id)
        )
        if run is None:
            raise RadarNotFoundError("Radar Run was not found")
        if run.status not in {"succeeded", "partial"}:
            raise RadarServiceError("Only completed Radar Runs can become a baseline")
        try:
            summary = parse_bounded_json_object(run.result_summary_json)
        except RadarPolicyError:
            summary = {}
        if summary.get("possible_baseline_drift") is not True:
            raise RadarServiceError("Radar Run does not require baseline acceptance")
        if not run.baseline_accepted:
            run.baseline_accepted = True
            add_event(
                session,
                tenant_id=tenant_id,
                actor_user_id=actor_id,
                action="radar.run_baseline_accepted",
                target_type="radar_run",
                target_id=run.id,
                safe_summary="Accepted inspected Radar baseline",
            )
            session.commit()
        return run
