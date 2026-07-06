from __future__ import annotations

import json
import os
import re

import pytest

from app.integrations.ai.base import AIGenerationRequest
from app.integrations.ai.openai_compatible import OpenAICompatibleProvider
from app.integrations.ai.prompts import build_search_intent_query_matrix_prompt

DEFAULT_MIMO_BASE_URL = "https://api.mimo.ai/v1/"
DEFAULT_MIMO_MODEL = "mimo-v2.5-pro"


def _live_mimo_enabled() -> bool:
    return os.environ.get("RUN_LIVE_MIMO") == "1" and bool(os.environ.get("MIMO_API_KEY"))


pytestmark = [
    pytest.mark.live_mimo,
    pytest.mark.skipif(
        not _live_mimo_enabled(),
        reason="set RUN_LIVE_MIMO=1 and MIMO_API_KEY to run optional MiMo live tests",
    ),
]


def test_mimo_connection_live_smoke() -> None:
    provider = _provider()
    result = provider.generate_text(
        AIGenerationRequest(
            system_prompt="Reply with exactly: ok",
            user_prompt="healthcheck",
            locale="en-US",
            max_output_tokens=64,
        )
    )

    content_length = len(result.text or "")
    print(
        "mimo_live_connection "
        f"model={_model()} status={'success' if result.success else result.error_code} "
        f"content_exists={bool(result.text)} content_length={content_length}"
    )

    assert result.success
    assert result.text


def test_search_intent_packaging_and_led_live_smoke() -> None:
    packaging = _generate_search_intent(
        product_profile=_packaging_profile(),
        product_family="packaging",
        forbidden_terms=[
            "LED",
            "lighting",
            "lamp",
            "fixture",
            "electrical wholesaler",
            "contractor lighting",
            "commercial LED",
        ],
    )
    led = _generate_search_intent(
        product_profile=_led_profile(),
        product_family="led_lighting",
        forbidden_terms=[
            "packaging",
            "packaging bags",
            "compostable bags",
            "mailer bags",
            "kraft paper bags",
            "cosmetic packaging",
            "food packaging",
        ],
    )

    packaging_summary = _validate_search_intent(
        packaging,
        expected_terms=("packaging", "bags", "compostable", "kraft", "custom packaging"),
        forbidden_terms=("led", "lighting", "electrical fixture", "commercial led"),
        expected_family="packaging",
    )
    led_summary = _validate_search_intent(
        led,
        expected_terms=("led", "lighting", "fixture", "electrical wholesaler", "contractor"),
        forbidden_terms=("packaging", "mailer", "kraft", "cosmetic packaging"),
        expected_family="led_lighting",
    )

    packaging_family = packaging_summary["detected_product_family"]
    led_family = led_summary["detected_product_family"]
    print(
        "mimo_live_search_intent "
        f"model={_model()} packaging_family={packaging_family} "
        f"packaging_queries={packaging_summary['query_count']} "
        f"packaging_forbidden_hits={packaging_summary['forbidden_hit_count']} "
        f"led_family={led_family} led_queries={led_summary['query_count']} "
        f"led_forbidden_hits={led_summary['forbidden_hit_count']}"
    )

    assert packaging_family != led_family


def _provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url=os.environ.get("MIMO_BASE_URL", DEFAULT_MIMO_BASE_URL),
        model=_model(),
        api_key=os.environ["MIMO_API_KEY"],
        timeout_seconds=45,
    )


def _model() -> str:
    return os.environ.get("MIMO_MODEL", DEFAULT_MIMO_MODEL)


def _generate_search_intent(
    *,
    product_profile: dict[str, object],
    product_family: str,
    forbidden_terms: list[str],
) -> dict[str, object]:
    prompt = build_search_intent_query_matrix_prompt(
        locale="zh-CN",
        product_profile_json=json.dumps(product_profile, ensure_ascii=False, sort_keys=True),
        filters={"country": "", "buyer_type": "", "industry": "", "result_count": 10},
        count=10,
        product_family=product_family,
        forbidden_cross_industry_terms=forbidden_terms,
    )
    result = _provider().generate_text(
        AIGenerationRequest(
            system_prompt=prompt.system_prompt,
            user_prompt=prompt.user_prompt,
            locale="zh-CN",
            max_output_tokens=1800,
        )
    )
    print(
        "mimo_live_generation "
        f"model={_model()} family={product_family} "
        f"status={'success' if result.success else result.error_code} "
        f"content_length={len(result.text or '')}"
    )
    assert result.success
    assert result.text
    return _load_json_object(result.text)


def _validate_search_intent(
    data: dict[str, object],
    *,
    expected_terms: tuple[str, ...],
    forbidden_terms: tuple[str, ...],
    expected_family: str,
) -> dict[str, object]:
    compact = _compact_for_validation(data)
    lower = compact.lower()
    query_rows = data.get("query_matrix", [])
    query_count = len(query_rows) if isinstance(query_rows, list) else 0
    detected_family = _detected_family(data)
    forbidden_hit_count = sum(1 for term in forbidden_terms if term in lower)

    assert query_count > 0
    assert detected_family == expected_family
    assert any(term in lower for term in expected_terms)
    assert forbidden_hit_count == 0
    assert not re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", compact)
    assert not re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", compact)
    assert "verified buyer" not in lower
    assert "purchase intent" not in lower
    assert "linkedin" not in lower
    assert "facebook" not in lower
    assert "whatsapp" not in lower
    assert "telegram" not in lower
    assert "crawl" not in lower
    assert "scrape" not in lower
    assert "automatic email" not in lower
    assert "send email" not in lower
    return {
        "detected_product_family": detected_family,
        "query_count": query_count,
        "forbidden_hit_count": forbidden_hit_count,
    }


def _compact_for_validation(data: dict[str, object]) -> str:
    allowed = {
        "product_context_check": data.get("product_context_check"),
        "product_keywords": data.get("product_keywords"),
        "use_cases": data.get("use_cases"),
        "buyer_company_types": data.get("buyer_company_types"),
        "query_matrix": data.get("query_matrix"),
        "query_self_check": data.get("query_self_check"),
    }
    return json.dumps(allowed, ensure_ascii=False)


def _detected_family(data: dict[str, object]) -> str:
    context = data.get("product_context_check")
    if isinstance(context, dict):
        return str(context.get("detected_product_family") or "")
    return ""


def _load_json_object(text: str) -> dict[str, object]:
    clean = (text or "").strip()
    if clean.startswith("```"):
        clean = clean.removeprefix("```json").removeprefix("```").strip()
        if clean.endswith("```"):
            clean = clean[:-3].strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        assert match is not None
        data = json.loads(match.group(0))
    assert isinstance(data, dict)
    return data


def _packaging_profile() -> dict[str, object]:
    return {
        "product_keywords_en": [
            "eco-friendly custom packaging bags",
            "compostable mailer bags",
            "kraft paper bags",
            "custom printed packaging",
        ],
        "target_industries": ["Packaging", "Retail", "DTC brands"],
        "buyer_types": ["Importer", "Distributor", "Private label brand"],
        "target_countries": ["United States", "Germany", "United Kingdom"],
        "search_keywords": [
            "eco-friendly custom packaging bags importer",
            "compostable mailer bags distributor",
        ],
        "negative_keywords": ["manufacturer", "factory", "supplier"],
    }


def _led_profile() -> dict[str, object]:
    return {
        "product_keywords_en": [
            "LED decorative lighting",
            "commercial LED fixtures",
            "LED strip lights",
        ],
        "target_industries": ["Lighting retail", "Electrical distribution", "Projects"],
        "buyer_types": ["Lighting distributor", "Electrical wholesaler", "Contractor"],
        "target_countries": ["United States", "United Arab Emirates", "Australia"],
        "search_keywords": [
            "LED decorative lighting distributor",
            "commercial LED fixtures electrical wholesaler",
        ],
        "negative_keywords": ["manufacturer", "factory", "supplier"],
    }
