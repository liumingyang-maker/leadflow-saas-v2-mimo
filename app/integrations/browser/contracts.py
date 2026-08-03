from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

AllowedBrowserTool = Literal[
    "open_allowed_url",
    "read_current_public_page",
    "follow_same_site_link",
    "capture_evidence",
    "stop_research",
]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BrowserAction(_StrictFrozenModel):
    tool: AllowedBrowserTool
    url: HttpUrl | None = None
    element_ref: str = Field(default="", pattern=r"^[A-Za-z0-9_-]{0,80}$")

    @model_validator(mode="after")
    def _require_url_only_for_open(self) -> BrowserAction:
        if self.tool == "open_allowed_url" and self.url is None:
            raise ValueError("open_allowed_url requires a URL")
        if self.tool != "open_allowed_url" and self.url is not None:
            raise ValueError("only open_allowed_url may include a URL")
        return self


class BrowserResearchPlan(_StrictFrozenModel):
    version: Literal["browser-plan-v1"]
    start_url: HttpUrl
    allowed_origins: tuple[str, ...] = Field(min_length=1, max_length=5)
    allowed_paths: tuple[str, ...] = Field(default=("/",), max_length=20)
    actions: tuple[BrowserAction, ...] = Field(min_length=1, max_length=12)

    @field_validator("allowed_origins")
    @classmethod
    def _validate_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            parsed = urlsplit(value)
            if (
                parsed.scheme.lower() != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
                or (parsed.port not in {None, 443})
            ):
                raise ValueError("allowed origins must be HTTPS origins")
            host = parsed.hostname.rstrip(".").lower().encode("idna").decode("ascii")
            origin = f"https://{host}"
            if origin not in normalized:
                normalized.append(origin)
        return tuple(normalized)

    @field_validator("allowed_paths")
    @classmethod
    def _validate_paths(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for value in values:
            if not value.startswith("/") or "//" in value or "/../" in f"/{value}/":
                raise ValueError("allowed paths must be absolute, normalized paths")
            clean = value.rstrip("/") or "/"
            if clean not in normalized:
                normalized.append(clean)
        return tuple(normalized)


class BrowserTaskDescriptor(_StrictFrozenModel):
    version: Literal["browser-task-v1"] = "browser-task-v1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    run_token: str = Field(min_length=32, max_length=256, repr=False)
    attempt: int = Field(ge=1, le=10_000)
    plan_json: str = Field(min_length=2, max_length=25_000)
    max_pages: int = Field(ge=1, le=25)
    max_seconds: int = Field(ge=10, le=300)
    max_tool_calls: int = Field(ge=1, le=30)
    max_artifact_bytes: int = Field(ge=1024, le=20 * 1024 * 1024)
    artifact_subdir: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")


class BrowserArtifactEntry(_StrictFrozenModel):
    name: str = Field(min_length=1, max_length=260)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0, le=20 * 1024 * 1024)
    content_type: Literal["image/png", "application/json", "text/plain"]

    @field_validator("name")
    @classmethod
    def _validate_relative_name(cls, value: str) -> str:
        if value.startswith(("/", "\\")) or ".." in value.split("/") or "\\" in value:
            raise ValueError("artifact name must be a safe relative path")
        if not value.endswith((".png", ".json", ".txt")):
            raise ValueError("artifact extension is not allowed")
        return value


class BrowserPageResult(_StrictFrozenModel):
    url: HttpUrl
    title: str = Field(max_length=500)
    text: str = Field(max_length=20_000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_injection_detected: bool = False
    artifacts: tuple[BrowserArtifactEntry, ...] = Field(default=(), max_length=4)


class BrowserTaskResult(_StrictFrozenModel):
    version: Literal["browser-result-v1"] = "browser-result-v1"
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    run_token: str = Field(min_length=32, max_length=256, repr=False)
    attempt: int = Field(ge=1, le=10_000)
    status: Literal["completed", "partial", "blocked", "failed", "cancelled"]
    pages: tuple[BrowserPageResult, ...] = Field(default=(), max_length=25)
    page_count: int = Field(ge=0, le=25)
    tool_call_count: int = Field(ge=0, le=30)
    bytes_written: int = Field(ge=0, le=20 * 1024 * 1024)
    error_code: str = Field(default="", max_length=80)
    error_summary: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _check_page_count(self) -> BrowserTaskResult:
        if self.page_count != len(self.pages):
            raise ValueError("page_count must match pages")
        return self
