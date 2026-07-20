"""
Low-volatility factor scoring.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from autowealth.factors.readiness import (
    LOW_VOL_MIN_CLOSES,
    insufficient_sample_warning,
)
from autowealth.factors.schema import (
    FactorScore,
    average_available,
    score_lower_better,
)


def low_vol_factor(
    symbol: str,
    price_data: pd.DataFrame,
    as_of_date: str,
    beta: Optional[float] = None,
) -> FactorScore:
    """
    Score lower volatility and drawdown. Beta is reserved for future benchmark-aware scoring.
    """
    prices = _close_prices(price_data)
    fixed_window = prices.tail(LOW_VOL_MIN_CLOSES)
    annualized_vol = _annualized_volatility(fixed_window)
    drawdown = _max_drawdown(fixed_window)
    raw_values = {
        "annualized_volatility": annualized_vol,
        "max_drawdown": drawdown,
        "beta": beta,
    }
    component_scores = {
        "annualized_volatility": score_lower_better(annualized_vol, 0.12, 0.6),
        "max_drawdown": score_lower_better(
            abs(drawdown) if drawdown is not None else None, 0.08, 0.5
        ),
    }
    warnings = []
    for name in ("annualized_volatility", "max_drawdown"):
        if raw_values[name] is not None:
            continue
        if len(prices) < LOW_VOL_MIN_CLOSES:
            warnings.append(
                insufficient_sample_warning(
                    name,
                    len(prices),
                    LOW_VOL_MIN_CLOSES,
                )
            )
        else:
            warnings.append(f"missing {name}; score degraded")
    warnings.append("beta scoring is reserved for a future benchmark-aware implementation")
    return FactorScore(
        symbol=symbol,
        factor_name="low_vol",
        score=average_available(component_scores),
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation="Low-volatility score summarizes historical volatility and drawdown for research only.",
        warnings=warnings,
    )


def _close_prices(price_data: pd.DataFrame) -> pd.Series:
    data = price_data.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    return data.dropna(subset=["date", "close"]).set_index("date")["close"].sort_index()


def _annualized_volatility(prices: pd.Series) -> Optional[float]:
    if len(prices) < LOW_VOL_MIN_CLOSES:
        return None
    returns = prices.pct_change().dropna()
    if len(returns) < LOW_VOL_MIN_CLOSES - 1:
        return None
    return float(returns.std(ddof=1) * np.sqrt(252))


def _max_drawdown(prices: pd.Series) -> Optional[float]:
    if len(prices) < LOW_VOL_MIN_CLOSES:
        return None
    running_max = prices.cummax()
    drawdown = prices / running_max - 1
    return float(drawdown.min())
