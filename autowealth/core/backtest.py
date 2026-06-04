"""
Backtest Engine Module

Implements a simple backtesting engine for trading strategies.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple


class BacktestEngine:
    """
    Backtest engine for simulating trading strategies.

    Supports buy/sell/hold signals, commission handling, and
    comprehensive performance metrics.
    """

    def __init__(self, initial_capital: float = 100000.0):
        """
        Initialize the backtest engine.

        Args:
            initial_capital: Starting capital (default: 100000).
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0.0  # Number of shares held
        self.equity_curve: List[float] = []
        self.trade_history: List[Dict] = []
        self.signals_history: List[str] = []
        self.price_history: List[float] = []
        self._in_position = False
        self._entry_price = 0.0
        self._entry_time = None

    def run_strategy(
        self,
        data: pd.DataFrame,
        signals: List[str],
        commission: float = 0.001,
    ) -> "BacktestEngine":
        """
        Run a backtest given price data and trading signals.

        Args:
            data: DataFrame with 'Close' price column. Index should be datetime.
            signals: List of 'buy'/'sell'/'hold' matching data length.
            commission: Commission rate per trade (default: 0.001 = 0.1%).

        Returns:
            Self for method chaining.
        """
        if len(data) != len(signals):
            raise ValueError(
                f"Data length ({len(data)}) must match signals length ({len(signals)})"
            )

        prices = data["Close"].values
        dates = data.index if hasattr(data.index, "to_list") else list(range(len(data)))

        self.equity_curve = []
        self.trade_history = []
        self.signals_history = signals.copy()
        self.price_history = prices.tolist()

        self.capital = self.initial_capital
        self.position = 0.0
        self._in_position = False
        self._entry_price = 0.0
        self._entry_time = None

        for i, (price, signal, date) in enumerate(zip(prices, signals, dates)):
            if signal == "buy" and not self._in_position:
                # Execute buy
                cost = price * (1 + commission)
                shares = self.capital / cost
                self.position = shares
                self.capital = 0.0
                self._in_position = True
                self._entry_price = price
                self._entry_time = date

                self.trade_history.append(
                    {
                        "type": "buy",
                        "price": price,
                        "shares": shares,
                        "cost": shares * price * commission,
                        "timestamp": date,
                        "equity": self._current_equity(price),
                    }
                )

            elif signal == "sell" and self._in_position:
                # Execute sell
                proceeds = self.position * price * (1 - commission)
                self.capital = proceeds
                exit_equity = self.capital

                self.trade_history.append(
                    {
                        "type": "sell",
                        "price": price,
                        "shares": self.position,
                        "cost": self.position * price * commission,
                        "timestamp": date,
                        "equity": exit_equity,
                        "pnl": exit_equity - (self._entry_price * self.position),
                        "return_pct": (price / self._entry_price - 1) * 100,
                    }
                )

                self.position = 0.0
                self._in_position = False
                self._entry_price = 0.0
                self._entry_time = None

            # Record equity
            current_equity = self._current_equity(price)
            self.equity_curve.append(current_equity)

        return self

    def _current_equity(self, price: float) -> float:
        """Calculate current equity given current price."""
        if self._in_position:
            return self.position * price
        return self.capital

    def get_performance_metrics(self) -> Dict:
        """
        Calculate and return backtest performance metrics.

        Returns:
            Dictionary with performance metrics.
        """
        if not self.equity_curve:
            return {
                "total_return": 0.0,
                "annualized_return": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
                "final_equity": self.initial_capital,
            }

        equity = np.array(self.equity_curve)
        final_equity = equity[-1]

        # Total return
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        # Annualized return (assume 252 trading days)
        n_days = len(equity)
        if n_days > 1 and total_return > -1:
            annualized_return = (1 + total_return) ** (252 / n_days) - 1
        else:
            annualized_return = total_return

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak
        max_drawdown = np.max(drawdown)

        # Daily returns for Sharpe
        daily_returns = np.diff(equity) / equity[:-1]
        if len(daily_returns) > 1 and np.std(daily_returns) > 0:
            sharpe_ratio = (np.mean(daily_returns) * 252) / (
                np.std(daily_returns) * np.sqrt(252)
            )
        else:
            sharpe_ratio = 0.0

        # Win rate from completed trades
        completed_trades = [
            t for t in self.trade_history if t["type"] == "sell" and "pnl" in t
        ]
        if completed_trades:
            wins = sum(1 for t in completed_trades if t["pnl"] > 0)
            win_rate = wins / len(completed_trades)
        else:
            win_rate = 0.0

        trade_count = len(completed_trades)

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "win_rate": win_rate,
            "trade_count": trade_count,
            "final_equity": final_equity,
            "initial_capital": self.initial_capital,
        }

    def get_equity_curve(self) -> pd.Series:
        """
        Return the equity curve as a pandas Series.

        Returns:
            pandas Series of equity values.
        """
        if not self.equity_curve:
            return pd.Series(dtype=float)
        return pd.Series(self.equity_curve)

    def get_trade_history(self) -> List[Dict]:
        """
        Return the trade history.

        Returns:
            List of trade dictionaries.
        """
        return self.trade_history.copy()
