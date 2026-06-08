"""
演示数据生成器 - 生成逼真的模拟金融数据用于演示和测试

支持股票、加密货币、投资组合和市场数据的模拟生成。
数据特征包括：趋势、波动率聚类、成交量变化等真实市场行为。
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class DemoDataGenerator:
    """演示数据生成器

    生成逼真的模拟金融数据，用于演示和测试环境。
    数据具有真实市场的统计特征，包括趋势、波动率聚类、成交量变化等。
    """

    # 常见股票的基准价格和波动率参数
    STOCK_PROFILES = {
        "AAPL": {"base_price": 175.0, "volatility": 0.025, "trend": 0.0003, "name": "Apple Inc."},
        "GOOGL": {"base_price": 140.0, "volatility": 0.028, "trend": 0.0002, "name": "Alphabet Inc."},
        "MSFT": {"base_price": 380.0, "volatility": 0.022, "trend": 0.0004, "name": "Microsoft Corp."},
        "AMZN": {"base_price": 185.0, "volatility": 0.030, "trend": 0.0003, "name": "Amazon.com Inc."},
        "META": {"base_price": 500.0, "volatility": 0.035, "trend": 0.0002, "name": "Meta Platforms Inc."},
        "TSLA": {"base_price": 250.0, "volatility": 0.045, "trend": 0.0001, "name": "Tesla Inc."},
        "NVDA": {"base_price": 900.0, "volatility": 0.040, "trend": 0.0005, "name": "NVIDIA Corp."},
        "JPM": {"base_price": 195.0, "volatility": 0.020, "trend": 0.0002, "name": "JPMorgan Chase"},
        "V": {"base_price": 280.0, "volatility": 0.018, "trend": 0.0002, "name": "Visa Inc."},
        "JNJ": {"base_price": 155.0, "volatility": 0.015, "trend": 0.0001, "name": "Johnson & Johnson"},
        "600519.SS": {"base_price": 1800.0, "volatility": 0.022, "trend": 0.0001, "name": "贵州茅台"},
        "000001.SS": {"base_price": 3200.0, "volatility": 0.018, "trend": 0.0001, "name": "上证指数"},
"600545.SS": {"base_price": 8.5, "volatility": 0.028, "trend": 0.0001, "name": "卓郎智能"},
        "600519.SS": {"base_price": 1800.0, "volatility": 0.022, "trend": 0.0001, "name": "贵州茅台"},
        "000001.SS": {"base_price": 3200.0, "volatility": 0.018, "trend": 0.0001, "name": "上证指数"},
        "000858.SZ": {"base_price": 150.0, "volatility": 0.025, "trend": 0.0002, "name": "五粮液"},
        "002594.SZ": {"base_price": 280.0, "volatility": 0.035, "trend": 0.0003, "name": "比亚迪"},
        "300750.SZ": {"base_price": 220.0, "volatility": 0.040, "trend": 0.0002, "name": "宁德时代"},
        "601318.SS": {"base_price": 48.0, "volatility": 0.025, "trend": 0.0001, "name": "中国平安"},
        "600036.SS": {"base_price": 35.0, "volatility": 0.022, "trend": 0.0001, "name": "招商银行"},
        "000333.SZ": {"base_price": 65.0, "volatility": 0.025, "trend": 0.0002, "name": "美的集团"},
        "002415.SZ": {"base_price": 32.0, "volatility": 0.030, "trend": 0.0001, "name": "海康威视"},
    }

    # 常见加密货币的基准价格和波动率参数
    CRYPTO_PROFILES = {
        "BTCUSDT": {"base_price": 65000.0, "volatility": 0.035, "trend": 0.0003, "name": "Bitcoin"},
        "ETHUSDT": {"base_price": 3400.0, "volatility": 0.040, "trend": 0.0002, "name": "Ethereum"},
        "BNBUSDT": {"base_price": 580.0, "volatility": 0.038, "trend": 0.0001, "name": "BNB"},
        "SOLUSDT": {"base_price": 170.0, "volatility": 0.050, "trend": 0.0002, "name": "Solana"},
        "ADAUSDT": {"base_price": 0.65, "volatility": 0.045, "trend": 0.0000, "name": "Cardano"},
        "XRPUSDT": {"base_price": 0.55, "volatility": 0.042, "trend": 0.0001, "name": "Ripple"},
        "DOGEUSDT": {"base_price": 0.15, "volatility": 0.055, "trend": 0.0000, "name": "Dogecoin"},
    }

    def __init__(self, seed: int = 42):
        """
        初始化演示数据生成器

        Args:
            seed: 随机种子，确保数据可复现
        """
        self.rng = np.random.RandomState(seed)

    def generate_stock_data(
        self,
        symbol: str = "AAPL",
        days: int = 365,
        base_price: Optional[float] = None,
        volatility: Optional[float] = None,
        trend: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        生成逼真的模拟股票数据

        使用几何布朗运动 + 波动率聚类模型生成数据，
        具有真实市场的统计特征。

        Args:
            symbol: 股票代码
            days: 生成的交易日数量
            base_price: 基准价格（默认从配置中获取）
            volatility: 日波动率（默认从配置中获取）
            trend: 日趋势漂移率（默认从配置中获取）

        Returns:
            包含 Open, High, Low, Close, Volume 列的 DataFrame，以日期为索引
        """
        # 获取股票参数
        profile = self.STOCK_PROFILES.get(symbol, {})
        base_price = base_price or profile.get("base_price", 100.0)
        volatility = volatility or profile.get("volatility", 0.025)
        trend = trend or profile.get("trend", 0.0002)

        # 生成日期序列（排除周末）
        end_date = datetime.now()
        dates = []
        current = end_date - timedelta(days=days * 2)
        while len(dates) < days:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current += timedelta(days=1)
        dates = dates[-days:]

        # 使用 GARCH(1,1) 模拟波动率聚类
        n = len(dates)
        returns = np.zeros(n)
        sigma = np.zeros(n)
        sigma[0] = volatility

        omega = volatility ** 2 * 0.05  # 长期方差
        alpha = 0.10  # ARCH 系数（近期冲击影响）
        beta = 0.85  # GARCH 系数（前期方差影响）

        for i in range(1, n):
            # GARCH 波动率更新
            sigma[i] = np.sqrt(omega + alpha * returns[i - 1] ** 2 + beta * sigma[i - 1] ** 2)
            # 带趋势的收益率
            returns[i] = trend + sigma[i] * self.rng.standard_normal()

        # 构建价格序列
        prices = base_price * np.exp(np.cumsum(returns))

        # 生成 OHLCV 数据
        open_prices = prices * (1 + self.rng.normal(0, 0.003, n))
        close_prices = prices
        intra_vol = sigma * prices
        high_prices = np.maximum(open_prices, close_prices) + np.abs(self.rng.normal(0, intra_vol * 0.3))
        low_prices = np.minimum(open_prices, close_prices) - np.abs(self.rng.normal(0, intra_vol * 0.3))

        # 成交量：基础成交量 + 随机变化 + 波动率影响
        base_volume = base_price * 1000000  # 基础成交量与价格相关
        volume = base_volume * (
            1 + 0.3 * self.rng.normal(size=n)
            + 0.5 * (sigma / volatility - 1)  # 波动率增大时成交量增加
        )
        volume = np.maximum(volume, base_volume * 0.1)  # 成交量下限

        df = pd.DataFrame({
            "Open": np.round(open_prices, 2),
            "High": np.round(high_prices, 2),
            "Low": np.round(low_prices, 2),
            "Close": np.round(close_prices, 2),
            "Volume": np.round(volume).astype(int),
        }, index=pd.DatetimeIndex(dates, name="Date"))

        # 确保 High >= Low
        df["High"] = df[["High", "Low", "Open", "Close"]].max(axis=1)
        df["Low"] = df[["High", "Low", "Open", "Close"]].min(axis=1)

        logger.info(f"生成模拟股票数据: {symbol}, {days}个交易日, "
                     f"起始价={base_price:.2f}, 终止价={prices[-1]:.2f}")

        return df

    def generate_crypto_data(
        self,
        symbol: str = "BTCUSDT",
        days: int = 365,
        base_price: Optional[float] = None,
        volatility: Optional[float] = None,
        trend: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        生成模拟加密货币数据

        加密货币数据具有更高的波动率和7x24交易特征。

        Args:
            symbol: 加密货币交易对 (如 BTCUSDT, ETHUSDT)
            days: 生成的天数
            base_price: 基准价格
            volatility: 日波动率
            trend: 日趋势漂移率

        Returns:
            包含 Open, High, Low, Close, Volume 列的 DataFrame
        """
        # 获取加密货币参数
        profile = self.CRYPTO_PROFILES.get(symbol, {})
        base_price = base_price or profile.get("base_price", 100.0)
        volatility = volatility or profile.get("volatility", 0.04)
        trend = trend or profile.get("trend", 0.0002)

        # 加密货币7x24交易，生成连续日期
        end_date = datetime.now()
        dates = [end_date - timedelta(days=days - i - 1) for i in range(days)]

        n = len(dates)

        # 使用带跳跃的模型（模拟加密货币的突发波动）
        returns = np.zeros(n)
        sigma = np.zeros(n)
        sigma[0] = volatility

        omega = volatility ** 2 * 0.05
        alpha = 0.15  # 更高的ARCH系数，加密货币冲击影响更大
        beta = 0.80

        for i in range(1, n):
            sigma[i] = np.sqrt(omega + alpha * returns[i - 1] ** 2 + beta * sigma[i - 1] ** 2)
            returns[i] = trend + sigma[i] * self.rng.standard_normal()

            # 随机跳跃（约5%的概率发生较大波动）
            if self.rng.random() < 0.05:
                jump_size = self.rng.choice([-1, 1]) * self.rng.uniform(0.02, 0.08)
                returns[i] += jump_size

        # 构建价格序列
        prices = base_price * np.exp(np.cumsum(returns))

        # OHLCV
        open_prices = prices * (1 + self.rng.normal(0, 0.005, n))
        close_prices = prices
        intra_vol = sigma * prices
        high_prices = np.maximum(open_prices, close_prices) + np.abs(self.rng.normal(0, intra_vol * 0.4))
        low_prices = np.minimum(open_prices, close_prices) - np.abs(self.rng.normal(0, intra_vol * 0.4))

        # 加密货币成交量模式：更不稳定
        base_volume = base_price * 500000
        volume = base_volume * (
            1 + 0.5 * self.rng.normal(size=n)
            + 0.8 * (sigma / volatility - 1)
        )
        volume = np.maximum(volume, base_volume * 0.05)

        df = pd.DataFrame({
            "Open": np.round(open_prices, 4),
            "High": np.round(high_prices, 4),
            "Low": np.round(low_prices, 4),
            "Close": np.round(close_prices, 4),
            "Volume": np.round(volume).astype(int),
        }, index=pd.DatetimeIndex(dates, name="Date"))

        df["High"] = df[["High", "Low", "Open", "Close"]].max(axis=1)
        df["Low"] = df[["High", "Low", "Open", "Close"]].min(axis=1)

        logger.info(f"生成模拟加密货币数据: {symbol}, {days}天, "
                     f"起始价={base_price:.4f}, 终止价={prices[-1]:.4f}")

        return df

    def generate_portfolio(self) -> Dict:
        """
        生成模拟投资组合

        Returns:
            包含持仓信息的字典，每项包含 symbol, name, quantity, cost_basis, current_price
        """
        holdings = [
            {"symbol": "AAPL", "name": "Apple Inc.", "quantity": 100, "cost_basis": 165.0},
            {"symbol": "GOOGL", "name": "Alphabet Inc.", "quantity": 50, "cost_basis": 130.0},
            {"symbol": "MSFT", "name": "Microsoft Corp.", "quantity": 75, "cost_basis": 350.0},
            {"symbol": "AMZN", "name": "Amazon.com Inc.", "quantity": 30, "cost_basis": 170.0},
            {"symbol": "NVDA", "name": "NVIDIA Corp.", "quantity": 20, "cost_basis": 800.0},
            {"symbol": "TSLA", "name": "Tesla Inc.", "quantity": 40, "cost_basis": 220.0},
            {"symbol": "JPM", "name": "JPMorgan Chase", "quantity": 80, "cost_basis": 180.0},
            {"symbol": "V", "name": "Visa Inc.", "quantity": 60, "cost_basis": 260.0},
        ]

        # 为每个持仓生成当前价格（基于成本价 + 随机变化）
        for holding in holdings:
            change_pct = self.rng.normal(0.05, 0.15)  # 平均5%收益，15%标准差
            holding["current_price"] = round(holding["cost_basis"] * (1 + change_pct), 2)
            holding["market_value"] = round(
                holding["quantity"] * holding["current_price"], 2
            )
            holding["gain_loss"] = round(
                (holding["current_price"] - holding["cost_basis"]) * holding["quantity"], 2
            )
            holding["return_pct"] = round(
                (holding["current_price"] - holding["cost_basis"]) / holding["cost_basis"] * 100, 2
            )

        total_value = sum(h["market_value"] for h in holdings)
        total_cost = sum(h["cost_basis"] * h["quantity"] for h in holdings)
        total_gain_loss = sum(h["gain_loss"] for h in holdings)

        portfolio = {
            "holdings": holdings,
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_gain_loss": round(total_gain_loss, 2),
            "total_return_pct": round(total_gain_loss / total_cost * 100, 2) if total_cost > 0 else 0,
        }

        logger.info(f"生成模拟投资组合: {len(holdings)}只股票, 总市值={total_value:,.2f}")

        return portfolio

    def generate_market_data(self) -> Dict[str, pd.DataFrame]:
        """
        生成模拟市场指数数据

        Returns:
            字典，key为指数代码，value为DataFrame
        """
        indices_config = {
            "^GSPC": {"name": "S&P 500", "base_price": 5200, "volatility": 0.012},
            "^DJI": {"name": "Dow Jones", "base_price": 39000, "volatility": 0.011},
            "^IXIC": {"name": "NASDAQ", "base_price": 16500, "volatility": 0.016},
            "^FTSE": {"name": "FTSE 100", "base_price": 8200, "volatility": 0.013},
            "^N225": {"name": "Nikkei 225", "base_price": 39000, "volatility": 0.015},
            "000001.SS": {"name": "上证指数", "base_price": 3100, "volatility": 0.014},
            "^HSI": {"name": "恒生指数", "base_price": 18000, "volatility": 0.018},
        }

        market_data = {}
        for symbol, config in indices_config.items():
            df = self.generate_stock_data(
                symbol=symbol,
                days=180,
                base_price=config["base_price"],
                volatility=config["volatility"],
                trend=0.0001,
            )
            market_data[symbol] = df

        logger.info(f"生成模拟市场数据: {len(market_data)}个指数")

        return market_data

    def generate_multi_stock_data(
        self,
        symbols: Optional[List[str]] = None,
        days: int = 365,
    ) -> Dict[str, pd.DataFrame]:
        """
        批量生成多只股票的模拟数据

        Args:
            symbols: 股票代码列表（默认使用预设列表）
            days: 每只股票的交易日数量

        Returns:
            字典，key为股票代码，value为DataFrame
        """
        if symbols is None:
            symbols = list(self.STOCK_PROFILES.keys())

        data = {}
        for symbol in symbols:
            data[symbol] = self.generate_stock_data(symbol=symbol, days=days)

        logger.info(f"批量生成模拟数据: {len(symbols)}只股票")

        return data

    def generate_trading_signals(self, data: pd.DataFrame) -> List[str]:
        """
        基于模拟数据生成交易信号

        使用简单的技术指标规则生成买卖信号。

        Args:
            data: 包含 Close 列的 DataFrame

        Returns:
            信号列表，每个元素为 'buy', 'sell', 或 'hold'
        """
        if data.empty or "Close" not in data.columns:
            return []

        signals = []
        prices = data["Close"].values
        n = len(prices)

        # 使用双均线策略生成信号
        short_ma = pd.Series(prices).rolling(window=10).mean()
        long_ma = pd.Series(prices).rolling(window=30).mean()

        for i in range(n):
            if i < 30:
                signals.append("hold")
                continue

            if short_ma.iloc[i - 1] <= long_ma.iloc[i - 1] and short_ma.iloc[i] > long_ma.iloc[i]:
                signals.append("buy")
            elif short_ma.iloc[i - 1] >= long_ma.iloc[i - 1] and short_ma.iloc[i] < long_ma.iloc[i]:
                signals.append("sell")
            else:
                signals.append("hold")

        return signals

    def generate_stock_info(self, symbol: str = "AAPL") -> Dict:
        """
        生成模拟的股票基本信息

        Args:
            symbol: 股票代码

        Returns:
            股票信息字典
        """
        profile = self.STOCK_PROFILES.get(symbol, {})
        base_price = profile.get("base_price", 100.0)
        name = profile.get("name", symbol)

        # 模拟基本面数据
        market_cap = base_price * self.rng.uniform(1e9, 3e12)
        pe_ratio = self.rng.uniform(10, 35)
        pb_ratio = self.rng.uniform(1, 10)
        dividend_yield = self.rng.uniform(0, 0.05)

        info = {
            "symbol": symbol,
            "name": name,
            "sector": self.rng.choice(["Technology", "Finance", "Healthcare", "Consumer", "Energy"]),
            "industry": name,
            "market_cap": round(market_cap, 0),
            "pe_ratio": round(pe_ratio, 2),
            "pb_ratio": round(pb_ratio, 2),
            "dividend_yield": round(dividend_yield, 4),
            "fifty_two_week_high": round(base_price * 1.2, 2),
            "fifty_two_week_low": round(base_price * 0.8, 2),
            "average_volume": round(base_price * 500000, 0),
            "current_price": round(base_price * (1 + self.rng.normal(0, 0.05)), 2),
            "previous_close": round(base_price, 2),
            "website": f"https://example.com/{symbol.lower()}",
            "description": f"{name} 是一家领先的科技公司，专注于创新和技术发展。",
        }

        return info
