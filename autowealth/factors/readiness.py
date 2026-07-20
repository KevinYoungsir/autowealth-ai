"""Centralized minimum-observation rules for research factors."""

from __future__ import annotations

from typing import Dict

MOMENTUM_RECENT_SKIP_DAYS = 21
MOMENTUM_SIX_MONTH_DAYS = 126
MOMENTUM_TWELVE_MONTH_DAYS = 252

MOMENTUM_SIX_MONTH_MIN_CLOSES = MOMENTUM_SIX_MONTH_DAYS + MOMENTUM_RECENT_SKIP_DAYS + 1
MOMENTUM_TWELVE_MONTH_MIN_CLOSES = MOMENTUM_TWELVE_MONTH_DAYS + MOMENTUM_RECENT_SKIP_DAYS + 1

LOW_VOL_MIN_CLOSES = 253
RSI_MIN_CLOSES = 15
BOLLINGER_MIN_CLOSES = 20
SHORT_TERM_RETURN_MIN_CLOSES = 21
VOLUME_RATIO_MIN_OBSERVATIONS = 60


def factor_lookback_manifest() -> Dict[str, Dict[str, object]]:
    """Return a JSON-ready description of factor readiness requirements."""
    return {
        "momentum_6m_ex_1m": {
            "field": "close",
            "minimum_observations": MOMENTUM_SIX_MONTH_MIN_CLOSES,
            "lookback_trading_days": MOMENTUM_SIX_MONTH_DAYS,
            "skip_recent_trading_days": MOMENTUM_RECENT_SKIP_DAYS,
        },
        "momentum_12m_ex_1m": {
            "field": "close",
            "minimum_observations": MOMENTUM_TWELVE_MONTH_MIN_CLOSES,
            "lookback_trading_days": MOMENTUM_TWELVE_MONTH_DAYS,
            "skip_recent_trading_days": MOMENTUM_RECENT_SKIP_DAYS,
        },
        "annualized_volatility": {
            "field": "close",
            "minimum_observations": LOW_VOL_MIN_CLOSES,
            "fixed_window_observations": LOW_VOL_MIN_CLOSES,
        },
        "max_drawdown": {
            "field": "close",
            "minimum_observations": LOW_VOL_MIN_CLOSES,
            "fixed_window_observations": LOW_VOL_MIN_CLOSES,
        },
        "rsi": {
            "field": "close",
            "minimum_observations": RSI_MIN_CLOSES,
        },
        "bollinger": {
            "field": "close",
            "minimum_observations": BOLLINGER_MIN_CLOSES,
        },
        "short_term_return": {
            "field": "close",
            "minimum_observations": SHORT_TERM_RETURN_MIN_CLOSES,
        },
        "volume_ratio": {
            "field": "volume",
            "minimum_observations": VOLUME_RATIO_MIN_OBSERVATIONS,
        },
    }


def insufficient_sample_warning(
    metric_name: str,
    actual_observations: int,
    minimum_observations: int,
) -> str:
    """Build an auditable warning for an unavailable factor component."""
    return (
        f"insufficient {metric_name} observations: "
        f"{actual_observations} available, {minimum_observations} required"
    )
