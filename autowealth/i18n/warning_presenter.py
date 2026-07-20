"""Derived warning labels that never replace persisted warning text."""

from __future__ import annotations

from autowealth.i18n.catalogs import (
    WARNING_CATEGORY_LABEL_CATALOGS,
    WARNING_CATEGORY_MESSAGE_CATALOGS,
)
from autowealth.i18n.locale import SupportedLocale
from autowealth.research.run_store import categorize_warning


def present_warnings(
    warnings: list[str],
    locale: SupportedLocale,
) -> list[dict[str, str]]:
    presentations: list[dict[str, str]] = []
    for source_message in warnings:
        category = categorize_warning(source_message)
        display_message = (
            source_message
            if locale == "en-US"
            else WARNING_CATEGORY_MESSAGE_CATALOGS[locale][category]
        )
        presentations.append(
            {
                "source_message": source_message,
                "display_message": display_message,
                "category": category,
                "category_label": WARNING_CATEGORY_LABEL_CATALOGS[locale][
                    category
                ],
            }
        )
    return presentations
