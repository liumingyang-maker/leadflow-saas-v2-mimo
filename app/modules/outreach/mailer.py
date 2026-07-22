"""Mailer adapters — fake mailer with environment boundary."""

from __future__ import annotations

import os
import uuid
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


def get_mailer() -> Mailer:
    if _is_allowed_env():
        return FakeMailer()
    return NotConfiguredMailer()
