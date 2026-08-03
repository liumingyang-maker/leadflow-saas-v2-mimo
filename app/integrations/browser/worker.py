"""Database-free execution entry point for the isolated Browser queue."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.integrations.browser.contracts import (
    BrowserResearchPlan,
    BrowserTaskDescriptor,
    BrowserTaskResult,
)
from app.integrations.browser.gateway import BrowserGateway

_FORBIDDEN_ENVIRONMENT_NAMES = frozenset(
    {
        "DATABASE_URL",
        "SECRET_KEY",
        "TENANT_SECRET_KEY",
        "MIMO_API_KEY",
        "MIMO_BASE_URL",
        "REDIS_URL",
        "USER_TOKEN",
        "ACCESS_TOKEN",
        "AUTHORIZATION",
    }
)
_SAFE_SUBDIR = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class BrowserTransport(Protocol):
    def get(self, name: str): ...

    def set(self, name: str, value: str, ex: int) -> object: ...


def assert_isolated_environment() -> None:
    """Fail if application credentials or the application Redis reach this process."""

    present = sorted(name for name in _FORBIDDEN_ENVIRONMENT_NAMES if os.environ.get(name))
    if present:
        raise RuntimeError(f"Browser Worker forbidden environment: {present[0]}")


def _key(run_id: str, attempt: int, kind: str) -> str:
    if not _SAFE_SUBDIR.fullmatch(run_id) or attempt < 1:
        raise ValueError("browser transport key is invalid")
    return f"browser:{kind}:{run_id}:{attempt}"


def heartbeat_key(run_id: str, attempt: int) -> str:
    return _key(run_id, attempt, "heartbeat")


def cancel_key(run_id: str, attempt: int) -> str:
    return _key(run_id, attempt, "cancel")


def write_heartbeat(
    transport: BrowserTransport,
    *,
    run_id: str,
    attempt: int,
    page_count: int,
    tool_call_count: int,
    max_seconds: int,
) -> None:
    payload = json.dumps(
        {
            "at": int(time.time()),
            "page_count": max(0, min(int(page_count), 25)),
            "tool_call_count": max(0, min(int(tool_call_count), 30)),
        },
        separators=(",", ":"),
    )
    transport.set(
        heartbeat_key(run_id, attempt),
        payload,
        ex=max(20, min(int(max_seconds), 300) * 2),
    )


def is_cancelled(transport: BrowserTransport, *, run_id: str, attempt: int) -> bool:
    return transport.get(cancel_key(run_id, attempt)) is not None


def resolve_artifact_directory(root: Path, subdir: str) -> Path:
    if not _SAFE_SUBDIR.fullmatch(subdir):
        raise ValueError("artifact_path_invalid")
    resolved_root = root.resolve()
    candidate = (resolved_root / subdir).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        raise ValueError("artifact_path_invalid") from None
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def cleanup_orphan_artifacts(root: Path, *, older_than_seconds: int = 24 * 60 * 60) -> list[str]:
    """Remove only old, marker-free, direct artifact directories."""

    if not root.exists():
        return []
    bounded_age = max(0, int(older_than_seconds))
    threshold = time.time() - bounded_age
    removed: list[str] = []
    for candidate in root.iterdir():
        if (
            not candidate.is_dir()
            or not _SAFE_SUBDIR.fullmatch(candidate.name)
            or (bounded_age > 0 and candidate.stat().st_mtime > threshold)
            or (candidate / ".active").exists()
            or (candidate / ".retain").exists()
        ):
            continue
        shutil.rmtree(candidate)
        removed.append(candidate.name)
    return sorted(removed)


def _browser_transport() -> BrowserTransport:
    browser_redis_url = os.environ.get("BROWSER_REDIS_URL", "")
    if not browser_redis_url:
        raise RuntimeError("BROWSER_REDIS_URL is required")
    from redis import Redis

    return Redis.from_url(browser_redis_url)


def _cancelled_result(descriptor: BrowserTaskDescriptor) -> BrowserTaskResult:
    return BrowserTaskResult(
        run_id=descriptor.run_id,
        run_token=descriptor.run_token,
        attempt=descriptor.attempt,
        status="cancelled",
        page_count=0,
        tool_call_count=0,
        bytes_written=0,
        error_code="cancelled",
        error_summary="Browser request was cancelled before execution.",
    )


def execute_browser_request(
    descriptor_json: str,
    *,
    transport_factory: Callable[[], BrowserTransport] = _browser_transport,
) -> dict[str, object]:
    """RQ callable: validate an opaque descriptor and return only a strict result."""

    assert_isolated_environment()
    descriptor = BrowserTaskDescriptor.model_validate_json(descriptor_json)
    artifact_root = Path(os.environ["BROWSER_ARTIFACT_DIR"])
    proxy_url = os.environ["HTTPS_PROXY"]
    artifact_dir = resolve_artifact_directory(artifact_root, descriptor.artifact_subdir)
    transport = transport_factory()
    if is_cancelled(transport, run_id=descriptor.run_id, attempt=descriptor.attempt):
        return _cancelled_result(descriptor).model_dump(mode="json")
    active_marker = artifact_dir / ".active"
    active_marker.touch(exist_ok=True)
    try:
        write_heartbeat(
            transport,
            run_id=descriptor.run_id,
            attempt=descriptor.attempt,
            page_count=0,
            tool_call_count=0,
            max_seconds=descriptor.max_seconds,
        )
        plan = BrowserResearchPlan.model_validate_json(descriptor.plan_json)
        gateway = BrowserGateway.from_descriptor(
            descriptor,
            artifact_dir=artifact_dir,
            proxy_url=proxy_url,
            cancel_check=lambda: is_cancelled(
                transport,
                run_id=descriptor.run_id,
                attempt=descriptor.attempt,
            ),
        )
        result = gateway.execute(plan)
        if is_cancelled(transport, run_id=descriptor.run_id, attempt=descriptor.attempt):
            result = result.model_copy(
                update={
                    "status": "cancelled",
                    "error_code": "cancelled",
                    "error_summary": "Browser request was cancelled during execution.",
                }
            )
        write_heartbeat(
            transport,
            run_id=descriptor.run_id,
            attempt=descriptor.attempt,
            page_count=result.page_count,
            tool_call_count=result.tool_call_count,
            max_seconds=descriptor.max_seconds,
        )
        return result.model_dump(mode="json")
    finally:
        active_marker.unlink(missing_ok=True)
