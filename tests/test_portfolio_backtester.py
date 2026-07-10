import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

import pandas as pd
import pytest

from autowealth.backtest import PortfolioBacktester


SYMBOLS = ["600519", "000001", "600036", "600900", "000858"]


def make_price_data(symbols=SYMBOLS):
    dates = pd.bdate_range("2020-01-02", "2022-12-30")
    data = {}
    for index, symbol in enumerate(symbols):
        base = 20 + index * 10
        close = [base * (1 + 0.0005 * i) + index for i in range(len(dates))]
        data[symbol] = pd.DataFrame(
            {
                "date": dates,
                "open": close,
                "high": [value * 1.01 for value in close],
                "low": [value * 0.99 for value in close],
                "close": close,
                "volume": 1_000_000,
                "amount": 10_000_000,
                "amplitude": 1.0,
                "pct_change": 0.1,
                "change": 0.01,
                "turnover": 0.5,
            }
        )
    return data


def make_backtester(**kwargs):
    defaults = {
        "initial_capital": 1_000_000,
        "start_date": "2020-01-01",
        "end_date": "2022-12-31",
        "rebalance_frequency": "yearly",
        "commission": 0.0003,
        "stamp_tax": 0.0005,
        "slippage": 0.0002,
    }
    defaults.update(kwargs)
    return PortfolioBacktester(**defaults)


def test_equal_weight_yearly_rebalance_with_five_a_shares():
    weights = {symbol: 0.2 for symbol in SYMBOLS}
    result = make_backtester().run(weights, price_data=make_price_data())

    assert not result["equity_curve"].empty
    assert not result["daily_returns"].empty
    assert set(result["trade_log"]["symbol"]) == set(SYMBOLS)


def test_weight_sum_cannot_exceed_one():
    weights = {symbol: 0.21 for symbol in SYMBOLS}

    with pytest.raises(ValueError, match="sum cannot exceed 1"):
        make_backtester().run(weights, price_data=make_price_data())


def test_performance_metric_fields_are_complete():
    result = make_backtester().run({symbol: 0.2 for symbol in SYMBOLS}, price_data=make_price_data())

    expected_fields = {
        "equity_curve",
        "daily_returns",
        "annualized_return",
        "total_return",
        "max_drawdown",
        "volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "turnover",
        "trade_log",
        "holdings_by_period",
        "annual_returns",
        "monthly_returns",
    }
    assert expected_fields.issubset(result.keys())


def test_rebalance_records_are_generated():
    result = make_backtester(rebalance_frequency="yearly").run(
        {symbol: 0.2 for symbol in SYMBOLS},
        price_data=make_price_data(),
    )

    holdings = result["holdings_by_period"]
    assert len(holdings) == 3
    assert holdings["date"].dt.year.tolist() == [2020, 2021, 2022]


def test_cash_weight_logic_keeps_cash_reserve():
    weights = {symbol: 0.16 for symbol in SYMBOLS}
    result = make_backtester(cash_weight=0.2).run(weights, price_data=make_price_data())

    first_holding = result["holdings_by_period"].iloc[0]
    assert first_holding["cash_weight"] >= 0.19


def test_cash_weight_rejects_overallocated_portfolio():
    weights = {symbol: 0.2 for symbol in SYMBOLS}

    with pytest.raises(ValueError, match="cash_weight"):
        make_backtester(cash_weight=0.1).run(weights, price_data=make_price_data())


def test_max_position_weight_constraint():
    weights = {symbol: 0.2 for symbol in SYMBOLS}

    with pytest.raises(ValueError, match="max_position_weight"):
        make_backtester(max_position_weight=0.15).run(weights, price_data=make_price_data())

