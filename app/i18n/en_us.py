from __future__ import annotations

from app.i18n.zh_cn import TRANSLATIONS as ZH_CN_TRANSLATIONS

TRANSLATIONS = {key: key for key in ZH_CN_TRANSLATIONS}
TRANSLATIONS.update(
    {
        "password_reset_email_body": (
            "Reset your LeadFlow password with this link:\n"
            "{link}\n\n"
            "This link expires in 30 minutes. If you did not request this, ignore this email."
        ),
        "verification_email_body": (
            "Welcome to LeadFlow.\n\n"
            "Verify your email address with this link:\n"
            "{link}\n\n"
            "This link expires in 30 minutes."
        ),
    }
)
