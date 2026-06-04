"""
鎯呯华鍒嗘瀽鏅鸿兘浣?- 鍩轰簬甯傚満鎯呯华鐢熸垚浜ゆ槗淇″彿
"""
from typing import Any, Dict

import pandas as pd

from autowealth.agents.base_agent import AgentSignal, BaseAgent


class SentimentAgent(BaseAgent):
    """
    甯傚満鎯呯华鍒嗘瀽鏅鸿兘浣?
    鍩轰簬浠锋牸鍔ㄩ噺銆佹垚浜ら噺鍙樺寲銆佹尝鍔ㄧ巼绛夊競鍦鸿涓烘寚鏍?    鍒嗘瀽甯傚満鎯呯华骞剁敓鎴愪氦鏄撲俊鍙?    """

    def __init__(self):
        super().__init__(
            name="SentimentAnalyst",
            description="鍩轰簬甯傚満鎯呯华鍜屾妧鏈姩閲忕敓鎴愪氦鏄撲俊鍙?
        )

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        甯傚満鎯呯华鍒嗘瀽骞剁敓鎴愪俊鍙?
        Args:
            symbol: 鑲＄エ浠ｇ爜
            data: 蹇呴』鍖呭惈 'historical_data' (DataFrame)

        Returns:
            AgentSignal
        """
        if not self.validate_data(data, ["historical_data"]):
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=0,
                reasoning="缂哄皯鍘嗗彶鏁版嵁锛屾棤娉曞垎鏋愬競鍦烘儏缁?
            )

        df = data["historical_data"]
        if len(df) < 20:
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=30,
                reasoning="鍘嗗彶鏁版嵁涓嶈冻锛屾棤娉曞垽鏂競鍦烘儏缁?
            )

        # 璁＄畻鎯呯华鎸囨爣
        sentiment_indicators = self._calculate_sentiment_indicators(df)

        # 鍒嗘瀽鎯呯华
        sentiment_score = sentiment_indicators["overall_sentiment"]
        momentum = sentiment_indicators["momentum"]
        volume_trend = sentiment_indicators["volume_trend"]
        volatility_state = sentiment_indicators["volatility_state"]

        # 鐢熸垚淇″彿
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

        # 璁＄畻鐩爣浠?        current_price = df["Close"].iloc[-1]
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
        """璁＄畻鎯呯华鎸囨爣"""
        # 浠锋牸鍔ㄩ噺
        returns_5d = (df["Close"].iloc[-1] - df["Close"].iloc[-5]) / df["Close"].iloc[-5] * 100
        returns_10d = (df["Close"].iloc[-1] - df["Close"].iloc[-10]) / df["Close"].iloc[-10] * 100
        momentum = (returns_5d + returns_10d) / 2

        # 鎴愪氦閲忚秼鍔?        vol_ma5 = df["Volume"].iloc[-5:].mean()
        vol_ma20 = df["Volume"].iloc[-20:].mean()
        volume_ratio = vol_ma5 / vol_ma20 if vol_ma20 > 0 else 1.0

        if volume_ratio > 1.3:
            volume_trend = "high"
        elif volume_ratio < 0.7:
            volume_trend = "low"
        else:
            volume_trend = "normal"

        # 娉㈠姩鐜?        volatility = df["Close"].pct_change().std() * 100
        if volatility > 3:
            volatility_state = "high"
        elif volatility < 1:
            volatility_state = "low"
        else:
            volatility_state = "normal"

        # 缁煎悎鎯呯华璇勫垎 (0-100)
        # 鍔ㄩ噺璐＄尞 40%锛屾垚浜ら噺璐＄尞 30%锛屾尝鍔ㄧ巼璐＄尞 30%
        momentum_score = 50 + momentum * 2  # 鍔ㄩ噺杞崲涓?0鍩哄噯鐨勫垎鏁?        momentum_score = max(0, min(100, momentum_score))

        if volume_trend == "high":
            volume_score = 70 if momentum > 0 else 30
        elif volume_trend == "low":
            volume_score = 40
        else:
            volume_score = 50

        if volatility_state == "high":
            volatility_score = 40  # 楂樻尝鍔ㄧ巼闄嶄綆鎯呯华鍒?        elif volatility_state == "low":
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
        """鐢熸垚鐪嬫定鐞嗙敱"""
        reasons = ["甯傚満鎯呯华绉瀬锛屽缓璁拱鍏?"]

        momentum = indicators.get("momentum", 0)
        if momentum > 5:
            reasons.append(f"- 寮哄姴涓婃定鍔ㄨ兘锛岃繎10鏃ュ钩鍧囨定骞?{momentum:.2f}%")
        else:
            reasons.append(f"- 姝ｅ悜鍔ㄩ噺锛岃繎10鏃ュ钩鍧囨定骞?{momentum:.2f}%")

        volume_trend = indicators.get("volume_trend", "normal")
        if volume_trend == "high":
            reasons.append("- 鎴愪氦閲忔斁澶э紝璧勯噾娴佸叆鏄庢樉")

        volatility = indicators.get("volatility_state", "normal")
        if volatility == "low":
            reasons.append("- 娉㈠姩鐜囪緝浣庯紝涓婃定鍩虹绋冲浐")

        return "\n".join(reasons)

    def _generate_bearish_reason(self, indicators: Dict) -> str:
        """鐢熸垚鐪嬭穼鐞嗙敱"""
        reasons = ["甯傚満鎯呯华娑堟瀬锛屽缓璁崠鍑?"]

        momentum = indicators.get("momentum", 0)
        if momentum < -5:
            reasons.append(f"- 寮哄姴涓嬭穼鍔ㄨ兘锛岃繎10鏃ュ钩鍧囪穼骞?{abs(momentum):.2f}%")
        else:
            reasons.append(f"- 璐熷悜鍔ㄩ噺锛岃繎10鏃ュ钩鍧囪穼骞?{abs(momentum):.2f}%")

        volume_trend = indicators.get("volume_trend", "normal")
        if volume_trend == "high":
            reasons.append("- 鎴愪氦閲忔斁澶э紝鎶涘帇娌夐噸")

        return "\n".join(reasons)

    def _generate_neutral_reason(self, indicators: Dict) -> str:
        """鐢熸垚涓€х悊鐢?""
        reasons = ["甯傚満鎯呯华涓€э紝寤鸿瑙傛湜:"]

        sentiment = indicators.get("overall_sentiment", 50)
        reasons.append(f"- 缁煎悎鎯呯华璇勫垎 {sentiment:.1f}/100锛屽浜庝腑鎬у尯闂?)

        volatility = indicators.get("volatility_state", "normal")
        if volatility == "high":
            reasons.append("- 娉㈠姩鐜囪緝楂橈紝甯傚満涓嶇‘瀹氭€уぇ")

        return "\n".join(reasons)
