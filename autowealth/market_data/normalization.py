from __future__ import annotations

import re
from typing import Optional, Sequence, Tuple, Union

from .schemas import EODBar, Venue

_RAW_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}$")
_CANONICAL_SYMBOL_PATTERN = re.compile(r"^([0-9]{6})\.(SH|SZ)$", re.IGNORECASE)
_VENUE_SUFFIX = {
    Venue.SSE: "SH",
    Venue.SZSE: "SZ",
}


def _coerce_venue(value: Union[Venue, str]) -> Venue:
    if isinstance(value, Venue):
        return value
    if type(value) is str:
        try:
            return Venue(value)
        except ValueError as exc:
            raise ValueError("venue must be sse or szse") from exc
    raise TypeError("venue must be Venue or str")


def normalize_canonical_symbol(
    symbol: str,
    venue: Optional[Union[Venue, str]] = None,
) -> str:
    """Normalize a six-digit A-share symbol to the canonical suffix form."""

    if type(symbol) is not str:
        raise TypeError("symbol must be str")
    if not symbol or symbol != symbol.strip() or any(character.isspace() for character in symbol):
        raise ValueError("symbol must not be empty or contain whitespace")

    normalized_venue = _coerce_venue(venue) if venue is not None else None
    canonical_match = _CANONICAL_SYMBOL_PATTERN.fullmatch(symbol)
    if canonical_match is not None:
        code, suffix = canonical_match.groups()
        normalized_suffix = suffix.upper()
        if normalized_venue is not None and _VENUE_SUFFIX[normalized_venue] != normalized_suffix:
            raise ValueError("symbol suffix conflicts with venue")
        return f"{code}.{normalized_suffix}"

    if _RAW_SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError("symbol must be six digits with an optional SH or SZ suffix")
    if normalized_venue is None:
        raise ValueError("venue is required for a symbol without a market suffix")
    return f"{symbol}.{_VENUE_SUFFIX[normalized_venue]}"


def normalize_eod_bars(bars: Sequence[EODBar]) -> Tuple[EODBar, ...]:
    """Return bars in deterministic dataset/date order without deduplication."""

    if type(bars) not in (list, tuple):
        raise TypeError("bars must be an exact list or exact tuple")
    normalized_bars = tuple(bars)
    if any(type(bar) is not EODBar for bar in normalized_bars):
        raise TypeError("bars must contain exact EODBar values")
    return tuple(
        sorted(
            normalized_bars,
            key=lambda bar: (*bar.dataset.identity, bar.trade_date.isoformat()),
        )
    )
