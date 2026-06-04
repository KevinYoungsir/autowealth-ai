"""
智能体协调器 - 负责协调多个智能体的分析和决策
"""
import logging
from typing import Any, Dict, List, Optional

from autowealth.agents.base_agent import AgentSignal, BaseAgent

logger = logging.getLogger(__name__)


class AgentCoordinator:
    """
    智能体协调器

    负责管理多个分析智能体，综合它们的信号生成最终投资决策
    """

    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.logger = logging.getLogger("autowealth.coordinator")

        # 默认权重配置
        self.agent_weights = {
            "TechnicalAnalyst": 0.35,    # 技术分析权重
            "FundamentalAnalyst": 0.35,  # 基本面分析权重
            "SentimentAnalyst": 0.30,    # 情绪分析权重
        }

    def register_agent(self, agent: BaseAgent, weight: Optional[float] = None):
        """
        注册智能体

        Args:
            agent: 智能体实例
            weight: 该智能体的决策权重 (0-1)
        """
        self.agents[agent.name] = agent
        if weight is not None:
            self.agent_weights[agent.name] = weight
        self.logger.info(f"注册智能体: {agent.name} (权重: {self.agent_weights.get(agent.name, 0.33)})")

    def unregister_agent(self, agent_name: str):
        """注销智能体"""
        if agent_name in self.agents:
            del self.agents[agent_name]
            if agent_name in self.agent_weights:
                del self.agent_weights[agent_name]
            self.logger.info(f"注销智能体: {agent_name}")

    def analyze(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        协调所有智能体进行分析

        Args:
            symbol: 股票代码
            data: 包含所有相关数据的字典

        Returns:
            包含所有智能体信号和综合决策的字典
        """
        self.logger.info(f"开始分析 {symbol}，智能体数量: {len(self.agents)}")

        # 收集所有智能体的信号
        signals: Dict[str, AgentSignal] = {}
        for name, agent in self.agents.items():
            try:
                signal = agent.analyze(symbol, data)
                signals[name] = signal
                self.logger.info(f"{name} 信号: {signal.signal_type} (置信度: {signal.confidence}%)")
            except Exception as e:
                self.logger.error(f"{name} 分析失败: {e}")
                signals[name] = AgentSignal(
                    agent_name=name,
                    signal_type="hold",
                    confidence=0,
                    reasoning=f"分析出错: {str(e)}"
                )

        # 综合决策
        final_decision = self._aggregate_signals(signals)

        return {
            "symbol": symbol,
            "individual_signals": signals,
            "final_decision": final_decision,
            "analysis_summary": self._generate_summary(signals, final_decision),
        }

    def _aggregate_signals(self, signals: Dict[str, AgentSignal]) -> Dict[str, Any]:
        """
        综合多个智能体的信号生成最终决策

        使用加权投票机制，考虑信号类型和置信度
        """
        if not signals:
            return {
                "signal_type": "hold",
                "confidence": 0,
                "reasoning": "没有可用的分析信号",
            }

        # 计算加权分数
        buy_score = 0.0
        sell_score = 0.0
        hold_score = 0.0
        total_weight = 0.0

        signal_details = []

        for agent_name, signal in signals.items():
            weight = self.agent_weights.get(agent_name, 0.33)
            confidence = signal.confidence / 100.0  # 归一化到0-1

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

        # 归一化分数
        if total_weight > 0:
            buy_score /= total_weight
            sell_score /= total_weight
            hold_score /= total_weight

        # 确定最终信号
        scores = {
            "buy": buy_score,
            "sell": sell_score,
            "hold": hold_score,
        }
        final_signal = max(scores, key=scores.get)
        final_confidence = scores[final_signal] * 100

        # 生成决策理由
        reasoning = self._generate_decision_reasoning(
            final_signal, final_confidence, signals, scores
        )

        # 计算目标价和止损价（取所有buy/sell信号的平均）
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
        """生成决策理由"""
        reasons = [f"综合决策: {final_signal.upper()} (置信度: {confidence:.1f}%)"]
        reasons.append("")
        reasons.append("各智能体分析结果:")

        for agent_name, signal in signals.items():
            weight = self.agent_weights.get(agent_name, 0.33)
            reasons.append(
                f"- {agent_name} (权重{weight*100:.0f}%): "
                f"{signal.signal_type.upper()} (置信度{signal.confidence}%)"
            )

        reasons.append("")
        reasons.append(f"综合评分 - 买入: {scores['buy']*100:.1f}%, "
                      f"卖出: {scores['sell']*100:.1f}%, "
                      f"观望: {scores['hold']*100:.1f}%")

        # 添加关键理由
        if final_signal == "buy":
            reasons.append("")
            reasons.append("买入理由:")
            for agent_name, signal in signals.items():
                if signal.signal_type == "buy":
                    # 提取第一行作为摘要
                    summary = signal.reasoning.split("\n")[0]
                    reasons.append(f"  • {agent_name}: {summary}")
        elif final_signal == "sell":
            reasons.append("")
            reasons.append("卖出理由:")
            for agent_name, signal in signals.items():
                if signal.signal_type == "sell":
                    summary = signal.reasoning.split("\n")[0]
                    reasons.append(f"  • {agent_name}: {summary}")

        return "\n".join(reasons)

    def _generate_summary(self, signals: Dict[str, AgentSignal], decision: Dict[str, Any]) -> str:
        """生成分析摘要"""
        symbol = decision.get("symbol", "Unknown")
        signal_type = decision.get("signal_type", "hold")
        confidence = decision.get("confidence", 0)

        buy_agents = [name for name, s in signals.items() if s.signal_type == "buy"]
        sell_agents = [name for name, s in signals.items() if s.signal_type == "sell"]
        hold_agents = [name for name, s in signals.items() if s.signal_type == "hold"]

        summary = f"【{symbol}】分析摘要\n"
        summary += f"综合建议: {signal_type.upper()} (置信度: {confidence}%)\n"
        summary += f"买入支持: {len(buy_agents)}个智能体 ({', '.join(buy_agents) if buy_agents else '无'})\n"
        summary += f"卖出支持: {len(sell_agents)}个智能体 ({', '.join(sell_agents) if sell_agents else '无'})\n"
        summary += f"观望支持: {len(hold_agents)}个智能体 ({', '.join(hold_agents) if hold_agents else '无'})\n"

        return summary

    def get_agent_status(self) -> Dict[str, Any]:
        """获取所有智能体状态"""
        return {
            "registered_agents": list(self.agents.keys()),
            "weights": self.agent_weights,
            "total_agents": len(self.agents),
        }
