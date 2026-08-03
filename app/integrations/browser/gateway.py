"""A narrow, fail-closed adapter over Playwright MCP."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.integrations.browser.contracts import (
    BrowserAction,
    BrowserArtifactEntry,
    BrowserPageResult,
    BrowserResearchPlan,
    BrowserTaskDescriptor,
    BrowserTaskResult,
)
from app.integrations.browser.mcp_client import McpClientError, StdioMcpClient
from app.integrations.browser.policy import BrowserPolicyError, validate_navigation
from app.integrations.browser.sanitizer import sanitize_browser_snapshot
from app.integrations.web.url_safety import Resolver, system_resolver

RAW_TOOL_ALLOWLIST = frozenset(
    {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_take_screenshot",
        "browser_close",
    }
)
PUBLIC_TOOLS = (
    "open_allowed_url",
    "read_current_public_page",
    "follow_same_site_link",
    "capture_evidence",
    "stop_research",
)
_ELEMENT_REF = re.compile(r"\b(?:ref=|\[ref=)([A-Za-z0-9_-]{1,80})")
_PAGE_URL = re.compile(r"(?m)^-\s*Page URL:\s*(https://[^\s]+)\s*$")


class BrowserGatewayError(RuntimeError):
    pass


class McpTransport(Protocol):
    def list_tools(self) -> set[str]: ...

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]: ...

    def close(self) -> None: ...


class BrowserGateway:
    """Expose a fixed high-level read-only vocabulary to the Browser worker."""

    public_tools = PUBLIC_TOOLS

    def __init__(
        self,
        *,
        client: McpTransport,
        artifact_dir: Path,
        proxy_url: str,
        run_id: str = "run",
        run_token: str = "a" * 32,
        attempt: int = 1,
        max_pages: int = 10,
        max_seconds: int = 120,
        max_tool_calls: int = 12,
        max_artifact_bytes: int = 5 * 1024 * 1024,
        resolver: Resolver = system_resolver,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self.client = client
        self.artifact_dir = artifact_dir
        self.proxy_url = proxy_url
        self.run_id = run_id
        self.run_token = run_token
        self.attempt = attempt
        self.max_pages = max_pages
        self.max_seconds = max_seconds
        self.max_tool_calls = max_tool_calls
        self.max_artifact_bytes = max_artifact_bytes
        self.resolver = resolver
        self.cancel_check = cancel_check or (lambda: False)
        self._tool_calls = 0
        self._started = 0.0
        self._last_snapshot_refs: set[str] = set()
        self._closed = False

    @classmethod
    def from_descriptor(
        cls,
        descriptor: BrowserTaskDescriptor,
        *,
        artifact_dir: Path,
        proxy_url: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> BrowserGateway:
        plan = BrowserResearchPlan.model_validate_json(descriptor.plan_json)
        args = build_mcp_command(
            artifact_dir=artifact_dir,
            max_artifact_bytes=descriptor.max_artifact_bytes,
            cancel_check=cancel_check,
            allowed_origins=plan.allowed_origins,
            proxy_url=proxy_url,
        )
        return cls(
            client=StdioMcpClient(args),
            artifact_dir=artifact_dir,
            proxy_url=proxy_url,
            run_id=descriptor.run_id,
            run_token=descriptor.run_token,
            attempt=descriptor.attempt,
            max_pages=descriptor.max_pages,
            max_seconds=descriptor.max_seconds,
            max_tool_calls=descriptor.max_tool_calls,
            max_artifact_bytes=descriptor.max_artifact_bytes,
        )

    def assert_raw_tool_contract(self) -> None:
        try:
            tools = self.client.list_tools()
        except McpClientError as exc:
            raise BrowserGatewayError("mcp_protocol_error") from exc
        if tools != RAW_TOOL_ALLOWLIST:
            raise BrowserGatewayError("mcp_protocol_error")

    def _check_budget(self) -> None:
        if self.cancel_check():
            raise BrowserGatewayError("cancelled")
        if self._tool_calls >= self.max_tool_calls:
            raise BrowserGatewayError("tool_budget_exhausted")
        if time.monotonic() - self._started > self.max_seconds:
            raise BrowserGatewayError("time_budget_exhausted")

    def _call(self, tool: str, arguments: dict[str, object]) -> dict[str, object]:
        if tool not in RAW_TOOL_ALLOWLIST:
            raise BrowserGatewayError("raw_tool_blocked")
        self._check_budget()
        self._tool_calls += 1
        try:
            result = self.client.call_tool(tool, arguments)
        except McpClientError as exc:
            raise BrowserGatewayError("mcp_execution_failed") from exc
        if not isinstance(result, dict):
            raise BrowserGatewayError("mcp_protocol_error")
        return result

    def _validated_result_url(
        self, raw_result: dict[str, object], plan: BrowserResearchPlan
    ) -> str:
        candidate = raw_result.get("url")
        if candidate is None:
            content = raw_result.get("content")
            if isinstance(content, list):
                text = "\n".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                )
                match = _PAGE_URL.search(text)
                candidate = match.group(1) if match else None
        if not isinstance(candidate, str):
            raise BrowserGatewayError("mcp_protocol_error")
        try:
            return validate_navigation(
                requested_url=str(plan.start_url),
                final_url=candidate,
                allowed_origins=plan.allowed_origins,
                allowed_paths=plan.allowed_paths,
                resolver=self.resolver,
            ).canonical_url
        except BrowserPolicyError as exc:
            raise BrowserGatewayError(exc.code) from None

    def _navigate(self, url: str, plan: BrowserResearchPlan) -> str:
        try:
            validated_target = validate_navigation(
                requested_url=str(plan.start_url),
                final_url=url,
                allowed_origins=plan.allowed_origins,
                allowed_paths=plan.allowed_paths,
                resolver=self.resolver,
            ).canonical_url
        except BrowserPolicyError as exc:
            raise BrowserGatewayError(exc.code) from None
        result = self._call("browser_navigate", {"url": validated_target})
        return self._validated_result_url(result, plan)

    def _snapshot(self, plan: BrowserResearchPlan) -> BrowserPageResult:
        raw = self._call("browser_snapshot", {})
        text = raw.get("text", raw.get("content", ""))
        title = raw.get("title", "")
        if not isinstance(text, str) or not isinstance(title, str):
            raise BrowserGatewayError("mcp_protocol_error")
        sanitized = sanitize_browser_snapshot(text)
        self._last_snapshot_refs = set(_ELEMENT_REF.findall(sanitized.text))
        url = self._validated_result_url(raw, plan)
        return BrowserPageResult(
            url=url,
            title=title[:500],
            text=sanitized.text,
            content_hash=hashlib.sha256(sanitized.text.encode("utf-8")).hexdigest(),
            prompt_injection_detected=sanitized.prompt_injection_detected,
        )

    def _click(self, action: BrowserAction, plan: BrowserResearchPlan) -> str:
        if not action.element_ref or action.element_ref not in self._last_snapshot_refs:
            raise BrowserGatewayError("element_reference_invalid")
        result = self._call("browser_click", {"target": action.element_ref})
        return self._validated_result_url(result, plan)

    def _capture(self, plan: BrowserResearchPlan) -> BrowserArtifactEntry | None:
        digest = hashlib.sha256(
            f"{self.run_id}:{self.attempt}:{self._tool_calls}".encode()
        ).hexdigest()
        filename = f"{digest}.png"
        self._call("browser_take_screenshot", {"type": "png", "filename": filename})
        path = self.artifact_dir / filename
        if not path.is_file():
            return None
        size = path.stat().st_size
        if size > self.max_artifact_bytes:
            path.unlink(missing_ok=True)
            raise BrowserGatewayError("artifact_budget_exhausted")
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        return BrowserArtifactEntry(
            name=f"{self.run_id}/{filename}",
            sha256=actual_hash,
            size_bytes=size,
            content_type="image/png",
        )

    def execute(self, plan: BrowserResearchPlan) -> BrowserTaskResult:
        pages: list[BrowserPageResult] = []
        self._started = time.monotonic()
        status = "completed"
        error_code = ""
        error_summary = ""
        try:
            self.assert_raw_tool_contract()
            self._navigate(str(plan.start_url), plan)
            for action in plan.actions:
                self._check_budget()
                if action.tool == "open_allowed_url":
                    assert action.url is not None
                    self._navigate(str(action.url), plan)
                elif action.tool == "read_current_public_page":
                    if len(pages) >= self.max_pages:
                        raise BrowserGatewayError("page_budget_exhausted")
                    pages.append(self._snapshot(plan))
                elif action.tool == "follow_same_site_link":
                    self._click(action, plan)
                elif action.tool == "capture_evidence":
                    artifact = self._capture(plan)
                    if artifact is not None:
                        if not pages:
                            if len(pages) >= self.max_pages:
                                raise BrowserGatewayError("page_budget_exhausted")
                            pages.append(self._snapshot(plan))
                        latest = pages[-1]
                        pages[-1] = latest.model_copy(
                            update={"artifacts": latest.artifacts + (artifact,)}
                        )
                elif action.tool == "stop_research":
                    break
        except BrowserGatewayError as exc:
            if exc.args[0] == "cancelled":
                status = "cancelled"
            else:
                status = "blocked" if exc.args[0].endswith("blocked") else "failed"
            error_code = str(exc.args[0])[:80]
            error_summary = "Browser gateway stopped the bounded request."
        finally:
            self.close()
        return BrowserTaskResult(
            run_id=self.run_id,
            run_token=self.run_token,
            attempt=self.attempt,
            status=status,
            pages=tuple(pages),
            page_count=len(pages),
            tool_call_count=self._tool_calls,
            bytes_written=sum(artifact.size_bytes for page in pages for artifact in page.artifacts),
            error_code=error_code,
            error_summary=error_summary,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.client.call_tool("browser_close", {})
        except Exception:
            pass
        finally:
            self.client.close()


def build_mcp_command(
    *,
    artifact_dir: Path,
    max_artifact_bytes: int,
    allowed_origins: tuple[str, ...],
    proxy_url: str,
) -> list[str]:
    """Build a fixed argv list; no plan or model field can append CLI flags."""

    return [
        "./node_modules/.bin/playwright-mcp",
        "--headless",
        "--isolated",
        "--block-service-workers",
        "--image-responses",
        "omit",
        "--output-mode",
        "file",
        "--output-dir",
        str(artifact_dir),
        "--output-max-size",
        str(max_artifact_bytes),
        "--timeout-action",
        "5000",
        "--timeout-navigation",
        "30000",
        "--allowed-origins",
        ";".join(allowed_origins),
        "--proxy-server",
        proxy_url,
    ]
