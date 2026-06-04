"""
技术分析智能体 - 基于技术指标生成交易信号
"""
from typing import Any, Dict

import pandas as pd

from autowealth.agents.base_agent import AgentSignal, BaseAgent
from autowealth.core.analyzer import TechnicalAnalyzer


class TechnicalAgent(BaseAgent):
    """
    技术分析智能体

    基于多种技术指标（MA、MACD、RSI、布林带、KDJ等）
    综合分析并生成交易信号
    """

    def __init__(self):
        super().__init__(
            name="TechnicalAnalyst",
            description="基于技术指标分析生成交易信号"
        )
        self.analyzer = TechnicalAnalyzer()

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        技术分析并生成信号

        Args:
            symbol: 股票代码
            data: 必须包含 'historical_data' (DataFrame)

        Returns:
            AgentSignal
        """
        if not self.validate_data(data, ["historical_data"]):
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=0,
                reasoning="缺少历史数据，无法进行分析"
            )

        df = data["historical_data"]
        if len(df) < 60:
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=30,
                reasoning="历史数据不足，建议观望"
            )

        # 计算所有技术指标
        analyzed_df = self.analyzer.full_analysis(df)
        latest = analyzed_df.iloc[-1]
        prev = analyzed_df.iloc[-2]

        # 分析各种信号
        signals = []
        confidences = []
        reasons = []

        # 1. MACD信号
        macd_signal = self._analyze_macd(latest, prev)
        signals.append(macd_signal["signal"])
        confidences.append(macd_signal["confidence"])
        reasons.append(macd_signal["reason"])

        # 2. RSI信号
        rsi_signal = self._analyze_rsi(latest)
        signals.append(rsi_signal["signal"])
        confidences.append(rsi_signal["confidence"])
        reasons.append(rsi_signal["reason"])

        # 3. 布林带信号
        bb_signal = self._analyze_bollinger(latest, prev)
        signals.append(bb_signal["signal"])
        confidences.append(bb_signal["confidence"])
        reasons.append(bb_signal["reason"])

        # 4. KDJ信号
        kdj_signal = self._analyze_kdj(latest, prev)
        signals.append(kdj_signal["signal"])
        confidences.append(kdj_signal["confidence"])
        reasons.append(kdj_signal["reason"])

        # 5. 均线信号
        ma_signal = self._analyze_moving_averages(latest)
        signals.append(ma_signal["signal"])
        confidences.append(ma_signal["confidence"])
        reasons.append(ma_signal["reason"])

        # 综合判断
        buy_count = signals.count("buy")
        sell_count = signals.count("sell")
        hold_count = signals.count("hold")

        if buy_count > sell_count and buy_count >= 3:
            final_signal = "buy"
        elif sell_count > buy_count and sell_count >= 3:
            final_signal = "sell"
        else:
            final_signal = "hold"

        # 计算综合置信度
        avg_confidence = sum(confidences) / len(confidences)

        # 如果信号一致性强，提高置信度
        if buy_count >= 4 or sell_count >= 4:
            avg_confidence = min(95, avg_confidence + 10)

        reasoning = f"技术分析综合结果: {buy_count}个买入信号, {sell_count}个卖出信号, {hold_count}个观望信号。\n"
        reasoning += "详细分析:\n" + "\n".join([f"- {r}" for r in reasons])

        # 计算目标价和止损价
        current_price = latest["Close"]
        if final_signal == "buy":
            target_price = current_price * 1.08  # 8%目标收益
            stop_loss = current_price * 0.95     # 5%止损
        elif final_signal == "sell":
            target_price = current_price * 0.92  # 8%下跌目标
            stop_loss = current_price * 1.05     # 5%反弹止损
        else:
            target_price = None
            stop_loss = None

        return AgentSignal(
            agent_name=self.name,
            signal_type=final_signal,
            confidence=round(avg_confidence, 2),
            reasoning=reasoning,
            target_price=round(target_price, 2) if target_price else None,
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            time_horizon="short",
            metadata={
                "buy_signals": buy_count,
                "sell_signals": sell_count,
                "hold_signals": hold_count,
                "indicators": {
                    "rsi": round(latest.get("RSI", 0), 2),
                    "macd": round(latest.get("MACD", 0), 4),
                    "kdj_k": round(latest.get("K", 0), 2),
                    "kdj_d": round(latest.get("D", 0), 2),
                }
            }
        )

    def _analyze_macd(self, latest: pd.Series, prev: pd.Series) -> Dict:
        """分析MACD信号"""
        macd = latest.get("MACD", 0)
        signal = latest.get("MACD_Signal", 0)
        histogram = latest.get("MACD_Histogram", 0)
        prev_histogram = prev.get("MACD_Histogram", 0)

        if macd > signal and histogram > 0 and histogram > prev_histogram:
            return {"signal": "buy", "confidence": 75, "reason": "MACD金叉且柱状图扩大，动能增强"}
        elif macd < signal and histogram < 0 and histogram < prev_histogram:
            return {"signal": "sell", "confidence": 75, "reason": "MACD死叉且柱状图扩大，动能减弱"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "MACD信号不明确"}

    def _analyze_rsi(self, latest: pd.Series) -> Dict:
        """分析RSI信号"""
        rsi = latest.get("RSI", 50)

        if rsi < 30:
            return {"signal": "buy", "confidence": 70, "reason": f"RSI超卖({rsi:.1f})，可能出现反弹"}
        elif rsi > 70:
            return {"signal": "sell", "confidence": 70, "reason": f"RSI超买({rsi:.1f})，可能出现回调"}
        elif 40 <= rsi <= 60:
            return {"signal": "hold", "confidence": 60, "reason": f"RSI中性({rsi:.1f})，趋势不明"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": f"RSI处于中间区域({rsi:.1f})"}

    def _analyze_bollinger(self, latest: pd.Series, prev: pd.Series) -> Dict:
        """分析布林带信号"""
        position = latest.get("BB_Position", 0.5)
        prev_position = prev.get("BB_Position", 0.5)
        width = latest.get("BB_Width", 0)

        if position < 0.1 and prev_position < position:
            return {"signal": "buy", "confidence": 65, "reason": "价格触及布林带下轨，可能反弹"}
        elif position > 0.9 and prev_position > position:
            return {"signal": "sell", "confidence": 65, "reason": "价格触及布林带上轨，可能回调"}
        elif width > 0 and position > 0.5:
            return {"signal": "hold", "confidence": 55, "reason": "价格在布林带中轨上方运行"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "布林带信号中性"}

    def _analyze_kdj(self, latest: pd.Series, prev: pd.Series) -> Dict:
        """分析KDJ信号"""
        k = latest.get("K", 50)
        d = latest.get("D", 50)
        j = latest.get("J", 50)
        prev_k = prev.get("K", 50)
        prev_d = prev.get("D", 50)

        if k > d and prev_k <= prev_d and k < 80:
            return {"signal": "buy", "confidence": 70, "reason": "KDJ金叉形成，买入信号"}
        elif k < d and prev_k >= prev_d and k > 20:
            return {"signal": "sell", "confidence": 70, "reason": "KDJ死叉形成，卖出信号"}
        elif j > 100:
            return {"signal": "sell", "confidence": 60, "reason": "J值过高，可能超买"}
        elif j < 0:
            return {"signal": "buy", "confidence": 60, "reason": "J值过低，可能超卖"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "KDJ信号中性"}

    def _analyze_moving_averages(self, latest: pd.Series) -> Dict:
        """分析均线信号"""
        close = latest.get("Close", 0)
        ma5 = latest.get("MA5", 0)
        ma20 = latest.get("MA20", 0)
        ma60 = latest.get("MA60", 0)

        if close > ma5 > ma20 > ma60:
            return {"signal": "buy", "confidence": 80, "reason": "多头排列，强势上涨"}
        elif close < ma5 < ma20 < ma60:
            return {"signal": "sell", "confidence": 80, "reason": "空头排列，弱势下跌"}
        elif close > ma20 and ma5 > ma20:
            return {"signal": "buy", "confidence": 60, "reason": "短期均线在长期均线上方"}
        elif close < ma20 and ma5 < ma20:
            return {"signal": "sell", "confidence": 60, "reason": "短期均线在长期均线下方"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "均线信号混合"}
