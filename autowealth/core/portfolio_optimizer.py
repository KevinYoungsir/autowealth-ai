"""
Portfolio Optimizer Module

Implements mean-variance optimization, max Sharpe ratio, min variance portfolio,
and efficient frontier calculation without external optimization libraries.
"""

import numpy as np
import pandas as pd
from typing import Optional, Tuple, List, Dict


class PortfolioOptimizer:
    """
    Portfolio optimizer implementing Markowitz mean-variance optimization.

    Uses numpy for matrix operations and implements optimization via
    analytical solutions and grid search (no cvxpy dependency).
    """

    def __init__(self, returns_data: pd.DataFrame):
        """
        Initialize the portfolio optimizer.

        Args:
            returns_data: DataFrame of asset returns (each column is an asset).
        """
        self.returns = returns_data.dropna()
        self.symbols = list(self.returns.columns)
        self.n_assets = len(self.symbols)

        # Compute mean returns and covariance matrix
        self.mean_returns = self.returns.mean().values
        self.cov_matrix = self.returns.cov().values

        # Annualization factor (assuming daily returns)
        self.ann_factor = 252

    def _portfolio_return(self, weights: np.ndarray) -> float:
        """Calculate annualized portfolio return."""
        return np.dot(weights, self.mean_returns) * self.ann_factor

    def _portfolio_variance(self, weights: np.ndarray) -> float:
        """Calculate annualized portfolio variance."""
        return np.dot(weights.T, np.dot(self.cov_matrix, weights)) * self.ann_factor

    def _portfolio_volatility(self, weights: np.ndarray) -> float:
        """Calculate annualized portfolio volatility (std dev)."""
        return np.sqrt(self._portfolio_variance(weights))

    def _sharpe_ratio(self, weights: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        p_return = self._portfolio_return(weights)
        p_vol = self._portfolio_volatility(weights)
        if p_vol == 0:
            return -np.inf
        return (p_return - risk_free_rate) / p_vol

    def _validate_weights(self, weights: np.ndarray) -> np.ndarray:
        """Ensure weights sum to 1 and are non-negative."""
        weights = np.maximum(weights, 0)
        if weights.sum() == 0:
            weights = np.ones(self.n_assets) / self.n_assets
        else:
            weights = weights / weights.sum()
        return weights

    def mean_variance_optimization(
        self, target_return: Optional[float] = None
    ) -> Dict:
        """
        Markowitz mean-variance optimization.

        Finds the minimum variance portfolio for a given target return.
        If target_return is None, returns the global minimum variance portfolio.

        Args:
            target_return: Target annualized return (default: None for min variance).

        Returns:
            Dictionary with 'weights', 'expected_return', 'volatility', 'sharpe_ratio'.
        """
        if target_return is None:
            return self.min_variance_portfolio()

        # Analytical solution using Lagrange multipliers for constrained optimization
        # Minimize: w^T * Sigma * w
        # Subject to: w^T * mu = target_return / ann_factor
        #             sum(w) = 1
        #             w >= 0 (handled via projection)

        mu = self.mean_returns
        Sigma = self.cov_matrix

        # Try analytical solution first (allowing short sales)
        ones = np.ones(self.n_assets)
        Sigma_inv = np.linalg.pinv(Sigma)

        a = np.dot(mu.T, np.dot(Sigma_inv, mu))
        b = np.dot(mu.T, np.dot(Sigma_inv, ones))
        c = np.dot(ones.T, np.dot(Sigma_inv, ones))

        target_daily = target_return / self.ann_factor

        denominator = a * c - b ** 2
        if abs(denominator) < 1e-10:
            # Fallback to equal weights if matrix is singular
            weights = np.ones(self.n_assets) / self.n_assets
        else:
            lambda1 = (c * target_daily - b) / denominator
            lambda2 = (a - b * target_daily) / denominator
            weights = Sigma_inv @ (lambda1 * mu + lambda2 * ones)

        # Project to non-negative weights
        weights = self._validate_weights(weights)

        return {
            "weights": dict(zip(self.symbols, weights)),
            "expected_return": self._portfolio_return(weights),
            "volatility": self._portfolio_volatility(weights),
            "sharpe_ratio": self._sharpe_ratio(weights),
        }

    def max_sharpe_ratio(self, risk_free_rate: float = 0.02) -> Dict:
        """
        Find the maximum Sharpe ratio portfolio.

        Uses analytical solution for the tangency portfolio when short sales
        are allowed, then projects to non-negative weights. Falls back to
        numerical search if needed.

        Args:
            risk_free_rate: Annual risk-free rate (default: 0.02).

        Returns:
            Dictionary with 'weights', 'expected_return', 'volatility', 'sharpe_ratio'.
        """
        mu = self.mean_returns
        Sigma = self.cov_matrix
        Sigma_inv = np.linalg.pinv(Sigma)

        # Tangency portfolio (analytical with short sales)
        excess_returns = mu - risk_free_rate / self.ann_factor
        weights = Sigma_inv @ excess_returns
        weights = self._validate_weights(weights)

        # Fine-tune with local search for non-negative constraint
        best_sharpe = self._sharpe_ratio(weights, risk_free_rate)
        best_weights = weights.copy()

        # Simple hill-climbing improvement
        np.random.seed(42)
        for _ in range(1000):
            # Random perturbation
            perturbation = np.random.normal(0, 0.1, self.n_assets)
            new_weights = best_weights + perturbation
            new_weights = self._validate_weights(new_weights)
            new_sharpe = self._sharpe_ratio(new_weights, risk_free_rate)
            if new_sharpe > best_sharpe:
                best_sharpe = new_sharpe
                best_weights = new_weights

        return {
            "weights": dict(zip(self.symbols, best_weights)),
            "expected_return": self._portfolio_return(best_weights),
            "volatility": self._portfolio_volatility(best_weights),
            "sharpe_ratio": best_sharpe,
        }

    def min_variance_portfolio(self) -> Dict:
        """
        Find the global minimum variance portfolio.

        Returns:
            Dictionary with 'weights', 'expected_return', 'volatility', 'sharpe_ratio'.
        """
        Sigma = self.cov_matrix
        Sigma_inv = np.linalg.pinv(Sigma)
        ones = np.ones(self.n_assets)

        # Analytical solution: w = Sigma^{-1} * 1 / (1^T * Sigma^{-1} * 1)
        denom = np.dot(ones.T, np.dot(Sigma_inv, ones))
        if abs(denom) < 1e-10:
            weights = np.ones(self.n_assets) / self.n_assets
        else:
            weights = np.dot(Sigma_inv, ones) / denom

        weights = self._validate_weights(weights)

        return {
            "weights": dict(zip(self.symbols, weights)),
            "expected_return": self._portfolio_return(weights),
            "volatility": self._portfolio_volatility(weights),
            "sharpe_ratio": self._sharpe_ratio(weights),
        }

    def get_efficient_frontier(self, n_points: int = 50) -> List[Dict]:
        """
        Compute the efficient frontier.

        Args:
            n_points: Number of points on the frontier (default: 50).

        Returns:
            List of dictionaries, each containing 'return', 'volatility', 'sharpe_ratio', 'weights'.
        """
        # Find return range
        min_var_result = self.min_variance_portfolio()
        min_return = min_var_result["expected_return"]

        # Max return is the max individual asset return
        max_return = np.max(self.mean_returns) * self.ann_factor

        # Also consider max Sharpe portfolio
        max_sharpe_result = self.max_sharpe_ratio()

        targets = np.linspace(min_return, max_return, n_points)
        frontier = []

        for target in targets:
            result = self.mean_variance_optimization(target_return=target)
            frontier.append(
                {
                    "return": result["expected_return"],
                    "volatility": result["volatility"],
                    "sharpe_ratio": result["sharpe_ratio"],
                    "weights": result["weights"],
                }
            )

        return frontier

    def allocate_weights(
        self, symbols: List[str], total_value: float = 100000.0
    ) -> Dict[str, float]:
        """
        Allocate capital based on optimal weights.

        Args:
            symbols: List of asset symbols to allocate.
            total_value: Total capital to allocate (default: 100000).

        Returns:
            Dictionary mapping symbol to allocated dollar amount.
        """
        # Use max Sharpe ratio as default strategy
        result = self.max_sharpe_ratio()
        weights = result["weights"]

        allocation = {}
        for symbol in symbols:
            if symbol in weights:
                allocation[symbol] = weights[symbol] * total_value
            else:
                allocation[symbol] = 0.0

        return allocation
