from __future__ import annotations


def test_testing_inbound_token_key_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("INBOUND_TOKEN_KEY", "test-inbound-token-key-that-is-long-enough")

    import app.config as cfg
    from app import create_app

    monkeypatch.setattr(
        cfg.TestingConfig, "INBOUND_TOKEN_KEY", "test-inbound-token-key-that-is-long-enough"
    )

    flask_app = create_app("testing")

    assert flask_app.config["INBOUND_TOKEN_KEY"] == "test-inbound-token-key-that-is-long-enough"
