"""Opt-in live MiMo web-search smoke test with deliberately bounded output."""

from __future__ import annotations

import os

from openai import OpenAI

from app.integrations.ai.contracts import CountryResearchPlan
from app.integrations.ai.mimo import MiMoProvider, ProviderError


def main() -> int:
    key = os.environ.get("MIMO_API_KEY", "").strip()
    base_url = os.environ.get("MIMO_BASE_URL", "").strip()
    model = os.environ.get("MIMO_MODEL", "mimo-v2.5")
    if not key or not base_url:
        print("FAIL provider_auth_or_quota")
        return 1

    client = OpenAI(api_key=key, base_url=base_url, timeout=60.0, max_retries=0)
    provider = MiMoProvider(client=client, model=model)
    plan = CountryResearchPlan(
        country_code="MX",
        languages=["es"],
        queries=["distribuidores de motores para motocicletas México"],
        include_terms=["motor", "distribuidor"],
        exclude_terms=["solo eléctrico"],
    )
    try:
        hits = provider.discover_companies(country_plan=plan)
    except ProviderError as exc:
        if exc.code == "provider_capability_missing":
            print("FAIL provider_capability_missing")
        elif exc.code in {"auth", "quota", "provider_not_configured"}:
            print("FAIL provider_auth_or_quota")
        else:
            print("FAIL provider_transient")
        return 1
    if hits and any(str(hit.url).startswith("https://") for hit in hits):
        print("PASS web_search")
        return 0
    print("FAIL provider_transient")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
