"""
Tests for portfolio_optimizer module.
"""

import numpy as np
import pandas as pd
import pytest

from autowealth.core.portfolio_optimizer import PortfolioOptimizer


@pytest.fixture
def sample_returns():
    """Generate sample returns data for 3 assets over 252 days."""
    np.random.seed(42)
    n_days = 252
    data = {
        "AAPL": np.random.normal(0.001, 0.02, n_days),
        "GOOGL": np.random.normal(0.0008, 0.018, n_days),
        "MSFT": np.random.normal(0.0012, 0.015, n_days),
    }
    return pd.DataFrame(data)


@pytest.fixture
def optimizer(sample_returns):
    """Create a PortfolioOptimizer instance."""
    return PortfolioOptimizer(sample_returns)


class TestPortfolioOptimizerInit:
    def test_init_sets_attributes(self, optimizer, sample_returns):
        assert optimizer.n_assets == 3
        assert optimizer.symbols == ["AAPL", "GOOGL", "MSFT"]
        assert len(optimizer.mean_returns) == 3
        assert optimizer.cov_matrix.shape == (3, 3)
        assert optimizer.ann_factor == 252

    def test_init_drops_na(self):
        data = pd.DataFrame({
            "A": [0.01, np.nan, 0.02],
            "B": [0.01, 0.02, 0.03],
        })
        opt = PortfolioOptimizer(data)
        assert len(opt.returns) == 2


class TestPortfolioOptimizerHelpers:
    def test_portfolio_return(self, optimizer):
        weights = np.array([0.3, 0.4, 0.3])
        ret = optimizer._portfolio_return(weights)
        expected = np.dot(weights, optimizer.mean_returns) * 252
        assert np.isclose(ret, expected)

    def test_portfolio_variance(self, optimizer):
        weights = np.array([0.3, 0.4, 0.3])
        var = optimizer._portfolio_variance(weights)
        expected = np.dot(weights.T, np.dot(optimizer.cov_matrix, weights)) * 252
        assert np.isclose(var, expected)

    def test_portfolio_volatility(self, optimizer):
        weights = np.array([0.3, 0.4, 0.3])
        vol = optimizer._portfolio_volatility(weights)
        var = optimizer._portfolio_variance(weights)
        assert np.isclose(vol, np.sqrt(var))

    def test_sharpe_ratio_zero_vol(self, optimizer):
        weights = np.zeros(3)
        sr = optimizer._sharpe_ratio(weights)
        assert sr == -np.inf

    def test_validate_weights_negative(self, optimizer):
        weights = np.array([-0.2, 0.5, 0.7])
        validated = optimizer._validate_weights(weights)
        assert np.all(validated >= 0)
        assert np.isclose(validated.sum(), 1.0)

    def test_validate_weights_all_zero(self, optimizer):
        weights = np.zeros(3)
        validated = optimizer._validate_weights(weights)
        assert np.allclose(validated, 1 / 3)


class TestMeanVarianceOptimization:
    def test_returns_dict_with_keys(self, optimizer):
        result = optimizer.mean_variance_optimization(target_return=0.15)
        assert set(result.keys()) == {"weights", "expected_return", "volatility", "sharpe_ratio"}

    def test_weights_sum_to_one(self, optimizer):
        result = optimizer.mean_variance_optimization(target_return=0.15)
        weights = np.array(list(result["weights"].values()))
        assert np.isclose(weights.sum(), 1.0)
        assert np.all(weights >= 0)

    def test_none_target_returns_min_variance(self, optimizer):
        result = optimizer.mean_variance_optimization(target_return=None)
        min_var = optimizer.min_variance_portfolio()
        assert np.isclose(result["volatility"], min_var["volatility"])

    def test_different_targets_different_volatilities(self, optimizer):
        r1 = optimizer.mean_variance_optimization(target_return=0.10)
        r2 = optimizer.mean_variance_optimization(target_return=0.20)
        # Higher target return should generally have higher or equal volatility
        # Allow small tolerance due to numerical optimization and projection
        assert r2["volatility"] >= r1["volatility"] - 0.05


class TestMaxSharpeRatio:
    def test_returns_dict_with_keys(self, optimizer):
        result = optimizer.max_sharpe_ratio()
        assert set(result.keys()) == {"weights", "expected_return", "volatility", "sharpe_ratio"}

    def test_weights_sum_to_one(self, optimizer):
        result = optimizer.max_sharpe_ratio()
        weights = np.array(list(result["weights"].values()))
        assert np.isclose(weights.sum(), 1.0)
        assert np.all(weights >= 0)

    def test_sharpe_is_finite(self, optimizer):
        result = optimizer.max_sharpe_ratio()
        assert np.isfinite(result["sharpe_ratio"])

    def test_custom_risk_free_rate(self, optimizer):
        result1 = optimizer.max_sharpe_ratio(risk_free_rate=0.02)
        result2 = optimizer.max_sharpe_ratio(risk_free_rate=0.05)
        # Different risk-free rates should give different Sharpe ratios
        assert result1["sharpe_ratio"] != result2["sharpe_ratio"]


class TestMinVariancePortfolio:
    def test_returns_dict_with_keys(self, optimizer):
        result = optimizer.min_variance_portfolio()
        assert set(result.keys()) == {"weights", "expected_return", "volatility", "sharpe_ratio"}

    def test_weights_sum_to_one(self, optimizer):
        result = optimizer.min_variance_portfolio()
        weights = np.array(list(result["weights"].values()))
        assert np.isclose(weights.sum(), 1.0)
        assert np.all(weights >= 0)

    def test_volatility_lower_than_equal_weight(self, optimizer):
        min_var = optimizer.min_variance_portfolio()
        eq_weights = np.ones(3) / 3
        eq_vol = optimizer._portfolio_volatility(eq_weights)
        assert min_var["volatility"] <= eq_vol + 1e-6


class TestEfficientFrontier:
    def test_returns_correct_number_of_points(self, optimizer):
        frontier = optimizer.get_efficient_frontier(n_points=20)
        assert len(frontier) == 20

    def test_each_point_has_required_keys(self, optimizer):
        frontier = optimizer.get_efficient_frontier(n_points=10)
        for point in frontier:
            assert set(point.keys()) == {"return", "volatility", "sharpe_ratio", "weights"}

    def test_returns_are_monotonic(self, optimizer):
        frontier = optimizer.get_efficient_frontier(n_points=20)
        returns = [p["return"] for p in frontier]
        # Should be non-decreasing
        for i in range(1, len(returns)):
            assert returns[i] >= returns[i - 1] - 1e-6

    def test_volatilities_are_non_negative(self, optimizer):
        frontier = optimizer.get_efficient_frontier(n_points=10)
        for point in frontier:
            assert point["volatility"] >= 0


class TestAllocateWeights:
    def test_returns_allocation_dict(self, optimizer):
        allocation = optimizer.allocate_weights(["AAPL", "GOOGL", "MSFT"], total_value=100000)
        assert set(allocation.keys()) == {"AAPL", "GOOGL", "MSFT"}

    def test_allocation_sums_to_total(self, optimizer):
        allocation = optimizer.allocate_weights(["AAPL", "GOOGL", "MSFT"], total_value=100000)
        total = sum(allocation.values())
        assert np.isclose(total, 100000)

    def test_allocation_non_negative(self, optimizer):
        allocation = optimizer.allocate_weights(["AAPL", "GOOGL", "MSFT"], total_value=100000)
        for v in allocation.values():
            assert v >= 0

    def test_unknown_symbol_gets_zero(self, optimizer):
        allocation = optimizer.allocate_weights(["AAPL", "UNKNOWN"], total_value=100000)
        assert allocation["UNKNOWN"] == 0.0


class TestEdgeCases:
    def test_single_asset(self):
        data = pd.DataFrame({"ONLY": np.random.normal(0.001, 0.01, 100)})
        opt = PortfolioOptimizer(data)
        result = opt.min_variance_portfolio()
        assert np.isclose(result["weights"]["ONLY"], 1.0)

    def test_two_assets(self):
        np.random.seed(123)
        data = pd.DataFrame({
            "A": np.random.normal(0.001, 0.02, 100),
            "B": np.random.normal(0.0005, 0.015, 100),
        })
        opt = PortfolioOptimizer(data)
        result = opt.max_sharpe_ratio()
        weights = np.array(list(result["weights"].values()))
        assert np.isclose(weights.sum(), 1.0)
        assert np.all(weights >= 0)
