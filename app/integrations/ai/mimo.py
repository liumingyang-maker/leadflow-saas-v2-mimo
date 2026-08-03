"""Xiaomi MiMo adapter with strict validation and safe failures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.integrations.ai.contracts import (
    CountryResearchPlan,
    ExtractedCompanyFacts,
    MissionPlan,
    SearchHit,
    SearchResults,
)
from app.modules.accounts.secret_store import SecretStore, SecretStoreError

if TYPE_CHECKING:
    from flask import Flask

    from app.integrations.web.fetcher import FetchResult


_Schema = TypeVar("_Schema", bound=BaseModel)
_PROMPT_DIR = Path(__file__).with_name("prompts")


class ProviderError(RuntimeError):
    def __init__(self, code: str, safe_summary: str, *, retryable: bool) -> None:
        super().__init__(f"{code}: {safe_summary}")
        self.code = code
        self.safe_summary = safe_summary
        self.retryable = retryable


class ProviderResponseError(ProviderError):
    def __init__(self) -> None:
        super().__init__(
            "invalid_response",
            "Provider response failed schema validation",
            retryable=False,
        )


class MiMoProvider:
    """Small provider boundary used by background acquisition jobs."""

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        web_search_enabled: bool = True,
    ) -> None:
        self.client = client
        self.model = model
        self.web_search_enabled = web_search_enabled
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> MiMoProvider:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def plan_mission(
        self,
        *,
        product_summary: str,
        target_profile: dict[str, Any],
    ) -> MissionPlan:
        prompt = _load_prompt("mission_plan_v1.txt")
        payload = json.dumps(
            {"product_summary": product_summary, "target_profile": target_profile},
            ensure_ascii=False,
            sort_keys=True,
        )
        plan = self._validated_request(prompt, payload, MissionPlan)
        expected_countries = target_profile.get("country_codes")
        if isinstance(expected_countries, list):
            expected = sorted(str(item).upper() for item in expected_countries)
            actual = sorted(run.country_code for run in plan.country_runs)
            if len(actual) != len(set(actual)) or actual != expected:
                raise ProviderResponseError()
        return plan

    def discover_companies(
        self,
        *,
        country_plan: CountryResearchPlan,
    ) -> list[SearchHit]:
        if not self.web_search_enabled:
            raise ProviderError(
                "provider_capability_missing",
                "MiMo web search is unavailable",
                retryable=False,
            )
        prompt = _load_prompt("company_discovery_v1.txt")
        output = self._validated_request(
            prompt,
            country_plan.model_dump_json(),
            SearchResults,
            web_search=True,
        )
        return output.search_hits

    def extract(self, snapshot: FetchResult) -> ExtractedCompanyFacts:
        prompt = _load_prompt("company_extract_v1.txt")
        payload = json.dumps(
            {
                "source_url": snapshot.final_url,
                "title": snapshot.title,
                "sanitized_text": snapshot.text,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        facts = self._validated_request(prompt, payload, ExtractedCompanyFacts)
        supplied_url = snapshot.final_url.rstrip("/")
        if any(
            str(claim.source_url).rstrip("/") != supplied_url for claim in facts.observed_claims
        ):
            raise ProviderResponseError()
        return facts

    def _validated_request(
        self,
        instructions: str,
        input_text: str,
        schema: type[_Schema],
        *,
        web_search: bool = False,
    ) -> _Schema:
        output_text = self._request_with_retry(
            instructions=instructions,
            input_text=input_text,
            web_search=web_search,
        )
        try:
            return schema.model_validate_json(output_text)
        except (ValidationError, ValueError, TypeError) as exc:
            repair_instructions = (
                f"{instructions}\n"
                "The previous response did not match the required JSON schema at: "
                f"{_safe_validation_paths(exc)}. Return only a corrected JSON object."
            )
        repaired_output = self._request_with_retry(
            instructions=repair_instructions,
            input_text=input_text,
            web_search=web_search,
        )
        try:
            return schema.model_validate_json(repaired_output)
        except (ValidationError, ValueError, TypeError):
            raise ProviderResponseError() from None

    def _request_with_retry(
        self,
        *,
        instructions: str,
        input_text: str,
        web_search: bool,
    ) -> str:
        for attempt in range(2):
            try:
                return self._request_once(
                    instructions=instructions,
                    input_text=input_text,
                    web_search=web_search,
                )
            except ProviderError as exc:
                if not exc.retryable or attempt == 1:
                    raise
            except Exception as exc:  # provider SDK exceptions vary by version
                mapped = _map_provider_error(exc, web_search=web_search)
                if not mapped.retryable or attempt == 1:
                    raise mapped from None
        raise AssertionError("unreachable")

    def _request_once(
        self,
        *,
        instructions: str,
        input_text: str,
        web_search: bool,
    ) -> str:
        chat = getattr(self.client, "chat", None)
        completions = getattr(chat, "completions", None)
        if completions is not None:
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
                "response_format": {"type": "json_object"},
                "max_completion_tokens": 4096,
                "stream": False,
                "timeout": 60,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            if web_search:
                kwargs.update(
                    tools=[
                        {
                            "type": "web_search",
                            "max_keyword": 3,
                            "force_search": True,
                            "limit": 10,
                        }
                    ],
                    tool_choice="auto",
                )
            response = completions.create(**kwargs)
            content = response.choices[0].message.content
            if not isinstance(content, str):
                raise ProviderResponseError()
            return content

        responses = getattr(self.client, "responses", None)
        if responses is None:
            raise ProviderError(
                "provider_unavailable", "MiMo client is unavailable", retryable=True
            )
        kwargs = {
            "model": self.model,
            "instructions": instructions,
            "input": input_text,
            "max_output_tokens": 4096,
            "timeout": 60,
        }
        if web_search:
            kwargs["tools"] = [{"type": "web_search", "max_keyword": 3}]
        response = responses.create(**kwargs)
        output_text = getattr(response, "output_text", None)
        if not isinstance(output_text, str):
            raise ProviderResponseError()
        return output_text


def _load_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _safe_validation_paths(exc: Exception) -> str:
    if not isinstance(exc, ValidationError):
        return "root"
    paths = sorted(
        {
            ".".join(str(part) for part in item["loc"]) or "root"
            for item in exc.errors(include_url=False, include_context=False, include_input=False)
        }
    )
    return ", ".join(paths[:10]) or "root"


def _map_provider_error(exc: Exception, *, web_search: bool) -> ProviderError:
    """Map provider failures without copying untrusted exception text."""

    name = type(exc).__name__.lower()
    status = getattr(exc, "status_code", None)
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return ProviderError("timeout", "MiMo request timed out", retryable=True)
    if status in {401, 403} or "authentication" in name or "permission" in name:
        return ProviderError("auth", "MiMo authentication failed", retryable=False)
    if status == 402:
        return ProviderError("quota", "MiMo quota is unavailable", retryable=False)
    if status == 429 or "ratelimit" in name or "rate_limit" in name:
        return ProviderError("rate_limit", "MiMo rate limit reached", retryable=True)
    if web_search and status in {400, 404, 422}:
        return ProviderError(
            "provider_capability_missing",
            "MiMo web search is unavailable",
            retryable=False,
        )
    if status is not None and 400 <= status < 500:
        return ProviderError("invalid_request", "MiMo rejected the request", retryable=False)
    return ProviderError("transient", "MiMo is temporarily unavailable", retryable=True)


def build_mimo_provider(app: Flask, *, tenant_id: str) -> MiMoProvider:
    """Build a tenant-scoped provider without placing its key in a job payload."""

    try:
        with Session(get_engine(app)) as session:
            key = SecretStore(session).load(tenant_id, "mimo_api_key")
    except SecretStoreError as exc:
        raise ProviderError(
            "provider_not_configured",
            "MiMo API key is not configured",
            retryable=False,
        ) from exc

    base_url = str(app.config.get("MIMO_BASE_URL", "")).strip()
    if not base_url:
        raise ProviderError(
            "provider_not_configured",
            "MiMo base URL is not configured",
            retryable=False,
        )

    from openai import OpenAI

    client = OpenAI(api_key=key, base_url=base_url, timeout=60.0, max_retries=0)
    return MiMoProvider(
        client=client,
        model=str(app.config["MIMO_MODEL"]),
        web_search_enabled=True,
    )
