import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

import pandas as pd

from autowealth.factors import (
    combine_factor_scores,
    low_vol_factor,
    momentum_factor,
    overbought_oversold_factor,
    quality_factor,
    value_factor,
)

SYMBOL = "600519"
AS_OF_DATE = "2024-12-31"


def make_price_data(days=320):
    dates = pd.bdate_range("2023-09-01", periods=days)
    close = []
    volume = []
    for index in range(days):
        trend = 100 * (1 + 0.0008 * index)
        wave = 2.0 if index % 20 < 10 else -1.5
        close.append(trend + wave)
        volume.append(1_000_000 + (index % 15) * 10_000)
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "volume": volume,
            "amount": [value * 10000 for value in close],
            "amplitude": 2.0,
            "pct_change": 0.1,
            "change": 0.1,
            "turnover": 0.5,
        }
    )


def make_financial_data():
    return {
        "pe": 18.0,
        "pb": 3.2,
        "dividend_yield": 0.025,
        "valuation_percentile": 0.35,
        "roe": 0.22,
        "gross_margin": 0.55,
        "net_margin": 0.28,
        "operating_cash_flow_quality": 1.2,
        "debt_to_asset": 0.32,
    }


def assert_score_range(score):
    assert 0 <= score.score <= 100
    assert score.symbol == SYMBOL
    assert score.as_of_date == AS_OF_DATE
    assert "advice" not in score.explanation.lower()


def test_each_factor_outputs_score_between_0_and_100():
    financial_data = make_financial_data()
    price_data = make_price_data()

    scores = [
        value_factor(SYMBOL, financial_data, AS_OF_DATE),
        quality_factor(SYMBOL, financial_data, AS_OF_DATE),
        momentum_factor(SYMBOL, price_data, AS_OF_DATE),
        low_vol_factor(SYMBOL, price_data, AS_OF_DATE),
        overbought_oversold_factor(SYMBOL, price_data, AS_OF_DATE),
    ]

    for score in scores:
        assert_score_range(score)
        assert score.raw_values


def test_missing_financial_data_degrades_without_crashing():
    score = value_factor(SYMBOL, {"pe": 20.0}, AS_OF_DATE)

    assert 0 <= score.score <= 100
    assert score.warnings
    assert any("missing pb" in warning for warning in score.warnings)


def test_missing_price_history_degrades_without_crashing():
    price_data = make_price_data(days=30)

    score = momentum_factor(SYMBOL, price_data, AS_OF_DATE)

    assert 0 <= score.score <= 100
    assert score.warnings


def test_single_price_point_does_not_make_low_vol_available_or_score_100():
    score = low_vol_factor(SYMBOL, make_price_data(days=1), AS_OF_DATE)

    assert score.raw_values["annualized_volatility"] is None
    assert score.raw_values["max_drawdown"] is None
    assert score.score != 100.0
    assert any("1 available, 253 required" in warning for warning in score.warnings)


def test_low_vol_requires_full_fixed_window():
    insufficient = low_vol_factor(
        SYMBOL,
        make_price_data(days=252),
        AS_OF_DATE,
    )
    ready = low_vol_factor(
        SYMBOL,
        make_price_data(days=253),
        AS_OF_DATE,
    )

    assert insufficient.raw_values["annualized_volatility"] is None
    assert insufficient.raw_values["max_drawdown"] is None
    assert ready.raw_values["annualized_volatility"] is not None
    assert ready.raw_values["max_drawdown"] is not None


def test_momentum_readiness_boundaries_preserve_existing_formula():
    six_ready = momentum_factor(
        SYMBOL,
        make_price_data(days=148),
        AS_OF_DATE,
    )
    twelve_short = momentum_factor(
        SYMBOL,
        make_price_data(days=273),
        AS_OF_DATE,
    )
    twelve_ready = momentum_factor(
        SYMBOL,
        make_price_data(days=274),
        AS_OF_DATE,
    )

    assert six_ready.raw_values["momentum_6m_ex_1m"] is not None
    assert six_ready.raw_values["momentum_12m_ex_1m"] is None
    assert twelve_short.raw_values["momentum_12m_ex_1m"] is None
    assert twelve_ready.raw_values["momentum_12m_ex_1m"] is not None


def test_overbought_oversold_component_readiness_boundaries():
    fourteen = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=14),
        AS_OF_DATE,
    )
    fifteen = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=15),
        AS_OF_DATE,
    )
    nineteen = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=19),
        AS_OF_DATE,
    )
    twenty = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=20),
        AS_OF_DATE,
    )
    twenty_one = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=21),
        AS_OF_DATE,
    )
    fifty_nine = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=59),
        AS_OF_DATE,
    )
    sixty = overbought_oversold_factor(
        SYMBOL,
        make_price_data(days=60),
        AS_OF_DATE,
    )

    assert fourteen.raw_values["rsi"] is None
    assert fifteen.raw_values["rsi"] is not None
    assert nineteen.raw_values["bollinger_position"] is None
    assert twenty.raw_values["rsi"] is not None
    assert twenty.raw_values["bollinger_position"] is not None
    assert twenty.raw_values["short_term_return"] is None
    assert twenty_one.raw_values["short_term_return"] is not None
    assert fifty_nine.raw_values["volume_ratio"] is None
    assert sixty.raw_values["short_term_return"] is not None
    assert sixty.raw_values["volume_ratio"] is not None


def test_composite_factor_weighted_score_is_correct():
    financial_data = make_financial_data()
    price_data = make_price_data()
    factor_scores = {
        "value": value_factor(SYMBOL, financial_data, AS_OF_DATE),
        "quality": quality_factor(SYMBOL, financial_data, AS_OF_DATE),
        "momentum": momentum_factor(SYMBOL, price_data, AS_OF_DATE),
        "low_vol": low_vol_factor(SYMBOL, price_data, AS_OF_DATE),
        "overbought_oversold": overbought_oversold_factor(SYMBOL, price_data, AS_OF_DATE),
    }
    weights = {
        "value": 0.25,
        "quality": 0.25,
        "momentum": 0.2,
        "low_vol": 0.15,
        "overbought_oversold": 0.15,
    }

    composite = combine_factor_scores(SYMBOL, factor_scores, weights, AS_OF_DATE)
    expected = sum(factor_scores[name].score * weights[name] for name in weights)

    assert 0 <= composite.score <= 100
    assert abs(composite.score - expected) < 1e-9
    assert composite.weights == weights


def test_composite_factor_can_normalize_weights():
    financial_data = make_financial_data()
    price_data = make_price_data()
    factor_scores = {
        "value": value_factor(SYMBOL, financial_data, AS_OF_DATE),
        "quality": quality_factor(SYMBOL, financial_data, AS_OF_DATE),
    }

    composite = combine_factor_scores(
        SYMBOL,
        factor_scores,
        {"value": 2.0, "quality": 1.0},
        AS_OF_DATE,
    )

    assert abs(sum(composite.weights.values()) - 1.0) < 1e-12
    assert 0 <= composite.score <= 100
