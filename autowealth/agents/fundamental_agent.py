"""
基本面分析智能体 - 基于公司基本面数据生成交易信号
"""
from typing import Any, Dict

from autowealth.agents.base_agent import AgentSignal, BaseAgent
from autowealth.core.analyzer import FundamentalAnalyzer


class FundamentalAgent(BaseAgent):
    """
    基本面分析智能体

    基于公司财务数据、估值指标、成长性等基本面因素
    分析并生成中长期投资建议
    """

    def __init__(self):
        super().__init__(
            name="FundamentalAnalyst",
            description="基于基本面分析生成中长期投资建议"
        )
        self.analyzer = FundamentalAnalyzer()

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        基本面分析并生成信号

        Args:
            symbol: 股票代码
            data: 必须包含 'stock_info' (Dict) 和 'historical_data' (DataFrame)

        Returns:
            AgentSignal
        """
        if not self.validate_data(data, ["stock_info", "historical_data"]):
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=0,
                reasoning="缺少基本面数据，无法进行分析"
            )

        stock_info = data["stock_info"]
        historical_data = data["historical_data"]

        # 执行基本面分析
        analysis = self.analyzer.full_fundamental_analysis(stock_info, historical_data)

        valuation = analysis["valuation"]
        growth = analysis["growth"]
        overall_score = analysis["overall_score"]

        # 基于评分生成信号
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

        # 计算目标价
        current_price = historical_data["Close"].iloc[-1]
        if signal_type == "buy":
            # 基于PE估值计算目标价
            pe = valuation.get("pe_ratio", 20)
            if pe > 0 and pe < 50:
                target_pe = 25  # 合理PE
                target_price = current_price * (target_pe / pe)
            else:
                target_price = current_price * 1.15  # 默认15%上涨空间
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
        """生成买入理由"""
        reasons = ["基本面分析综合评分优秀，建议买入:"]

        if valuation.get("pe_ratio", 100) < 20:
            reasons.append(f"- PE估值合理 ({valuation['pe_ratio']:.2f})，具有安全边际")
        elif valuation.get("pe_ratio", 100) < 30:
            reasons.append(f"- PE估值适中 ({valuation['pe_ratio']:.2f})")

        if valuation.get("pb_ratio", 100) < 3:
            reasons.append(f"- PB估值较低 ({valuation['pb_ratio']:.2f})")

        if valuation.get("dividend_yield", 0) > 0.02:
            reasons.append(f"- 股息率可观 ({valuation['dividend_yield']*100:.2f}%)")

        if growth.get("trend") in ["uptrend", "strong_uptrend"]:
            reasons.append(f"- 价格趋势向上，近3月涨幅 {growth.get('return_3m', 0):.2f}%")

        return "\n".join(reasons)

    def _generate_sell_reason(self, valuation: Dict, growth: Dict) -> str:
        """生成卖出理由"""
        reasons = ["基本面分析综合评分较差，建议卖出或规避:"]

        if valuation.get("pe_ratio", 0) > 50:
            reasons.append(f"- PE估值过高 ({valuation['pe_ratio']:.2f})，存在泡沫风险")

        if valuation.get("pb_ratio", 0) > 10:
            reasons.append(f"- PB估值过高 ({valuation['pb_ratio']:.2f})")

        if growth.get("trend") in ["downtrend", "strong_downtrend"]:
            reasons.append(f"- 价格趋势向下，近3月跌幅 {growth.get('return_3m', 0):.2f}%")

        return "\n".join(reasons)

    def _generate_hold_reason(self, valuation: Dict, growth: Dict) -> str:
        """生成观望理由"""
        reasons = ["基本面分析评分中性，建议观望:"]

        pe = valuation.get("pe_ratio", 0)
        if 20 <= pe <= 40:
            reasons.append(f"- PE估值适中 ({pe:.2f})，无明显低估或高估")

        trend = growth.get("trend", "unknown")
        if trend == "sideways":
            reasons.append("- 价格处于横盘整理阶段，方向不明")

        return "\n".join(reasons)
