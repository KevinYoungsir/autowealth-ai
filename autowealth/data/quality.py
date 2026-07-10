"""
Basic market data quality checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd


MAX_MISSING_BUSINESS_DAYS = 8


@dataclass
class DataQualityReport:
    """
    Result object for data quality checks.
    """

    passed: bool
    row_count: int
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


def check_price_quality(df: pd.DataFrame) -> DataQualityReport:
    """
    Run basic checks for normalized daily OHLCV data.
    """
    row_count = len(df)
    report = DataQualityReport(passed=True, row_count=row_count)

    if df.empty:
        report.errors.append("dataframe is empty")
        report.passed = False
        return report

    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    report.start_date = _format_date(data["date"].min())
    report.end_date = _format_date(data["date"].max())

    _check_required_dates(data, report)
    _check_duplicate_dates(data, report)
    _check_date_continuity(data, report)
    _check_ohlc(data, report)
    _check_close(data, report)
    _check_volume(data, report)

    report.passed = not report.errors
    return report


def _check_required_dates(data: pd.DataFrame, report: DataQualityReport) -> None:
    if data["date"].isna().any():
        report.errors.append("date contains missing or invalid values")


def _check_duplicate_dates(data: pd.DataFrame, report: DataQualityReport) -> None:
    if data["date"].duplicated().any():
        report.errors.append("date contains duplicated values")


def _check_date_continuity(data: pd.DataFrame, report: DataQualityReport) -> None:
    dates = data["date"].dropna().sort_values()
    if len(dates) < 2:
        return

    large_gaps = []
    for previous, current in zip(dates.iloc[:-1], dates.iloc[1:]):
        missing_business_days = max(
            int(np.busday_count(previous.date(), current.date())) - 1,
            0,
        )
        if missing_business_days > MAX_MISSING_BUSINESS_DAYS:
            large_gaps.append((previous, current, missing_business_days))

    if large_gaps:
        report.warnings.append(
            "date has gaps exceeding 8 missing business days; review source "
            "coverage because extended market closures may be included"
        )


def _check_ohlc(data: pd.DataFrame, report: DataQualityReport) -> None:
    required = ["open", "high", "low", "close"]
    if any(column not in data.columns for column in required):
        report.errors.append("missing one or more OHLC columns")
        return

    ohlc = data[required].apply(pd.to_numeric, errors="coerce")
    invalid_high = ohlc["high"] < ohlc[["open", "low", "close"]].max(axis=1)
    invalid_low = ohlc["low"] > ohlc[["open", "high", "close"]].min(axis=1)
    if invalid_high.any() or invalid_low.any():
        report.errors.append("OHLC values are inconsistent")


def _check_close(data: pd.DataFrame, report: DataQualityReport) -> None:
    if "close" not in data.columns:
        report.errors.append("missing close column")
        return

    close = pd.to_numeric(data.get("close"), errors="coerce")
    if (close <= 0).any():
        report.errors.append("close contains zero or negative values")


def _check_volume(data: pd.DataFrame, report: DataQualityReport) -> None:
    if "volume" not in data.columns:
        report.errors.append("missing volume column")
        return

    volume = pd.to_numeric(data.get("volume"), errors="coerce")
    if (volume < 0).any():
        report.errors.append("volume contains negative values")
    if volume.isna().all():
        report.warnings.append("volume is entirely missing")


def _format_date(value: pd.Timestamp) -> Optional[str]:
    if pd.isna(value):
        return None
    return value.strftime("%Y-%m-%d")
