"""
AutoWealth AI 涓诲紩鎿?- 鏁村悎鎵€鏈夋ā鍧楃殑缁熶竴鎺ュ彛
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
    AutoWealth AI 涓诲紩鎿?
    鏁村悎鏁版嵁鑾峰彇銆佹妧鏈垎鏋愩€佸熀鏈潰鍒嗘瀽銆佸鏅鸿兘浣撳喅绛栫瓑鍔熻兘
    鎻愪緵绠€鍗曟槗鐢ㄧ殑鎶曡祫鍒嗘瀽鎺ュ彛
    """

    def __init__(self):
        self.settings = get_settings()
        self.logger = logging.getLogger("autowealth.engine")

        # 鍒濆鍖栨牳蹇冪粍浠?        self.data_fetcher = DataFetcher()
        self.technical_analyzer = TechnicalAnalyzer()
        self.fundamental_analyzer = FundamentalAnalyzer()

        # 鍒濆鍖栨櫤鑳戒綋绯荤粺
        self.coordinator = AgentCoordinator()
        self._register_default_agents()

        self.logger.info("AutoWealth AI 寮曟搸鍒濆鍖栧畬鎴?)

    def _register_default_agents(self):
        """娉ㄥ唽榛樿鐨勬櫤鑳戒綋"""
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
        缁煎悎鍒嗘瀽鑲＄エ

        Args:
            symbol: 鑲＄エ浠ｇ爜 (濡? AAPL, 600519.SS)
            include_technical: 鏄惁鍖呭惈鎶€鏈垎鏋?            include_fundamental: 鏄惁鍖呭惈鍩烘湰闈㈠垎鏋?            include_sentiment: 鏄惁鍖呭惈鎯呯华鍒嗘瀽

        Returns:
            鍖呭惈瀹屾暣鍒嗘瀽缁撴灉鐨勫瓧鍏?        """
        self.logger.info(f"寮€濮嬪垎鏋? {symbol}")

        result = {
            "symbol": symbol,
            "success": False,
            "error": None,
        }

        try:
            # 1. 鑾峰彇鏁版嵁
            self.logger.info(f"鑾峰彇 {symbol} 鐨勬暟鎹?..")
            historical_data = self.data_fetcher.get_stock_data(symbol, period="1y")
            stock_info = self.data_fetcher.get_stock_info(symbol)

            if historical_data.empty:
                raise ValueError(f"鏃犳硶鑾峰彇 {symbol} 鐨勬暟鎹?)

            # 2. 鍑嗗鍒嗘瀽鏁版嵁
            analysis_data = {
                "historical_data": historical_data,
                "stock_info": stock_info,
            }

            # 3. 鎵ц鍒嗘瀽
            if any([include_technical, include_fundamental, include_sentiment]):
                analysis_result = self.coordinator.analyze(symbol, analysis_data)
                result["decision"] = analysis_result["final_decision"]
                result["individual_signals"] = analysis_result["individual_signals"]
                result["summary"] = analysis_result["analysis_summary"]

            # 4. 娣诲姞璇︾粏鍒嗘瀽鏁版嵁
            if include_technical:
                result["technical_analysis"] = self.technical_analyzer.full_analysis(historical_data).iloc[-10:].to_dict()

            if include_fundamental and stock_info.get("symbol"):
                result["fundamental_analysis"] = self.fundamental_analyzer.full_fundamental_analysis(
                    stock_info, historical_data
                )

            result["stock_info"] = stock_info
            result["success"] = True
            self.logger.info(f"{symbol} 鍒嗘瀽瀹屾垚")

        except Exception as e:
            self.logger.error(f"鍒嗘瀽 {symbol} 澶辫触: {e}")
            result["error"] = str(e)

        return result

    def analyze_batch(self, symbols: List[str]) -> Dict[str, Any]:
        """
        鎵归噺鍒嗘瀽澶氬彧鑲＄エ

        Args:
            symbols: 鑲＄エ浠ｇ爜鍒楄〃

        Returns:
            鍖呭惈鎵€鏈夊垎鏋愮粨鏋滅殑瀛楀吀
        """
        self.logger.info(f"寮€濮嬫壒閲忓垎鏋?{len(symbols)} 鍙偂绁?..")

        results = {}
        for symbol in symbols:
            try:
                results[symbol] = self.analyze(symbol)
            except Exception as e:
                self.logger.error(f"鍒嗘瀽 {symbol} 澶辫触: {e}")
                results[symbol] = {"symbol": symbol, "success": False, "error": str(e)}

        # 鎺掑簭鐢熸垚鎺ㄨ崘鍒楄〃
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

        # 鎸夌疆淇″害鎺掑簭
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
        """鑾峰彇甯傚満姒傝"""
        self.logger.info("鑾峰彇甯傚満姒傝...")

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
            self.logger.error(f"鑾峰彇甯傚満姒傝澶辫触: {e}")
            return {"success": False, "error": str(e)}

    def get_portfolio_analysis(self, holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        鍒嗘瀽鎶曡祫缁勫悎

        Args:
            holdings: 鎸佷粨鍒楄〃锛屾瘡椤瑰寘鍚?symbol 鍜?quantity

        Returns:
            鎶曡祫缁勫悎鍒嗘瀽缁撴灉
        """
        self.logger.info(f"鍒嗘瀽鎶曡祫缁勫悎锛屽叡 {len(holdings)} 鍙偂绁?..")

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
                    current_price = result["stock_info"].get("market_cap", 0)
                    # 璁＄畻鎸佷粨浠峰€硷紙绠€鍖栫増锛?                    holding_value = quantity * current_price
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
                self.logger.error(f"鍒嗘瀽鎸佷粨 {symbol} 澶辫触: {e}")

        return {
            "holdings": analysis_results,
            "total_value": total_value,
            "total_gain_loss": total_gain_loss,
            "return_pct": (total_gain_loss / (total_value - total_gain_loss) * 100) if total_value > 0 else 0,
        }


# 渚挎嵎鍑芥暟
def quick_analyze(symbol: str) -> Dict[str, Any]:
    """蹇€熷垎鏋愬崟鍙偂绁?""
    engine = AutoWealthEngine()
    return engine.analyze(symbol)


def batch_analyze(symbols: List[str]) -> Dict[str, Any]:
    """鎵归噺鍒嗘瀽澶氬彧鑲＄エ"""
    engine = AutoWealthEngine()
    return engine.analyze_batch(symbols)
