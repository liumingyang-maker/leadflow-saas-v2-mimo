"""Tests for SMTP mailer adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.modules.outreach.mailer as mailer_module
from app.modules.outreach.mailer import (
    FakeMailer,
    NotConfiguredMailer,
    SmtpMailer,
    get_mailer,
)

ROOT = Path(__file__).resolve().parents[1]


class RecordingSmtp:
    created: list[tuple[str, int, int]] = []
    instances: list[RecordingSmtp] = []

    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.logged_in = False
        self.sent = False
        self.created.append((host, port, timeout))
        self.instances.append(self)

    def __enter__(self) -> RecordingSmtp:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = bool(user and password)

    def send_message(self, msg: object) -> None:
        self.sent = msg is not None


class RecordingSmtpSsl(RecordingSmtp):
    created: list[tuple[str, int, int]] = []
    instances: list[RecordingSmtpSsl] = []


def _reset_recorders() -> None:
    RecordingSmtp.created = []
    RecordingSmtp.instances = []
    RecordingSmtpSsl.created = []
    RecordingSmtpSsl.instances = []


class TestSmtpMailerProtocol:
    """SmtpMailer must implement the Mailer protocol."""

    def test_has_send_method(self) -> None:
        assert hasattr(SmtpMailer, "send")

    def test_instantiation(self) -> None:
        mailer = SmtpMailer(
            host="smtp.example.com",
            port=587,
            user="user",
            password="pass",
            from_email="from@example.com",
        )
        assert mailer is not None


class TestSmtpMailerSend:
    """SmtpMailer.send should handle connection errors gracefully."""

    def test_connection_error_returns_failure(self) -> None:
        mailer = SmtpMailer(
            host="invalid.host.example",
            port=587,
            user="user",
            password="pass",
            from_email="from@example.com",
            use_tls=False,
        )
        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )
        assert not result.success
        assert result.error_code in ("smtp_connection_error", "smtp_error")

    def test_error_never_leaks_credentials(self) -> None:
        password = "super-secret-password-12345"
        mailer = SmtpMailer(
            host="invalid.host.example",
            port=587,
            user="user",
            password=password,
            from_email="from@example.com",
            use_tls=False,
        )
        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )
        assert password not in result.error_summary
        assert password not in result.error_code

    def test_smtp_ssl_path_uses_smtp_ssl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_recorders()
        monkeypatch.setattr(mailer_module.smtplib, "SMTP", RecordingSmtp)
        monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", RecordingSmtpSsl)
        mailer = SmtpMailer(
            host="smtpdm.aliyun.com",
            port=465,
            user="sender@example.com",
            password="redacted-test-password",
            from_email="sender@example.com",
            use_tls=False,
            use_ssl=True,
        )

        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )

        assert result.success
        assert RecordingSmtp.created == []
        assert RecordingSmtpSsl.created == [("smtpdm.aliyun.com", 465, 30)]
        assert RecordingSmtpSsl.instances[0].started_tls is False
        assert RecordingSmtpSsl.instances[0].sent is True

    def test_port_465_uses_smtp_ssl_without_starttls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_recorders()
        monkeypatch.setattr(mailer_module.smtplib, "SMTP", RecordingSmtp)
        monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", RecordingSmtpSsl)
        mailer = SmtpMailer(
            host="smtpdm.aliyun.com",
            port=465,
            user="sender@example.com",
            password="redacted-test-password",
            from_email="sender@example.com",
        )

        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )

        assert result.success
        assert RecordingSmtp.created == []
        assert RecordingSmtpSsl.created == [("smtpdm.aliyun.com", 465, 30)]
        assert RecordingSmtpSsl.instances[0].started_tls is False

    def test_starttls_path_uses_smtp_and_starttls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_recorders()
        monkeypatch.setattr(mailer_module.smtplib, "SMTP", RecordingSmtp)
        monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", RecordingSmtpSsl)
        mailer = SmtpMailer(
            host="smtp.example.com",
            port=587,
            user="user",
            password="redacted-test-password",
            from_email="from@example.com",
            use_tls=True,
            use_ssl=False,
        )

        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )

        assert result.success
        assert RecordingSmtp.created == [("smtp.example.com", 587, 30)]
        assert RecordingSmtpSsl.created == []
        assert RecordingSmtp.instances[0].started_tls is True

    def test_plain_smtp_path_does_not_starttls(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _reset_recorders()
        monkeypatch.setattr(mailer_module.smtplib, "SMTP", RecordingSmtp)
        monkeypatch.setattr(mailer_module.smtplib, "SMTP_SSL", RecordingSmtpSsl)
        mailer = SmtpMailer(
            host="smtp.example.com",
            port=25,
            user="user",
            password="redacted-test-password",
            from_email="from@example.com",
            use_tls=False,
            use_ssl=False,
        )

        result = mailer.send(
            to_email="to@example.com",
            subject="Test",
            body_text="Hello",
            body_html="",
        )

        assert result.success
        assert RecordingSmtp.created == [("smtp.example.com", 25, 30)]
        assert RecordingSmtpSsl.created == []
        assert RecordingSmtp.instances[0].started_tls is False

    def test_tls_and_ssl_combination_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="SMTP_USE_TLS and SMTP_USE_SSL"):
            SmtpMailer(
                host="smtp.example.com",
                port=465,
                user="user",
                password="redacted-test-password",
                from_email="from@example.com",
                use_tls=True,
                use_ssl=True,
            )


class TestGetMailerFactory:
    """get_mailer() should return the right mailer based on env."""

    def test_dev_returns_fake(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("SMTP_HOST", raising=False)
        mailer = get_mailer()
        assert isinstance(mailer, FakeMailer)

    def test_dev_with_smtp_returns_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("SMTP_FROM", "from@example.com")
        mailer = get_mailer()
        assert isinstance(mailer, SmtpMailer)

    def test_prod_no_smtp_returns_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("SMTP_HOST", raising=False)
        mailer = get_mailer()
        assert isinstance(mailer, NotConfiguredMailer)

    def test_prod_with_smtp_returns_smtp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USER", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("SMTP_FROM", "from@example.com")
        mailer = get_mailer()
        assert isinstance(mailer, SmtpMailer)

    def test_aliyun_style_env_enables_smtp_ssl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SMTP_HOST", "smtpdm.aliyun.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "sender@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "redacted-test-password")
        monkeypatch.setenv("SMTP_FROM", "sender@example.com")
        monkeypatch.setenv("SMTP_USE_TLS", "false")
        monkeypatch.setenv("SMTP_USE_SSL", "true")

        mailer = get_mailer()

        assert isinstance(mailer, SmtpMailer)
        assert mailer._use_tls is False
        assert mailer._use_ssl is True


def test_aliyun_directmail_config_is_documented_without_real_password() -> None:
    docs = (ROOT / "docs" / "SECRETS_AND_ENVIRONMENT.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "smtpdm.aliyun.com" in docs
    assert "SMTP_USE_SSL=true" in docs
    assert "SMTP_USE_SSL=false" in env_example
    assert "DirectMail SMTP password" not in docs
    assert "DirectMail SMTP password" not in env_example
