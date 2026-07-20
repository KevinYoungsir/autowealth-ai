"""
Medium-term momentum factor scoring.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from autowealth.factors.schema import (
    FactorScore,
    average_available,
    score_higher_better,
)
from autowealth.factors.readiness import (
    MOMENTUM_RECENT_SKIP_DAYS,
    MOMENTUM_SIX_MONTH_DAYS,
    MOMENTUM_SIX_MONTH_MIN_CLOSES,
    MOMENTUM_TWELVE_MONTH_DAYS,
    MOMENTUM_TWELVE_MONTH_MIN_CLOSES,
    insufficient_sample_warning,
)

RECENT_REVERSAL_SKIP_DAYS = MOMENTUM_RECENT_SKIP_DAYS
SIX_MONTH_DAYS = MOMENTUM_SIX_MONTH_DAYS
TWELVE_MONTH_DAYS = MOMENTUM_TWELVE_MONTH_DAYS


def momentum_factor(symbol: str, price_data: pd.DataFrame, as_of_date: str) -> FactorScore:
    """
    Score 6-month and 12-month momentum while skipping the latest month.
    """
    prices = _close_prices(price_data)
    six_month = _momentum(prices, SIX_MONTH_DAYS, RECENT_REVERSAL_SKIP_DAYS)
    twelve_month = _momentum(prices, TWELVE_MONTH_DAYS, RECENT_REVERSAL_SKIP_DAYS)
    raw_values = {
        "momentum_6m_ex_1m": six_month,
        "momentum_12m_ex_1m": twelve_month,
    }
    component_scores = {
        "momentum_6m_ex_1m": score_higher_better(six_month, -0.2, 0.5),
        "momentum_12m_ex_1m": score_higher_better(twelve_month, -0.3, 0.8),
    }
    requirements = {
        "momentum_6m_ex_1m": MOMENTUM_SIX_MONTH_MIN_CLOSES,
        "momentum_12m_ex_1m": MOMENTUM_TWELVE_MONTH_MIN_CLOSES,
    }
    warnings = []
    for name, value in raw_values.items():
        if value is not None:
            continue
        minimum = requirements[name]
        if len(prices) < minimum:
            warnings.append(insufficient_sample_warning(name, len(prices), minimum))
        else:
            warnings.append(f"missing {name}; score degraded")
    return FactorScore(
        symbol=symbol,
        factor_name="momentum",
        score=average_available(component_scores),
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation="Momentum score uses medium-term price trends excluding the latest month for research only.",
        warnings=warnings,
    )


def _close_prices(price_data: pd.DataFrame) -> pd.Series:
    data = price_data.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    return data.dropna(subset=["date", "close"]).set_index("date")["close"].sort_index()


def _momentum(prices: pd.Series, lookback_days: int, skip_days: int) -> Optional[float]:
    required = lookback_days + skip_days + 1
    if len(prices) < required:
        return None
    end_price = prices.iloc[-skip_days - 1]
    start_price = prices.iloc[-required]
    if start_price <= 0:
        return None
    return float(end_price / start_price - 1)
