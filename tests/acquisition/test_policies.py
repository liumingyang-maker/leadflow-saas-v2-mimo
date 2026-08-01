from __future__ import annotations

import pytest


def test_invalid_acquisition_budget_fails_closed(monkeypatch):
    monkeypatch.setenv("ACQUISITION_MAX_CANDIDATES", "0")
    from app.config import resolve_config

    with pytest.raises(RuntimeError, match="ACQUISITION_MAX_CANDIDATES"):
        resolve_config("development")


def test_non_integer_acquisition_budget_fails_closed(monkeypatch):
    monkeypatch.setenv("ACQUISITION_MAX_VERIFY", "many")
    from app.config import resolve_config

    with pytest.raises(RuntimeError, match="ACQUISITION_MAX_VERIFY must be an integer"):
        resolve_config("development")


def test_acquisition_budget_defaults_are_bounded(monkeypatch):
    for name in (
        "ACQUISITION_MAX_CANDIDATES",
        "ACQUISITION_MAX_VERIFY",
        "ACQUISITION_MAX_SEARCH_ACTIONS",
        "FETCH_MAX_PAGES_PER_SITE",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.config import resolve_config

    config = resolve_config("testing")
    assert config.ACQUISITION_MAX_CANDIDATES == 30
    assert config.ACQUISITION_MAX_VERIFY == 10
    assert config.ACQUISITION_MAX_SEARCH_ACTIONS == 5
    assert config.FETCH_MAX_PAGES_PER_SITE == 5
