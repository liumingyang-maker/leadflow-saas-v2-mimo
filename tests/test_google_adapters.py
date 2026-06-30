"""Tests for Google Search and Maps adapter integration."""

from __future__ import annotations

import pytest

from app.integrations.collection.adapters import (
    GoogleMapsAdapter,
    GoogleSearchAdapter,
)


class TestGoogleSearchAdapter:
    """GoogleSearchAdapter protocol and input validation."""

    def test_protocol_compliance(self) -> None:
        """GoogleSearchAdapter must have collect method."""
        adapter = GoogleSearchAdapter(api_key="test", cx="test")
        assert hasattr(adapter, "collect")

    def test_empty_query_returns_error(self) -> None:
        adapter = GoogleSearchAdapter(api_key="test", cx="test")
        result = adapter.collect(payload={"query": ""}, max_results=10)
        assert result.error_code == "invalid_input"
        assert result.found_count == 0

    def test_missing_query_returns_error(self) -> None:
        adapter = GoogleSearchAdapter(api_key="test", cx="test")
        result = adapter.collect(payload={}, max_results=10)
        assert result.error_code == "invalid_input"


class TestGoogleMapsAdapter:
    """GoogleMapsAdapter protocol and input validation."""

    def test_protocol_compliance(self) -> None:
        adapter = GoogleMapsAdapter(api_key="test")
        assert hasattr(adapter, "collect")

    def test_empty_query_returns_error(self) -> None:
        adapter = GoogleMapsAdapter(api_key="test")
        result = adapter.collect(payload={"query": "", "location": "NYC"}, max_results=10)
        assert result.error_code == "invalid_input"

    def test_empty_location_returns_error(self) -> None:
        adapter = GoogleMapsAdapter(api_key="test")
        result = adapter.collect(payload={"query": "coffee", "location": ""}, max_results=10)
        assert result.error_code == "invalid_input"

    def test_missing_both_returns_error(self) -> None:
        adapter = GoogleMapsAdapter(api_key="test")
        result = adapter.collect(payload={}, max_results=10)
        assert result.error_code == "invalid_input"


class TestAdapterRegistry:
    """Adapter registry should include real adapters when API keys are set."""

    def test_google_search_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When API key is set, real adapter should be registered."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("GOOGLE_SEARCH_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_SEARCH_CX", "test-cx")
        # Re-import to trigger registration
        import importlib

        import app.modules.jobs.worker as worker_mod

        importlib.reload(worker_mod)
        adapter = worker_mod._get_adapter("google_search")
        assert isinstance(adapter, GoogleSearchAdapter)

    def test_google_maps_registered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When API key is set, real adapter should be registered."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
        import importlib

        import app.modules.jobs.worker as worker_mod

        importlib.reload(worker_mod)
        adapter = worker_mod._get_adapter("google_maps")
        assert isinstance(adapter, GoogleMapsAdapter)
