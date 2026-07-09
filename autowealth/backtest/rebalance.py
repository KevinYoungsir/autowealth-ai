"""
Rebalance date generation for portfolio backtests.
"""

from __future__ import annotations

import pandas as pd


SUPPORTED_REBALANCE_FREQUENCIES = {"monthly", "quarterly", "yearly", "five_year"}


def generate_rebalance_dates(
    trading_dates: pd.DatetimeIndex,
    frequency: str,
) -> pd.DatetimeIndex:
    """
    Generate rebalance dates from available trading dates.

    The first available trading date is always included so the portfolio can
    establish its initial target weights.
    """
    frequency = frequency.lower()
    if frequency not in SUPPORTED_REBALANCE_FREQUENCIES:
        raise ValueError(
            "rebalance_frequency must be one of: monthly, quarterly, yearly, five_year"
        )

    dates = pd.DatetimeIndex(pd.to_datetime(trading_dates)).sort_values().unique()
    if len(dates) == 0:
        return pd.DatetimeIndex([])

    selected = [dates[0]]
    periods = _period_labels(dates, frequency)
    period_frame = pd.DataFrame({"date": dates, "period": periods})
    first_dates = period_frame.groupby("period", sort=True)["date"].first().tolist()

    for date in first_dates:
        if date != selected[0]:
            selected.append(date)

    return pd.DatetimeIndex(selected)


def _period_labels(dates: pd.DatetimeIndex, frequency: str):
    if frequency == "monthly":
        return dates.to_period("M")
    if frequency == "quarterly":
        return dates.to_period("Q")
    if frequency == "yearly":
        return dates.to_period("Y")

    base_year = int(dates[0].year)
    labels = [f"{base_year + ((date.year - base_year) // 5) * 5}" for date in dates]
    return labels

