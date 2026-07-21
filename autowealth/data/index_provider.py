"""A-share index providers with canonical benchmark symbols."""

from __future__ import annotations

import re
from typing import Optional, Protocol, runtime_checkable

import pandas as pd

from autowealth.data.schema import normalize_date, normalize_market_data

CANONICAL_INDEX_SYMBOLS = (
    "000300",
    "000905",
    "000852",
    "000001",
    "399001",
    "399006",
)

_INDEX_ALIASES = {
    "沪深300": "000300",
    "中证500": "000905",
    "中证1000": "000852",
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    **{symbol: symbol for symbol in CANONICAL_INDEX_SYMBOLS},
}


class UnsupportedIndexSymbolError(ValueError):
    """Raised when a benchmark cannot be mapped to a canonical symbol."""

    reason_code = "unsupported_symbol"


class UnsupportedIndexEndpointError(RuntimeError):
    """Raised when the installed data-source module lacks an adapter endpoint."""


@runtime_checkable
class IndexDataProvider(Protocol):
    """Read-only protocol for normalized benchmark daily bars."""

    def get_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame: ...


def canonical_index_symbol(value: str) -> str:
    """Resolve a supported name or code to the stable six-digit symbol."""
    key = re.sub(r"\s+", "", str(value).strip()).upper()
    if key.startswith(("SH", "SZ")) and len(key) == 8:
        key = key[2:]
    if key.endswith((".SH", ".SS", ".SZ")):
        key = key.split(".", maxsplit=1)[0]
    try:
        return _INDEX_ALIASES[key]
    except KeyError as exc:
        supported = ", ".join(CANONICAL_INDEX_SYMBOLS)
        raise UnsupportedIndexSymbolError(
            f"unsupported A-share index {value!r}; canonical symbols: {supported}"
        ) from exc


def exchange_prefixed_index_symbol(value: str) -> str:
    """Convert a canonical symbol to the sh/sz form used by some endpoints."""
    symbol = canonical_index_symbol(value)
    prefix = "sz" if symbol.startswith("399") else "sh"
    return f"{prefix}{symbol}"


class AShareIndexProvider:
    """Primary AKShare adapter backed by ``index_zh_a_hist``.

    AKShare is imported only when ``get_daily`` is explicitly called. Existing
    callers can continue passing supported names or canonical codes.
    """

    provider_name = "AShareIndexProvider"
    endpoint = "index_zh_a_hist"

    INDEX_SYMBOLS = {
        "上证指数": "000001",
        "深证成指": "399001",
        "沪深300": "000300",
        "沪深 300": "000300",
        "中证500": "000905",
        "中证 500": "000905",
        "中证1000": "000852",
        "中证 1000": "000852",
        "创业板指": "399006",
        "000001": "000001",
        "399001": "399001",
        "000300": "000300",
        "000905": "000905",
        "000852": "000852",
        "399006": "399006",
    }

    def __init__(self, akshare_module: Optional[object] = None):
        self.ak = akshare_module

    def get_daily(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        *,
        index: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily historical data for a supported A 股 index.

        ``symbol`` is the protocol parameter. ``index`` remains as a keyword-only
        compatibility alias for callers of the original adapter.
        """
        requested_symbol, requested_start, requested_end = _index_request_arguments(
            symbol,
            start_date,
            end_date,
            index=index,
        )
        canonical = self.resolve_symbol(requested_symbol)
        raw = self._endpoint()(
            symbol=canonical,
            period="daily",
            start_date=normalize_date(requested_start),
            end_date=normalize_date(requested_end),
        )
        return normalize_market_data(raw)

    def provider_symbol(self, symbol: str) -> str:
        return canonical_index_symbol(symbol)

    @classmethod
    def resolve_symbol(cls, index: str) -> str:
        return canonical_index_symbol(index)

    def _endpoint(self):
        module = self._akshare()
        endpoint = getattr(module, self.endpoint, None)
        if not callable(endpoint):
            raise UnsupportedIndexEndpointError(f"AKShare endpoint {self.endpoint} is unavailable")
        return endpoint

    def _akshare(self):
        if self.ak is None:
            try:
                import akshare as ak
            except ImportError as exc:
                raise ImportError(
                    "AShareIndexProvider requires akshare: pip install akshare"
                ) from exc
            self.ak = ak
        return self.ak


class AKShareIndexDailyProvider(AShareIndexProvider):
    """Fallback AKShare adapter backed by ``stock_zh_index_daily``."""

    provider_name = "AKShareIndexDailyProvider"
    endpoint = "stock_zh_index_daily"

    def get_daily(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        *,
        index: Optional[str] = None,
    ) -> pd.DataFrame:
        requested_symbol, requested_start, requested_end = _index_request_arguments(
            symbol,
            start_date,
            end_date,
            index=index,
        )
        canonical = self.resolve_symbol(requested_symbol)
        raw = self._endpoint()(symbol=self.provider_symbol(canonical))
        normalized = normalize_market_data(raw)
        start = pd.Timestamp(requested_start)
        end = pd.Timestamp(requested_end)
        return normalized[normalized["date"].between(start, end, inclusive="both")].reset_index(
            drop=True
        )

    def provider_symbol(self, symbol: str) -> str:
        return exchange_prefixed_index_symbol(symbol)


def _index_request_arguments(
    symbol: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    *,
    index: Optional[str],
) -> tuple[str, str, str]:
    if symbol is not None and index is not None:
        raise TypeError("pass either symbol or the legacy index alias, not both")
    requested_symbol = symbol if symbol is not None else index
    if requested_symbol is None:
        raise TypeError("symbol is required")
    if start_date is None or end_date is None:
        raise TypeError("start_date and end_date are required")
    return str(requested_symbol), str(start_date), str(end_date)


def default_index_providers(
    akshare_module: Optional[object] = None,
) -> list[IndexDataProvider]:
    """Return the deterministic primary/fallback adapter order."""
    return [
        AShareIndexProvider(akshare_module=akshare_module),
        AKShareIndexDailyProvider(akshare_module=akshare_module),
    ]
