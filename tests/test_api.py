"""
FastAPI 端点测试
使用 TestClient 进行单元测试，无需启动真实服务器。
部分测试使用 unittest.mock 来避免外部网络依赖（yfinance 速率限制）。
"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from autowealth.api.server import create_app


@pytest.fixture(scope="module")
def client():
    """创建 TestClient 实例"""
    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Mock 数据辅助函数
# ---------------------------------------------------------------------------

# 全局共享日期索引，确保多只股票数据可以对齐
_MOCK_DATES = pd.date_range(end=pd.Timestamp("2026-01-01"), periods=100, freq="B")


def _mock_stock_data(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """创建模拟股票数据（每只股票的 seed 不同以确保价格走势不同）"""
    import numpy as np

    # 使用全局计数器来确保每次调用生成不同的数据
    if not hasattr(_mock_stock_data, "_call_count"):
        _mock_stock_data._call_count = 0
    _mock_stock_data._call_count += 1
    np.random.seed(seed + _mock_stock_data._call_count * 7)

    prices = 100 + np.cumsum(np.random.randn(n) * 0.5)
    prices = np.abs(prices) + 1.0  # 确保价格始终为正
    return pd.DataFrame({
        "Open": prices * 0.99,
        "High": prices * 1.02,
        "Low": prices * 0.98,
        "Close": prices,
        "Volume": np.random.randint(1_000_000, 10_000_000, n),
    }, index=_MOCK_DATES[:n])


def _mock_stock_info() -> dict:
    """创建模拟股票信息"""
    return {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "market_cap": 3_000_000_000_000,
        "pe_ratio": 30.0,
        "pb_ratio": 8.0,
        "dividend_yield": 0.005,
        "fifty_two_week_high": 200.0,
        "fifty_two_week_low": 150.0,
        "average_volume": 50_000_000,
        "website": "https://www.apple.com",
        "description": "Apple Inc. designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories worldwide.",
        "current_price": 180.0,
        "regularMarketPrice": 180.0,
    }


# ---------------------------------------------------------------------------
# 测试类
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """测试健康检查端点"""

    def test_health_check(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "autowealth-ai"


class TestAnalyzeEndpoint:
    """测试单股分析端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_info")
    def test_analyze_stock_success(self, mock_info, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)
        mock_info.return_value = _mock_stock_info()

        payload = {
            "symbol": "AAPL",
            "include_technical": True,
            "include_fundamental": True,
            "include_sentiment": True,
        }
        response = client.post("/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "success" in data

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_info")
    def test_analyze_stock_minimal_payload(self, mock_info, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)
        mock_info.return_value = _mock_stock_info()

        payload = {"symbol": "MSFT"}
        response = client.post("/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "MSFT"

    def test_analyze_stock_invalid_symbol(self, client: TestClient):
        """测试无效股票代码仍返回 200（success=False）或 500"""
        payload = {"symbol": "INVALID_SYMBOL_XYZ"}
        response = client.post("/analyze", json=payload)
        assert response.status_code in (200, 500)


class TestBatchAnalyzeEndpoint:
    """测试批量分析端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_info")
    def test_batch_analyze(self, mock_info, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)
        mock_info.return_value = _mock_stock_info()

        payload = {"symbols": ["AAPL", "MSFT"]}
        response = client.post("/analyze/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "recommendations" in data
        assert "summary" in data
        assert data["summary"]["total"] == 2

    def test_batch_analyze_empty_list(self, client: TestClient):
        payload = {"symbols": []}
        response = client.post("/analyze/batch", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["summary"]["total"] == 0


class TestPortfolioEndpoint:
    """测试投资组合分析端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_info")
    def test_portfolio_analyze(self, mock_info, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)
        mock_info.return_value = _mock_stock_info()

        payload = {
            "holdings": [
                {"symbol": "AAPL", "quantity": 100, "cost_basis": 150.0},
                {"symbol": "MSFT", "quantity": 50, "cost_basis": 300.0},
            ]
        }
        response = client.post("/portfolio/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "holdings" in data
        assert "total_value" in data
        assert "total_gain_loss" in data
        assert "return_pct" in data

    def test_portfolio_analyze_empty(self, client: TestClient):
        payload = {"holdings": []}
        response = client.post("/portfolio/analyze", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["total_value"] == 0.0
        assert data["total_gain_loss"] == 0.0


class TestMarketOverviewEndpoint:
    """测试市场概览端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_multiple_stocks")
    def test_market_overview(self, mock_multi, client: TestClient):
        mock_multi.return_value = {
            "^GSPC": _mock_stock_data(50),
            "^DJI": _mock_stock_data(50),
        }

        response = client.get("/market/overview")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "indices" in data


class TestBacktestEndpoint:
    """测试回测端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    def test_backtest_buy_hold(self, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)

        payload = {
            "symbol": "AAPL",
            "strategy": "buy_hold",
            "initial_capital": 100000.0,
        }
        response = client.post("/backtest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert data["strategy"] == "buy_hold"
        assert "metrics" in data
        assert "equity_curve" in data
        assert len(data["equity_curve"]) > 0

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    def test_backtest_sma_cross(self, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)

        payload = {
            "symbol": "MSFT",
            "strategy": "sma_cross",
            "initial_capital": 50000.0,
        }
        response = client.post("/backtest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "sma_cross"
        assert "metrics" in data

    @patch("autowealth.core.data_fetcher.DataFetcher.get_stock_data")
    def test_backtest_rsi(self, mock_data, client: TestClient):
        mock_data.return_value = _mock_stock_data(100)

        payload = {
            "symbol": "AAPL",
            "strategy": "rsi",
            "initial_capital": 100000.0,
        }
        response = client.post("/backtest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["strategy"] == "rsi"


class TestOptimizeEndpoint:
    """测试组合优化端点"""

    @patch("autowealth.core.data_fetcher.DataFetcher.get_multiple_stocks")
    def test_optimize_max_sharpe(self, mock_multi, client: TestClient):
        mock_multi.return_value = {
            "AAPL": _mock_stock_data(100),
            "MSFT": _mock_stock_data(100),
            "GOOGL": _mock_stock_data(100),
        }

        payload = {"symbols": ["AAPL", "MSFT", "GOOGL"]}
        response = client.post("/optimize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "weights" in data
        assert "expected_return" in data
        assert "volatility" in data
        assert "sharpe_ratio" in data
        # 权重之和应接近 1
        total_weight = sum(data["weights"].values())
        assert abs(total_weight - 1.0) < 0.01

    @patch("autowealth.core.data_fetcher.DataFetcher.get_multiple_stocks")
    def test_optimize_target_return(self, mock_multi, client: TestClient):
        mock_multi.return_value = {
            "AAPL": _mock_stock_data(100),
            "MSFT": _mock_stock_data(100),
            "GOOGL": _mock_stock_data(100),
        }

        payload = {
            "symbols": ["AAPL", "MSFT", "GOOGL"],
            "target_return": 0.10,
        }
        response = client.post("/optimize", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "weights" in data
        assert "expected_return" in data

    def test_optimize_insufficient_symbols(self, client: TestClient):
        """测试股票数量不足时应返回错误"""
        payload = {"symbols": ["AAPL"]}
        response = client.post("/optimize", json=payload)
        # 单只股票无法进行组合优化
        assert response.status_code == 500


class TestRequestValidation:
    """测试请求参数校验"""

    def test_analyze_missing_symbol(self, client: TestClient):
        payload = {}
        response = client.post("/analyze", json=payload)
        assert response.status_code == 422

    def test_batch_missing_symbols(self, client: TestClient):
        payload = {}
        response = client.post("/analyze/batch", json=payload)
        assert response.status_code == 422

    def test_portfolio_missing_holdings(self, client: TestClient):
        payload = {}
        response = client.post("/portfolio/analyze", json=payload)
        assert response.status_code == 422

    def test_backtest_missing_symbol(self, client: TestClient):
        payload = {"strategy": "buy_hold"}
        response = client.post("/backtest", json=payload)
        assert response.status_code == 422

    def test_optimize_missing_symbols(self, client: TestClient):
        payload = {}
        response = client.post("/optimize", json=payload)
        assert response.status_code == 422
