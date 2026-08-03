"""Tenant-owned application service for the disabled Browser foundation."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, is_enabled
from app.extensions import get_engine
from app.integrations.browser.contracts import (
    BrowserAction,
    BrowserResearchPlan,
    BrowserTaskDescriptor,
    BrowserTaskResult,
)
from app.integrations.browser.models import BrowserResearchRun, BrowserSitePolicy
from app.integrations.browser.policy import (
    BrowserPolicyError,
    evaluate_site_policy,
    validate_navigation,
)
from app.integrations.browser.repository import BrowserRunRepository, BrowserSitePolicyRepository
from app.integrations.browser.sanitizer import sanitize_browser_snapshot
from app.integrations.browser.worker import cancel_key
from app.integrations.web.url_safety import UnsafeUrlError, validate_browser_public_url

logger = logging.getLogger(__name__)
_ACTIVE_STATUSES = ("queued", "running")
_TERMINAL_STATUSES = frozenset({"completed", "partial", "blocked", "failed", "cancelled"})


class BrowserServiceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BrowserSubmitResult:
    run_id: str
    status: str


@dataclass(frozen=True)
class BrowserImportResult:
    decision: str
    run_id: str


@dataclass(frozen=True)
class BrowserPollResult:
    run_id: str
    status: str
    transport_status: str


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise BrowserServiceError("tenant_id_required")
    return clean


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _browser_redis(app):
    from redis import Redis

    redis_url = str(app.config.get("BROWSER_REDIS_URL", ""))
    if not redis_url:
        raise BrowserServiceError("browser_transport_unavailable")
    redis = Redis.from_url(redis_url)
    try:
        redis.ping()
    except Exception as exc:
        raise BrowserServiceError("browser_transport_unavailable") from exc
    return redis


def _enqueue_descriptor(descriptor_json: str):
    """Enqueue only an opaque descriptor on the dedicated Browser Redis."""

    from redis import Redis

    redis_url = os.environ.get("BROWSER_REDIS_URL", "redis://localhost:6380/0")
    connection = Redis.from_url(redis_url)
    connection.ping()
    job = Queue("browser", connection=connection).enqueue(
        "app.integrations.browser.worker.execute_browser_request",
        descriptor_json,
        job_timeout=330,
        result_ttl=600,
        failure_ttl=600,
    )
    return str(job.id)


def _policy_json(value: str, *, field: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BrowserServiceError(f"policy_{field}_invalid") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise BrowserServiceError(f"policy_{field}_invalid")
    return parsed


def _plan_for_request(
    *,
    requested_url: str,
    policy: BrowserSitePolicy,
    requested_actions: tuple[str, ...],
    max_pages: int,
    max_tool_calls: int,
) -> BrowserResearchPlan:
    actions: list[BrowserAction] = []
    for action_name in requested_actions:
        payload: dict[str, object] = {"tool": action_name}
        if action_name == "open_allowed_url":
            payload["url"] = requested_url
        actions.append(BrowserAction.model_validate(payload))
    try:
        return BrowserResearchPlan.model_validate(
            {
                "version": "browser-plan-v1",
                "start_url": requested_url,
                "allowed_origins": _policy_json(
                    policy.allowed_origins_json, field="allowed_origins"
                ),
                "allowed_paths": _policy_json(policy.allowed_paths_json, field="allowed_paths"),
                "actions": actions,
            }
        )
    except ValidationError as exc:
        raise BrowserServiceError("browser_plan_invalid") from exc


def _budget_for(app, policy: BrowserSitePolicy) -> dict[str, int]:
    return {
        "max_pages": min(int(app.config["BROWSER_MAX_PAGES"]), policy.max_pages),
        "max_seconds": min(int(app.config["BROWSER_MAX_SECONDS"]), policy.max_seconds),
        "max_tool_calls": int(app.config["BROWSER_MAX_TOOL_CALLS"]),
        "max_artifact_bytes": int(app.config["BROWSER_MAX_ARTIFACT_BYTES"]),
    }


def submit_browser_run(
    app,
    *,
    tenant_id: str,
    owner_type: str,
    owner_id: str,
    requested_url: str,
    requested_actions: tuple[str, ...],
) -> BrowserSubmitResult:
    tenant_id = _require_tenant(tenant_id)
    if not is_enabled(app, Capability.BROWSER_RESEARCH):
        raise BrowserServiceError("browser_capability_disabled")
    if owner_type not in {"radar_run", "acquisition_candidate", "smoke"} or not owner_id:
        raise BrowserServiceError("browser_owner_invalid")
    if not requested_actions or len(requested_actions) > int(app.config["BROWSER_MAX_TOOL_CALLS"]):
        raise BrowserServiceError("browser_actions_invalid")
    try:
        safe_url = validate_browser_public_url(requested_url)
    except UnsafeUrlError as exc:
        raise BrowserServiceError("browser_url_blocked") from exc

    with Session(get_engine(app)) as session:
        policy_repository = BrowserSitePolicyRepository(session)
        policy = policy_repository.get_by_domain(safe_url.host, tenant_id=tenant_id)
        decision = evaluate_site_policy(policy, requested_url=safe_url.canonical_url)
        if policy is None or decision.decision != "approved":
            raise BrowserServiceError(decision.reason_code)
        existing = session.scalar(
            select(BrowserResearchRun.id).where(
                BrowserResearchRun.tenant_id == tenant_id,
                BrowserResearchRun.owner_type == owner_type,
                BrowserResearchRun.owner_id == owner_id,
                BrowserResearchRun.status.in_(_ACTIVE_STATUSES),
            )
        )
        if existing is not None:
            raise BrowserServiceError("browser_owner_already_active")
        budget = _budget_for(app, policy)
        if len(requested_actions) > budget["max_tool_calls"]:
            raise BrowserServiceError("browser_actions_invalid")
        plan = _plan_for_request(
            requested_url=safe_url.canonical_url,
            policy=policy,
            requested_actions=requested_actions,
            max_pages=budget["max_pages"],
            max_tool_calls=budget["max_tool_calls"],
        )
        run_token = secrets.token_urlsafe(32)
        run = BrowserResearchRun(
            tenant_id=tenant_id,
            owner_type=owner_type,
            owner_id=owner_id,
            site_policy_id=policy.id,
            requested_url=safe_url.canonical_url,
            canonical_domain=safe_url.host,
            policy_decision_json=_json(
                {"decision": decision.decision, "reason": decision.reason_code}
            ),
            plan_hash=_sha256(plan.model_dump_json()),
            budget_json=_json(budget),
            run_token_digest=_sha256(run_token),
        )
        session.add(run)
        session.commit()

        run_repository = BrowserRunRepository(session)
        attempt = run_repository.claim(
            run.id, tenant_id=tenant_id, lease_seconds=budget["max_seconds"]
        )
        if attempt is None:
            session.rollback()
            raise BrowserServiceError("browser_claim_failed")
        descriptor = BrowserTaskDescriptor(
            run_id=run.id,
            run_token=run_token,
            attempt=attempt,
            plan_json=plan.model_dump_json(),
            max_pages=budget["max_pages"],
            max_seconds=budget["max_seconds"],
            max_tool_calls=budget["max_tool_calls"],
            max_artifact_bytes=budget["max_artifact_bytes"],
            artifact_subdir=run.id,
        )
        run.descriptor_hash = _sha256(descriptor.model_dump_json())
        session.commit()

        try:
            transport_job_id = _enqueue_descriptor(descriptor.model_dump_json())
        except Exception:
            run_repository.mark_enqueue_failed(run.id, tenant_id=tenant_id)
            session.commit()
            raise BrowserServiceError("browser_transport_unavailable") from None
        run.transport_job_id = transport_job_id[:128]
        session.commit()
        return BrowserSubmitResult(run_id=run.id, status="queued")


def _result_matches_run(
    run: BrowserResearchRun, parsed: BrowserTaskResult, *, attempt: int
) -> bool:
    return (
        parsed.run_id == run.id
        and parsed.attempt == attempt == run.attempt
        and hmac.compare_digest(_sha256(parsed.run_token), run.run_token_digest)
    )


def _validate_result(
    run: BrowserResearchRun,
    policy: BrowserSitePolicy | None,
    parsed: BrowserTaskResult,
) -> tuple[str, str]:
    if policy is None:
        raise BrowserServiceError("result_policy_missing")
    try:
        budget = json.loads(run.budget_json)
        max_pages = int(budget["max_pages"])
        max_tool_calls = int(budget["max_tool_calls"])
        max_artifact_bytes = int(budget["max_artifact_bytes"])
        allowed_origins = tuple(_policy_json(policy.allowed_origins_json, field="allowed_origins"))
        allowed_paths = tuple(_policy_json(policy.allowed_paths_json, field="allowed_paths"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BrowserServiceError("result_budget_invalid") from exc
    if (
        parsed.page_count > max_pages
        or parsed.tool_call_count > max_tool_calls
        or parsed.bytes_written > max_artifact_bytes
    ):
        raise BrowserServiceError("result_budget_exceeded")
    final_url = ""
    manifest: list[dict[str, object]] = []
    for page in parsed.pages:
        try:
            final_url = validate_navigation(
                requested_url=run.requested_url,
                final_url=str(page.url),
                allowed_origins=allowed_origins,
                allowed_paths=allowed_paths,
                resolver=lambda host: validate_browser_public_url(f"https://{host}/").resolved_ips,
            ).canonical_url
        except (BrowserPolicyError, UnsafeUrlError) as exc:
            raise BrowserServiceError("result_url_blocked") from exc
        if sanitize_browser_snapshot(page.text).text != page.text:
            raise BrowserServiceError("result_sanitizer_invalid")
        for artifact in page.artifacts:
            if not artifact.name.startswith(f"{run.id}/"):
                raise BrowserServiceError("result_artifact_invalid")
            manifest.append(artifact.model_dump(mode="json"))
    if sum(int(item["size_bytes"]) for item in manifest) > parsed.bytes_written:
        raise BrowserServiceError("result_artifact_invalid")
    return final_url, _json(manifest)


def import_browser_result(
    app,
    *,
    tenant_id: str,
    run_id: str,
    attempt: int,
    result: dict[str, object],
) -> BrowserImportResult:
    tenant_id = _require_tenant(tenant_id)
    with Session(get_engine(app)) as session:
        run_repository = BrowserRunRepository(session)
        run = run_repository.get(run_id, tenant_id=tenant_id)
        if run is None or run.status in _TERMINAL_STATUSES:
            return BrowserImportResult("stale_result_ignored", run_id)
        try:
            parsed = BrowserTaskResult.model_validate(result)
        except ValidationError:
            return BrowserImportResult("invalid_result_rejected", run_id)
        if not _result_matches_run(run, parsed, attempt=attempt):
            logger.warning("browser_result_stale run_id=%s attempt=%s", run_id, attempt)
            return BrowserImportResult("stale_result_ignored", run_id)
        policy = None
        if run.site_policy_id:
            policy = BrowserSitePolicyRepository(session).get(
                run.site_policy_id, tenant_id=tenant_id
            )
        try:
            final_url, manifest_json = _validate_result(run, policy, parsed)
        except BrowserServiceError:
            return BrowserImportResult("invalid_result_rejected", run_id)
        stored_result = parsed.model_dump(mode="json", exclude={"run_token"})
        completed = run_repository.complete(
            run.id,
            tenant_id=tenant_id,
            attempt=attempt,
            run_token_digest=run.run_token_digest,
            status=parsed.status,
            result_json=_json(stored_result),
            artifact_manifest_json=manifest_json,
            final_url=final_url,
        )
        if not completed:
            session.rollback()
            return BrowserImportResult("stale_result_ignored", run_id)
        session.commit()
        return BrowserImportResult("imported", run_id)


def poll_browser_run(app, *, tenant_id: str, run_id: str) -> BrowserPollResult:
    tenant_id = _require_tenant(tenant_id)
    with Session(get_engine(app)) as session:
        run = BrowserRunRepository(session).get(run_id, tenant_id=tenant_id)
        if run is None:
            raise BrowserServiceError("browser_run_not_found")
        if not run.transport_job_id:
            return BrowserPollResult(run_id, run.status, "not_enqueued")
        try:
            job = Job.fetch(run.transport_job_id, connection=_browser_redis(app))
            transport_status = str(job.get_status())
            if transport_status == "finished" and isinstance(job.result, dict):
                decision = import_browser_result(
                    app,
                    tenant_id=tenant_id,
                    run_id=run_id,
                    attempt=run.attempt,
                    result=job.result,
                ).decision
                job.delete()
                transport_status = decision
        except (BrowserServiceError, NoSuchJobError):
            transport_status = "transport_missing"
        return BrowserPollResult(run_id, run.status, transport_status)


def cancel_browser_run(app, *, tenant_id: str, run_id: str) -> BrowserImportResult:
    tenant_id = _require_tenant(tenant_id)
    with Session(get_engine(app)) as session:
        repository = BrowserRunRepository(session)
        run = repository.cancel(run_id, tenant_id=tenant_id)
        if run is None:
            return BrowserImportResult("cancel_not_applied", run_id)
        session.commit()
        try:
            redis = _browser_redis(app)
            redis.set(cancel_key(run.id, max(1, run.attempt)), "1", ex=600)
            if run.transport_job_id:
                Job.fetch(run.transport_job_id, connection=redis).cancel()
        except (BrowserServiceError, NoSuchJobError):
            pass
        return BrowserImportResult("cancelled", run_id)


def cleanup_browser_artifacts(app, *, tenant_id: str, dry_run: bool = True) -> list[str]:
    """Conservatively remove only terminal tenant-owned artifact directories after 30 days."""

    tenant_id = _require_tenant(tenant_id)
    root = Path(str(app.config.get("BROWSER_ARTIFACT_DIR", "/browser-artifacts")))
    if not root.exists():
        return []
    cutoff = time.time() - 30 * 24 * 60 * 60
    with Session(get_engine(app)) as session:
        run_ids = set(
            session.scalars(
                select(BrowserResearchRun.id).where(
                    BrowserResearchRun.tenant_id == tenant_id,
                    BrowserResearchRun.status.in_(tuple(_TERMINAL_STATUSES)),
                )
            )
        )
        candidates = [
            directory
            for directory in root.iterdir()
            if directory.is_dir()
            and directory.name in run_ids
            and directory.stat().st_mtime <= cutoff
            and not (directory / ".retain").exists()
        ]
        if dry_run:
            return sorted(directory.name for directory in candidates)
        for directory in candidates:
            shutil.rmtree(directory)
        return sorted(directory.name for directory in candidates)
