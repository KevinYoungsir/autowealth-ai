"""
鎶€鏈垎鏋愭櫤鑳戒綋 - 鍩轰簬鎶€鏈寚鏍囩敓鎴愪氦鏄撲俊鍙?"""
from typing import Any, Dict

import pandas as pd

from autowealth.agents.base_agent import AgentSignal, BaseAgent
from autowealth.core.analyzer import TechnicalAnalyzer


class TechnicalAgent(BaseAgent):
    """
    鎶€鏈垎鏋愭櫤鑳戒綋

    鍩轰簬澶氱鎶€鏈寚鏍囷紙MA銆丮ACD銆丷SI銆佸竷鏋楀甫銆並DJ绛夛級
    缁煎悎鍒嗘瀽骞剁敓鎴愪氦鏄撲俊鍙?    """

    def __init__(self):
        super().__init__(
            name="TechnicalAnalyst",
            description="鍩轰簬鎶€鏈寚鏍囧垎鏋愮敓鎴愪氦鏄撲俊鍙?
        )
        self.analyzer = TechnicalAnalyzer()

    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        鎶€鏈垎鏋愬苟鐢熸垚淇″彿

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
                reasoning="缂哄皯鍘嗗彶鏁版嵁锛屾棤娉曡繘琛屽垎鏋?
            )

        df = data["historical_data"]
        if len(df) < 60:
            return AgentSignal(
                agent_name=self.name,
                signal_type="hold",
                confidence=30,
                reasoning="鍘嗗彶鏁版嵁涓嶈冻锛屽缓璁鏈?
            )

        # 璁＄畻鎵€鏈夋妧鏈寚鏍?        analyzed_df = self.analyzer.full_analysis(df)
        latest = analyzed_df.iloc[-1]
        prev = analyzed_df.iloc[-2]

        # 鍒嗘瀽鍚勭淇″彿
        signals = []
        confidences = []
        reasons = []

        # 1. MACD淇″彿
        macd_signal = self._analyze_macd(latest, prev)
        signals.append(macd_signal["signal"])
        confidences.append(macd_signal["confidence"])
        reasons.append(macd_signal["reason"])

        # 2. RSI淇″彿
        rsi_signal = self._analyze_rsi(latest)
        signals.append(rsi_signal["signal"])
        confidences.append(rsi_signal["confidence"])
        reasons.append(rsi_signal["reason"])

        # 3. 甯冩灄甯︿俊鍙?        bb_signal = self._analyze_bollinger(latest, prev)
        signals.append(bb_signal["signal"])
        confidences.append(bb_signal["confidence"])
        reasons.append(bb_signal["reason"])

        # 4. KDJ淇″彿
        kdj_signal = self._analyze_kdj(latest, prev)
        signals.append(kdj_signal["signal"])
        confidences.append(kdj_signal["confidence"])
        reasons.append(kdj_signal["reason"])

        # 5. 鍧囩嚎淇″彿
        ma_signal = self._analyze_moving_averages(latest)
        signals.append(ma_signal["signal"])
        confidences.append(ma_signal["confidence"])
        reasons.append(ma_signal["reason"])

        # 缁煎悎鍒ゆ柇
        buy_count = signals.count("buy")
        sell_count = signals.count("sell")
        hold_count = signals.count("hold")

        if buy_count > sell_count and buy_count >= 3:
            final_signal = "buy"
        elif sell_count > buy_count and sell_count >= 3:
            final_signal = "sell"
        else:
            final_signal = "hold"

        # 璁＄畻缁煎悎缃俊搴?        avg_confidence = sum(confidences) / len(confidences)

        # 濡傛灉淇″彿涓€鑷存€у己锛屾彁楂樼疆淇″害
        if buy_count >= 4 or sell_count >= 4:
            avg_confidence = min(95, avg_confidence + 10)

        reasoning = f"鎶€鏈垎鏋愮患鍚堢粨鏋? {buy_count}涓拱鍏ヤ俊鍙? {sell_count}涓崠鍑轰俊鍙? {hold_count}涓鏈涗俊鍙枫€俓n"
        reasoning += "璇︾粏鍒嗘瀽:\n" + "\n".join([f"- {r}" for r in reasons])

        # 璁＄畻鐩爣浠峰拰姝㈡崯浠?        current_price = latest["Close"]
        if final_signal == "buy":
            target_price = current_price * 1.08  # 8%鐩爣鏀剁泭
            stop_loss = current_price * 0.95     # 5%姝㈡崯
        elif final_signal == "sell":
            target_price = current_price * 0.92  # 8%涓嬭穼鐩爣
            stop_loss = current_price * 1.05     # 5%鍙嶅脊姝㈡崯
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
        """鍒嗘瀽MACD淇″彿"""
        macd = latest.get("MACD", 0)
        signal = latest.get("MACD_Signal", 0)
        histogram = latest.get("MACD_Histogram", 0)
        prev_histogram = prev.get("MACD_Histogram", 0)

        if macd > signal and histogram > 0 and histogram > prev_histogram:
            return {"signal": "buy", "confidence": 75, "reason": "MACD閲戝弶涓旀煴鐘跺浘鎵╁ぇ锛屽姩鑳藉寮?}
        elif macd < signal and histogram < 0 and histogram < prev_histogram:
            return {"signal": "sell", "confidence": 75, "reason": "MACD姝诲弶涓旀煴鐘跺浘鎵╁ぇ锛屽姩鑳藉噺寮?}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "MACD淇″彿涓嶆槑纭?}

    def _analyze_rsi(self, latest: pd.Series) -> Dict:
        """鍒嗘瀽RSI淇″彿"""
        rsi = latest.get("RSI", 50)

        if rsi < 30:
            return {"signal": "buy", "confidence": 70, "reason": f"RSI瓒呭崠({rsi:.1f})锛屽彲鑳藉嚭鐜板弽寮?}
        elif rsi > 70:
            return {"signal": "sell", "confidence": 70, "reason": f"RSI瓒呬拱({rsi:.1f})锛屽彲鑳藉嚭鐜板洖璋?}
        elif 40 <= rsi <= 60:
            return {"signal": "hold", "confidence": 60, "reason": f"RSI涓€?{rsi:.1f})锛岃秼鍔夸笉鏄?}
        else:
            return {"signal": "hold", "confidence": 50, "reason": f"RSI澶勪簬涓棿鍖哄煙({rsi:.1f})"}

    def _analyze_bollinger(self, latest: pd.Series, prev: pd.Series) -> Dict:
        """鍒嗘瀽甯冩灄甯︿俊鍙?""
        position = latest.get("BB_Position", 0.5)
        prev_position = prev.get("BB_Position", 0.5)
        width = latest.get("BB_Width", 0)

        if position < 0.1 and prev_position < position:
            return {"signal": "buy", "confidence": 65, "reason": "浠锋牸瑙﹀強甯冩灄甯︿笅杞紝鍙兘鍙嶅脊"}
        elif position > 0.9 and prev_position > position:
            return {"signal": "sell", "confidence": 65, "reason": "浠锋牸瑙﹀強甯冩灄甯︿笂杞紝鍙兘鍥炶皟"}
        elif width > 0 and position > 0.5:
            return {"signal": "hold", "confidence": 55, "reason": "浠锋牸鍦ㄥ竷鏋楀甫涓建涓婃柟杩愯"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "甯冩灄甯︿俊鍙蜂腑鎬?}

    def _analyze_kdj(self, latest: pd.Series, prev: pd.Series) -> Dict:
        """鍒嗘瀽KDJ淇″彿"""
        k = latest.get("K", 50)
        d = latest.get("D", 50)
        j = latest.get("J", 50)
        prev_k = prev.get("K", 50)
        prev_d = prev.get("D", 50)

        if k > d and prev_k <= prev_d and k < 80:
            return {"signal": "buy", "confidence": 70, "reason": "KDJ閲戝弶褰㈡垚锛屼拱鍏ヤ俊鍙?}
        elif k < d and prev_k >= prev_d and k > 20:
            return {"signal": "sell", "confidence": 70, "reason": "KDJ姝诲弶褰㈡垚锛屽崠鍑轰俊鍙?}
        elif j > 100:
            return {"signal": "sell", "confidence": 60, "reason": "J鍊艰繃楂橈紝鍙兘瓒呬拱"}
        elif j < 0:
            return {"signal": "buy", "confidence": 60, "reason": "J鍊艰繃浣庯紝鍙兘瓒呭崠"}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "KDJ淇″彿涓€?}

    def _analyze_moving_averages(self, latest: pd.Series) -> Dict:
        """鍒嗘瀽鍧囩嚎淇″彿"""
        close = latest.get("Close", 0)
        ma5 = latest.get("MA5", 0)
        ma20 = latest.get("MA20", 0)
        ma60 = latest.get("MA60", 0)

        if close > ma5 > ma20 > ma60:
            return {"signal": "buy", "confidence": 80, "reason": "澶氬ご鎺掑垪锛屽己鍔夸笂娑?}
        elif close < ma5 < ma20 < ma60:
            return {"signal": "sell", "confidence": 80, "reason": "绌哄ご鎺掑垪锛屽急鍔夸笅璺?}
        elif close > ma20 and ma5 > ma20:
            return {"signal": "buy", "confidence": 60, "reason": "鐭湡鍧囩嚎鍦ㄩ暱鏈熷潎绾夸笂鏂?}
        elif close < ma20 and ma5 < ma20:
            return {"signal": "sell", "confidence": 60, "reason": "鐭湡鍧囩嚎鍦ㄩ暱鏈熷潎绾夸笅鏂?}
        else:
            return {"signal": "hold", "confidence": 50, "reason": "鍧囩嚎淇″彿娣峰悎"}
