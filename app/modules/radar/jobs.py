"""Handlers for explicitly requested Radar scanning Jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
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
    RadarSnapshotError,
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
    valid_count = 0
    nonvalid_count = 0
    reasons: set[str] = set()
    page_records: list[dict[str, str]] = []
    try:
        try:
            planned = plan_radar_pages(
                official_url=profile.official_url,
                canonical_domain=profile.canonical_domain,
                tracking_config_json=profile.tracking_config_json,
                page_limit=page_limit,
                resolver=fetcher.resolver,
            )
        except (RadarSnapshotError, ValueError):
            return _finish_run(
                app,
                run_id=run.id,
                tenant_id=run.tenant_id,
                status="failed",
                stage="planning_failed",
                nonvalid_count=1,
                reasons={"planning_failed"},
                page_records=page_records,
            )
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
                    page_records=page_records,
                )
            try:
                fetched = fetcher.fetch(page.requested_url)
            except FetchError as exc:
                reason = exc.code if exc.code in _SAFE_FETCH_CODES else "source_unreachable"
                with Session(get_engine(app)) as session:
                    snapshot = finalize_unreachable_snapshot(
                        session,
                        profile_id=profile.id,
                        run_id=run.id,
                        page_kind=page.page_kind,
                        requested_url=page.requested_url,
                        canonical_url=page.canonical_url,
                        reason_code=reason,
                    )
                    page_records.append(_page_record(snapshot, page_kind=page.page_kind))
                    session.commit()
                nonvalid_count += 1
                reasons.add(reason)
                continue
            try:
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
                    page_records.append(_page_record(snapshot, page_kind=page.page_kind))
                    session.commit()
            except RadarSnapshotError:
                nonvalid_count += 1
                reasons.add("final_url_rejected")
                page_records.append(_planned_page_record(page, validation_status="rejected"))
                continue
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
        stage="reconciling",
        valid_count=valid_count,
        nonvalid_count=nonvalid_count,
        reasons=reasons,
        page_records=page_records,
        terminal=False,
    )
    if _is_cancelled(app, run_id=run.id, tenant_id=run.tenant_id):
        return {**summary, "run_status": "cancelled"}
    signal_summary = _reconcile_change_signals(app, run=run, profile=profile)
    summary.update(signal_summary)
    relationship_summary = {"relationships": 0, "automatic_candidates": 0, "confirmed": 0}
    if (
        status in {"succeeded", "partial"}
        and not signal_summary["possible_baseline_drift"]
        and not _is_cancelled(app, run_id=run.id, tenant_id=run.tenant_id)
    ):
        relationship_summary = _resolve_relationships_and_candidates(
            app,
            run=run,
            profile=profile,
            budget=budget,
        )
        summary.update(relationship_summary)
    if not _is_cancelled(app, run_id=run.id, tenant_id=run.tenant_id):
        summary.update(
            _aggregate_run_notification(
                app,
                run=run,
                profile=profile,
                run_status=status,
                signals=int(signal_summary["signals"]),
                confirmed_relationships=int(relationship_summary["confirmed"]),
                drift=bool(signal_summary["possible_baseline_drift"]),
            )
        )
    return _finish_run(
        app,
        run_id=run.id,
        tenant_id=run.tenant_id,
        status=status,
        stage="completed",
        summary_override=summary,
    )


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
        if run.status == "running":
            run.heartbeat_at = datetime.now(UTC)
            session.commit()
            return run, profile
        if run.status != "queued":
            raise ValueError("Radar Run is not active")
        now = datetime.now(UTC)
        started = session.execute(
            update(RadarRun)
            .where(
                RadarRun.id == run.id,
                RadarRun.tenant_id == job.tenant_id,
                RadarRun.status == "queued",
                RadarRun.active_key == "active",
            )
            .values(
                status="running",
                stage="static_fetch",
                started_at=now,
                heartbeat_at=now,
            )
        )
        if started.rowcount != 1:
            session.expire(run)
            if run.status == "cancelled":
                return run, profile
            raise ValueError("Radar Run was not available to start")
        session.commit()
        session.refresh(run)
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
    page_records: list[dict[str, str]] | None = None,
    terminal: bool = True,
    summary_override: dict[str, object] | None = None,
) -> dict[str, object]:
    summary = summary_override or {
        "valid_snapshots": valid_count,
        "nonvalid_pages": nonvalid_count,
        "reason_codes": sorted(reasons or set())[:20],
        "browser_jobs": 0,
        "pages": list((page_records or [])[:25]),
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
        run.stage = stage
        run.heartbeat_at = datetime.now(UTC)
        run.result_summary_json = canonical_json(summary)
        if terminal:
            run.status = status
            run.active_key = None
            run.finished_at = run.heartbeat_at
        session.commit()
    return summary


def _page_record(snapshot: RadarSnapshot, *, page_kind: str) -> dict[str, str]:
    return {
        "canonical_url": snapshot.canonical_url[:300],
        "page_kind": page_kind[:24],
        "snapshot_id": snapshot.id[:64],
        "validation_status": snapshot.validation_status[:24],
    }


def _planned_page_record(page: object, *, validation_status: str) -> dict[str, str]:
    return {
        "canonical_url": str(getattr(page, "canonical_url", ""))[:300],
        "page_kind": str(getattr(page, "page_kind", "other"))[:24],
        "snapshot_id": "",
        "validation_status": validation_status[:24],
    }


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
        locked_run = session.scalar(
            select(RadarRun)
            .where(RadarRun.id == run.id, RadarRun.tenant_id == run.tenant_id)
            .with_for_update()
        )
        if locked_run is None or locked_run.status == "cancelled":
            return {"relationships": 0, "automatic_candidates": 0, "confirmed": 0}
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
        session.expire_all()
        stored_run = session.get(RadarRun, run.id)
        if stored_run is None or stored_run.status == "cancelled":
            session.rollback()
            return {"relationships": 0, "automatic_candidates": 0, "confirmed": 0}
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
    confirmed = sum(
        1
        for _relationship_id, relationship_type, strength, _domain in relationship_ids
        if relationship_type in {"dealer", "distributor"} and strength == "confirmed"
    )
    return {
        "relationships": len(relationship_ids),
        "automatic_candidates": converted,
        "confirmed": confirmed,
    }


def _reconcile_change_signals(
    app: Any,
    *,
    run: RadarRun,
    profile: CompetitorProfile,
) -> dict[str, object]:
    """Persist deterministic Diffs and one bounded in-app aggregate notification."""

    from app.modules.radar.diff import detect_baseline_drift, diff_snapshots

    with Session(get_engine(app)) as session:
        locked_run = session.scalar(
            select(RadarRun)
            .where(RadarRun.id == run.id, RadarRun.tenant_id == run.tenant_id)
            .with_for_update()
        )
        if locked_run is None or locked_run.status == "cancelled":
            return {"signals": 0, "possible_baseline_drift": False, "notification": False}
        session.expire_on_commit = False
        current_records = _valid_snapshot_records(session, run)
        previous_run = _previous_accepted_run(
            session,
            tenant_id=run.tenant_id,
            profile_id=profile.id,
            current_run_id=run.id,
        )
        if previous_run is None:
            return {"signals": 0, "possible_baseline_drift": False, "notification": False}
        previous_records = _valid_snapshot_records(session, previous_run)
        drift = detect_baseline_drift(
            previous_run=previous_run,
            current_run=run,
            previous_pages=tuple(item[1] for item in previous_records),
            current_pages=tuple(item[1] for item in current_records),
            previous_facts_by_page={
                url: _fact_fingerprints(snapshot.facts_json)
                for snapshot, url, _kind in previous_records
            },
            current_facts_by_page={
                url: _fact_fingerprints(snapshot.facts_json)
                for snapshot, url, _kind in current_records
            },
            page_kinds={
                url: kind for _snapshot, url, kind in (*previous_records, *current_records)
            },
            policy_version="radar-drift-v1",
        )
        previous_by_url = {url: item for item, url, _kind in previous_records}
        created: list[RadarChangeSignal] = []
        for snapshot, canonical_url, _kind in current_records:
            baseline = previous_by_url.get(canonical_url)
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
        session.expire_all()
        stored_run = session.get(RadarRun, run.id)
        if stored_run is None or stored_run.status == "cancelled":
            session.rollback()
            return {"signals": 0, "possible_baseline_drift": False, "notification": False}
        result = parse_bounded_json_object(stored_run.result_summary_json)
        result["possible_baseline_drift"] = drift.is_drift
        result["drift_reason_codes"] = list(drift.reason_codes)
        stored_run.result_summary_json = canonical_json(result)
        stored_run.baseline_accepted = not drift.is_drift
        session.commit()
    return {
        "signals": len(created),
        "possible_baseline_drift": drift.is_drift,
        "notification": False,
    }


def _aggregate_run_notification(
    app: Any,
    *,
    run: RadarRun,
    profile: CompetitorProfile,
    run_status: str,
    signals: int,
    confirmed_relationships: int,
    drift: bool,
) -> dict[str, bool]:
    """Create one bounded, tenant-owned in-app notification for actionable Run outcomes."""

    if (
        run_status not in {"partial", "failed"}
        and not confirmed_relationships
        and (not signals or drift)
    ):
        return {"notification": False}
    from app.modules.acquisition.models import Notification

    reasons: list[str] = []
    if run_status in {"partial", "failed"}:
        reasons.append(run_status)
    if confirmed_relationships:
        reasons.append(f"{confirmed_relationships} confirmed relationship(s)")
    if signals and not drift:
        reasons.append(f"{signals} material change(s)")
    with Session(get_engine(app)) as session:
        stored_run = session.scalar(
            select(RadarRun)
            .where(RadarRun.id == run.id, RadarRun.tenant_id == run.tenant_id)
            .with_for_update()
        )
        if stored_run is None or stored_run.status == "cancelled":
            return {"notification": False}
        existing = session.scalar(
            select(Notification).where(
                Notification.tenant_id == run.tenant_id,
                Notification.dedupe_key == f"radar-run:{profile.id}:{run.id}",
            )
        )
        if existing is not None:
            return {"notification": False}
        session.add(
            Notification(
                tenant_id=run.tenant_id,
                kind="radar_change",
                title=f"{profile.company_name} Radar update",
                body="; ".join(reasons[:5])[:1000],
                target_url=f"/radar/runs/{run.id}",
                dedupe_key=f"radar-run:{profile.id}:{run.id}",
            )
        )
        session.commit()
    return {"notification": True}


def _valid_snapshot_records(
    session: Session,
    run: RadarRun,
) -> list[tuple[RadarSnapshot, str, str]]:
    """Resolve this Run's logical pages, including immutable snapshots reused from a prior Run."""

    stored = session.get(RadarRun, run.id)
    if stored is None:
        return []
    try:
        result = parse_bounded_json_object(stored.result_summary_json)
    except ValueError:
        result = {}
    raw_pages = result.get("pages")
    if isinstance(raw_pages, list):
        entries = [item for item in raw_pages[:25] if isinstance(item, dict)]
        snapshot_ids = [
            item.get("snapshot_id")
            for item in entries
            if item.get("validation_status") == "valid"
            and isinstance(item.get("snapshot_id"), str)
            and item["snapshot_id"]
        ]
        if snapshot_ids:
            by_id = {
                snapshot.id: snapshot
                for snapshot in session.scalars(
                    select(RadarSnapshot).where(
                        RadarSnapshot.tenant_id == run.tenant_id,
                        RadarSnapshot.id.in_(snapshot_ids),
                        RadarSnapshot.validation_status == "valid",
                    )
                )
            }
            records: list[tuple[RadarSnapshot, str, str]] = []
            for entry in entries:
                snapshot_id = entry.get("snapshot_id")
                canonical_url = entry.get("canonical_url")
                page_kind = entry.get("page_kind")
                snapshot = by_id.get(snapshot_id) if isinstance(snapshot_id, str) else None
                if (
                    snapshot is not None
                    and isinstance(canonical_url, str)
                    and isinstance(page_kind, str)
                ):
                    records.append((snapshot, canonical_url, page_kind))
            return records
    return [
        (snapshot, snapshot.canonical_url, snapshot.page_kind)
        for snapshot in session.scalars(
            select(RadarSnapshot).where(
                RadarSnapshot.tenant_id == run.tenant_id,
                RadarSnapshot.run_id == run.id,
                RadarSnapshot.validation_status == "valid",
            )
        )
    ]


def _previous_accepted_run(
    session: Session,
    *,
    tenant_id: str,
    profile_id: str,
    current_run_id: str,
) -> RadarRun | None:
    return session.scalar(
        select(RadarRun)
        .where(
            RadarRun.tenant_id == tenant_id,
            RadarRun.profile_id == profile_id,
            RadarRun.id != current_run_id,
            RadarRun.status.in_(("succeeded", "partial")),
            RadarRun.baseline_accepted.is_(True),
        )
        .order_by(RadarRun.finished_at.desc(), RadarRun.id.desc())
        .limit(1)
    )


def _fact_fingerprints(value: str) -> tuple[str, ...]:
    try:
        parsed = parse_bounded_json_object(value)
    except ValueError:
        return ()
    facts = parsed.get("facts")
    if not isinstance(facts, list):
        return ()
    fingerprints: list[str] = []
    for fact in facts[:100]:
        if isinstance(fact, dict) and isinstance(fact.get("key"), str):
            fingerprints.append(canonical_json({"key": fact["key"], "value": fact.get("value")}))
    return tuple(sorted(fingerprints))


def finalize_radar_worker_failure(app: Any, *, job_id: str, tenant_id: str) -> None:
    """Release a Run only when its root Job exhausted retries or otherwise failed."""

    with Session(get_engine(app)) as session:
        job = session.get(Job, job_id)
        if job is None or job.tenant_id != tenant_id or job.status != "failed":
            return
        run = session.scalar(
            select(RadarRun).where(
                RadarRun.root_job_id == job.id,
                RadarRun.tenant_id == tenant_id,
                RadarRun.status.in_(("queued", "running")),
            )
        )
        if run is None:
            return
        run.status = "failed"
        run.stage = "worker_failed"
        run.active_key = None
        run.heartbeat_at = datetime.now(UTC)
        run.finished_at = run.heartbeat_at
        run.result_summary_json = canonical_json({"reason_codes": ["worker_failed"]})
        session.commit()


RADAR_HANDLERS = {"radar_scan": handle_radar_scan}
