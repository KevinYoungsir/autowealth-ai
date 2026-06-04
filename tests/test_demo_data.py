"""
测试演示数据生成器 - 验证模拟数据的格式正确性和范围合理性
"""

import numpy as np
import pandas as pd
import pytest

from autowealth.core.demo_data import DemoDataGenerator


@pytest.fixture
def generator():
    """创建演示数据生成器实例"""
    return DemoDataGenerator(seed=42)


class TestDemoDataGeneratorInit:
    """测试演示数据生成器初始化"""

    def test_init_default_seed(self):
        """测试默认种子初始化"""
        gen = DemoDataGenerator()
        assert gen.rng is not None

    def test_init_custom_seed(self):
        """测试自定义种子初始化"""
        gen1 = DemoDataGenerator(seed=123)
        gen2 = DemoDataGenerator(seed=123)
        # 相同种子应产生相同结果（比较数据列，忽略因 datetime.now() 导致的索引差异）
        data1 = gen1.generate_stock_data("AAPL", days=10)
        data2 = gen2.generate_stock_data("AAPL", days=10)
        pd.testing.assert_frame_equal(data1.reset_index(drop=True), data2.reset_index(drop=True))


class TestGenerateStockData:
    """测试股票数据生成"""

    def test_stock_data_columns(self, generator):
        """测试生成的股票数据包含正确的列"""
        df = generator.generate_stock_data("AAPL", days=100)
        expected_cols = {"Open", "High", "Low", "Close", "Volume"}
        assert set(df.columns) == expected_cols

    def test_stock_data_length(self, generator):
        """测试生成的股票数据行数正确"""
        df = generator.generate_stock_data("AAPL", days=200)
        assert len(df) == 200

    def test_stock_data_index_is_datetime(self, generator):
        """测试股票数据的索引为日期时间类型"""
        df = generator.generate_stock_data("AAPL", days=50)
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_stock_data_high_gte_low(self, generator):
        """测试最高价始终大于等于最低价"""
        df = generator.generate_stock_data("AAPL", days=100)
        assert (df["High"] >= df["Low"]).all()

    def test_stock_data_high_gte_close(self, generator):
        """测试最高价始终大于等于收盘价"""
        df = generator.generate_stock_data("AAPL", days=100)
        assert (df["High"] >= df["Close"]).all()

    def test_stock_data_low_lte_close(self, generator):
        """测试最低价始终小于等于收盘价"""
        df = generator.generate_stock_data("AAPL", days=100)
        assert (df["Low"] <= df["Close"]).all()

    def test_stock_data_prices_positive(self, generator):
        """测试所有价格均为正值"""
        df = generator.generate_stock_data("AAPL", days=100)
        assert (df[["Open", "High", "Low", "Close"]] > 0).all().all()

    def test_stock_data_volume_positive(self, generator):
        """测试成交量均为正值"""
        df = generator.generate_stock_data("AAPL", days=100)
        assert (df["Volume"] > 0).all()

    def test_stock_data_known_symbol_profile(self, generator):
        """测试已知股票代码使用正确的基准价格"""
        df = generator.generate_stock_data("AAPL", days=10)
        # 起始价格应接近基准价格175
        assert abs(df["Close"].iloc[0] - 175.0) < 20.0

    def test_stock_data_unknown_symbol(self, generator):
        """测试未知股票代码使用默认参数"""
        df = generator.generate_stock_data("UNKNOWN", days=50)
        assert len(df) == 50
        assert (df["Close"] > 0).all()

    def test_stock_data_no_weekends(self, generator):
        """测试股票数据不包含周末"""
        df = generator.generate_stock_data("AAPL", days=100)
        weekdays = df.index.weekday
        assert (weekdays < 5).all()

    def test_stock_data_custom_params(self, generator):
        """测试自定义参数生成股票数据"""
        df = generator.generate_stock_data(
            "CUSTOM", days=30, base_price=50.0, volatility=0.01, trend=0.001
        )
        assert len(df) == 30
        # 起始价格应接近50
        assert abs(df["Close"].iloc[0] - 50.0) < 5.0


class TestGenerateCryptoData:
    """测试加密货币数据生成"""

    def test_crypto_data_columns(self, generator):
        """测试加密货币数据包含正确的列"""
        df = generator.generate_crypto_data("BTCUSDT", days=100)
        expected_cols = {"Open", "High", "Low", "Close", "Volume"}
        assert set(df.columns) == expected_cols

    def test_crypto_data_length(self, generator):
        """测试加密货币数据行数正确（包含周末）"""
        df = generator.generate_crypto_data("BTCUSDT", days=200)
        assert len(df) == 200

    def test_crypto_data_prices_positive(self, generator):
        """测试加密货币价格均为正值"""
        df = generator.generate_crypto_data("BTCUSDT", days=100)
        assert (df[["Open", "High", "Low", "Close"]] > 0).all().all()

    def test_crypto_data_high_gte_low(self, generator):
        """测试加密货币最高价大于等于最低价"""
        df = generator.generate_crypto_data("BTCUSDT", days=100)
        assert (df["High"] >= df["Low"]).all()

    def test_crypto_data_known_symbol(self, generator):
        """测试已知加密货币使用正确的基准价格"""
        df = generator.generate_crypto_data("BTCUSDT", days=10)
        assert abs(df["Close"].iloc[0] - 65000.0) < 5000.0

    def test_crypto_data_includes_weekends(self, generator):
        """测试加密货币数据包含周末（7x24交易）"""
        df = generator.generate_crypto_data("BTCUSDT", days=50)
        weekdays = df.index.weekday
        # 加密货币应该有周末数据
        assert (weekdays >= 5).any()


class TestGeneratePortfolio:
    """测试投资组合生成"""

    def test_portfolio_has_holdings(self, generator):
        """测试投资组合包含持仓"""
        portfolio = generator.generate_portfolio()
        assert "holdings" in portfolio
        assert len(portfolio["holdings"]) > 0

    def test_portfolio_total_value(self, generator):
        """测试投资组合总市值计算正确"""
        portfolio = generator.generate_portfolio()
        expected_total = sum(h["market_value"] for h in portfolio["holdings"])
        assert abs(portfolio["total_value"] - expected_total) < 0.01

    def test_portfolio_holding_fields(self, generator):
        """测试每个持仓包含必要字段"""
        portfolio = generator.generate_portfolio()
        required_fields = {"symbol", "name", "quantity", "cost_basis", "current_price",
                           "market_value", "gain_loss", "return_pct"}
        for holding in portfolio["holdings"]:
            assert required_fields.issubset(set(holding.keys()))

    def test_portfolio_quantities_positive(self, generator):
        """测试持仓数量为正"""
        portfolio = generator.generate_portfolio()
        assert all(h["quantity"] > 0 for h in portfolio["holdings"])

    def test_portfolio_cost_basis_positive(self, generator):
        """测试成本价为正"""
        portfolio = generator.generate_portfolio()
        assert all(h["cost_basis"] > 0 for h in portfolio["holdings"])


class TestGenerateMarketData:
    """测试市场数据生成"""

    def test_market_data_indices(self, generator):
        """测试市场数据包含主要指数"""
        market = generator.generate_market_data()
        expected_indices = {"^GSPC", "^DJI", "^IXIC"}
        assert expected_indices.issubset(set(market.keys()))

    def test_market_data_each_has_dataframe(self, generator):
        """测试每个指数都有DataFrame数据"""
        market = generator.generate_market_data()
        for symbol, df in market.items():
            assert isinstance(df, pd.DataFrame)
            assert len(df) > 0

    def test_market_data_columns(self, generator):
        """测试市场数据DataFrame包含正确列"""
        market = generator.generate_market_data()
        for df in market.values():
            assert "Close" in df.columns


class TestGenerateTradingSignals:
    """测试交易信号生成"""

    def test_signals_length_matches_data(self, generator):
        """测试信号长度与数据长度匹配"""
        data = generator.generate_stock_data("AAPL", days=100)
        signals = generator.generate_trading_signals(data)
        assert len(signals) == len(data)

    def test_signals_valid_values(self, generator):
        """测试信号只包含有效值"""
        data = generator.generate_stock_data("AAPL", days=100)
        signals = generator.generate_trading_signals(data)
        valid = {"buy", "sell", "hold"}
        assert all(s in valid for s in signals)

    def test_signals_empty_data(self, generator):
        """测试空数据返回空信号"""
        empty_df = pd.DataFrame({"Close": []})
        signals = generator.generate_trading_signals(empty_df)
        assert signals == []


class TestGenerateStockInfo:
    """测试股票信息生成"""

    def test_stock_info_fields(self, generator):
        """测试股票信息包含必要字段"""
        info = generator.generate_stock_info("AAPL")
        required_fields = {"symbol", "name", "sector", "market_cap", "pe_ratio", "pb_ratio"}
        assert required_fields.issubset(set(info.keys()))

    def test_stock_info_symbol(self, generator):
        """测试股票信息symbol正确"""
        info = generator.generate_stock_info("AAPL")
        assert info["symbol"] == "AAPL"

    def test_stock_info_positive_values(self, generator):
        """测试股票信息中数值字段为正"""
        info = generator.generate_stock_info("AAPL")
        assert info["market_cap"] > 0
        assert info["pe_ratio"] > 0
        assert info["pb_ratio"] > 0


class TestGenerateMultiStockData:
    """测试批量股票数据生成"""

    def test_multi_stock_count(self, generator):
        """测试批量生成的股票数量"""
        symbols = ["AAPL", "GOOGL", "MSFT"]
        data = generator.generate_multi_stock_data(symbols=symbols, days=50)
        assert len(data) == 3

    def test_multi_stock_default_symbols(self, generator):
        """测试默认批量生成使用预设列表"""
        data = generator.generate_multi_stock_data(days=10)
        assert len(data) > 5  # 预设列表有多个股票

    def test_multi_stock_each_has_data(self, generator):
        """测试每只股票都有数据"""
        symbols = ["AAPL", "GOOGL"]
        data = generator.generate_multi_stock_data(symbols=symbols, days=30)
        for symbol, df in data.items():
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 30
