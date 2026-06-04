"""
Tests for backtest module.
"""

import numpy as np
import pandas as pd
import pytest

from autowealth.core.backtest import BacktestEngine


@pytest.fixture
def sample_price_data():
    """Generate sample price data."""
    np.random.seed(42)
    n_days = 100
    # Create a trending price series
    returns = np.random.normal(0.001, 0.02, n_days)
    prices = 100 * np.exp(np.cumsum(returns))
    dates = pd.date_range(start="2024-01-01", periods=n_days, freq="D")
    return pd.DataFrame({"Close": prices}, index=dates)


@pytest.fixture
def backtest_engine():
    """Create a BacktestEngine instance."""
    return BacktestEngine(initial_capital=100000.0)


class TestBacktestEngineInit:
    def test_init_default_capital(self):
        engine = BacktestEngine()
        assert engine.initial_capital == 100000.0
        assert engine.capital == 100000.0
        assert engine.position == 0.0

    def test_init_custom_capital(self):
        engine = BacktestEngine(initial_capital=50000.0)
        assert engine.initial_capital == 50000.0
        assert engine.capital == 50000.0

    def test_init_empty_lists(self):
        engine = BacktestEngine()
        assert engine.equity_curve == []
        assert engine.trade_history == []


class TestRunStrategy:
    def test_basic_buy_sell(self, backtest_engine, sample_price_data):
        # 100 days total: buy at day 20, sell at day 80
        # 20 + 1 + 59 + 1 + 19 = 100
        signals = ["hold"] * 20 + ["buy"] + ["hold"] * 59 + ["sell"] + ["hold"] * 19
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 2  # 1 buy + 1 sell
        assert backtest_engine.trade_history[0]["type"] == "buy"
        assert backtest_engine.trade_history[1]["type"] == "sell"

    def test_multiple_trades(self, backtest_engine, sample_price_data):
        signals = (
            ["hold"] * 10
            + ["buy"]
            + ["hold"] * 20
            + ["sell"]
            + ["hold"] * 10
            + ["buy"]
            + ["hold"] * 20
            + ["sell"]
            + ["hold"] * 36  # Total 100
        )
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 4  # 2 buys + 2 sells

    def test_no_trades_all_hold(self, backtest_engine, sample_price_data):
        signals = ["hold"] * len(sample_price_data)
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 0
        assert len(backtest_engine.equity_curve) == len(sample_price_data)

    def test_consecutive_buys_ignored(self, backtest_engine, sample_price_data):
        signals = ["hold"] * 10 + ["buy", "buy", "buy"] + ["hold"] * 87
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 1  # Only 1 buy executed

    def test_sell_without_position_ignored(self, backtest_engine, sample_price_data):
        signals = ["sell", "sell"] + ["hold"] * 98
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 0

    def test_length_mismatch_raises_error(self, backtest_engine, sample_price_data):
        signals = ["hold"] * 50  # Wrong length
        with pytest.raises(ValueError, match="Data length"):
            backtest_engine.run_strategy(sample_price_data, signals)

    def test_commission_applied(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals, commission=0.01)
        buy_trade = backtest_engine.trade_history[0]
        assert buy_trade["cost"] > 0  # Commission was charged

    def test_method_chaining(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        result = backtest_engine.run_strategy(sample_price_data, signals)
        assert result is backtest_engine


class TestGetPerformanceMetrics:
    def test_metrics_keys(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        expected_keys = {
            "total_return",
            "annualized_return",
            "max_drawdown",
            "sharpe_ratio",
            "win_rate",
            "trade_count",
            "final_equity",
            "initial_capital",
        }
        assert set(metrics.keys()) == expected_keys

    def test_no_trades_metrics(self, backtest_engine, sample_price_data):
        signals = ["hold"] * len(sample_price_data)
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        assert metrics["total_return"] == 0.0
        assert metrics["trade_count"] == 0
        assert metrics["win_rate"] == 0.0
        assert metrics["final_equity"] == backtest_engine.initial_capital

    def test_total_return_calculation(self, backtest_engine, sample_price_data):
        # Buy at start, sell at end
        signals = ["buy"] + ["hold"] * 98 + ["sell"]
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        expected_return = (sample_price_data["Close"].iloc[-1] / sample_price_data["Close"].iloc[0]) - 1
        # Should be close to expected (minus commission)
        assert abs(metrics["total_return"] - expected_return) < 0.01

    def test_win_rate_calculation(self, backtest_engine, sample_price_data):
        signals = (
            ["hold"] * 10
            + ["buy"]
            + ["hold"] * 20
            + ["sell"]  # First trade
            + ["hold"] * 10
            + ["buy"]
            + ["hold"] * 20
            + ["sell"]  # Second trade
            + ["hold"] * 36  # Total 100
        )
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        assert 0.0 <= metrics["win_rate"] <= 1.0
        assert metrics["trade_count"] == 2

    def test_max_drawdown_non_negative(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        assert metrics["max_drawdown"] >= 0.0

    def test_sharpe_ratio_finite(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        metrics = backtest_engine.get_performance_metrics()
        assert np.isfinite(metrics["sharpe_ratio"])


class TestGetEquityCurve:
    def test_returns_series(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        curve = backtest_engine.get_equity_curve()
        assert isinstance(curve, pd.Series)
        assert len(curve) == len(sample_price_data)

    def test_empty_curve_before_run(self, backtest_engine):
        curve = backtest_engine.get_equity_curve()
        assert len(curve) == 0

    def test_equity_values_positive(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        curve = backtest_engine.get_equity_curve()
        assert (curve > 0).all()


class TestGetTradeHistory:
    def test_returns_list(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        history = backtest_engine.get_trade_history()
        assert isinstance(history, list)
        assert len(history) == 2

    def test_trade_dict_keys(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        history = backtest_engine.get_trade_history()
        buy_trade = history[0]
        assert buy_trade["type"] == "buy"
        assert "price" in buy_trade
        assert "shares" in buy_trade
        assert "timestamp" in buy_trade
        assert "equity" in buy_trade

        sell_trade = history[1]
        assert sell_trade["type"] == "sell"
        assert "pnl" in sell_trade
        assert "return_pct" in sell_trade

    def test_isolation(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        history1 = backtest_engine.get_trade_history()
        history2 = backtest_engine.get_trade_history()
        # Modifying one should not affect the other
        history1.append({"test": "data"})
        assert len(history2) == 2


class TestEdgeCases:
    def test_single_day_data(self):
        data = pd.DataFrame({"Close": [100.0]}, index=pd.date_range("2024-01-01", periods=1))
        engine = BacktestEngine()
        signals = ["buy"]
        engine.run_strategy(data, signals)
        assert len(engine.equity_curve) == 1

    def test_immediate_sell_after_buy(self, backtest_engine, sample_price_data):
        signals = ["hold"] * 10 + ["buy", "sell"] + ["hold"] * 88
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 2
        # Should have some commission loss
        metrics = backtest_engine.get_performance_metrics()
        assert metrics["total_return"] < 0  # Due to commission

    def test_alternating_signals(self, backtest_engine, sample_price_data):
        # Alternating buy/sell should only trade when position changes
        signals = ["buy", "sell", "buy", "sell", "buy", "sell"] + ["hold"] * 94
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals)
        assert len(backtest_engine.trade_history) == 6

    def test_zero_commission(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals, commission=0.0)
        buy_trade = backtest_engine.trade_history[0]
        assert buy_trade["cost"] == 0.0

    def test_high_commission(self, backtest_engine, sample_price_data):
        # 10 + 1 + 78 + 1 + 10 = 100
        signals = ["hold"] * 10 + ["buy"] + ["hold"] * 78 + ["sell"] + ["hold"] * 10
        assert len(signals) == 100
        backtest_engine.run_strategy(sample_price_data, signals, commission=0.1)
        metrics = backtest_engine.get_performance_metrics()
        # High commission should significantly reduce returns
        assert metrics["total_return"] < 0.1
