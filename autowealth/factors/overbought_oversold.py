"""
Overbought and oversold research factor scoring.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from autowealth.factors.schema import (
    FactorScore,
    average_available,
    score_center_better,
    score_lower_better,
)


def overbought_oversold_factor(
    symbol: str,
    price_data: pd.DataFrame,
    as_of_date: str,
) -> FactorScore:
    """
    Score whether short-term trading conditions are balanced rather than extreme.

    This factor is a research score only and does not produce buy or sell signals.
    """
    data = _prepare_price_data(price_data)
    rsi = _rsi(data["close"])
    bollinger_position = _bollinger_position(data["close"])
    short_term_return = _short_term_return(data["close"])
    volume_ratio = _volume_ratio(data["volume"])
    raw_values = {
        "rsi": rsi,
        "bollinger_position": bollinger_position,
        "short_term_return": short_term_return,
        "volume_ratio": volume_ratio,
    }
    component_scores = {
        "rsi": score_center_better(rsi, 50, 35),
        "bollinger_position": score_center_better(bollinger_position, 0.5, 0.5),
        "short_term_return": score_center_better(short_term_return, 0.0, 0.25),
        "volume_ratio": score_lower_better(abs(volume_ratio - 1) if volume_ratio is not None else None, 0, 2),
    }
    warnings = [
        f"missing {name}; score degraded" for name, value in raw_values.items() if value is None
    ]
    return FactorScore(
        symbol=symbol,
        factor_name="overbought_oversold",
        score=average_available(component_scores),
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation=(
            "Overbought/oversold score measures short-term technical extremes for research only; "
            "it is not a trading signal."
        ),
        warnings=warnings,
    )


def _prepare_price_data(price_data: pd.DataFrame) -> pd.DataFrame:
    data = price_data.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    if "volume" not in data.columns:
        data["volume"] = pd.NA
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    return data.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)


def _rsi(close: pd.Series, window: int = 14) -> Optional[float]:
    if len(close) < window + 1:
        return None
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(window).mean()
    losses = (-delta.clip(upper=0)).rolling(window).mean()
    latest_loss = losses.iloc[-1]
    if latest_loss == 0:
        return 100.0
    rs = gains.iloc[-1] / latest_loss
    return float(100 - 100 / (1 + rs))


def _bollinger_position(close: pd.Series, window: int = 20) -> Optional[float]:
    if len(close) < window:
        return None
    rolling = close.tail(window)
    mean = rolling.mean()
    std = rolling.std(ddof=1)
    if std == 0 or pd.isna(std):
        return 0.5
    lower = mean - 2 * std
    upper = mean + 2 * std
    return float((close.iloc[-1] - lower) / (upper - lower))


def _short_term_return(close: pd.Series, window: int = 20) -> Optional[float]:
    if len(close) < window + 1:
        return None
    base = close.iloc[-window - 1]
    if base <= 0:
        return None
    return float(close.iloc[-1] / base - 1)


def _volume_ratio(volume: pd.Series, window: int = 60) -> Optional[float]:
    clean = volume.dropna()
    if len(clean) < 2:
        return None
    lookback = clean.tail(window)
    average = lookback.mean()
    if average <= 0:
        return None
    return float(clean.iloc[-1] / average)

