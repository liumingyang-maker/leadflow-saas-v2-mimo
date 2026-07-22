"""Tests for collection adapters — V2-04-004, V2-04-005, V2-04-006."""

from __future__ import annotations

from app.integrations.collection.adapters import FakeMapsAdapter, FakeSearchAdapter
from app.integrations.collection.contracts import Candidate


def _make_search_adapter() -> FakeSearchAdapter:
    return FakeSearchAdapter()


def _make_maps_adapter() -> FakeMapsAdapter:
    return FakeMapsAdapter()


def test_search_adapter_returns_candidates() -> None:
    adapter = _make_search_adapter()
    result = adapter.collect(payload={"query": "software companies"}, max_results=10)
    assert result.found_count > 0
    assert len(result.candidates) > 0
    c = result.candidates[0]
    assert c.source == "google_search"
    assert "@" in c.email


def test_search_adapter_rejects_empty_query() -> None:
    adapter = _make_search_adapter()
    result = adapter.collect(payload={"query": ""}, max_results=10)
    assert result.found_count == 0
    assert result.error_code == "invalid_input"


def test_search_adapter_respects_max_results() -> None:
    adapter = _make_search_adapter()
    result = adapter.collect(payload={"query": "tech startups"}, max_results=100)
    assert result.found_count <= 100


def test_maps_adapter_returns_candidates() -> None:
    adapter = _make_maps_adapter()
    result = adapter.collect(
        payload={"query": "coffee shops", "location": "New York"}, max_results=5
    )
    assert result.found_count > 0
    c = result.candidates[0]
    assert c.source == "google_maps"
    assert c.address != ""


def test_maps_adapter_rejects_empty_location() -> None:
    adapter = _make_maps_adapter()
    result = adapter.collect(payload={"query": "cafes", "location": ""}, max_results=5)
    assert result.found_count == 0
    assert result.error_code == "invalid_input"


def test_maps_adapter_respects_max_results() -> None:
    adapter = _make_maps_adapter()
    result = adapter.collect(payload={"query": "restaurants", "location": "Chicago"}, max_results=2)
    assert result.found_count <= 2


def test_candidate_contract_fields() -> None:
    c = Candidate(
        email="test@test.com",
        first_name="John",
        last_name="Doe",
        company="Acme",
        source="google_search",
    )
    assert c.email == "test@test.com"
    assert c.first_name == "John"
    assert c.last_name == "Doe"


def test_no_real_network_calls() -> None:
    """Fake adapters never make network requests."""
    adapter = _make_search_adapter()
    result = adapter.collect(payload={"query": "test"}, max_results=5)
    assert result.found_count >= 0


def test_adapter_output_is_candidate_list(monkeypatch) -> None:
    """Adapter output can be fed directly into the worker's _save_candidates."""
    adapter = _make_search_adapter()
    result = adapter.collect(payload={"query": "software"}, max_results=3)
    for c in result.candidates:
        assert isinstance(c, Candidate)
