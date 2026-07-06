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
                _fake_search_intent_query_matrix(request.user_prompt),
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

        if "search_result_paste_parser_v2" in request.system_prompt:
            text = json.dumps(_fake_search_result_paste_parser_v2(), ensure_ascii=False)
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


def _fake_search_result_paste_parser_v2() -> dict[str, object]:
    return {
        "parse_summary": {
            "source_type": "search_engine_results",
            "total_items_seen": 6,
            "candidate_count": 3,
            "rejected_count": 3,
            "duplicate_hint_count": 0,
            "safety_warnings": [
                "候选客户未验证，需要人工确认。",
                "未保存私人邮箱或手机号。",
            ],
        },
        "candidates": [
            {
                "source_item_id": "item_001",
                "company_name": "GreenPack Distribution",
                "domain": "greenpack-distribution.example",
                "source_url": "https://greenpack-distribution.example",
                "country": "United States",
                "buyer_type": "Distributor",
                "classification": "buyer",
                "product_fit": "high",
                "source_quality": "official_site",
                "fit_score": 82,
                "confidence_score": 74,
                "match_reason": "Snippet suggests a distributor reviewing packaging categories.",
                "risk_reason": "Unverified search snippet; confirm product category manually.",
                "next_action": "review",
                "sanitized_snippet": (
                    "Distributor profile with sustainable packaging category signals."
                ),
            },
            {
                "source_item_id": "item_002",
                "company_name": "Eco Retail Brands",
                "domain": "ecoretailbrands.example",
                "source_url": "https://ecoretailbrands.example",
                "country": "Germany",
                "buyer_type": "Private label brand",
                "classification": "buyer",
                "product_fit": "medium",
                "source_quality": "company_profile",
                "fit_score": 76,
                "confidence_score": 68,
                "match_reason": "Pasted text indicates retail brand needs packaging suppliers.",
                "risk_reason": "May be a brand article rather than procurement page.",
                "next_action": "research",
                "sanitized_snippet": "Retail brand profile mentioning custom packaging needs.",
            },
            {
                "source_item_id": "item_003",
                "company_name": "North Market Import",
                "domain": "northmarketimport.example",
                "source_url": "https://northmarketimport.example",
                "country": "United Kingdom",
                "buyer_type": "Importer",
                "classification": "maybe_buyer",
                "product_fit": "medium",
                "source_quality": "unknown",
                "fit_score": 65,
                "confidence_score": 55,
                "match_reason": "Manual list entry looks like an importer but evidence is limited.",
                "risk_reason": "Thin source text; manually confirm buyer role.",
                "next_action": "review",
                "sanitized_snippet": "Importer name and country only.",
            },
        ],
        "rejected_items": [
            {"source_item_id": "item_004", "reason": "supplier"},
            {"source_item_id": "item_005", "reason": "directory"},
            {"source_item_id": "item_006", "reason": "marketplace"},
        ],
        "query_feedback": {
            "suggested_negative_keywords": ["manufacturer", "factory", "supplier", "marketplace"],
            "suggested_better_queries": [
                "eco-friendly packaging distributor -manufacturer -factory",
                "custom packaging importer Germany -supplier -marketplace",
            ],
            "domain_blacklist_suggestions": ["example-directory.test"],
            "notes": ["目录和市场站噪音偏多，下一轮搜索应加强排除词。"],
        },
    }


def _fake_search_intent_query_matrix(user_prompt: str) -> dict[str, object]:
    lower = user_prompt.lower()
    if "detected current product family: led_lighting" in lower:
        return _fake_led_search_intent_query_matrix()
    if "detected current product family: packaging" in lower:
        return _fake_packaging_search_intent_query_matrix()
    packaging_hits = sum(
        term in lower
        for term in (
            "packaging",
            "bag",
            "bags",
            "mailer",
            "kraft",
            "compostable",
            "cosmetic packaging",
        )
    )
    lighting_hits = sum(
        term in lower
        for term in (
            "led",
            "lighting",
            "lamp",
            "fixture",
            "electrical wholesaler",
            "decorative lighting",
        )
    )
    if lighting_hits > packaging_hits:
        return _fake_led_search_intent_query_matrix()
    return _fake_packaging_search_intent_query_matrix()


def _base_search_intent_safety() -> dict[str, object]:
    return {
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
        "next_search_steps": [
            "先复制 3-5 条最像买家的搜索词。",
            "手动去 Google、Brave 或 Bing 搜索。",
            "把搜索结果摘要粘贴回来，让 AI 筛选候选客户。",
        ],
    }


def _fake_packaging_search_intent_query_matrix() -> dict[str, object]:
    data = {
        "product_context_check": {
            "detected_product_family": "packaging",
            "core_products_used": [
                "eco-friendly packaging",
                "compostable mailer bags",
                "custom packaging bags",
            ],
            "excluded_unrelated_terms": ["LED", "lighting", "electrical wholesaler"],
            "confidence": 92,
        },
        "intent_summary": (
            "AI 判断当前产品是包装类产品，优先寻找包装进口商、经销商、私标品牌和零售品牌。"
        ),
        "product_keywords": [
            "eco-friendly packaging",
            "compostable mailer bags",
            "custom packaging bags",
        ],
        "product_synonyms": [
            "sustainable packaging",
            "private label packaging",
            "custom printed bags",
        ],
        "use_cases": [
            "cosmetic packaging brands",
            "coffee roasters",
            "pet food brands",
            "sustainable DTC brands",
        ],
        "target_industries": ["Food packaging", "Cosmetics", "Retail", "DTC brands"],
        "buyer_roles": ["procurement manager", "category buyer", "sourcing manager"],
        "buyer_company_types": ["Importer", "Distributor", "Private label brand", "Retailer"],
        "target_countries": ["United States", "Germany", "United Kingdom"],
        "multilingual_terms": [
            {
                "country": "Germany",
                "language": "German",
                "buyer_terms": ["Importeur", "Großhändler", "Händler"],
                "query_terms": ["kompostierbare Versandtaschen Importeur Deutschland"],
                "negative_terms": ["Hersteller", "Fabrik"],
            }
        ],
        "query_matrix": [
            {
                "group": "buyer_type",
                "query": (
                    "eco-friendly packaging importer United States -manufacturer -supplier -factory"
                ),
                "target_country": "United States",
                "buyer_type": "Importer",
                "why_useful": "偏向寻找进口型包装买家，而不是包装生产同行。",
                "risk": "仍可能出现目录页，需要人工确认。",
                "copy_label": "US packaging importer",
                "product_terms_used": ["eco-friendly packaging"],
                "buyer_terms_used": ["importer"],
                "country_terms_used": ["United States"],
                "negative_terms_used": ["manufacturer", "supplier", "factory"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
            {
                "group": "country",
                "query": "compostable mailer bags distributor Germany -manufacturer -factory",
                "target_country": "Germany",
                "buyer_type": "Distributor",
                "why_useful": "德国经销商可能采购环保邮寄袋。",
                "risk": "需要排除本地工厂。",
                "copy_label": "Germany compostable mailer distributor",
                "product_terms_used": ["compostable mailer bags"],
                "buyer_terms_used": ["distributor"],
                "country_terms_used": ["Germany"],
                "negative_terms_used": ["manufacturer", "factory"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
            {
                "group": "private_label",
                "query": "custom packaging bags private label brand UK -supplier -marketplace",
                "target_country": "United Kingdom",
                "buyer_type": "Private label brand",
                "why_useful": "私标品牌可能需要定制包装袋。",
                "risk": "品牌官网不一定显示采购入口。",
                "copy_label": "UK private label packaging",
                "product_terms_used": ["custom packaging bags"],
                "buyer_terms_used": ["private label brand"],
                "country_terms_used": ["UK"],
                "negative_terms_used": ["supplier", "marketplace"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
        ],
        "query_self_check": [
            {
                "query": "custom packaging",
                "risk": "too broad",
                "improved_query": "custom packaging bags importer -manufacturer -factory -supplier",
            }
        ],
    }
    return {**data, **_base_search_intent_safety()}


def _fake_led_search_intent_query_matrix() -> dict[str, object]:
    data = {
        "product_context_check": {
            "detected_product_family": "led_lighting",
            "core_products_used": [
                "LED lighting",
                "decorative lighting",
                "commercial LED fixtures",
            ],
            "excluded_unrelated_terms": ["packaging bags", "mailer bags", "kraft paper bags"],
            "confidence": 93,
        },
        "intent_summary": (
            "AI 判断当前产品是 LED 照明类产品，优先寻找照明经销商、电气批发商和工程供应商。"
        ),
        "product_keywords": [
            "LED lighting",
            "decorative lighting",
            "commercial LED fixtures",
        ],
        "product_synonyms": ["LED fixtures", "commercial lighting", "decorative lamps"],
        "use_cases": [
            "lighting distributors",
            "hotel lighting projects",
            "event production companies",
            "electrical wholesalers",
        ],
        "target_industries": ["Electrical distribution", "Hospitality projects", "Lighting retail"],
        "buyer_roles": ["procurement manager", "project buyer", "lighting category manager"],
        "buyer_company_types": [
            "Lighting distributor",
            "Electrical wholesaler",
            "Contractor",
            "Project supplier",
        ],
        "target_countries": ["United States", "United Arab Emirates", "Australia"],
        "multilingual_terms": [
            {
                "country": "United Arab Emirates",
                "language": "English",
                "buyer_terms": ["lighting distributor", "electrical wholesaler"],
                "query_terms": ["decorative lighting wholesaler UAE"],
                "negative_terms": ["manufacturer", "factory"],
            }
        ],
        "query_matrix": [
            {
                "group": "buyer_type",
                "query": "LED lighting distributor United States -manufacturer -factory -supplier",
                "target_country": "United States",
                "buyer_type": "Lighting distributor",
                "why_useful": "偏向寻找销售 LED 照明产品的渠道商。",
                "risk": "部分结果可能是制造商，需要人工确认。",
                "copy_label": "US LED lighting distributor",
                "product_terms_used": ["LED lighting"],
                "buyer_terms_used": ["distributor"],
                "country_terms_used": ["United States"],
                "negative_terms_used": ["manufacturer", "factory", "supplier"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
            {
                "group": "country",
                "query": "decorative lighting wholesaler UAE -manufacturer -marketplace",
                "target_country": "United Arab Emirates",
                "buyer_type": "Wholesaler",
                "why_useful": "阿联酋装饰灯批发商可能适合人工开发。",
                "risk": "批发商和供应商词可能混杂。",
                "copy_label": "UAE decorative lighting wholesaler",
                "product_terms_used": ["decorative lighting"],
                "buyer_terms_used": ["wholesaler"],
                "country_terms_used": ["UAE"],
                "negative_terms_used": ["manufacturer", "marketplace"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
            {
                "group": "procurement",
                "query": (
                    "commercial LED fixtures electrical wholesaler Australia -factory -supplier"
                ),
                "target_country": "Australia",
                "buyer_type": "Electrical wholesaler",
                "why_useful": "电气批发商可能采购商业 LED 灯具。",
                "risk": "需要人工判断是否面向项目或渠道采购。",
                "copy_label": "Australia electrical wholesaler",
                "product_terms_used": ["commercial LED fixtures"],
                "buyer_terms_used": ["electrical wholesaler"],
                "country_terms_used": ["Australia"],
                "negative_terms_used": ["factory", "supplier"],
                "relevance_to_current_product": "high",
                "cross_industry_risk": "none",
            },
        ],
        "query_self_check": [
            {
                "query": "LED lighting supplier",
                "risk": "supplier-biased",
                "improved_query": "LED lighting distributor -manufacturer -factory -supplier",
            }
        ],
    }
    return {**data, **_base_search_intent_safety()}
