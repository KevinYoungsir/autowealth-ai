"""
情绪分析智能体 - 基于市场情绪生成交易信号
"""
from typing import Any, Dict

import pandas as pd

from autowealth.agents.base_agent import AgentSignal, BaseAgent


class SentimentAgent(BaseAgent):
    """
    市场情绪分析智能体

    基于价格动量、成交量变化、波动率等市场行为指标
    分析市场情绪并生成交易信号
    """

    def __init__(self):
        super().__init__(
            name="SentimentAnalyst",
            description="基于市场情绪和技术动量生成交易信号"
        )

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        市场情绪分析并生成信号

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
                reasoning="缺少历史数据，无法分析市场情绪"
            )

        df = data["historical_data"]
        if len(df) < 20:
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=30,
                reasoning="历史数据不足，无法判断市场情绪"
            )

        # 计算情绪指标
        sentiment_indicators = self._calculate_sentiment_indicators(df)

        # 分析情绪
        sentiment_score = sentiment_indicators["overall_sentiment"]
        momentum = sentiment_indicators["momentum"]
        volume_trend = sentiment_indicators["volume_trend"]
        volatility_state = sentiment_indicators["volatility_state"]

        # 生成信号
        if sentiment_score > 70 and momentum > 0:
            signal_type = "buy"
            confidence = sentiment_score
            reasoning = self._generate_bullish_reason(sentiment_indicators)
        elif sentiment_score < 30 and momentum < 0:
            signal_type = "sell"
            confidence = 100 - sentiment_score
            reasoning = self._generate_bearish_reason(sentiment_indicators)
        else:
            signal_type = "hold"
            confidence = 50
            reasoning = self._generate_neutral_reason(sentiment_indicators)

        # 计算目标价
        current_price = df["Close"].iloc[-1]
        if signal_type == "buy":
            target_price = current_price * (1 + abs(momentum) / 100)
            stop_loss = current_price * 0.93
        elif signal_type == "sell":
            target_price = current_price * (1 - abs(momentum) / 100)
            stop_loss = current_price * 1.07
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
            time_horizon="medium",
            metadata={
                "sentiment_score": round(sentiment_score, 2),
                "momentum": round(momentum, 2),
                "volume_trend": volume_trend,
                "volatility_state": volatility_state,
            }
        )

    def _calculate_sentiment_indicators(self, df: pd.DataFrame) -> Dict:
        """计算情绪指标"""
        # 价格动量
        returns_5d = (df["Close"].iloc[-1] - df["Close"].iloc[-5]) / df["Close"].iloc[-5] * 100
        returns_10d = (df["Close"].iloc[-1] - df["Close"].iloc[-10]) / df["Close"].iloc[-10] * 100
        momentum = (returns_5d + returns_10d) / 2

        # 成交量趋势
        vol_ma5 = df["Volume"].iloc[-5:].mean()
        vol_ma20 = df["Volume"].iloc[-20:].mean()
        volume_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0

        if volume_ratio > 1.3:
            volume_trend = "high"
        elif volume_ratio < 0.7:
            volume_trend = "low"
        else:
            volume_trend = "normal"

        # 波动率
        volatility = df["Close"].pct_change().std() * 100
        if volatility > 3:
            volatility_state = "high"
        elif volatility < 1:
            volatility_state = "low"
        else:
            volatility_state = "normal"

        # 综合情绪评分 (0-100)
        # 动量贡献 40%，成交量贡献 30%，波动率贡献 30%
        momentum_score = 50 + momentum * 2  # 动量转换为50基准的分数
        momentum_score = max(0, min(100, momentum_score))

        if volume_trend == "high":
            volume_score = 70 if momentum > 0 else 30
        elif volume_trend == "low":
            volume_score = 40
        else:
            volume_score = 50

        if volatility_state == "high":
            volatility_score = 40  # 高波动率降低情绪分
        elif volatility_state == "low":
            volatility_score = 60
        else:
            volatility_score = 50

        overall_sentiment = (
            momentum_score * 0.4 + volume_score * 0.3 + volatility_score * 0.3
        )

        return {
            "momentum": momentum,
            "returns_5d": returns_5d,
            "returns_10d": returns_10d,
            "volume_ratio": volume_ratio,
            "volume_trend": volume_trend,
            "volatility": volatility,
            "volatility_state": volatility_state,
            "momentum_score": momentum_score,
            "volume_score": volume_score,
            "volatility_score": volatility_score,
            "overall_sentiment": overall_sentiment,
        }

    def _generate_bullish_reason(self, indicators: Dict) -> str:
        """生成看涨理由"""
        reasons = ["市场情绪积极，建议买入:"]

        momentum = indicators.get("momentum", 0)
        if momentum > 5:
            reasons.append(f"- 强劲上涨动能，近10日平均涨幅 {momentum:.2f}%")
        else:
            reasons.append(f"- 正向动量，近10日平均涨幅 {momentum:.2f}%")

        volume_trend = indicators.get("volume_trend", "normal")
        if volume_trend == "high":
            reasons.append("- 成交量放大，资金流入明显")

        volatility = indicators.get("volatility_state", "normal")
        if volatility == "low":
            reasons.append("- 波动率较低，上涨基础稳固")

        return "\n".join(reasons)

    def _generate_bearish_reason(self, indicators: Dict) -> str:
        """生成看跌理由"""
        reasons = ["市场情绪消极，建议卖出:"]

        momentum = indicators.get("momentum", 0)
        if momentum < -5:
            reasons.append(f"- 强劲下跌动能，近10日平均跌幅 {abs(momentum):.2f}%")
        else:
            reasons.append(f"- 负向动量，近10日平均跌幅 {abs(momentum):.2f}%")

        volume_trend = indicators.get("volume_trend", "normal")
        if volume_trend == "high":
            reasons.append("- 成交量放大，抛压沉重")

        return "\n".join(reasons)

    def _generate_neutral_reason(self, indicators: Dict) -> str:
        """生成中性理由"""
        reasons = ["市场情绪中性，建议观望:"]

        sentiment = indicators.get("overall_sentiment", 50)
        reasons.append(f"- 综合情绪评分 {sentiment:.1f}/100，处于中性区间")

        volatility = indicators.get("volatility_state", "normal")
        if volatility == "high":
            reasons.append("- 波动率较高，市场不确定性大")

        return "\n".join(reasons)
