"""
鍩烘湰闈㈠垎鏋愭櫤鑳戒綋 - 鍩轰簬鍏徃鍩烘湰闈㈡暟鎹敓鎴愪氦鏄撲俊鍙?"""
from typing import Any, Dict

from autowealth.agents.base_agent import AgentSignal, BaseAgent
from autowealth.core.analyzer import FundamentalAnalyzer


class FundamentalAgent(BaseAgent):
    """
    鍩烘湰闈㈠垎鏋愭櫤鑳戒綋

    鍩轰簬鍏徃璐㈠姟鏁版嵁銆佷及鍊兼寚鏍囥€佹垚闀挎€х瓑鍩烘湰闈㈠洜绱?    鍒嗘瀽骞剁敓鎴愪腑闀挎湡鎶曡祫寤鸿
    """

    def __init__(self):
        super().__init__(
            name="FundamentalAnalyst",
            description="鍩轰簬鍩烘湰闈㈠垎鏋愮敓鎴愪腑闀挎湡鎶曡祫寤鸿"
        )
        self.analyzer = FundamentalAnalyzer()

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        鍩烘湰闈㈠垎鏋愬苟鐢熸垚淇″彿

        Args:
            symbol: 鑲＄エ浠ｇ爜
            data: 蹇呴』鍖呭惈 'stock_info' (Dict) 鍜?'historical_data' (DataFrame)

        Returns:
            AgentSignal
        """
        if not self.validate_data(data, ["stock_info", "historical_data"]):
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=0,
                reasoning="缂哄皯鍩烘湰闈㈡暟鎹紝鏃犳硶杩涜鍒嗘瀽"
            )

        stock_info = data["stock_info"]
        historical_data = data["historical_data"]

        # 鎵ц鍩烘湰闈㈠垎鏋?        analysis = self.analyzer.full_fundamental_analysis(stock_info, historical_data)

        valuation = analysis["valuation"]
        growth = analysis["growth"]
        overall_score = analysis["overall_score"]

        # 鍩轰簬璇勫垎鐢熸垚淇″彿
        if overall_score >= 70:
            signal_type = "buy"
            confidence = min(95, overall_score)
            reasoning = self._generate_buy_reason(valuation, growth)
        elif overall_score <= 30:
            signal_type = "sell"
            confidence = min(95, 100 - overall_score)
            reasoning = self._generate_sell_reason(valuation, growth)
        else:
            signal_type = "hold"
            confidence = 50
            reasoning = self._generate_hold_reason(valuation, growth)

        # 璁＄畻鐩爣浠?        current_price = historical_data["Close"].iloc[-1]
        if signal_type == "buy":
            # 鍩轰簬PE浼板€艰绠楃洰鏍囦环
            pe = valuation.get("pe_ratio", 20)
            if pe > 0 and pe < 50:
                target_pe = 25  # 鍚堢悊PE
                target_price = current_price * (target_pe / pe)
            else:
                target_price = current_price * 1.15  # 榛樿15%涓婃定绌洪棿
            stop_loss = current_price * 0.90
        elif signal_type == "sell":
            target_price = current_price * 0.85
            stop_loss = current_price * 1.10
        else:
            target_price = None
            stop_loss = None

        return AgentSignal(
            agent_name=self.name,
            signal_type=signal_type,
            confidence=round(confidence, 2),
            reasoning=reasoning,
            target_price=round(target_price, 2) if target_price else None,
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            time_horizon="long",
            metadata={
                "valuation_score": round(valuation["valuation_score"], 2),
                "growth_score": round(growth["growth_score"], 2),
                "overall_score": round(overall_score, 2),
                "pe_ratio": valuation.get("pe_ratio", 0),
                "pb_ratio": valuation.get("pb_ratio", 0),
                "trend": growth.get("trend", "unknown"),
            }
        )

    def _generate_buy_reason(self, valuation: Dict, growth: Dict) -> str:
        """鐢熸垚涔板叆鐞嗙敱"""
        reasons = ["鍩烘湰闈㈠垎鏋愮患鍚堣瘎鍒嗕紭绉€锛屽缓璁拱鍏?"]

        if valuation.get("pe_ratio", 100) < 20:
            reasons.append(f"- PE浼板€煎悎鐞?({valuation['pe_ratio']:.2f})锛屽叿鏈夊畨鍏ㄨ竟闄?)
        elif valuation.get("pe_ratio", 100) < 30:
            reasons.append(f"- PE浼板€奸€備腑 ({valuation['pe_ratio']:.2f})")

        if valuation.get("pb_ratio", 100) < 3:
            reasons.append(f"- PB浼板€艰緝浣?({valuation['pb_ratio']:.2f})")

        if valuation.get("dividend_yield", 0) > 0.02:
            reasons.append(f"- 鑲℃伅鐜囧彲瑙?({valuation['dividend_yield']*100:.2f}%)")

        if growth.get("trend") in ["uptrend", "strong_uptrend"]:
            reasons.append(f"- 浠锋牸瓒嬪娍鍚戜笂锛岃繎3鏈堟定骞?{growth.get('return_3m', 0):.2f}%")

        return "\n".join(reasons)

    def _generate_sell_reason(self, valuation: Dict, growth: Dict) -> str:
        """鐢熸垚鍗栧嚭鐞嗙敱"""
        reasons = ["鍩烘湰闈㈠垎鏋愮患鍚堣瘎鍒嗚緝宸紝寤鸿鍗栧嚭鎴栬閬?"]

        if valuation.get("pe_ratio", 0) > 50:
            reasons.append(f"- PE浼板€艰繃楂?({valuation['pe_ratio']:.2f})锛屽瓨鍦ㄦ场娌闄?)

        if valuation.get("pb_ratio", 0) > 10:
            reasons.append(f"- PB浼板€艰繃楂?({valuation['pb_ratio']:.2f})")

        if growth.get("trend") in ["downtrend", "strong_downtrend"]:
            reasons.append(f"- 浠锋牸瓒嬪娍鍚戜笅锛岃繎3鏈堣穼骞?{growth.get('return_3m', 0):.2f}%")

        return "\n".join(reasons)

    def _generate_hold_reason(self, valuation: Dict, growth: Dict) -> str:
        """鐢熸垚瑙傛湜鐞嗙敱"""
        reasons = ["鍩烘湰闈㈠垎鏋愯瘎鍒嗕腑鎬э紝寤鸿瑙傛湜:"]

        pe = valuation.get("pe_ratio", 0)
        if 20 <= pe <= 40:
            reasons.append(f"- PE浼板€奸€備腑 ({pe:.2f})锛屾棤鏄庢樉浣庝及鎴栭珮浼?)

        trend = growth.get("trend", "unknown")
        if trend == "sideways":
            reasons.append("- 浠锋牸澶勪簬妯洏鏁寸悊闃舵锛屾柟鍚戜笉鏄?)

        return "\n".join(reasons)
