from __future__ import annotations

import json

from app.integrations.ai.base import AIGenerationRequest, AIGenerationResult, AIProviderTestResult


class FakeAIProvider:
    def __init__(self, *, model: str = "fake-ai") -> None:
        self._model = model or "fake-ai"

    def test_connection(self) -> AIProviderTestResult:
        return AIProviderTestResult(success=True)

    def generate_text(self, request: AIGenerationRequest) -> AIGenerationResult:
        if "product_profile_extraction" in request.system_prompt:
            text = json.dumps(
                {
                    "product_keywords_cn": ["样品产品", "外贸产品"],
                    "product_keywords_en": ["sample product", "export product"],
                    "product_categories": ["General merchandise"],
                    "selling_points_cn": ["交付稳定", "适合小批量试单"],
                    "selling_points_en": ["Stable delivery", "Suitable for trial orders"],
                    "target_industries": ["Retail", "Distribution"],
                    "buyer_types": ["Importer", "Distributor"],
                    "target_countries": ["United States", "Germany"],
                    "search_keywords": ["sample product importer", "export product distributor"],
                    "negative_keywords": ["job", "career"],
                    "outreach_angles": ["Introduce stable supply for small trial orders"],
                    "suggested_email_tone": "professional and concise",
                    "product_summary_en": "A practical export product for overseas buyers.",
                    "moq_summary": "unknown",
                    "certificates": [],
                    "delivery_capacity": "unknown",
                    "factory_type": "unknown",
                    "ideal_buyer_profile": "Importers and distributors looking for stable supply.",
                    "oem_odm_capability": "unknown",
                    "price_positioning": "unknown",
                },
                ensure_ascii=False,
            )
            return AIGenerationResult(
                success=True,
                text=text,
                provider="fake",
                model=self._model,
                input_tokens=_rough_tokens(request.system_prompt + request.user_prompt),
                output_tokens=_rough_tokens(text),
            )

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
