"""
鏅鸿兘浣撳崗璋冨櫒 - 璐熻矗鍗忚皟澶氫釜鏅鸿兘浣撶殑鍒嗘瀽鍜屽喅绛?"""
import logging
from typing import Any, Dict, List, Optional

from autowealth.agents.base_agent import AgentSignal, BaseAgent

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    鏅鸿兘浣撳崗璋冨櫒

    璐熻矗绠＄悊澶氫釜鍒嗘瀽鏅鸿兘浣擄紝缁煎悎瀹冧滑鐨勪俊鍙风敓鎴愭渶缁堟姇璧勫喅绛?    """

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.logger = logging.getLogger("autowealth.coordinator")

        # 榛樿鏉冮噸閰嶇疆
        self.agent_weights = {
            "TechnicalAnalyst": 0.35,    # 鎶€鏈垎鏋愭潈閲?            "FundamentalAnalyst": 0.35,  # 鍩烘湰闈㈠垎鏋愭潈閲?            "SentimentAnalyst": 0.30,    # 鎯呯华鍒嗘瀽鏉冮噸
        }

    def register_agent(self, agent: BaseAgent, weight: Optional[float] = None):
        """
        娉ㄥ唽鏅鸿兘浣?
        Args:
            agent: 鏅鸿兘浣撳疄渚?            weight: 璇ユ櫤鑳戒綋鐨勫喅绛栨潈閲?(0-1)
        """
        self.agents[agent.name] = agent
        if weight is not None:
            self.agent_weights[agent.name] = weight
        self.logger.info(f"娉ㄥ唽鏅鸿兘浣? {agent.name} (鏉冮噸: {self.agent_weights.get(agent.name, 0.33)})")

    def unregister_agent(self, agent_name: str):
        """娉ㄩ攢鏅鸿兘浣?""
        if agent_name in self.agents:
            del self.agents[agent_name]
            if agent_name in self.agent_weights:
                del self.agent_weights[agent_name]
            self.logger.info(f"娉ㄩ攢鏅鸿兘浣? {agent_name}")

    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        鍗忚皟鎵€鏈夋櫤鑳戒綋杩涜鍒嗘瀽

        Args:
            symbol: 鑲＄エ浠ｇ爜
            data: 鍖呭惈鎵€鏈夌浉鍏虫暟鎹殑瀛楀吀

        Returns:
            鍖呭惈鎵€鏈夋櫤鑳戒綋淇″彿鍜岀患鍚堝喅绛栫殑瀛楀吀
        """
        self.logger.info(f"寮€濮嬪垎鏋?{symbol}锛屾櫤鑳戒綋鏁伴噺: {len(self.agents)}")

        # 鏀堕泦鎵€鏈夋櫤鑳戒綋鐨勪俊鍙?        signals: Dict[str, AgentSignal] = {}
        for name, agent in self.agents.items():
            try:
                signal = agent.analyze(symbol, data)
                signals[name] = signal
                self.logger.info(f"{name} 淇″彿: {signal.signal_type} (缃俊搴? {signal.confidence}%)")
            except Exception as e:
                self.logger.error(f"{name} 鍒嗘瀽澶辫触: {e}")
                signals[name] = AgentSignal(
                    agent_name=name,
                    signal_type="hold",
                    confidence=0,
                    reasoning=f"鍒嗘瀽鍑洪敊: {str(e)}"
                )

        # 缁煎悎鍐崇瓥
        final_decision = self._aggregate_signals(signals)

        return {
            "symbol": symbol,
            "individual_signals": signals,
            "final_decision": final_decision,
            "analysis_summary": self._generate_summary(signals, final_decision),
        }

    def _aggregate_signals(self, signals: Dict[str, AgentSignal]) -> Dict[str, Any]:
        """
        缁煎悎澶氫釜鏅鸿兘浣撶殑淇″彿鐢熸垚鏈€缁堝喅绛?
        浣跨敤鍔犳潈鎶曠エ鏈哄埗锛岃€冭檻淇″彿绫诲瀷鍜岀疆淇″害
        """
        if not signals:
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "娌℃湁鍙敤鐨勫垎鏋愪俊鍙?,
            }

        # 璁＄畻鍔犳潈鍒嗘暟
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        total_weight = 0.0

        signal_details = []

        for agent_name, signal in signals.items():
            weight = self.agent_weights.get(agent_name, 0.33)
            confidence = signal.confidence / 100.0  # 褰掍竴鍖栧埌0-1

            weighted_score = weight * confidence
            total_weight += weight

            if signal.signal_type == "buy":
                buy_score += weighted_score
            elif signal.signal_type == "sell":
                sell_score += weighted_score
            else:  # hold
                hold_score += weighted_score

            signal_details.append({
                "agent": agent_name,
                "signal": signal.signal_type,
                "confidence": signal.confidence,
                "weight": weight,
            })

        # 褰掍竴鍖栧垎鏁?        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
            hold_score /= total_weight

        # 纭畾鏈€缁堜俊鍙?        scores = {
            "buy": buy_score,
            "sell": sell_score,
            "hold": hold_score,
        }
        final_signal = max(scores, key=scores.get)
        final_confidence = scores[final_signal] * 100

        # 鐢熸垚鍐崇瓥鐞嗙敱
        reasoning = self._generate_decision_reasoning(
            final_signal, final_confidence, signals, scores
        )

        # 璁＄畻鐩爣浠峰拰姝㈡崯浠凤紙鍙栨墍鏈塨uy/sell淇″彿鐨勫钩鍧囷級
        target_prices = []
        stop_losses = []
        for signal in signals.values():
            if signal.signal_type == final_signal:
                if signal.target_price:
                    target_prices.append(signal.target_price)
                if signal.stop_loss:
                    stop_losses.append(signal.stop_loss)

        return {
            "signal_type": final_signal,
            "confidence": round(final_confidence, 2),
            "reasoning": reasoning,
            "target_price": round(sum(target_prices) / len(target_prices), 2) if target_prices else None,
            "stop_loss": round(sum(stop_losses) / len(stop_losses), 2) if stop_losses else None,
            "scores": {k: round(v * 100, 2) for k, v in scores.items()},
            "signal_details": signal_details,
        }

    def _generate_decision_reasoning(
        self,
        final_signal: str,
        confidence: float,
        signals: Dict[str, AgentSignal],
        scores: Dict[str, float],
    ) -> str:
        """鐢熸垚鍐崇瓥鐞嗙敱"""
        reasons = [f"缁煎悎鍐崇瓥: {final_signal.upper()} (缃俊搴? {confidence:.1f}%)"]
        reasons.append("")
        reasons.append("鍚勬櫤鑳戒綋鍒嗘瀽缁撴灉:")

        for agent_name, signal in signals.items():
            weight = self.agent_weights.get(agent_name, 0.33)
            reasons.append(
                f"- {agent_name} (鏉冮噸{weight*100:.0f}%): "
                f"{signal.signal_type.upper()} (缃俊搴signal.confidence}%)"
            )

        reasons.append("")
        reasons.append(f"缁煎悎璇勫垎 - 涔板叆: {scores['buy']*100:.1f}%, "
                      f"鍗栧嚭: {scores['sell']*100:.1f}%, "
                      f"瑙傛湜: {scores['hold']*100:.1f}%")

        # 娣诲姞鍏抽敭鐞嗙敱
        if final_signal == "buy":
            reasons.append("")
            reasons.append("涔板叆鐞嗙敱:")
            for agent_name, signal in signals.items():
                if signal.signal_type == "buy":
                    # 鎻愬彇绗竴琛屼綔涓烘憳瑕?                    summary = signal.reasoning.split("\n")[0]
                    reasons.append(f"  鈥?{agent_name}: {summary}")
        elif final_signal == "sell":
            reasons.append("")
            reasons.append("鍗栧嚭鐞嗙敱:")
            for agent_name, signal in signals.items():
                if signal.signal_type == "sell":
                    summary = signal.reasoning.split("\n")[0]
                    reasons.append(f"  鈥?{agent_name}: {summary}")

        return "\n".join(reasons)

    def _generate_summary(self, signals: Dict[str, AgentSignal], decision: Dict[str, Any]) -> str:
        """鐢熸垚鍒嗘瀽鎽樿"""
        symbol = decision.get("symbol", "Unknown")
        signal_type = decision.get("signal_type", "hold")
        confidence = decision.get("confidence", 0)

        buy_agents = [name for name, s in signals.items() if s.signal_type == "buy"]
        sell_agents = [name for name, s in signals.items() if s.signal_type == "sell"]
        hold_agents = [name for name, s in signals.items() if s.signal_type == "hold"]

        summary = f"銆恵symbol}銆戝垎鏋愭憳瑕乗n"
        summary += f"缁煎悎寤鸿: {signal_type.upper()} (缃俊搴? {confidence}%)\n"
        summary += f"涔板叆鏀寔: {len(buy_agents)}涓櫤鑳戒綋 ({', '.join(buy_agents) if buy_agents else '鏃?})\n"
        summary += f"鍗栧嚭鏀寔: {len(sell_agents)}涓櫤鑳戒綋 ({', '.join(sell_agents) if sell_agents else '鏃?})\n"
        summary += f"瑙傛湜鏀寔: {len(hold_agents)}涓櫤鑳戒綋 ({', '.join(hold_agents) if hold_agents else '鏃?})\n"

        return summary

    def get_agent_status(self) -> Dict[str, Any]:
        """鑾峰彇鎵€鏈夋櫤鑳戒綋鐘舵€?""
        return {
            "registered_agents": list(self.agents.keys()),
            "weights": self.agent_weights,
            "total_agents": len(self.agents),
        }
