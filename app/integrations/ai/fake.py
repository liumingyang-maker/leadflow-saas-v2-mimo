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

        if "target_customer_plan_generation" in request.system_prompt:
            text = json.dumps(
                {
                    "ideal_buyer_types": ["Importer", "Distributor", "Retail chain buyer"],
                    "target_industries": ["Retail", "Home goods", "Promotional products"],
                    "recommended_countries": ["United States", "Germany", "Australia"],
                    "search_keywords": [
                        "insulated bottle importer",
                        "drinkware distributor",
                        "promotional bottle wholesaler",
                    ],
                    "negative_keywords": ["job", "career", "free"],
                    "channel_recommendations": ["示例客户", "搜索候选", "CSV 导入"],
                    "buyer_pain_points": [
                        "needs stable small-batch supply",
                        "needs custom branding options",
                    ],
                    "match_scoring_rules": [
                        "has a public company website",
                        "sells or distributes adjacent products",
                        "matches target country or buyer type",
                    ],
                    "first_batch_strategy": "Start with 10 example candidates for user review.",
                    "disqualification_rules": [
                        "private individual contacts",
                        "job boards",
                        "companies without clear product fit",
                    ],
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

        if "target_customer_candidate_matching" in request.system_prompt:
            text = json.dumps(
                {
                    "candidates": [
                        {
                            "company_name": "Northstar Outdoor Supply",
                            "country": "United States",
                            "website": "https://northstar-outdoor.example",
                            "industry": "Outdoor retail",
                            "buyer_type": "Distributor",
                            "source_channel": "示例客户",
                            "match_reason": "Carries drinkware-adjacent outdoor products.",
                            "confidence_score": 82,
                            "suggested_next_action": "Review website categories before outreach.",
                        },
                        {
                            "company_name": "Meyer Promo Gifts",
                            "country": "Germany",
                            "website": "https://meyer-promo.example",
                            "industry": "Promotional products",
                            "buyer_type": "Wholesaler",
                            "source_channel": "示例客户",
                            "match_reason": "Likely fit for branded bottle trial orders.",
                            "confidence_score": 78,
                            "suggested_next_action": "Check catalog fit, then add to CRM.",
                        },
                        {
                            "company_name": "Pacific Home Goods",
                            "country": "Australia",
                            "website": "https://pacific-home-goods.example",
                            "industry": "Home goods",
                            "buyer_type": "Importer",
                            "source_channel": "搜索候选",
                            "match_reason": "Imports household categories with gift potential.",
                            "confidence_score": 74,
                            "suggested_next_action": "Verify product category before contact.",
                        },
                    ]
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

        if "basic_search_strategy_generation" in request.system_prompt:
            text = json.dumps(
                {
                    "buyer_types": ["Importer", "Distributor", "Promotional products buyer"],
                    "target_countries": ["United States", "Germany", "Australia"],
                    "search_keywords": [
                        "insulated bottle importer",
                        "drinkware distributor",
                        "custom bottle wholesaler",
                        "private label water bottle buyer",
                    ],
                    "negative_keywords": ["job", "career", "free", "supplier"],
                    "query_templates": [
                        "{product_keyword} importer",
                        "{product_keyword} distributor",
                        "{product_keyword} private label",
                    ],
                    "query_rationale": [
                        "Start from importer and distributor queries before paid channels.",
                        "Use private label terms for OEM/ODM fit.",
                    ],
                    "match_scoring_hints": [
                        "Prefer companies selling adjacent retail or promotional categories.",
                        "Penalize suppliers, job boards, and directory-only pages.",
                    ],
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

        if "pasted_search_result_parsing" in request.system_prompt:
            text = json.dumps(
                {
                    "candidates": [
                        {
                            "company_name": "Atlas Promo Supply",
                            "country": "United States",
                            "website": "https://atlas-promo.example",
                            "industry": "Promotional products",
                            "buyer_type": "Distributor",
                            "source_channel": "pasted_search_results",
                            "match_reason": (
                                "Pasted result suggests a promotional products catalog."
                            ),
                            "confidence_score": 80,
                            "suggested_next_action": (
                                "Review catalog categories before adding to CRM."
                            ),
                        },
                        {
                            "company_name": "Nordic Outdoor Goods",
                            "country": "Germany",
                            "website": "https://nordic-outdoor.example",
                            "industry": "Outdoor retail",
                            "buyer_type": "Importer",
                            "source_channel": "pasted_search_results",
                            "match_reason": (
                                "Search snippet references outdoor drinkware accessories."
                            ),
                            "confidence_score": 76,
                            "suggested_next_action": (
                                "Check whether drinkware is a current category."
                            ),
                        },
                    ]
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
