from __future__ import annotations

from app.integrations.ai.base import AIGenerationRequest, AIGenerationResult, AIProviderTestResult


class DisabledProvider:
    def test_connection(self) -> AIProviderTestResult:
        return AIProviderTestResult(success=False, error_code="ai_disabled")

    def generate_text(self, request: AIGenerationRequest) -> AIGenerationResult:
        return AIGenerationResult(success=False, provider="disabled", error_code="ai_disabled")
