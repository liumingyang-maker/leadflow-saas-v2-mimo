from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutreachDraftPrompt:
    system_prompt: str
    user_prompt: str


def build_outreach_draft_prompt(
    *,
    locale: str,
    company: str,
    contact_name: str,
    title: str,
    industry: str,
    website: str,
    source: str,
    notes: str = "",
) -> OutreachDraftPrompt:
    if locale == "en-US":
        system = (
            "You write concise B2B outreach email drafts. Return only a subject line "
            "and plain text body. Do not claim facts not provided. Do not send email."
        )
        user = (
            "Create an outreach draft for this lead.\n"
            f"Company: {_clean(company)}\n"
            f"Contact: {_clean(contact_name)}\n"
            f"Title: {_clean(title)}\n"
            f"Industry: {_clean(industry)}\n"
            f"Website: {_clean(website)}\n"
            f"Lead source: {_clean(source)}\n"
            f"Additional instruction: {_clean(notes)}\n"
            "Format:\nSubject: ...\n\nBody..."
        )
    else:
        system = (
            "你是一名克制、专业的 B2B 外联邮件草稿助手。只返回邮件主题和纯文本正文。"
            "不要编造未提供的事实。不要发送邮件。"
        )
        user = (
            "请为以下线索生成一封外联邮件草稿。\n"
            f"公司：{_clean(company)}\n"
            f"联系人：{_clean(contact_name)}\n"
            f"职位：{_clean(title)}\n"
            f"行业：{_clean(industry)}\n"
            f"网站：{_clean(website)}\n"
            f"线索来源：{_clean(source)}\n"
            f"补充要求：{_clean(notes)}\n"
            "格式：\n主题：...\n\n正文..."
        )
    return OutreachDraftPrompt(system_prompt=system, user_prompt=user)


def build_product_profile_extraction_prompt(
    *, locale: str, raw_fields: dict[str, str]
) -> OutreachDraftPrompt:
    keys = (
        "product_keywords_cn",
        "product_keywords_en",
        "product_categories",
        "selling_points_cn",
        "selling_points_en",
        "target_industries",
        "buyer_types",
        "target_countries",
        "search_keywords",
        "negative_keywords",
        "outreach_angles",
        "suggested_email_tone",
        "product_summary_en",
        "moq_summary",
        "certificates",
        "delivery_capacity",
        "factory_type",
        "ideal_buyer_profile",
        "oem_odm_capability",
        "price_positioning",
    )
    system = (
        "feature: product_profile_extraction\n"
        "Extract a structured foreign trade product profile from user-provided text only. "
        "Return strict JSON only. Do not invent certificates, MOQ, delivery capacity, or "
        'customer countries. If unknown, use an empty array for list fields or "unknown" '
        "for text fields. Do not include markdown fences. JSON keys must be exactly: "
        f"{', '.join(keys)}."
    )
    if locale == "zh-CN":
        system += " UI language is Simplified Chinese, but JSON keys stay English."
    user = (
        "Company introduction:\n"
        f"{_clean_long(raw_fields.get('raw_company_intro', ''))}\n\n"
        "Main products:\n"
        f"{_clean_long(raw_fields.get('raw_products', ''))}\n\n"
        "Website URL, saved only and not crawled:\n"
        f"{_clean_long(raw_fields.get('raw_website_url', ''))}\n\n"
        "Target markets:\n"
        f"{_clean_long(raw_fields.get('raw_target_markets', ''))}\n\n"
        "Factory advantages:\n"
        f"{_clean_long(raw_fields.get('raw_advantages', ''))}\n\n"
        "Certificates:\n"
        f"{_clean_long(raw_fields.get('raw_certificates', ''))}\n\n"
        "MOQ:\n"
        f"{_clean_long(raw_fields.get('raw_moq', ''))}\n\n"
        "Delivery capacity:\n"
        f"{_clean_long(raw_fields.get('raw_delivery_capacity', ''))}\n\n"
        "Existing customer countries:\n"
        f"{_clean_long(raw_fields.get('raw_customer_countries', ''))}"
    )
    return OutreachDraftPrompt(system_prompt=system, user_prompt=user)


def build_target_customer_plan_prompt(
    *, locale: str, product_profile_json: str
) -> OutreachDraftPrompt:
    keys = (
        "ideal_buyer_types",
        "target_industries",
        "recommended_countries",
        "search_keywords",
        "negative_keywords",
        "channel_recommendations",
        "buyer_pain_points",
        "match_scoring_rules",
        "first_batch_strategy",
        "disqualification_rules",
    )
    system = (
        "feature: target_customer_plan_generation\n"
        "Create a target customer discovery plan from confirmed product memory only. "
        "Return strict JSON only. Do not claim verified buyers or purchase intent. "
        "Do not include private emails, phone numbers, or personal data. JSON keys must "
        f"be exactly: {', '.join(keys)}."
    )
    if locale == "zh-CN":
        system += " UI language is Simplified Chinese, but JSON keys stay English."
    user = (
        "Confirmed tenant product memory JSON:\n"
        f"{_clean_jsonish(product_profile_json)}\n\n"
        "Suggest buyer types, countries, industries, search keywords, and conservative "
        "matching rules for the first batch of target customer candidates."
    )
    return OutreachDraftPrompt(system_prompt=system, user_prompt=user)


def build_target_customer_candidate_prompt(
    *,
    locale: str,
    product_profile_json: str,
    target_plan_json: str,
    filters: dict[str, object],
    count: int,
) -> OutreachDraftPrompt:
    system = (
        "feature: target_customer_candidate_matching\n"
        "Generate clearly test-safe example B2B target customer candidates. Return strict "
        "JSON only with a top-level candidates array. Do not include private email, phone, "
        "personal data, verified buyer claims, guaranteed purchase intent, or scraped data. "
        "Each candidate must include company_name, country, website, industry, buyer_type, "
        "source_channel, match_reason, confidence_score, and suggested_next_action."
    )
    if locale == "zh-CN":
        system += " UI language is Simplified Chinese, but JSON keys stay English."
    user = (
        f"Requested count: {max(1, min(count, 25))}\n"
        f"Filters JSON: {_clean_jsonish(_json_dumps(filters))}\n\n"
        "Confirmed tenant product memory JSON:\n"
        f"{_clean_jsonish(product_profile_json)}\n\n"
        "Target customer plan JSON:\n"
        f"{_clean_jsonish(target_plan_json)}"
    )
    return OutreachDraftPrompt(system_prompt=system, user_prompt=user)


def _clean(value: str) -> str:
    return (value or "").strip()[:500]


def _clean_long(value: str) -> str:
    return (value or "").strip()[:2000]


def _clean_jsonish(value: str) -> str:
    return (value or "").strip()[:6000]


def _json_dumps(value: dict[str, object]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
