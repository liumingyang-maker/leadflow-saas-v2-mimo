from __future__ import annotations

from app.integrations.ai.base import AIGenerationRequest, AIGenerationResult, AIProviderTestResult


class FakeAIProvider:
    def __init__(self, *, model: str = "fake-ai") -> None:
        self._model = model or "fake-ai"

    def test_connection(self) -> AIProviderTestResult:
        return AIProviderTestResult(success=True)

    def generate_text(self, request: AIGenerationRequest) -> AIGenerationResult:
        if request.locale == "en-US":
            text = (
                "Subject: Quick idea for your growth pipeline\n\n"
                "Hi there,\n\n"
                "I noticed your team may be a fit for LeadFlow. We help teams find, "
                "review, and follow up with qualified leads without adding manual "
                "spreadsheet work.\n\n"
                "Would it make sense to compare notes this week?\n"
            )
        else:
            text = (
                "主题：关于增长线索的一个想法\n\n"
                "你好，\n\n"
                "我注意到贵团队可能适合使用 LeadFlow。我们帮助团队发现、审核并跟进"
                "高质量线索，减少手动整理表格的工作。\n\n"
                "这周是否方便简单交流一下？\n"
            )
        return AIGenerationResult(
            success=True,
            text=text,
            provider="fake",
            model=self._model,
            input_tokens=_rough_tokens(request.system_prompt + request.user_prompt),
            output_tokens=_rough_tokens(text),
        )


def _rough_tokens(value: str) -> int:
    return max(1, len(value) // 4)
