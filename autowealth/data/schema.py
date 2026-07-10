"""
统一行情数据 schema。
"""

from __future__ import annotations

from typing import Mapping

import pandas as pd


MARKET_DATA_COLUMNS = [
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "amplitude",
    "pct_change",
    "change",
    "turnover",
]


AKSHARE_COLUMN_MAP: Mapping[str, str] = {
    "日期": "date",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
    "振幅": "amplitude",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "换手率": "turnover",
}


def normalize_market_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert raw market data into the project-wide lowercase schema.

    Missing fields are added with ``pd.NA`` so downstream data quality checks and
    cache readers can rely on a stable set of columns.
    """
    normalized = df.copy()
    normalized = normalized.rename(columns=AKSHARE_COLUMN_MAP)

    for column in MARKET_DATA_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA

    normalized = normalized[MARKET_DATA_COLUMNS]
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")

    numeric_columns = [column for column in MARKET_DATA_COLUMNS if column != "date"]
    for column in numeric_columns:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = normalized.sort_values("date").reset_index(drop=True)
    return normalized


def normalize_date(value: str) -> str:
    """
    Normalize ``YYYYMMDD`` or ``YYYY-MM-DD`` values to ``YYYYMMDD``.
    """
    parsed = pd.to_datetime(value, errors="raise")
    return parsed.strftime("%Y%m%d")


def normalize_adjust(value: str) -> str:
    """
    Normalize adjust mode for A 股 daily data.
    """
    normalized = (value or "none").lower()
    aliases = {
        "qfq": "qfq",
        "hfq": "hfq",
        "none": "none",
        "": "none",
        "不复权": "none",
        "前复权": "qfq",
        "后复权": "hfq",
    }
    if normalized not in aliases:
        raise ValueError("adjust must be one of: qfq, hfq, none")
    return aliases[normalized]


def akshare_adjust(value: str) -> str:
    """
    Convert normalized adjust mode to AKShare's ``stock_zh_a_hist`` argument.
    """
    normalized = normalize_adjust(value)
    return "" if normalized == "none" else normalized

