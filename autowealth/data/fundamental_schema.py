"""Point-in-time-aware fundamental data schema."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Optional

import pandas as pd

FUNDAMENTAL_COLUMNS = [
    "symbol",
    "report_date",
    "available_date",
    "pe",
    "pb",
    "dividend_yield",
    "roe",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "operating_cash_flow",
    "net_profit",
    "source",
    "fetched_at",
]

FUNDAMENTAL_NUMERIC_COLUMNS = [
    "pe",
    "pb",
    "dividend_yield",
    "roe",
    "gross_margin",
    "net_margin",
    "debt_ratio",
    "operating_cash_flow",
    "net_profit",
]


@dataclass(frozen=True)
class FundamentalRecord:
    """One normalized fundamental observation.

    ``report_date`` is the accounting period end. ``available_date`` is the
    first date on which the observation was actually public. Historical
    research must gate records by ``available_date``, never by report date.
    """

    symbol: str
    report_date: str
    available_date: str
    pe: Optional[float] = None
    pb: Optional[float] = None
    dividend_yield: Optional[float] = None
    roe: Optional[float] = None
    gross_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_ratio: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    net_profit: Optional[float] = None
    source: str = "unknown"
    fetched_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_fundamental_data(data: pd.DataFrame) -> pd.DataFrame:
    """Return a stable fundamental DataFrame without inventing missing values."""
    normalized = data.copy()
    for column in FUNDAMENTAL_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA

    normalized = normalized[FUNDAMENTAL_COLUMNS]
    normalized["symbol"] = normalized["symbol"].astype("string")
    normalized["report_date"] = pd.to_datetime(normalized["report_date"], errors="coerce")
    normalized["available_date"] = pd.to_datetime(normalized["available_date"], errors="coerce")
    normalized["fetched_at"] = pd.to_datetime(normalized["fetched_at"], errors="coerce", utc=True)
    for column in FUNDAMENTAL_NUMERIC_COLUMNS:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized["source"] = normalized["source"].fillna("unknown").astype(str)
    return normalized.sort_values(
        ["symbol", "available_date", "report_date"],
        na_position="last",
        kind="mergesort",
    ).reset_index(drop=True)


def validate_fundamental_history(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Validate publication order and resolve exact report duplicates.

    Rows whose publication date precedes the report period are retained for
    audit but their ``available_date`` is invalidated, so as-of selection cannot
    consume them. Exact report/publication duplicates keep the row with the
    latest fetched timestamp, then the last stable source row.
    """
    normalized = normalize_fundamental_data(data)
    warnings: list[str] = []

    invalid_order = (
        normalized["available_date"].notna()
        & normalized["report_date"].notna()
        & (normalized["available_date"] < normalized["report_date"])
    )
    invalid_count = int(invalid_order.sum())
    if invalid_count:
        warnings.append(
            f"invalidated {invalid_count} fundamental rows with "
            "available_date earlier than report_date"
        )
        normalized.loc[invalid_order, "available_date"] = pd.NaT

    normalized = normalized.sort_values(
        ["symbol", "report_date", "available_date", "fetched_at", "source"],
        na_position="last",
        kind="mergesort",
    )
    duplicate_keys = ["symbol", "report_date", "available_date"]
    duplicate_mask = normalized.duplicated(duplicate_keys, keep="last")
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count:
        warnings.append(
            f"removed {duplicate_count} duplicate fundamental rows; "
            "kept latest fetched_at then last stable source row"
        )
        normalized = normalized.loc[~duplicate_mask]

    return normalize_fundamental_data(normalized), warnings


def eligible_fundamentals_asof(
    data: pd.DataFrame,
    as_of_date: str | pd.Timestamp,
    symbol: Optional[str] = None,
) -> pd.DataFrame:
    """Filter to records that were public no later than ``as_of_date``."""
    cutoff = pd.Timestamp(as_of_date).normalize()
    normalized = normalize_fundamental_data(data)
    eligible = normalized[
        normalized["available_date"].notna()
        & (normalized["available_date"] <= cutoff)
        & normalized["report_date"].notna()
        & (normalized["report_date"] <= cutoff)
    ]
    if symbol is not None:
        eligible = eligible[eligible["symbol"] == str(symbol)]
    return eligible.copy().reset_index(drop=True)


def latest_fundamental_asof(
    data: pd.DataFrame,
    symbol: str,
    as_of_date: str | pd.Timestamp,
) -> Optional[FundamentalRecord]:
    """Select the latest eligible record for one symbol."""
    eligible = eligible_fundamentals_asof(data, as_of_date, symbol=symbol)
    if eligible.empty:
        return None
    row = eligible.sort_values(["available_date", "report_date"]).iloc[-1]
    return fundamental_record_from_mapping(row.to_dict())


def fundamental_record_from_mapping(values: Mapping[str, object]) -> FundamentalRecord:
    """Convert a normalized mapping into ``FundamentalRecord``."""
    return FundamentalRecord(
        symbol=str(values.get("symbol", "")),
        report_date=_date_string(values.get("report_date")),
        available_date=_date_string(values.get("available_date")),
        pe=_optional_float(values.get("pe")),
        pb=_optional_float(values.get("pb")),
        dividend_yield=_optional_float(values.get("dividend_yield")),
        roe=_optional_float(values.get("roe")),
        gross_margin=_optional_float(values.get("gross_margin")),
        net_margin=_optional_float(values.get("net_margin")),
        debt_ratio=_optional_float(values.get("debt_ratio")),
        operating_cash_flow=_optional_float(values.get("operating_cash_flow")),
        net_profit=_optional_float(values.get("net_profit")),
        source=str(values.get("source") or "unknown"),
        fetched_at=_timestamp_string(values.get("fetched_at")),
    )


def _date_string(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _timestamp_string(value: object) -> str:
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    return "" if pd.isna(parsed) else parsed.isoformat()


def _optional_float(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed
