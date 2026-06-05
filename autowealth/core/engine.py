"""
AutoWealth AI 主引擎 - 整合所有模块的统一接口
"""
import logging
from typing import Any, Dict, List, Optional

from autowealth.agents.base_agent import AgentSignal
from autowealth.agents.coordinator import AgentCoordinator
from autowealth.agents.fundamental_agent import FundamentalAgent
from autowealth.agents.sentiment_agent import SentimentAgent
from autowealth.agents.technical_agent import TechnicalAgent
from autowealth.config.settings import get_settings
from autowealth.core.analyzer import FundamentalAnalyzer, TechnicalAnalyzer
from autowealth.core.data_fetcher import DataFetcher

logger = logging.getLogger(__name__)


class AutoWealthEngine:
    """
    AutoWealth AI 主引擎

    整合数据获取、技术分析、基本面分析、多智能体决策等功能
    提供简单易用的投资分析接口
    """

    def __init__(self, data_source="auto", twelve_data_api_key=None):
        self.settings = get_settings()
        self.logger = logging.getLogger("autowealth.engine")

        # 初始化核心组件
        self.data_fetcher = DataFetcher(source=data_source, twelve_data_api_key=twelve_data_api_key)
        self.technical_analyzer = TechnicalAnalyzer()
        self.fundamental_analyzer = FundamentalAnalyzer()

        # 初始化智能体系统
        self.coordinator = AgentCoordinator()
        self._register_default_agents()

        self.logger.info("AutoWealth AI 引擎初始化完成")

    def _register_default_agents(self):
        """注册默认的智能体"""
        self.coordinator.register_agent(TechnicalAgent(), weight=0.35)
        self.coordinator.register_agent(FundamentalAgent(), weight=0.35)
        self.coordinator.register_agent(SentimentAgent(), weight=0.30)

    def analyze(
        self,
        symbol: str,
        include_technical: bool = True,
        include_fundamental: bool = True,
        include_sentiment: bool = True,
    ) -> Dict[str, Any]:
        """
        综合分析股票

        Args:
            symbol: 股票代码 (如: AAPL, 600519.SS)
            include_technical: 是否包含技术分析
            include_fundamental: 是否包含基本面分析
            include_sentiment: 是否包含情绪分析

        Returns:
            包含完整分析结果的字典
        """
        self.logger.info(f"开始分析: {symbol}")

        result = {
            "symbol": symbol,
            "success": False,
            "error": None,
        }

        try:
            # 1. 获取数据
            self.logger.info(f"获取 {symbol} 的数据...")
            historical_data = self.data_fetcher.get_stock_data(symbol, period="1y")
            stock_info = self.data_fetcher.get_stock_info(symbol)

            if historical_data.empty:
                raise ValueError(f"无法获取 {symbol} 的数据")

            # 2. 准备分析数据
            analysis_data = {
                "historical_data": historical_data,
                "stock_info": stock_info,
            }

            # 3. 执行分析
            if any([include_technical, include_fundamental, include_sentiment]):
                analysis_result = self.coordinator.analyze(symbol, analysis_data)
                result["decision"] = analysis_result["final_decision"]
                result["individual_signals"] = analysis_result["individual_signals"]
                result["summary"] = analysis_result["analysis_summary"]

            # 4. 添加详细分析数据
            if include_technical:
                result["technical_analysis"] = self.technical_analyzer.full_analysis(historical_data).iloc[-10:].to_dict()

            if include_fundamental and stock_info.get("symbol"):
                result["fundamental_analysis"] = self.fundamental_analyzer.full_fundamental_analysis(
                    stock_info, historical_data
                )

            result["stock_info"] = stock_info
            result["success"] = True
            self.logger.info(f"{symbol} 分析完成")

        except Exception as e:
            self.logger.error(f"分析 {symbol} 失败: {e}")
            result["error"] = str(e)

        return result

    def analyze_batch(self, symbols: List[str]) -> Dict[str, Any]:
        """
        批量分析多只股票

        Args:
            symbols: 股票代码列表

        Returns:
            包含所有分析结果的字典
        """
        self.logger.info(f"开始批量分析 {len(symbols)} 只股票...")

        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.analyze(symbol)
            except Exception as e:
                self.logger.error(f"分析 {symbol} 失败: {e}")
                results[symbol] = {"symbol": symbol, "success": False, "error": str(e)}

        # 排序生成推荐列表
        buy_signals = []
        sell_signals = []
        hold_signals = []

        for symbol, result in results.items():
            if result.get("success") and "decision" in result:
                decision = result["decision"]
                if decision["signal_type"] == "buy":
                    buy_signals.append((symbol, decision["confidence"]))
                elif decision["signal_type"] == "sell":
                    sell_signals.append((symbol, decision["confidence"]))
                else:
                    hold_signals.append((symbol, decision["confidence"]))

        # 按置信度排序
        buy_signals.sort(key=lambda x: x[1], reverse=True)
        sell_signals.sort(key=lambda x: x[1], reverse=True)
        hold_signals.sort(key=lambda x: x[1], reverse=True)

        return {
            "results": results,
            "recommendations": {
                "buy": buy_signals,
                "sell": sell_signals,
                "hold": hold_signals,
            },
            "summary": {
                "total": len(symbols),
                "success": sum(1 for r in results.values() if r.get("success")),
                "buy_count": len(buy_signals),
                "sell_count": len(sell_signals),
                "hold_count": len(hold_signals),
            }
        }

    def get_market_overview(self) -> Dict[str, Any]:
        """获取市场概览"""
        self.logger.info("获取市场概览...")

        try:
            indices = self.data_fetcher.get_market_indices("global")
            overview = {}

            for symbol, data in indices.items():
                if not data.empty:
                    latest = data.iloc[-1]
                    prev = data.iloc[-2] if len(data) > 1 else latest
                    change = (latest["Close"] - prev["Close"]) / prev["Close"] * 100

                    overview[symbol] = {
                        "price": latest["Close"],
                        "change_pct": round(change, 2),
                        "volume": latest.get("Volume", 0),
                    }

            return {"success": True, "indices": overview}

        except Exception as e:
            self.logger.error(f"获取市场概览失败: {e}")
            return {"success": False, "error": str(e)}

    def get_portfolio_analysis(self, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析投资组合

        Args:
            holdings: 持仓列表，每项包含 symbol 和 quantity

        Returns:
            投资组合分析结果
        """
        self.logger.info(f"分析投资组合，共 {len(holdings)} 只股票...")

        analysis_results = []
        total_value = 0
        total_gain_loss = 0

        for holding in holdings:
            symbol = holding.get("symbol")
            quantity = holding.get("quantity", 0)
            cost_basis = holding.get("cost_basis", 0)

            try:
                result = self.analyze(symbol)
                if result.get("success"):
                    # 从历史数据获取最新收盘价作为当前价格
                    hist = result.get("stock_info", {})
                    current_price = hist.get("current_price", hist.get("regularMarketPrice", 0))
                    if current_price == 0:
                        current_price = hist.get("previous_close", 0)
                    holding_value = quantity * current_price
                    gain_loss = (current_price - cost_basis) * quantity if cost_basis > 0 else 0

                    total_value += holding_value
                    total_gain_loss += gain_loss

                    analysis_results.append({
                        "symbol": symbol,
                        "quantity": quantity,
                        "current_price": current_price,
                        "holding_value": holding_value,
                        "cost_basis": cost_basis,
                        "gain_loss": gain_loss,
                        "decision": result.get("decision", {}),
                    })

            except Exception as e:
                self.logger.error(f"分析持仓 {symbol} 失败: {e}")

        return {
            "holdings": analysis_results,
            "total_value": total_value,
            "total_gain_loss": total_gain_loss,
            "return_pct": (total_gain_loss / (total_value - total_gain_loss) * 100) if total_value > 0 else 0,
        }


# 便捷函数
def quick_analyze(symbol: str) -> Dict[str, Any]:
    """快速分析单只股票"""
    engine = AutoWealthEngine()
    return engine.analyze(symbol)


def batch_analyze(symbols: List[str]) -> Dict[str, Any]:
    """批量分析多只股票"""
    engine = AutoWealthEngine()
    return engine.analyze_batch(symbols)
