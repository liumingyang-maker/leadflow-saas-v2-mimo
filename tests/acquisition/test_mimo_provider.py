from __future__ import annotations

from types import SimpleNamespace

import pytest


class FakeResponses:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeOpenAI:
    def __init__(self, output_text: str) -> None:
        self.responses = FakeResponses(output_text)


def test_mimo_planner_returns_one_run_per_country():
    from app.integrations.ai.mimo import MiMoProvider

    client = FakeOpenAI(
        '{"plan_version":"mission-plan-v1","country_runs":['
        '{"country_code":"MX","languages":["es"],"queries":["motores distribuidores"],'
        '"include_terms":["motor"],"exclude_terms":["solo electrico"]}]}'
    )
    plan = MiMoProvider(client=client, model="mimo-v2.5").plan_mission(
        product_summary="motorcycle engines",
        target_profile={"country_codes": ["MX"], "buyer_types": ["distributor"]},
    )
    assert [run.country_code for run in plan.country_runs] == ["MX"]
    assert client.responses.calls[0]["timeout"] == 60


def test_invalid_provider_json_is_safe_error():
    from app.integrations.ai.mimo import MiMoProvider, ProviderResponseError

    provider = MiMoProvider(client=FakeOpenAI('{"country_runs":[]}'), model="mimo-v2.5")
    with pytest.raises(ProviderResponseError, match="invalid_response") as caught:
        provider.plan_mission(
            product_summary="motorcycle engines",
            target_profile={"country_codes": ["MX"], "buyer_types": ["distributor"]},
        )
    assert "country_runs" not in str(caught.value)


def test_planner_rejects_missing_or_duplicate_country_runs():
    from app.integrations.ai.mimo import MiMoProvider, ProviderResponseError

    client = FakeOpenAI(
        '{"plan_version":"mission-plan-v1","country_runs":['
        '{"country_code":"MX","languages":["es"],"queries":["one"]},'
        '{"country_code":"MX","languages":["es"],"queries":["two"]}]}'
    )
    with pytest.raises(ProviderResponseError):
        MiMoProvider(client=client, model="mimo-v2.5").plan_mission(
            product_summary="engines",
            target_profile={"country_codes": ["MX", "CO"]},
        )


def test_mimo_extracts_only_validated_company_facts():
    from app.integrations.ai.mimo import MiMoProvider

    client = FakeOpenAI(
        '{"company_name":"Motores MX","canonical_domain":"motores.mx",'
        '"hq_country_code":"MX","opportunity_country_code":"MX",'
        '"buyer_type":"distributor","product_terms":["engine"],'
        '"contact_paths":["https://motores.mx/contact"],'
        '"observed_claims":[{"claim_id":"claim-1","text":"Sells motorcycle engines",'
        '"source_url":"https://motores.mx/products"}],"inferences":[],"unknowns":[]}'
    )
    snapshot = SimpleNamespace(
        final_url="https://motores.mx/products", title="Products", text="engines"
    )
    result = MiMoProvider(client=client, model="mimo-v2.5").extract(snapshot)
    assert result.company_name == "Motores MX"
    assert str(result.observed_claims[0].source_url) == "https://motores.mx/products"


def test_mimo_rejects_observed_claim_citing_an_unsupplied_url():
    from app.integrations.ai.mimo import MiMoProvider, ProviderResponseError

    client = FakeOpenAI(
        '{"company_name":"Motores MX","canonical_domain":"motores.mx",'
        '"observed_claims":[{"claim_id":"claim-1","text":"Invented",'
        '"source_url":"https://untrusted.example/claim"}]}'
    )
    snapshot = SimpleNamespace(
        final_url="https://motores.mx/products", title="Products", text="engines"
    )
    with pytest.raises(ProviderResponseError):
        MiMoProvider(client=client, model="mimo-v2.5").extract(snapshot)


def test_mimo_discovery_reports_missing_web_search_capability():
    from app.integrations.ai.contracts import CountryResearchPlan
    from app.integrations.ai.mimo import MiMoProvider, ProviderError

    client = FakeOpenAI('{"error":"web search unavailable"}')
    provider = MiMoProvider(client=client, model="mimo-v2.5", web_search_enabled=False)
    country_plan = CountryResearchPlan(
        country_code="MX", languages=["es"], queries=["motores distribuidores"]
    )
    with pytest.raises(ProviderError) as caught:
        provider.discover_companies(country_plan=country_plan)
    assert caught.value.code == "provider_capability_missing"
    assert caught.value.retryable is False


def test_official_chat_completion_path_enables_bounded_web_search():
    from app.integrations.ai.contracts import CountryResearchPlan
    from app.integrations.ai.mimo import MiMoProvider

    class FakeCompletions:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            message = SimpleNamespace(
                content=(
                    '{"search_hits":[{"url":"https://example.com/company",'
                    '"title":"Example","excerpt":"Distributor","query":"dealer"}]}'
                )
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    country_plan = CountryResearchPlan(country_code="MX", languages=["es"], queries=["dealer"])
    hits = MiMoProvider(client=client, model="mimo-v2.5").discover_companies(
        country_plan=country_plan
    )
    call = completions.calls[0]
    assert str(hits[0].url) == "https://example.com/company"
    assert call["response_format"] == {"type": "json_object"}
    assert call["tools"][0] == {
        "type": "web_search",
        "max_keyword": 3,
        "force_search": True,
        "limit": 10,
    }


def test_transient_provider_failure_retries_once_and_hides_detail():
    from app.integrations.ai.mimo import MiMoProvider, ProviderError

    secret_detail = "response-body-with-secret"

    class FailingResponses:
        def __init__(self) -> None:
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            raise TimeoutError(secret_detail)

    client = SimpleNamespace(responses=FailingResponses())
    provider = MiMoProvider(client=client, model="mimo-v2.5")
    with pytest.raises(ProviderError) as caught:
        provider.plan_mission(product_summary="engines", target_profile={"country_codes": ["MX"]})
    assert caught.value.code == "timeout"
    assert caught.value.retryable is True
    assert secret_detail not in str(caught.value)
    assert client.responses.calls == 2
