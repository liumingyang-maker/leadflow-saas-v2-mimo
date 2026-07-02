from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AIGenerationRequest:
    system_prompt: str
    user_prompt: str
    locale: str = "zh-CN"
    max_output_tokens: int = 800


@dataclass(frozen=True)
class AIGenerationResult:
    success: bool
    text: str = ""
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error_code: str = ""
    error_summary: str = ""


@dataclass(frozen=True)
class AIProviderTestResult:
    success: bool
    error_code: str = ""
    error_summary: str = ""


class AIProvider(Protocol):
    def test_connection(self) -> AIProviderTestResult: ...

    def generate_text(self, request: AIGenerationRequest) -> AIGenerationResult: ...
