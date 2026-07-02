from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urljoin

from app.integrations.ai.base import AIGenerationRequest, AIGenerationResult, AIProviderTestResult


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: int = 25,
    ) -> None:
        clean_base_url = (base_url or "").strip()
        self._base_url = f"{clean_base_url.rstrip('/')}/" if clean_base_url else ""
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def test_connection(self) -> AIProviderTestResult:
        result = self.generate_text(
            AIGenerationRequest(
                system_prompt="You are a helpful assistant. Reply with exactly: ok",
                user_prompt="healthcheck",
                max_output_tokens=128,
            )
        )
        if result.success:
            return AIProviderTestResult(success=True)
        return AIProviderTestResult(
            success=False,
            error_code=result.error_code,
            error_summary=result.error_summary,
        )

    def generate_text(self, request: AIGenerationRequest) -> AIGenerationResult:
        if not self._api_key:
            return AIGenerationResult(
                success=False,
                provider="openai_compatible",
                model=self._model,
                error_code="missing_api_key",
            )
        if not self._base_url or not self._model:
            return AIGenerationResult(
                success=False,
                provider="openai_compatible",
                model=self._model,
                error_code="provider_not_configured",
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_output_tokens,
        }
        try:
            data = self._post_json("chat/completions", payload)
            message = data.get("choices", [{}])[0].get("message", {})
            text = (message.get("content") or "").strip()
            # Support reasoning models (MiMo, DeepSeek R1) where
            # the final answer may be in reasoning_content when
            # max_tokens is insufficient for both reasoning and output.
            if not text:
                text = (message.get("reasoning_content") or "").strip()
            usage = data.get("usage", {})
            if not text:
                return AIGenerationResult(
                    success=False,
                    provider="openai_compatible",
                    model=self._model,
                    error_code="empty_response",
                )
            return AIGenerationResult(
                success=True,
                text=text,
                provider="openai_compatible",
                model=self._model,
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
            )
        except urllib.error.HTTPError as exc:
            return AIGenerationResult(
                success=False,
                provider="openai_compatible",
                model=self._model,
                error_code=f"http_{exc.code}",
                error_summary="AI provider returned an HTTP error",
            )
        except (OSError, TimeoutError, ValueError, KeyError, IndexError, json.JSONDecodeError):
            return AIGenerationResult(
                success=False,
                provider="openai_compatible",
                model=self._model,
                error_code="provider_error",
                error_summary="AI provider request failed",
            )

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            urljoin(self._base_url, path),
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
