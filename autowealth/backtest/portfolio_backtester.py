"""
A 股组合级研究回测引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional

import pandas as pd

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
from autowealth.backtest.rebalance import generate_rebalance_dates
from autowealth.data.ashare_provider import AShareDataProvider


@dataclass
class PortfolioBacktestResult:
    """
    Container for portfolio backtest outputs.
    """

    equity_curve: pd.Series
    daily_returns: pd.Series
    annualized_return: float
    total_return: float
    max_drawdown: float
    volatility: float
    sharpe_ratio: float
    calmar_ratio: float
    turnover: float
    trade_log: pd.DataFrame
    holdings_by_period: pd.DataFrame
    annual_returns: pd.Series
    monthly_returns: pd.Series

    def to_dict(self) -> Dict[str, object]:
        return {
            "equity_curve": self.equity_curve,
            "daily_returns": self.daily_returns,
            "annualized_return": self.annualized_return,
            "total_return": self.total_return,
            "max_drawdown": self.max_drawdown,
            "volatility": self.volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "calmar_ratio": self.calmar_ratio,
            "turnover": self.turnover,
            "trade_log": self.trade_log,
            "holdings_by_period": self.holdings_by_period,
            "annual_returns": self.annual_returns,
            "monthly_returns": self.monthly_returns,
        }


class PortfolioBacktester:
    """
    Multi-symbol A 股 portfolio backtester for research use.

    This engine accepts target weights and simulates periodic rebalancing with
    configurable commission, stamp tax and slippage. It does not implement
    stock selection, trading APIs or live order execution.
    """

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        start_date: str = "2009-01-01",
        end_date: str = "2024-12-31",
        rebalance_frequency: str = "yearly",
        commission: float = 0.0003,
        stamp_tax: float = 0.0005,
        slippage: float = 0.0002,
        cash_weight: float = 0.0,
        max_position_weight: float = 1.0,
        data_provider: Optional[AShareDataProvider] = None,
    ):
        self.initial_capital = float(initial_capital)
        self.start_date = start_date
        self.end_date = end_date
        self.rebalance_frequency = rebalance_frequency
        self.commission = float(commission)
        self.stamp_tax = float(stamp_tax)
        self.slippage = float(slippage)
        self.cash_weight = float(cash_weight)
        self.max_position_weight = float(max_position_weight)
        self.data_provider = data_provider

        self._validate_config()

    def run(
        self,
        target_weights: Mapping[str, float],
        price_data: Optional[Mapping[str, pd.DataFrame]] = None,
        adjust: str = "qfq",
    ) -> Dict[str, object]:
        """
        Run a portfolio backtest.

        Args:
            target_weights: Symbol-to-target-weight mapping. Sum must not exceed
                the investable capital after ``cash_weight``.
            price_data: Optional normalized OHLCV DataFrames keyed by symbol.
                When omitted, data is fetched with ``AShareDataProvider``.
            adjust: AKShare adjustment mode used only when fetching data.
        """
        weights = self._validate_weights(target_weights)
        prices = self._prepare_price_matrix(weights, price_data, adjust)
        rebalance_dates = set(generate_rebalance_dates(prices.index, self.rebalance_frequency))

        shares = {symbol: 0.0 for symbol in weights}
        cash = self.initial_capital
        equity_points: List[Dict[str, float]] = []
        trade_log: List[Dict[str, object]] = []
        holdings_snapshots: List[Dict[str, object]] = []
        turnover_numerator = 0.0

        for date, row in prices.iterrows():
            portfolio_value = self._portfolio_value(cash, shares, row)

            if date in rebalance_dates:
                rebalance_result = self._rebalance(date, row, portfolio_value, cash, shares, weights)
                cash = rebalance_result["cash"]
                shares = rebalance_result["shares"]
                trade_log.extend(rebalance_result["trades"])
                holdings_snapshots.append(
                    self._holdings_snapshot(date, cash, shares, row, weights)
                )
                turnover_numerator += rebalance_result["turnover_value"]

            equity_points.append(
                {"date": date, "equity": self._portfolio_value(cash, shares, row)}
            )

        equity_curve = pd.DataFrame(equity_points).set_index("date")["equity"]
        returns = daily_returns(equity_curve)
        result = PortfolioBacktestResult(
            equity_curve=equity_curve,
            daily_returns=returns,
            annualized_return=annualized_return(equity_curve),
            total_return=total_return(equity_curve),
            max_drawdown=max_drawdown(equity_curve),
            volatility=volatility(returns),
            sharpe_ratio=sharpe_ratio(returns),
            calmar_ratio=calmar_ratio(equity_curve),
            turnover=turnover_numerator / self.initial_capital,
            trade_log=pd.DataFrame(trade_log),
            holdings_by_period=pd.DataFrame(holdings_snapshots),
            annual_returns=annual_returns(equity_curve),
            monthly_returns=monthly_returns(equity_curve),
        )
        return result.to_dict()

    def run_weight_schedule(
        self,
        target_weights_by_date: Mapping[object, Mapping[str, float]],
        price_data: Optional[Mapping[str, pd.DataFrame]] = None,
        adjust: str = "qfq",
    ) -> Dict[str, object]:
        """Run a backtest with a point-in-time target-weight schedule.

        This is a backward-compatible companion to ``run``. Every generated
        rebalance date must have one target-weight mapping. Symbols omitted from
        a period mapping receive a zero target weight for that rebalance.
        """
        if not target_weights_by_date:
            raise ValueError("target_weights_by_date cannot be empty")

        schedule: Dict[pd.Timestamp, Dict[str, float]] = {}
        symbols = set()
        for date, target_weights in target_weights_by_date.items():
            timestamp = pd.Timestamp(date).normalize()
            if timestamp in schedule:
                raise ValueError(f"duplicate target weight schedule date: {timestamp.date()}")
            validated = self._validate_weights(target_weights)
            schedule[timestamp] = validated
            symbols.update(validated)

        if not symbols:
            raise ValueError("target weight schedule contains no symbols")

        prices = self._prepare_price_matrix(
            {symbol: 0.0 for symbol in sorted(symbols)},
            price_data,
            adjust,
        )
        rebalance_dates = pd.DatetimeIndex(
            generate_rebalance_dates(prices.index, self.rebalance_frequency)
        ).normalize()
        missing_dates = [date for date in rebalance_dates if date not in schedule]
        if missing_dates:
            formatted = ", ".join(date.strftime("%Y-%m-%d") for date in missing_dates)
            raise ValueError(f"target weight schedule missing rebalance dates: {formatted}")

        shares = {symbol: 0.0 for symbol in sorted(symbols)}
        cash = self.initial_capital
        equity_points: List[Dict[str, float]] = []
        trade_log: List[Dict[str, object]] = []
        holdings_snapshots: List[Dict[str, object]] = []
        turnover_numerator = 0.0
        rebalance_date_set = set(rebalance_dates)

        for date, row in prices.iterrows():
            portfolio_value = self._portfolio_value(cash, shares, row)
            if date.normalize() in rebalance_date_set:
                period_weights = {
                    symbol: schedule[date.normalize()].get(symbol, 0.0)
                    for symbol in shares
                }
                rebalance_result = self._rebalance(
                    date,
                    row,
                    portfolio_value,
                    cash,
                    shares,
                    period_weights,
                )
                cash = rebalance_result["cash"]
                shares = rebalance_result["shares"]
                trade_log.extend(rebalance_result["trades"])
                holdings_snapshots.append(
                    self._holdings_snapshot(date, cash, shares, row, period_weights)
                )
                turnover_numerator += rebalance_result["turnover_value"]

            equity_points.append(
                {"date": date, "equity": self._portfolio_value(cash, shares, row)}
            )

        equity_curve = pd.DataFrame(equity_points).set_index("date")["equity"]
        returns = daily_returns(equity_curve)
        result = PortfolioBacktestResult(
            equity_curve=equity_curve,
            daily_returns=returns,
            annualized_return=annualized_return(equity_curve),
            total_return=total_return(equity_curve),
            max_drawdown=max_drawdown(equity_curve),
            volatility=volatility(returns),
            sharpe_ratio=sharpe_ratio(returns),
            calmar_ratio=calmar_ratio(equity_curve),
            turnover=turnover_numerator / self.initial_capital,
            trade_log=pd.DataFrame(trade_log),
            holdings_by_period=pd.DataFrame(holdings_snapshots),
            annual_returns=annual_returns(equity_curve),
            monthly_returns=monthly_returns(equity_curve),
        )
        return result.to_dict()

    def _validate_config(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        if self.cash_weight < 0 or self.cash_weight > 1:
            raise ValueError("cash_weight must be between 0 and 1")
        if self.max_position_weight <= 0 or self.max_position_weight > 1:
            raise ValueError("max_position_weight must be between 0 and 1")
        for field_name in ("commission", "stamp_tax", "slippage"):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(f"{field_name} must be non-negative")

    def _validate_weights(self, target_weights: Mapping[str, float]) -> Dict[str, float]:
        if not target_weights:
            raise ValueError("target_weights cannot be empty")

        weights = {str(symbol): float(weight) for symbol, weight in target_weights.items()}
        for symbol, weight in weights.items():
            if weight < 0:
                raise ValueError(f"target weight for {symbol} cannot be negative")
            if weight > self.max_position_weight:
                raise ValueError(
                    f"target weight for {symbol} exceeds max_position_weight "
                    f"({weight:.4f} > {self.max_position_weight:.4f})"
                )

        weight_sum = sum(weights.values())
        if weight_sum > 1 + 1e-12:
            raise ValueError("target weight sum cannot exceed 1")
        if weight_sum > 1 - self.cash_weight + 1e-12:
            raise ValueError("target weights plus cash_weight cannot exceed 1")
        return weights

    def _prepare_price_matrix(
        self,
        weights: Mapping[str, float],
        price_data: Optional[Mapping[str, pd.DataFrame]],
        adjust: str,
    ) -> pd.DataFrame:
        frames = {}
        for symbol in weights:
            df = self._load_symbol_data(symbol, price_data, adjust)
            data = df.copy()
            data["date"] = pd.to_datetime(data["date"], errors="coerce")
            data["close"] = pd.to_numeric(data["close"], errors="coerce")
            data = data.dropna(subset=["date", "close"])
            data = data[(data["date"] >= pd.to_datetime(self.start_date))]
            data = data[(data["date"] <= pd.to_datetime(self.end_date))]
            if data.empty:
                raise ValueError(f"no price data available for {symbol}")
            frames[symbol] = data.set_index("date")["close"].sort_index()

        prices = pd.concat(frames, axis=1).sort_index()
        prices = prices.ffill().dropna(how="any")
        if prices.empty:
            raise ValueError("price matrix is empty after alignment")
        return prices

    def _load_symbol_data(
        self,
        symbol: str,
        price_data: Optional[Mapping[str, pd.DataFrame]],
        adjust: str,
    ) -> pd.DataFrame:
        if price_data is not None:
            if symbol not in price_data:
                raise ValueError(f"missing price_data for {symbol}")
            return price_data[symbol]

        provider = self.data_provider or AShareDataProvider()
        return provider.get_daily(symbol, self.start_date, self.end_date, adjust=adjust)

    def _rebalance(
        self,
        date: pd.Timestamp,
        prices: pd.Series,
        portfolio_value: float,
        cash: float,
        shares: Dict[str, float],
        weights: Mapping[str, float],
    ) -> Dict[str, object]:
        target_shares = {
            symbol: (portfolio_value * weight) / prices[symbol]
            for symbol, weight in weights.items()
        }
        trades = []
        turnover_value = 0.0
        new_shares = shares.copy()

        for symbol, target_share in target_shares.items():
            current_share = new_shares[symbol]
            diff = target_share - current_share
            if diff >= 0:
                continue

            shares_to_sell = abs(diff)
            trade_value = shares_to_sell * prices[symbol]
            cost = trade_value * (self.commission + self.stamp_tax + self.slippage)
            cash += trade_value - cost
            new_shares[symbol] -= shares_to_sell
            turnover_value += trade_value
            trades.append(
                self._trade_record(date, symbol, "sell", shares_to_sell, prices[symbol], trade_value, cost)
            )

        buy_orders = []
        for symbol, target_share in target_shares.items():
            diff = target_share - new_shares[symbol]
            if diff <= 0:
                continue
            trade_value = diff * prices[symbol]
            total_cost = trade_value * (1 + self.commission + self.slippage)
            buy_orders.append((symbol, diff, trade_value, total_cost))

        total_buy_cost = sum(order[3] for order in buy_orders)
        buy_scale = min(1.0, cash / total_buy_cost) if total_buy_cost > 0 else 1.0

        for symbol, requested_shares, requested_value, _ in buy_orders:
            shares_to_buy = requested_shares * buy_scale
            trade_value = requested_value * buy_scale
            cost = trade_value * (self.commission + self.slippage)
            cash -= trade_value + cost
            new_shares[symbol] += shares_to_buy
            turnover_value += trade_value
            trades.append(
                self._trade_record(date, symbol, "buy", shares_to_buy, prices[symbol], trade_value, cost)
            )

        return {
            "cash": max(float(cash), 0.0),
            "shares": new_shares,
            "trades": trades,
            "turnover_value": turnover_value,
        }

    def _holdings_snapshot(
        self,
        date: pd.Timestamp,
        cash: float,
        shares: Mapping[str, float],
        prices: pd.Series,
        weights: Mapping[str, float],
    ) -> Dict[str, object]:
        equity = self._portfolio_value(cash, shares, prices)
        snapshot: Dict[str, object] = {"date": date, "equity": equity, "cash": cash}
        snapshot["cash_weight"] = cash / equity if equity else 0.0
        for symbol in weights:
            value = shares[symbol] * prices[symbol]
            snapshot[f"{symbol}_shares"] = shares[symbol]
            snapshot[f"{symbol}_weight"] = value / equity if equity else 0.0
        return snapshot

    @staticmethod
    def _portfolio_value(cash: float, shares: Mapping[str, float], prices: pd.Series) -> float:
        return float(cash + sum(shares[symbol] * prices[symbol] for symbol in shares))

    @staticmethod
    def _trade_record(
        date: pd.Timestamp,
        symbol: str,
        side: str,
        shares: float,
        price: float,
        trade_value: float,
        cost: float,
    ) -> Dict[str, object]:
        return {
            "date": date,
            "symbol": symbol,
            "side": side,
            "shares": float(shares),
            "price": float(price),
            "trade_value": float(trade_value),
            "cost": float(cost),
        }

