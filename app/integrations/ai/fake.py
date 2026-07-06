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

        if "search_intent_query_matrix" in request.system_prompt:
            text = json.dumps(
                {
                    "intent_summary": (
                        "AI 判断该产品适合先找进口商、经销商、批发商、私标品牌和采购公司，"
                        "搜索时应排除供应商、工厂、平台和目录噪音。"
                    ),
                    "product_keywords": [
                        "eco-friendly packaging",
                        "custom packaging bags",
                        "LED decorative lighting",
                    ],
                    "product_synonyms": [
                        "sustainable packaging",
                        "private label packaging",
                        "commercial LED lighting",
                    ],
                    "use_cases": [
                        "cosmetic packaging brands",
                        "coffee roasters",
                        "lighting distributors",
                        "hotel lighting projects",
                    ],
                    "target_industries": [
                        "Retail",
                        "Food packaging",
                        "Cosmetics",
                        "Electrical distribution",
                    ],
                    "buyer_roles": [
                        "procurement manager",
                        "category buyer",
                        "sourcing manager",
                    ],
                    "buyer_company_types": [
                        "Importer",
                        "Distributor",
                        "Wholesaler",
                        "Retailer",
                        "Private label brand",
                        "Procurement company",
                    ],
                    "target_countries": ["United States", "Germany", "United Arab Emirates"],
                    "negative_keywords": [
                        "manufacturer",
                        "supplier",
                        "factory",
                        "marketplace",
                        "directory",
                        "Alibaba",
                        "Amazon",
                        "eBay",
                    ],
                    "supplier_exclusion_terms": ["manufacturer", "factory", "supplier"],
                    "marketplace_exclusion_terms": ["Alibaba", "Amazon", "eBay"],
                    "directory_noise_terms": ["directory", "blog", "article", "news"],
                    "multilingual_terms": [
                        {
                            "country": "Germany",
                            "language": "German",
                            "buyer_terms": ["Importeur", "Großhändler", "Händler"],
                            "query_terms": ["custom packaging Importeur Deutschland"],
                            "negative_terms": ["Hersteller", "Fabrik"],
                        },
                        {
                            "country": "Spain",
                            "language": "Spanish",
                            "buyer_terms": ["importador", "distribuidor", "mayorista"],
                            "query_terms": ["LED lighting distribuidor España"],
                            "negative_terms": ["fabricante", "proveedor"],
                        },
                    ],
                    "query_matrix": [
                        {
                            "group": "buyer_type",
                            "query": (
                                "eco-friendly packaging importer -manufacturer -factory "
                                "-supplier -Alibaba -Amazon"
                            ),
                            "target_country": "United States",
                            "buyer_type": "Importer",
                            "why_useful": "偏向寻找进口型买家，而不是包装生产同行。",
                            "risk": "仍可能出现目录页，需要人工确认。",
                            "copy_label": "US packaging importer",
                        },
                        {
                            "group": "use_case",
                            "query": (
                                "custom cosmetic packaging brand buyer -manufacturer "
                                "-factory -supplier"
                            ),
                            "target_country": "United States",
                            "buyer_type": "Private label brand",
                            "why_useful": "化妆品品牌可能采购定制包装。",
                            "risk": "品牌官网不一定显示采购入口。",
                            "copy_label": "Cosmetic packaging brand",
                        },
                        {
                            "group": "multilingual",
                            "query": "LED lighting distribuidor España -fabricante -proveedor",
                            "target_country": "Spain",
                            "buyer_type": "Distributor",
                            "why_useful": "用当地语言寻找 LED 经销商。",
                            "risk": "需要人工判断是否为买家。",
                            "copy_label": "Spain LED distributor",
                        },
                    ],
                    "query_self_check": [
                        {
                            "query": "custom packaging",
                            "risk": "too broad",
                            "improved_query": (
                                "custom packaging importer -manufacturer -factory -supplier"
                            ),
                        },
                        {
                            "query": "LED lighting supplier",
                            "risk": "supplier-biased",
                            "improved_query": "LED lighting distributor -manufacturer -factory",
                        },
                    ],
                    "next_search_steps": [
                        "先复制 3-5 条最像买家的搜索词。",
                        "手动去 Google、Brave 或 Bing 搜索。",
                        "把搜索结果摘要粘贴回来，让 AI 筛选候选客户。",
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

        if "candidate_company_research" in request.system_prompt:
            text = json.dumps(
                {
                    "summary": (
                        "This candidate appears to be a public B2B company profile that "
                        "may be worth manual review."
                    ),
                    "why_potential_buyer": (
                        "The supplied metadata suggests a possible importer or distributor fit, "
                        "but the evidence is not verified."
                    ),
                    "product_fit": (
                        "Likely adjacent to the tenant product category based on candidate "
                        "buyer type and match reason."
                    ),
                    "buyer_type": "Distributor",
                    "country_region": "United States",
                    "possible_use_cases": ["Trial order review", "Catalog fit check"],
                    "positive_signals": [
                        {
                            "signal": "Candidate metadata mentions adjacent product categories",
                            "source": "candidate_metadata",
                            "confidence": "medium",
                        }
                    ],
                    "risk_signals": [
                        {
                            "risk": "Source data is thin and has not been manually verified",
                            "source": "candidate_metadata",
                            "severity": "medium",
                        }
                    ],
                    "fit_score": 72,
                    "confidence_score": 58,
                    "suggested_next_action": (
                        "Open the source link and confirm product category fit before "
                        "adding to CRM."
                    ),
                    "suggested_outreach_angle": (
                        "Lead with a small trial order and stable supply angle after "
                        "manual confirmation."
                    ),
                    "disclaimer": "未验证，需要人工确认",
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

        if "candidate_outreach_draft" in request.system_prompt:
            text = json.dumps(
                {
                    "subject": "Possible fit for your outdoor retail range",
                    "body": (
                        "Hi,\n\n"
                        "I noticed your public company information may be related to outdoor "
                        "retail and distribution. We manufacture insulated drinkware for "
                        "buyers who need steady supply, clear packaging options, and small "
                        "trial-order support.\n\n"
                        "Based on the limited research available, there could be a fit if "
                        "you are reviewing drinkware or outdoor accessory suppliers. Would "
                        "it be useful if I shared a short catalog and sample options for "
                        "your team to review?\n\n"
                        "Best regards"
                    ),
                    "short_body": (
                        "Hi, based on limited public information, our insulated drinkware "
                        "line may be relevant to your outdoor retail range. Would a short "
                        "catalog and sample options be useful for review?"
                    ),
                    "follow_up_angle": (
                        "Follow up with a concise catalog offer and ask whether drinkware "
                        "is a relevant category this season."
                    ),
                    "personalization_notes": [
                        "Reference outdoor retail or distribution only as an unverified fit.",
                        "Lead with trial-order support and stable supply.",
                    ],
                    "confidence_note": (
                        "This draft is based on limited public candidate metadata and an "
                        "unverified research report. Please confirm fit before sending."
                    ),
                    "disclaimer": (
                        "Draft only. Not sent. AI result is for reference and needs manual "
                        "confirmation."
                    ),
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
