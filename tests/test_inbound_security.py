from __future__ import annotations


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True

    def get(self, key: str) -> int | None:
        return self.values.get(key)

    def delete(self, key: str) -> int:
        self.values.pop(key, None)
        self.expires.pop(key, None)
        return 1


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


def test_inbound_rate_limit_uses_redis_atomic_counter(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.core import abuse
    from app.modules.inbound import service

    fake = FakeRedis()
    monkeypatch.setattr(abuse.Redis, "from_url", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(service, "RATE_LIMIT_COUNT", 2)

    flask_app = create_app("testing")
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["REDIS_URL"] = "redis://redis:6379/0"

    assert service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="1.2.3.4")
    assert service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="1.2.3.4")
    assert not service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="1.2.3.4")
    assert list(fake.expires.values()) == [service.RATE_LIMIT_WINDOW_SECONDS]


def test_inbound_rate_limit_keys_are_scoped(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.core import abuse
    from app.modules.inbound import service

    fake = FakeRedis()
    monkeypatch.setattr(abuse.Redis, "from_url", lambda *_args, **_kwargs: fake)
    monkeypatch.setattr(service, "RATE_LIMIT_COUNT", 1)

    flask_app = create_app("testing")
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["REDIS_URL"] = "redis://redis:6379/0"

    assert service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="1.2.3.4")
    assert service.check_rate_limit(flask_app, scope="inbound:token-b", bucket="1.2.3.4")
    assert service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="5.6.7.8")
    assert not service.check_rate_limit(flask_app, scope="inbound:token-a", bucket="1.2.3.4")


def test_inbound_api_returns_429_when_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("INBOUND_TOKEN_KEY", "test-inbound-token-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests
    from app.modules.inbound import service

    monkeypatch.setattr(service, "RATE_LIMIT_COUNT", 1)
    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    _token, plaintext = service.generate_token(flask_app, tenant_id="tenant-1")

    client = flask_app.test_client()
    first = client.post(f"/api/inbound/{plaintext}", json={"email": "lead@example.com"})
    second = client.post(f"/api/inbound/{plaintext}", json={"email": "other@example.com"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.get_json() == {"error": "rate_limited"}
