"""Handlers for explicitly requested Radar scanning Jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.web.fetcher import FetchError, StaticFetcher
from app.modules.jobs.models import Job
from app.modules.radar.models import (
    CompetitorProfile,
    RadarChangeSignal,
    RadarRun,
    RadarSnapshot,
)
from app.modules.radar.policies import canonical_json, parse_bounded_json_object
from app.modules.radar.snapshots import (
    finalize_snapshot,
    finalize_unreachable_snapshot,
    plan_radar_pages,
)

_SAFE_FETCH_CODES = {
    "response_too_large",
    "source_timeout",
    "source_unreachable",
    "unsupported_content_type",
    "policy_url_blocked",
    "dns_changed",
    "invalid_redirect",
    "too_many_redirects",
}


def handle_radar_scan(app: Any, job: Job, payload: dict[str, object]) -> dict[str, object]:
    """Fetch one bounded manual Run. Browser fallback is deliberately not started."""

    run_id = _required_run_id(payload)
    if job.tenant_id.strip() == "":
        raise ValueError("Radar Job tenant is required")
    run, profile = _start_run(app, job=job, run_id=run_id)
    if run.status == "cancelled":
        return {"run_status": "cancelled", "browser_jobs": 0}

    budget = parse_bounded_json_object(run.budget_json)
    page_limit = _bounded_int(budget.get("pages"), default=10, minimum=1, maximum=25)
    fetcher = StaticFetcher.from_app(app)
    planned = plan_radar_pages(
        official_url=profile.official_url,
        canonical_domain=profile.canonical_domain,
        tracking_config_json=profile.tracking_config_json,
        page_limit=page_limit,
        resolver=fetcher.resolver,
    )
    valid_count = 0
    nonvalid_count = 0
    reasons: set[str] = set()
    try:
        index = 0
        while index < len(planned):
            page = planned[index]
            index += 1
            if _is_cancelled(app, run_id=run.id, tenant_id=run.tenant_id):
                return _finish_run(
                    app,
                    run_id=run.id,
                    tenant_id=run.tenant_id,
                    status="cancelled",
                    stage="cancelled",
                    valid_count=valid_count,
                    nonvalid_count=nonvalid_count,
                    reasons=reasons,
                )
            try:
                fetched = fetcher.fetch(page.requested_url)
            except FetchError as exc:
                reason = exc.code if exc.code in _SAFE_FETCH_CODES else "source_unreachable"
                with Session(get_engine(app)) as session:
                    finalize_unreachable_snapshot(
                        session,
                        profile_id=profile.id,
                        run_id=run.id,
                        page_kind=page.page_kind,
                        requested_url=page.requested_url,
                        canonical_url=page.canonical_url,
                        reason_code=reason,
                    )
                    session.commit()
                nonvalid_count += 1
                reasons.add(reason)
                continue
            with Session(get_engine(app)) as session:
                snapshot = finalize_snapshot(
                    session,
                    profile_id=profile.id,
                    run_id=run.id,
                    page_kind=page.page_kind,
                    fetched_page=fetched,
                )
                validation_status = snapshot.validation_status
                facts_json = snapshot.facts_json
                session.commit()
            if validation_status == "valid":
                valid_count += 1
            else:
                nonvalid_count += 1
                reasons.update(_reason_codes(facts_json))
            if page.page_kind == "home" and validation_status == "valid":
                observed = plan_radar_pages(
                    official_url=profile.official_url,
                    canonical_domain=profile.canonical_domain,
                    tracking_config_json=profile.tracking_config_json,
                    observed_links=fetched.observed_links,
                    page_limit=page_limit,
                    resolver=fetcher.resolver,
                )
                planned = _merge_plans(planned, observed, page_limit=page_limit)
    finally:
        fetcher.close()

    if valid_count and not nonvalid_count:
        status = "succeeded"
    elif valid_count:
        status = "partial"
    else:
        status = "failed"
    summary = _finish_run(
        app,
        run_id=run.id,
        tenant_id=run.tenant_id,
        status=status,
        stage="completed",
        valid_count=valid_count,
        nonvalid_count=nonvalid_count,
        reasons=reasons,
    )
    signal_summary = _reconcile_change_signals(app, run=run, profile=profile)
    summary.update(signal_summary)
    if status in {"succeeded", "partial"} and not signal_summary["possible_baseline_drift"]:
        relationship_summary = _resolve_relationships_and_candidates(
            app,
            run=run,
            profile=profile,
            budget=budget,
        )
        summary.update(relationship_summary)
    return summary


def _start_run(app: Any, *, job: Job, run_id: str) -> tuple[RadarRun, CompetitorProfile]:
    with Session(get_engine(app)) as session:
        session.expire_on_commit = False
        run = session.scalar(
            select(RadarRun).where(RadarRun.id == run_id, RadarRun.tenant_id == job.tenant_id)
        )
        if run is None or run.root_job_id != job.id:
            raise ValueError("Radar Run does not belong to this Job")
        profile = session.scalar(
            select(CompetitorProfile).where(
                CompetitorProfile.id == run.profile_id,
                CompetitorProfile.tenant_id == job.tenant_id,
            )
        )
        if profile is None:
            raise ValueError("Radar profile was not found")
        if run.status == "cancelled":
            return run, profile
        if run.status not in {"queued", "running"}:
            raise ValueError("Radar Run is not active")
        now = datetime.now(UTC)
        run.status = "running"
        run.stage = "static_fetch"
        run.started_at = run.started_at or now
        run.heartbeat_at = now
        session.commit()
        return run, profile


def _is_cancelled(app: Any, *, run_id: str, tenant_id: str) -> bool:
    with Session(get_engine(app)) as session:
        run = session.scalar(
            select(RadarRun.status).where(RadarRun.id == run_id, RadarRun.tenant_id == tenant_id)
        )
        return run == "cancelled"


def _finish_run(
    app: Any,
    *,
    run_id: str,
    tenant_id: str,
    status: str,
    stage: str,
    valid_count: int = 0,
    nonvalid_count: int = 0,
    reasons: set[str] | None = None,
) -> dict[str, object]:
    summary = {
        "valid_snapshots": valid_count,
        "nonvalid_pages": nonvalid_count,
        "reason_codes": sorted(reasons or set())[:20],
        "browser_jobs": 0,
        "run_status": status,
    }
    with Session(get_engine(app)) as session:
        run = session.scalar(
            select(RadarRun).where(RadarRun.id == run_id, RadarRun.tenant_id == tenant_id)
        )
        if run is None:
            raise ValueError("Radar Run was not found")
        if run.status == "cancelled":
            summary["run_status"] = "cancelled"
            return summary
        run.status = status
        run.stage = stage
        run.heartbeat_at = datetime.now(UTC)
        run.finished_at = run.heartbeat_at
        run.result_summary_json = canonical_json(summary)
        session.commit()
    return summary


def _required_run_id(payload: dict[str, object]) -> str:
    if set(payload) != {"run_id"}:
        raise ValueError("Radar Job payload must contain only run_id")
    value = payload.get("run_id")
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("Radar Job run_id is required")
    return value.strip()


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value) if not isinstance(value, bool) else default
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(result, maximum))


def _reason_codes(facts_json: str) -> set[str]:
    try:
        data = parse_bounded_json_object(facts_json)
    except ValueError:
        return set()
    raw = data.get("reason_codes", [])
    return {item for item in raw if isinstance(item, str) and len(item) <= 80}


def _merge_plans(existing, observed, *, page_limit: int):
    merged = list(existing)
    seen = {item.canonical_url for item in merged}
    for item in observed:
        if len(merged) >= page_limit:
            break
        if item.canonical_url not in seen:
            merged.append(item)
            seen.add(item.canonical_url)
    return tuple(merged)


def _resolve_relationships_and_candidates(
    app: Any,
    *,
    run: RadarRun,
    profile: CompetitorProfile,
    budget: dict[str, object],
) -> dict[str, object]:
    """Resolve deterministic proposals; only confirmed dealers/distributors may convert."""

    from app.modules.acquisition.service import (
        AcquisitionError,
        create_candidate_from_radar_relationship,
    )
    from app.modules.radar.relationships import extract_relationships

    relationship_ids: list[tuple[str, str, str, str]] = []
    with Session(get_engine(app)) as session:
        session.expire_on_commit = False
        snapshots = list(
            session.scalars(
                select(RadarSnapshot).where(
                    RadarSnapshot.tenant_id == run.tenant_id,
                    RadarSnapshot.run_id == run.id,
                    RadarSnapshot.validation_status == "valid",
                )
            )
        )
        for snapshot in snapshots:
            try:
                relationships = extract_relationships(
                    session,
                    profile_id=profile.id,
                    run_id=run.id,
                    snapshot_id=snapshot.id,
                )
            except ValueError:
                continue
            for relationship in relationships:
                relationship_ids.append(
                    (
                        relationship.id,
                        relationship.relationship_type,
                        relationship.evidence_strength,
                        relationship.canonical_domain,
                    )
                )
        session.commit()

    maximum = _bounded_int(budget.get("automatic_conversions"), default=10, minimum=0, maximum=20)
    converted = 0
    for relationship_id, relationship_type, strength, domain in relationship_ids:
        if converted >= maximum:
            break
        if relationship_type not in {"dealer", "distributor"} or strength != "confirmed":
            continue
        try:
            create_candidate_from_radar_relationship(
                app,
                tenant_id=run.tenant_id,
                actor_id=run.requested_by,
                mission_id=profile.mission_id,
                relationship_id=relationship_id,
                expected_domain=domain,
            )
        except AcquisitionError:
            continue
        converted += 1
    return {"relationships": len(relationship_ids), "automatic_candidates": converted}


def _reconcile_change_signals(
    app: Any,
    *,
    run: RadarRun,
    profile: CompetitorProfile,
) -> dict[str, object]:
    """Persist deterministic Diffs and one bounded in-app aggregate notification."""

    from app.modules.acquisition.models import Notification
    from app.modules.radar.diff import detect_baseline_drift, diff_snapshots

    with Session(get_engine(app)) as session:
        session.expire_on_commit = False
        current = list(
            session.scalars(
                select(RadarSnapshot).where(
                    RadarSnapshot.tenant_id == run.tenant_id,
                    RadarSnapshot.run_id == run.id,
                    RadarSnapshot.validation_status == "valid",
                )
            )
        )
        previous_run = session.scalar(
            select(RadarRun)
            .where(
                RadarRun.tenant_id == run.tenant_id,
                RadarRun.profile_id == profile.id,
                RadarRun.id != run.id,
                RadarRun.status.in_(("succeeded", "partial")),
            )
            .order_by(RadarRun.finished_at.desc(), RadarRun.id.desc())
            .limit(1)
        )
        if previous_run is None:
            return {"signals": 0, "possible_baseline_drift": False, "notification": False}
        previous = list(
            session.scalars(
                select(RadarSnapshot).where(
                    RadarSnapshot.tenant_id == run.tenant_id,
                    RadarSnapshot.run_id == previous_run.id,
                    RadarSnapshot.validation_status == "valid",
                )
            )
        )
        drift = detect_baseline_drift(
            previous_run=previous_run,
            current_run=run,
            previous_pages=tuple(item.canonical_url for item in previous),
            current_pages=tuple(item.canonical_url for item in current),
            policy_version="radar-drift-v1",
        )
        previous_by_url = {item.canonical_url: item for item in previous}
        created: list[RadarChangeSignal] = []
        for snapshot in current:
            baseline = previous_by_url.get(snapshot.canonical_url)
            if baseline is None or baseline.content_hash == snapshot.content_hash:
                continue
            delta = diff_snapshots(
                baseline.facts_json,
                snapshot.facts_json,
                detector_version="radar-diff-v1",
            )
            if (
                delta
                == b'{"added":{},"changed":{},"detector_version":"radar-diff-v1","removed":{}}'
            ):
                continue
            signal = RadarChangeSignal(
                tenant_id=run.tenant_id,
                profile_id=profile.id,
                run_id=run.id,
                previous_snapshot_id=baseline.id,
                current_snapshot_id=snapshot.id,
                change_type="other",
                materiality="informational" if drift.is_drift else "material",
                before_json=baseline.facts_json,
                after_json=snapshot.facts_json,
                reason_codes_json=canonical_json(
                    ["structural_diff", *drift.reason_codes]
                    if drift.is_drift
                    else ["structural_diff"]
                ),
                evidence_json=canonical_json(
                    [{"source_url": snapshot.canonical_url, "excerpt": snapshot.excerpt[:1000]}]
                ),
                detector_version="radar-diff-v1",
            )
            try:
                with session.begin_nested():
                    session.add(signal)
                    session.flush()
            except IntegrityError:
                continue
            created.append(signal)
        notified = False
        if created and not drift.is_drift:
            dedupe = f"radar-run:{profile.id}:{run.id}"
            existing = session.scalar(
                select(Notification).where(
                    Notification.tenant_id == run.tenant_id,
                    Notification.dedupe_key == dedupe,
                )
            )
            if existing is None:
                highlights = ", ".join(item.current_snapshot_id[:12] for item in created[:5])
                session.add(
                    Notification(
                        tenant_id=run.tenant_id,
                        kind="radar_change",
                        title=f"{profile.company_name} changed",
                        body=f"{len(created)} change(s) detected: {highlights}"[:1000],
                        target_url=f"/radar/runs/{run.id}",
                        dedupe_key=dedupe,
                    )
                )
                notified = True
        stored_run = session.get(RadarRun, run.id)
        if stored_run is not None:
            result = parse_bounded_json_object(stored_run.result_summary_json)
            result["possible_baseline_drift"] = drift.is_drift
            result["drift_reason_codes"] = list(drift.reason_codes)
            stored_run.result_summary_json = canonical_json(result)
        session.commit()
    return {
        "signals": len(created),
        "possible_baseline_drift": drift.is_drift,
        "notification": notified,
    }


RADAR_HANDLERS = {"radar_scan": handle_radar_scan}
