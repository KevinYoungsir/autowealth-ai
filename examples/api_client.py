"""
AutoWealth AI API 客户端示例
展示如何调用各个 RESTful API 端点

使用方式:
    1. 先启动 API 服务: python -m uvicorn autowealth.api.server:create_app --reload
    2. 运行本示例: python examples/api_client.py
"""
import json
import os
from typing import Any, Dict, List, Optional

import requests

# API 基础地址
BASE_URL = os.getenv("AUTOWEALTH_API_URL", "http://127.0.0.1:8000")


def _post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """发送 POST 请求"""
    url = f"{BASE_URL}{endpoint}"
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()


def _get(endpoint: str) -> Dict[str, Any]:
    """发送 GET 请求"""
    url = f"{BASE_URL}{endpoint}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def health_check() -> Dict[str, str]:
    """健康检查"""
    return _get("/health")


def analyze_stock(
    symbol: str,
    include_technical: bool = True,
    include_fundamental: bool = True,
    include_sentiment: bool = True,
) -> Dict[str, Any]:
    """
    分析单只股票

    Args:
        symbol: 股票代码，如 "AAPL", "600519.SS"
        include_technical: 是否包含技术分析
        include_fundamental: 是否包含基本面分析
        include_sentiment: 是否包含情绪分析
    """
    payload = {
        "symbol": symbol,
        "include_technical": include_technical,
        "include_fundamental": include_fundamental,
        "include_sentiment": include_sentiment,
    }
    return _post("/analyze", payload)


def analyze_batch(symbols: List[str]) -> Dict[str, Any]:
    """
    批量分析多只股票

    Args:
        symbols: 股票代码列表，如 ["AAPL", "MSFT", "GOOGL"]
    """
    payload = {"symbols": symbols}
    return _post("/analyze/batch", payload)


def analyze_portfolio(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    分析投资组合

    Args:
        holdings: 持仓列表，每项包含 symbol, quantity, cost_basis
        示例:
            [
                {"symbol": "AAPL", "quantity": 100, "cost_basis": 150.0},
                {"symbol": "MSFT", "quantity": 50, "cost_basis": 300.0},
            ]
    """
    payload = {"holdings": holdings}
    return _post("/portfolio/analyze", payload)


def market_overview() -> Dict[str, Any]:
    """获取市场概览"""
    return _get("/market/overview")


def backtest(
    symbol: str,
    strategy: str = "buy_hold",
    initial_capital: float = 100000.0,
) -> Dict[str, Any]:
    """
    执行回测

    Args:
        symbol: 股票代码
        strategy: 策略名称，可选 "buy_hold", "sma_cross", "rsi"
        initial_capital: 初始资金
    """
    payload = {
        "symbol": symbol,
        "strategy": strategy,
        "initial_capital": initial_capital,
    }
    return _post("/backtest", payload)


def optimize_portfolio(
    symbols: List[str],
    target_return: Optional[float] = None,
) -> Dict[str, Any]:
    """
    投资组合优化

    Args:
        symbols: 股票代码列表
        target_return: 目标年化收益率（如 0.1 表示 10%），为 None 时最大化夏普比率
    """
    payload: Dict[str, Any] = {"symbols": symbols}
    if target_return is not None:
        payload["target_return"] = target_return
    return _post("/optimize", payload)


def print_json(data: Dict[str, Any], title: str = "") -> None:
    """美观地打印 JSON 数据"""
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    """主函数：演示所有 API 调用"""
    print("AutoWealth AI API 客户端示例")
    print(f"API 地址: {BASE_URL}")

    # 1. 健康检查
    try:
        health = health_check()
        print_json(health, "1. 健康检查 /health")
    except requests.exceptions.ConnectionError:
        print(f"\n错误: 无法连接到 API 服务 ({BASE_URL})")
        print("请确保服务已启动: python -m uvicorn autowealth.api.server:create_app --reload")
        return

    # 2. 分析单只股票
    print("\n>>> 正在分析 AAPL ...")
    result = analyze_stock("AAPL", include_technical=True, include_fundamental=True)
    print_json(result, "2. 单股分析 /analyze (AAPL)")

    # 3. 批量分析
    print("\n>>> 正在批量分析 AAPL, MSFT ...")
    batch_result = analyze_batch(["AAPL", "MSFT"])
    print_json(batch_result, "3. 批量分析 /analyze/batch")

    # 4. 投资组合分析
    print("\n>>> 正在分析投资组合 ...")
    portfolio_result = analyze_portfolio([
        {"symbol": "AAPL", "quantity": 100, "cost_basis": 150.0},
        {"symbol": "MSFT", "quantity": 50, "cost_basis": 300.0},
    ])
    print_json(portfolio_result, "4. 投资组合分析 /portfolio/analyze")

    # 5. 市场概览
    print("\n>>> 正在获取市场概览 ...")
    market = market_overview()
    print_json(market, "5. 市场概览 /market/overview")

    # 6. 回测
    print("\n>>> 正在回测 AAPL (buy_hold 策略) ...")
    bt_result = backtest("AAPL", strategy="buy_hold", initial_capital=100000.0)
    print_json(bt_result, "6. 回测 /backtest (AAPL, buy_hold)")

    # 7. 组合优化
    print("\n>>> 正在优化组合 AAPL, MSFT, GOOGL ...")
    opt_result = optimize_portfolio(["AAPL", "MSFT", "GOOGL"])
    print_json(opt_result, "7. 组合优化 /optimize")

    # 8. 带目标收益的组合优化
    print("\n>>> 正在优化组合 (目标收益 10%) ...")
    opt_result2 = optimize_portfolio(["AAPL", "MSFT", "GOOGL"], target_return=0.10)
    print_json(opt_result2, "8. 组合优化 /optimize (target_return=10%)")

    print("\n" + "=" * 60)
    print("所有示例调用完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
