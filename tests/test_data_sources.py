"""
AutoWealth AI - 多数据源模块测试

测试 DataFetcher、EastMoneyDataSource、BinanceDataSource 的所有功能，
包括正常情况、边界情况和异常情况。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import json

# 添加项目根目录到路径，确保可以导入 autowealth
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock yfinance 以避免安装依赖
sys.modules['yfinance'] = MagicMock()

import numpy as np
import pandas as pd
import pytest

from autowealth.core.data_fetcher import DataFetcher, EastMoneyDataSource, BinanceDataSource


# ============================================================
# 测试数据工厂
# ============================================================

def make_mock_akshare_data(rows=100):
    """创建模拟的 akshare 返回数据（A股历史数据格式）"""
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")
    rng = np.random.RandomState(42)
    base_price = 100.0

    data = {
        "日期": dates.strftime("%Y-%m-%d"),
        "开盘": base_price + rng.randn(rows) * 2,
        "收盘": base_price + rng.randn(rows) * 2,
        "最高": base_price + 2 + rng.randn(rows) * 2,
        "最低": base_price - 2 + rng.randn(rows) * 2,
        "成交量": rng.randint(1000000, 10000000, rows),
        "成交额": rng.randint(100000000, 1000000000, rows),
        "振幅": rng.uniform(1, 5, rows),
        "涨跌幅": rng.uniform(-5, 5, rows),
        "涨跌额": rng.uniform(-5, 5, rows),
        "换手率": rng.uniform(0.5, 5, rows),
    }
    return pd.DataFrame(data)


def make_mock_akshare_info():
    """创建模拟的 akshare 股票信息"""
    return pd.DataFrame({
        "item": ["股票简称", "所属行业", "总市值", "市盈率", "市净率", "52周最高价", "52周最低价", "公司简介"],
        "value": ["贵州茅台", "白酒", "2000000000000", "30.5", "8.2", "1800.00", "1200.00", "中国白酒龙头企业"]
    })


def make_mock_binance_klines(rows=100):
    """创建模拟的币安 K线数据"""
    base_time = 1704067200000  # 2024-01-01 00:00:00 UTC
    klines = []
    rng = np.random.RandomState(42)

    for i in range(rows):
        open_price = 40000 + rng.randn() * 1000
        close_price = open_price + rng.randn() * 500
        high_price = max(open_price, close_price) + rng.uniform(100, 500)
        low_price = min(open_price, close_price) - rng.uniform(100, 500)
        volume = rng.uniform(100, 1000)

        kline = [
            base_time + i * 86400000,  # Open time
            str(open_price),           # Open
            str(high_price),           # High
            str(low_price),            # Low
            str(close_price),          # Close
            str(volume),               # Volume
            base_time + i * 86400000 + 86399999,  # Close time
            str(volume * close_price), # Quote asset volume
            rng.randint(100, 1000),    # Number of trades
            str(volume * 0.5),         # Taker buy base asset volume
            str(volume * close_price * 0.5),  # Taker buy quote asset volume
            "0"                        # Ignore
        ]
        klines.append(kline)

    return klines


def make_mock_binance_ticker():
    """创建模拟的币安 24hr ticker 数据"""
    return {
        "symbol": "BTCUSDT",
        "priceChange": "500.00",
        "priceChangePercent": "1.25",
        "weightedAvgPrice": "40500.00",
        "prevClosePrice": "40000.00",
        "lastPrice": "40500.00",
        "lastQty": "0.5",
        "bidPrice": "40499.00",
        "bidQty": "1.0",
        "askPrice": "40501.00",
        "askQty": "1.0",
        "openPrice": "40000.00",
        "highPrice": "41000.00",
        "lowPrice": "39500.00",
        "volume": "10000.0",
        "quoteVolume": "405000000.0",
        "openTime": 1704067200000,
        "closeTime": 1704153600000,
        "firstId": 1,
        "lastId": 1000,
        "count": 1000
    }


# ============================================================
# DataFetcher 初始化测试
# ============================================================

class TestDataFetcherInit:
    """测试 DataFetcher 初始化"""

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_default_source(self, mock_get_settings):
        """验证默认数据源为 yfinance"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        fetcher = DataFetcher()
        assert fetcher.source == "yfinance"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_yfinance_source(self, mock_get_settings):
        """验证 yfinance 数据源设置"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        fetcher = DataFetcher(source="yfinance")
        assert fetcher.source == "yfinance"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_eastmoney_source(self, mock_get_settings):
        """验证 eastmoney 数据源设置"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        fetcher = DataFetcher(source="eastmoney")
        assert fetcher.source == "eastmoney"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_binance_source(self, mock_get_settings):
        """验证 binance 数据源设置"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        fetcher = DataFetcher(source="binance")
        assert fetcher.source == "binance"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_source_case_insensitive(self, mock_get_settings):
        """验证数据源参数大小写不敏感"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        fetcher = DataFetcher(source="YFINANCE")
        assert fetcher.source == "yfinance"

        fetcher = DataFetcher(source="EastMoney")
        assert fetcher.source == "eastmoney"

        fetcher = DataFetcher(source="BINANCE")
        assert fetcher.source == "binance"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_cache_dir_creation(self, mock_get_settings):
        """验证缓存目录自动创建"""
        import tempfile
        import shutil

        temp_dir = tempfile.mkdtemp()
        cache_path = Path(temp_dir) / "test_cache"

        mock_settings = MagicMock()
        mock_settings.data_cache_dir = str(cache_path)
        mock_get_settings.return_value = mock_settings

        try:
            fetcher = DataFetcher()
            assert fetcher.cache_dir.exists()
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


# ============================================================
# is_crypto_symbol 静态方法测试
# ============================================================

class TestIsCryptoSymbol:
    """测试 is_crypto_symbol 静态方法"""

    def test_btcusdt_is_crypto(self):
        """验证 BTCUSDT 被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("BTCUSDT") is True

    def test_ethusdt_is_crypto(self):
        """验证 ETHUSDT 被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("ETHUSDT") is True

    def test_btc_busd_is_crypto(self):
        """验证 BTCBUSD 被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("BTCBUSD") is True

    def test_eth_btc_is_crypto(self):
        """验证 ETHBTC 被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("ETHBTC") is True

    def test_aapl_is_not_crypto(self):
        """验证 AAPL 不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("AAPL") is False

    def test_chinese_stock_is_not_crypto(self):
        """验证 A股代码不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("600519.SS") is False
        assert DataFetcher.is_crypto_symbol("000001.SZ") is False

    def test_short_symbol_is_not_crypto(self):
        """验证短代码不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("BTC") is False
        assert DataFetcher.is_crypto_symbol("USDT") is False

    def test_none_is_not_crypto(self):
        """验证 None 不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol(None) is False

    def test_empty_string_is_not_crypto(self):
        """验证空字符串不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol("") is False

    def test_non_string_is_not_crypto(self):
        """验证非字符串类型不被识别为加密货币"""
        assert DataFetcher.is_crypto_symbol(12345) is False
        assert DataFetcher.is_crypto_symbol(["BTCUSDT"]) is False

    def test_case_insensitive(self):
        """验证大小写不敏感"""
        assert DataFetcher.is_crypto_symbol("btcusdt") is True
        assert DataFetcher.is_crypto_symbol("BtcUsdt") is True


# ============================================================
# EastMoneyDataSource 测试
# ============================================================

class TestEastMoneyDataSource:
    """测试 EastMoneyDataSource 类"""

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_init_import_error(self, mock_get_settings):
        """验证 akshare 未安装时抛出 ImportError"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        with patch.dict('sys.modules', {'akshare': None}):
            with pytest.raises(ImportError) as exc_info:
                EastMoneyDataSource()
            assert "akshare" in str(exc_info.value)

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_data_success(self, mock_get_settings):
        """验证获取A股数据成功"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_data = make_mock_akshare_data(50)
        mock_ak.stock_zh_a_hist.return_value = mock_data

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()
            source.ak = mock_ak

            result = source.get_stock_data("600519", period="1y")

            assert isinstance(result, pd.DataFrame)
            assert "Open" in result.columns
            assert "High" in result.columns
            assert "Low" in result.columns
            assert "Close" in result.columns
            assert "Volume" in result.columns
            assert len(result) == 50

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_data_with_suffix(self, mock_get_settings):
        """验证带后缀的A股代码处理"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_data = make_mock_akshare_data(50)
        mock_ak.stock_zh_a_hist.return_value = mock_data

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()
            source.ak = mock_ak

            # 测试 .SS 后缀
            source.get_stock_data("600519.SS")
            call_args = mock_ak.stock_zh_a_hist.call_args
            assert call_args[1]["symbol"] == "600519"

            # 测试 .SZ 后缀
            source.get_stock_data("000001.SZ")
            call_args = mock_ak.stock_zh_a_hist.call_args
            assert call_args[1]["symbol"] == "000001"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_data_empty_result(self, mock_get_settings):
        """验证空数据时抛出 ValueError"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = pd.DataFrame()

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()
            source.ak = mock_ak

            with pytest.raises(ValueError) as exc_info:
                source.get_stock_data("600519")
            assert "无法获取" in str(exc_info.value)

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_info_success(self, mock_get_settings):
        """验证获取A股信息成功"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_ak.stock_individual_info_em.return_value = make_mock_akshare_info()

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()
            source.ak = mock_ak

            result = source.get_stock_info("600519")

            assert result["symbol"] == "600519"
            assert result["name"] == "贵州茅台"
            assert result["sector"] == "白酒"
            assert "market_cap" in result

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_info_empty_result(self, mock_get_settings):
        """验证空信息时返回错误字典"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_ak.stock_individual_info_em.return_value = pd.DataFrame()

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()
            source.ak = mock_ak

            result = source.get_stock_info("600519")

            assert "error" in result
            assert result["symbol"] == "600519"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_parse_period(self, mock_get_settings):
        """验证周期解析"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            source = EastMoneyDataSource()

            assert source._parse_period("1d").days == 1
            assert source._parse_period("1y").days == 365
            assert source._parse_period("2y").days == 730
            assert source._parse_period("5y").days == 1825
            assert source._parse_period("max").days == 3650


# ============================================================
# BinanceDataSource 测试
# ============================================================

class TestBinanceDataSource:
    """测试 BinanceDataSource 类"""

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_init_import_error(self, mock_get_settings):
        """验证 requests 未安装时抛出 ImportError"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        with patch.dict('sys.modules', {'requests': None}):
            with pytest.raises(ImportError) as exc_info:
                BinanceDataSource()
            assert "requests" in str(exc_info.value)

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_data_success(self, mock_get_settings):
        """验证获取加密货币数据成功"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_klines(50)
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            source = BinanceDataSource()
            source.requests = mock_requests

            result = source.get_crypto_data("BTCUSDT", interval="1d")

            assert isinstance(result, pd.DataFrame)
            assert "Open" in result.columns
            assert "High" in result.columns
            assert "Low" in result.columns
            assert "Close" in result.columns
            assert "Volume" in result.columns
            assert len(result) == 50

            # 验证数值类型正确
            assert pd.api.types.is_numeric_dtype(result["Open"])
            assert pd.api.types.is_numeric_dtype(result["Close"])

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_data_symbol_uppercase(self, mock_get_settings):
        """验证 symbol 自动转大写"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_klines(10)
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            source = BinanceDataSource()
            source.requests = mock_requests

            source.get_crypto_data("btcusdt")

            call_args = mock_requests.get.call_args
            assert call_args[1]["params"]["symbol"] == "BTCUSDT"

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_data_empty_result(self, mock_get_settings):
        """验证空数据时抛出 ValueError"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            source = BinanceDataSource()
            source.requests = mock_requests

            with pytest.raises(ValueError) as exc_info:
                source.get_crypto_data("BTCUSDT")
            assert "无法获取" in str(exc_info.value)

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_info_success(self, mock_get_settings):
        """验证获取加密货币信息成功"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_ticker()
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            source = BinanceDataSource()
            source.requests = mock_requests

            result = source.get_crypto_info("BTCUSDT")

            assert result["symbol"] == "BTCUSDT"
            assert result["sector"] == "Cryptocurrency"
            assert result["industry"] == "Cryptocurrency"
            assert "last_price" in result
            assert "price_change_percent" in result

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_info_error(self, mock_get_settings):
        """验证获取信息失败时返回错误字典"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_requests = MagicMock()
        mock_requests.get.side_effect = Exception("Network error")

        with patch.dict('sys.modules', {'requests': mock_requests}):
            source = BinanceDataSource()
            source.requests = mock_requests

            result = source.get_crypto_info("BTCUSDT")

            assert "error" in result
            assert result["symbol"] == "BTCUSDT"


# ============================================================
# DataFetcher 整合测试
# ============================================================

class TestDataFetcherIntegration:
    """测试 DataFetcher 整合功能"""

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_data_routing(self, mock_get_settings):
        """验证加密货币自动路由到币安"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_klines(50)
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            fetcher = DataFetcher(source="yfinance")
            fetcher._binance = BinanceDataSource()
            fetcher._binance.requests = mock_requests

            result = fetcher.get_stock_data("BTCUSDT")

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 50

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_info_crypto_routing(self, mock_get_settings):
        """验证加密货币信息自动路由到币安"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_ticker()
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            fetcher = DataFetcher(source="yfinance")
            fetcher._binance = BinanceDataSource()
            fetcher._binance.requests = mock_requests

            result = fetcher.get_stock_info("BTCUSDT")

            assert result["sector"] == "Cryptocurrency"
            assert "last_price" in result

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_stock_data_eastmoney_source(self, mock_get_settings):
        """验证 eastmoney 数据源调用 akshare"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_data = make_mock_akshare_data(50)
        mock_ak.stock_zh_a_hist.return_value = mock_data

        with patch.dict('sys.modules', {'akshare': mock_ak}):
            fetcher = DataFetcher(source="eastmoney")
            fetcher._eastmoney = EastMoneyDataSource()
            fetcher._eastmoney.ak = mock_ak

            result = fetcher.get_stock_data("600519")

            assert isinstance(result, pd.DataFrame)
            mock_ak.stock_zh_a_hist.assert_called_once()

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_get_crypto_data_method(self, mock_get_settings):
        """验证 get_crypto_data 方法直接调用币安"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_klines(50)
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'requests': mock_requests}):
            fetcher = DataFetcher()
            fetcher._binance = BinanceDataSource()
            fetcher._binance.requests = mock_requests

            result = fetcher.get_crypto_data("ETHUSDT", interval="1h")

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 50

            # 验证 interval 参数传递
            call_args = mock_requests.get.call_args
            assert call_args[1]["params"]["interval"] == "1h"


# ============================================================
# 边界情况测试
# ============================================================

class TestEdgeCases:
    """测试边界情况"""

    @patch('autowealth.core.data_fetcher.get_settings')
    def test_multiple_stocks_with_mixed_types(self, mock_get_settings):
        """验证批量获取混合类型（股票+加密货币）"""
        mock_settings = MagicMock()
        mock_settings.data_cache_dir = "/tmp/test_cache"
        mock_get_settings.return_value = mock_settings

        mock_ak = MagicMock()
        mock_ak.stock_zh_a_hist.return_value = make_mock_akshare_data(50)

        mock_response = MagicMock()
        mock_response.json.return_value = make_mock_binance_klines(50)
        mock_response.raise_for_status.return_value = None

        mock_requests = MagicMock()
        mock_requests.get.return_value = mock_response

        with patch.dict('sys.modules', {'akshare': mock_ak, 'requests': mock_requests}):
            fetcher = DataFetcher(source="eastmoney")
            fetcher._eastmoney = EastMoneyDataSource()
            fetcher._eastmoney.ak = mock_ak
            fetcher._binance = BinanceDataSource()
            fetcher._binance.requests = mock_requests

            # 混合股票和加密货币
            symbols = ["600519", "BTCUSDT", "000001"]
            results = fetcher.get_multiple_stocks(symbols)

            assert "600519" in results
            assert "BTCUSDT" in results
            assert "000001" in results


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
