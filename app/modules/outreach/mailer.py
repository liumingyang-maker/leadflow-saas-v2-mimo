"""Mailer adapters — fake, SMTP, and environment boundary."""

from __future__ import annotations

import os
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol


class MailerResult:
    def __init__(
        self,
        *,
        success: bool,
        provider_message_id: str = "",
        error_code: str = "",
        error_summary: str = "",
    ) -> None:
        self.success = success
        self.provider_message_id = provider_message_id
        self.error_code = error_code
        self.error_summary = error_summary


class Mailer(Protocol):
    def send(
        self, *, to_email: str, subject: str, body_text: str, body_html: str
    ) -> MailerResult: ...


def _is_allowed_env() -> bool:
    env = os.environ.get("APP_ENV", "development").lower()
    return env in ("development", "dev", "testing", "test")


class FakeMailer:
    """Fake mailer for development/testing — never sends real email."""

    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str) -> MailerResult:
        msg_id = f"fake_msg_{uuid.uuid4().hex}"
        return MailerResult(success=True, provider_message_id=msg_id)


class NotConfiguredMailer:
    """Production/staging mailer when no real provider configured."""

    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str) -> MailerResult:
        return MailerResult(
            success=False,
            error_code="mailer_not_configured",
            error_summary="Email sending is not configured",
        )


class SmtpMailer:
    """Real SMTP mailer — sends email via SMTP, STARTTLS, or implicit SSL."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> None:
        if use_tls and use_ssl:
            raise ValueError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be true")
        implicit_ssl = port == 465
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email
        self._use_tls = False if implicit_ssl else use_tls
        self._use_ssl = use_ssl or implicit_ssl

    def send(self, *, to_email: str, subject: str, body_text: str, body_html: str) -> MailerResult:
        msg = MIMEMultipart("alternative")
        msg["From"] = self._from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        try:
            smtp_client = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
            with smtp_client(self._host, self._port, timeout=30) as server:
                if self._use_tls:
                    server.starttls()
                server.login(self._user, self._password)
                server.send_message(msg)
            msg_id = f"smtp_{uuid.uuid4().hex}"
            return MailerResult(success=True, provider_message_id=msg_id)
        except smtplib.SMTPAuthenticationError:
            return MailerResult(
                success=False,
                error_code="smtp_auth_failed",
                error_summary="SMTP authentication failed",
            )
        except smtplib.SMTPException:
            return MailerResult(
                success=False,
                error_code="smtp_error",
                error_summary="Failed to send email via SMTP",
            )
        except (OSError, TimeoutError):
            return MailerResult(
                success=False,
                error_code="smtp_connection_error",
                error_summary="Could not connect to SMTP server",
            )


def _smtp_is_configured() -> bool:
    return bool(os.environ.get("SMTP_HOST"))


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _smtp_mailer_from_env() -> SmtpMailer:
    use_tls = _env_bool("SMTP_USE_TLS", "true")
    use_ssl = _env_bool("SMTP_USE_SSL", "false")
    return SmtpMailer(
        host=os.environ["SMTP_HOST"],
        port=int(os.environ.get("SMTP_PORT", "587")),
        user=os.environ.get("SMTP_USER", ""),
        password=os.environ.get("SMTP_PASSWORD", ""),
        from_email=os.environ.get("SMTP_FROM", ""),
        use_tls=use_tls,
        use_ssl=use_ssl,
    )


def get_mailer() -> Mailer:
    if _is_allowed_env():
        if _smtp_is_configured():
            return _smtp_mailer_from_env()
        return FakeMailer()
    # Production/staging: require SMTP config
    if _smtp_is_configured():
        return _smtp_mailer_from_env()
    return NotConfiguredMailer()
