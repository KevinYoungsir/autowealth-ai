"""A-share fundamental provider with explicit point-in-time limitations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

import pandas as pd

from autowealth.data.fundamental_schema import normalize_fundamental_data


@dataclass
class FundamentalProviderResult:
    """Normalized provider output and its evidence limitations."""

    data: pd.DataFrame
    source: str
    point_in_time: bool
    warnings: list[str] = field(default_factory=list)


class FundamentalDataProvider(Protocol):
    """Interface implemented by real and mock fundamental providers."""

    def get_fundamentals(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> FundamentalProviderResult: ...


class AShareFundamentalProvider:
    """Fetch historical A-share financial indicators through AKShare.

    Network access occurs only inside ``get_fundamentals``. The preferred
    AKShare endpoint exposes historical financial indicators, but availability
    dates are accepted only when the source returns an explicit announcement or
    disclosure-date column. Report dates are never substituted silently.
    """

    def __init__(
        self,
        akshare_module: Optional[object] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self._akshare_module = akshare_module
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def get_fundamentals(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> FundamentalProviderResult:
        ak = self._akshare_module or self._import_akshare()
        clean_symbol = _clean_symbol(symbol)
        warnings: list[str] = []

        if hasattr(ak, "stock_financial_analysis_indicator_em"):
            source = "akshare.stock_financial_analysis_indicator_em"
            raw = ak.stock_financial_analysis_indicator_em(
                symbol=_eastmoney_symbol(clean_symbol),
                indicator="按报告期",
            )
        elif hasattr(ak, "stock_financial_analysis_indicator"):
            source = "akshare.stock_financial_analysis_indicator"
            raw = ak.stock_financial_analysis_indicator(
                symbol=clean_symbol,
                start_year=pd.Timestamp(start_date).strftime("%Y"),
            )
            warnings.append(
                "AKShare fallback endpoint does not provide reliable historical announcement dates"
            )
        else:
            raise RuntimeError("installed AKShare has no supported fundamental indicator endpoint")

        normalized, has_explicit_available_date = self._normalize_raw(
            raw,
            symbol=clean_symbol,
            source=source,
        )
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        normalized = normalized[
            normalized["report_date"].between(start, end, inclusive="both")
        ].reset_index(drop=True)

        if normalized.empty:
            warnings.append(f"{clean_symbol} fundamental provider returned no rows")
        if not has_explicit_available_date or normalized["available_date"].isna().any():
            warnings.append(
                "reliable historical available_date is missing; data is not strict point-in-time"
            )
        for field_name in ("pe", "pb", "dividend_yield"):
            if normalized.empty or normalized[field_name].isna().all():
                warnings.append(
                    f"historical {field_name} unavailable from this endpoint; "
                    "current values were not backfilled"
                )

        point_in_time = bool(
            has_explicit_available_date
            and not normalized.empty
            and normalized["available_date"].notna().all()
        )
        return FundamentalProviderResult(
            data=normalized,
            source=source,
            point_in_time=point_in_time,
            warnings=_dedupe(warnings),
        )

    def _normalize_raw(
        self,
        raw: pd.DataFrame,
        symbol: str,
        source: str,
    ) -> tuple[pd.DataFrame, bool]:
        raw = pd.DataFrame(raw).copy()
        report_column = _first_column(raw, "REPORT_DATE", "report_date", "日期", "报告日")
        available_column = _first_column(
            raw,
            "NOTICE_DATE",
            "ANNOUNCEMENT_DATE",
            "DISCLOSURE_DATE",
            "available_date",
            "公告日期",
            "披露日期",
        )
        fetched_at = self._clock().astimezone(timezone.utc).isoformat()

        normalized = pd.DataFrame(index=raw.index)
        normalized["symbol"] = symbol
        normalized["report_date"] = _column_or_na(raw, report_column)
        normalized["available_date"] = _column_or_na(raw, available_column)
        normalized["pe"] = _numeric_column(raw, "PE", "pe", "市盈率")
        normalized["pb"] = _numeric_column(raw, "PB", "pb", "市净率")
        normalized["dividend_yield"] = _percentage_column(
            raw, "DIVIDEND_YIELD", "dividend_yield", "股息率"
        )
        normalized["roe"] = _percentage_column(
            raw, "ROEJQ", "ROE", "净资产收益率(%)", "加权净资产收益率(%)"
        )
        normalized["gross_margin"] = _percentage_column(
            raw, "XSMLL", "gross_margin", "销售毛利率(%)", "毛利率(%)"
        )
        normalized["net_margin"] = _percentage_column(
            raw, "XSJLL", "net_margin", "销售净利率(%)", "净利率(%)"
        )
        normalized["debt_ratio"] = _percentage_column(
            raw, "ZCFZL", "debt_ratio", "资产负债率(%)"
        )
        normalized["operating_cash_flow"] = _numeric_column(
            raw,
            "NETCASHOPERATE",
            "operating_cash_flow",
            "经营活动产生的现金流量净额",
            "经营活动现金流量净额",
        )
        normalized["net_profit"] = _numeric_column(
            raw, "PARENTNETPROFIT", "net_profit", "归属净利润", "净利润(元)"
        )
        normalized["source"] = source
        normalized["fetched_at"] = fetched_at
        return normalize_fundamental_data(normalized), available_column is not None

    @staticmethod
    def _import_akshare():
        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError(
                "AShareFundamentalProvider requires akshare: pip install akshare"
            ) from exc
        return ak


def _clean_symbol(symbol: str) -> str:
    clean = str(symbol).strip().upper()
    for suffix in (".SH", ".SS", ".SZ", ".BJ"):
        clean = clean.replace(suffix, "")
    return clean


def _eastmoney_symbol(symbol: str) -> str:
    if symbol.startswith(("4", "8", "92")):
        return f"{symbol}.BJ"
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _first_column(data: pd.DataFrame, *names: str) -> Optional[str]:
    return next((name for name in names if name in data.columns), None)


def _column_or_na(data: pd.DataFrame, column: Optional[str]) -> pd.Series:
    if column is None:
        return pd.Series(pd.NA, index=data.index, dtype="object")
    return data[column]


def _numeric_column(data: pd.DataFrame, *names: str) -> pd.Series:
    column = _first_column(data, *names)
    return pd.to_numeric(_column_or_na(data, column), errors="coerce")


def _percentage_column(data: pd.DataFrame, *names: str) -> pd.Series:
    values = _numeric_column(data, *names)
    return values.where(values.abs() <= 1, values / 100.0)


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
