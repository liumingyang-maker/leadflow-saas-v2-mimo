"""Tests for SMTP mailer adapter."""

from __future__ import annotations

import pytest

from app.modules.outreach.mailer import (
    FakeMailer,
    NotConfiguredMailer,
    SmtpMailer,
    get_mailer,
)


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
