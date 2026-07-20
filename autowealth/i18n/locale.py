"""Stable locale selection for deterministic research reports."""

from __future__ import annotations

from typing import Any, Literal, cast

from autowealth.i18n.catalogs import CATALOGS, PERSISTED_CATALOGS


SupportedLocale = Literal["zh-CN", "en-US"]
SUPPORTED_LOCALES: tuple[SupportedLocale, ...] = ("zh-CN", "en-US")
DEFAULT_REPORT_LOCALE: SupportedLocale = "en-US"


def ensure_supported_locale(locale: str) -> SupportedLocale:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError(f"unsupported locale: {locale}")
    return cast(SupportedLocale, locale)


def message(locale: SupportedLocale, key: str, **values: Any) -> str:
    template = CATALOGS[locale][key]
    return template.format(**values)


def present_persisted_text(text: str, locale: SupportedLocale) -> str:
    """Localize known persisted prose while retaining unknown source text."""
    if locale == "en-US":
        return text
    translated = PERSISTED_CATALOGS[locale].get(text)
    if translated is not None:
        return translated
    return message(locale, "persisted_unknown", source=text)
