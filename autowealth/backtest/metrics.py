"""
Portfolio performance metrics for research backtests.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


def daily_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate daily percentage returns from an equity curve.
    """
    equity = _as_series(equity_curve)
    return equity.pct_change().fillna(0.0)


def total_return(equity_curve: pd.Series) -> float:
    """
    Calculate total return over the full period.
    """
    equity = _as_series(equity_curve)
    if equity.empty or equity.iloc[0] == 0:
        return 0.0
    return float(equity.iloc[-1] / equity.iloc[0] - 1)


def annualized_return(equity_curve: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """
    Calculate compound annualized return.
    """
    equity = _as_series(equity_curve)
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0

    gross_return = equity.iloc[-1] / equity.iloc[0]
    if gross_return <= 0:
        return -1.0

    years = len(equity) / periods_per_year
    if years <= 0:
        return 0.0
    return float(gross_return ** (1 / years) - 1)


def max_drawdown(equity_curve: pd.Series) -> float:
    """
    Calculate maximum drawdown as a negative decimal value.
    """
    equity = _as_series(equity_curve)
    if equity.empty:
        return 0.0

    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return float(drawdown.min())


def volatility(returns: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """
    Calculate annualized volatility.
    """
    values = _as_series(returns).dropna()
    if len(values) < 2:
        return 0.0
    return float(values.std(ddof=1) * np.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """
    Calculate annualized Sharpe ratio.
    """
    values = _as_series(returns).dropna()
    if len(values) < 2:
        return 0.0

    excess = values - risk_free_rate / periods_per_year
    std = excess.std(ddof=1)
    if std == 0 or pd.isna(std):
        return 0.0
    return float(excess.mean() / std * np.sqrt(periods_per_year))


def calmar_ratio(equity_curve: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """
    Calculate Calmar ratio using annualized return divided by absolute max drawdown.
    """
    drawdown = abs(max_drawdown(equity_curve))
    if drawdown == 0:
        return 0.0
    return float(annualized_return(equity_curve, periods_per_year) / drawdown)


def annual_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate calendar-year returns.
    """
    equity = _as_series(equity_curve)
    if equity.empty:
        return pd.Series(dtype=float)
    return equity.resample("YE").last().pct_change().dropna()


def monthly_returns(equity_curve: pd.Series) -> pd.Series:
    """
    Calculate calendar-month returns.
    """
    equity = _as_series(equity_curve)
    if equity.empty:
        return pd.Series(dtype=float)
    return equity.resample("ME").last().pct_change().dropna()


def _as_series(values: pd.Series) -> pd.Series:
    if isinstance(values, pd.DataFrame):
        if values.shape[1] != 1:
            raise ValueError("Expected a single-column DataFrame or Series")
        values = values.iloc[:, 0]
    series = pd.Series(values).astype(float)
    if not isinstance(series.index, pd.DatetimeIndex):
        return series
    return series.sort_index()

