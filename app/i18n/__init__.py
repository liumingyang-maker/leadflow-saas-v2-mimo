from __future__ import annotations

import logging
from collections.abc import Mapping
from urllib.parse import urlsplit

from flask import Flask, Response, g, has_request_context, redirect, request, url_for

from app.i18n.en_us import TRANSLATIONS as EN_US
from app.i18n.zh_cn import TRANSLATIONS as ZH_CN

DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = ("zh-CN", "en-US")
LOCALE_COOKIE_NAME = "lang"
LOCALE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
LOCALE_LABELS = {"zh-CN": "中文", "en-US": "EN"}

_TRANSLATIONS: Mapping[str, Mapping[str, str]] = {
    "zh-CN": ZH_CN,
    "en-US": EN_US,
}
_LOGGER = logging.getLogger(__name__)


def register_i18n(app: Flask) -> None:
    app.jinja_env.globals.update(
        t=translate,
        get_locale=get_locale,
        supported_locales=SUPPORTED_LOCALES,
        locale_labels=LOCALE_LABELS,
    )

    @app.before_request
    def resolve_request_locale() -> None:
        g.locale = resolve_locale()

    @app.context_processor
    def inject_i18n() -> dict[str, object]:
        current_locale = get_locale()
        return {
            "t": translate,
            "locale": current_locale,
            "supported_locales": SUPPORTED_LOCALES,
            "locale_labels": LOCALE_LABELS,
        }

    @app.get("/locale/<locale>")
    def switch_locale(locale: str):
        if locale not in SUPPORTED_LOCALES:
            locale = DEFAULT_LOCALE
        target = _safe_redirect_target(
            request.args.get("next", ""),
            request.referrer or "",
        )
        response = redirect(target)
        _set_locale_cookie(response, locale)
        return response


def translate(key: str, **kwargs: object) -> str:
    value = _TRANSLATIONS.get(get_locale(), {}).get(key)
    if value is None:
        _LOGGER.warning("Missing translation key: %s", key)
        value = key
    if kwargs:
        try:
            return value.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            _LOGGER.warning("Invalid translation interpolation for key: %s", key)
            return value
    return value


def get_locale() -> str:
    if not has_request_context():
        return DEFAULT_LOCALE
    return getattr(g, "locale", DEFAULT_LOCALE)


def resolve_locale() -> str:
    cookie_locale = request.cookies.get(LOCALE_COOKIE_NAME, "")
    if cookie_locale in SUPPORTED_LOCALES:
        return cookie_locale
    accepted = request.accept_languages.best_match(SUPPORTED_LOCALES)
    if accepted in SUPPORTED_LOCALES:
        return accepted
    return DEFAULT_LOCALE


def localized_email_text(key: str, locale: str | None = None, **kwargs: object) -> str:
    selected_locale = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    value = _TRANSLATIONS.get(selected_locale, {}).get(key)
    if value is None:
        _LOGGER.warning("Missing email translation key: %s", key)
        value = key
    if kwargs:
        return value.format(**kwargs)
    return value


def _safe_redirect_target(*candidates: str) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        parsed = urlsplit(candidate)
        if parsed.scheme or parsed.netloc:
            current_host = request.host
            if parsed.scheme in {"http", "https"} and parsed.netloc == current_host:
                path = parsed.path or "/"
                query = f"?{parsed.query}" if parsed.query else ""
                return f"{path}{query}"
            continue
        if candidate.startswith("/") and not candidate.startswith("//"):
            return candidate
    return url_for("login")


def _set_locale_cookie(response: Response, locale: str) -> None:
    response.set_cookie(
        LOCALE_COOKIE_NAME,
        locale,
        max_age=LOCALE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        path="/",
    )
