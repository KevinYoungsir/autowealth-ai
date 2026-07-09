"""
A 股组合级研究回测模块。

该包只提供研究用途的组合回测、调仓日期和绩效指标计算能力。
"""

from autowealth.backtest.metrics import (
    annual_returns,
    annualized_return,
    calmar_ratio,
    daily_returns,
    max_drawdown,
    monthly_returns,
    sharpe_ratio,
    total_return,
    volatility,
)
from autowealth.backtest.portfolio_backtester import PortfolioBacktester
from autowealth.backtest.rebalance import generate_rebalance_dates

__all__ = [
    "PortfolioBacktester",
    "annual_returns",
    "annualized_return",
    "calmar_ratio",
    "daily_returns",
    "generate_rebalance_dates",
    "max_drawdown",
    "monthly_returns",
    "sharpe_ratio",
    "total_return",
    "volatility",
]

