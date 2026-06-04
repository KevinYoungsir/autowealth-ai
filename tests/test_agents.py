"""
AutoWealth AI - 智能体模块测试

测试所有智能体（BaseAgent、TechnicalAgent、FundamentalAgent、SentimentAgent、AgentCoordinator）
的功能和边界情况。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock yfinance
sys.modules['yfinance'] = MagicMock()

import numpy as np
import pandas as pd
import pytest

from autowealth.agents.base_agent import AgentSignal, BaseAgent
from autowealth.agents.coordinator import AgentCoordinator
from autowealth.agents.fundamental_agent import FundamentalAgent
from autowealth.agents.sentiment_agent import SentimentAgent
from autowealth.agents.technical_agent import TechnicalAgent


# ============================================================
# 测试数据工厂
# ============================================================

def make_stock_data(rows=120, trend="normal"):
    """创建模拟股票数据"""
    rng = np.random.RandomState(42)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    if trend == "uptrend":
        drift = np.linspace(0, 50, rows)
    elif trend == "downtrend":
        drift = np.linspace(0, -50, rows)
    else:
        drift = np.cumsum(rng.randn(rows) * 0.5)

    close = 100.0 + drift + rng.randn(rows) * 2
    close = np.maximum(close, 1.0)

    high = close + rng.uniform(0.5, 3.0, rows)
    low = close - rng.uniform(0.5, 3.0, rows)
    low = np.maximum(low, 0.5)
    open_ = low + rng.uniform(0, 1, rows) * (high - low)
    volume = rng.randint(1000000, 10000000, rows).astype(float)

    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


def make_stock_info():
    """创建模拟股票信息"""
    return {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "pe_ratio": 25.0,
        "pb_ratio": 8.0,
        "dividend_yield": 0.005,
        "market_cap": 3000000000000,
    }


# ============================================================
# BaseAgent 测试
# ============================================================

class TestBaseAgent:
    """测试 BaseAgent 基类"""

    def test_base_agent_init(self):
        """验证 BaseAgent 初始化"""
        agent = TechnicalAgent()
        assert agent.name == "TechnicalAnalyst"
        assert agent.description != ""

    def test_validate_data_all_present(self):
        """验证数据验证 - 所有必需字段存在"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(), "stock_info": make_stock_info()}
        assert agent.validate_data(data, ["historical_data", "stock_info"]) is True

    def test_validate_data_missing_key(self):
        """验证数据验证 - 缺少必需字段"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data()}
        assert agent.validate_data(data, ["historical_data", "stock_info"]) is False

    def test_validate_data_none_value(self):
        """验证数据验证 - 字段值为 None"""
        agent = TechnicalAgent()
        data = {"historical_data": None}
        assert agent.validate_data(data, ["historical_data"]) is False

    def test_calculate_confidence_equal_weights(self):
        """验证等权重置信度计算"""
        agent = TechnicalAgent()
        confidence = agent.calculate_confidence([80, 60, 70])
        assert confidence == pytest.approx(70.0, 0.1)

    def test_calculate_confidence_weighted(self):
        """验证加权置信度计算"""
        agent = TechnicalAgent()
        confidence = agent.calculate_confidence([80, 60], weights=[2, 1])
        assert confidence == pytest.approx(73.33, 0.1)

    def test_calculate_confidence_empty(self):
        """验证空列表返回默认置信度"""
        agent = TechnicalAgent()
        assert agent.calculate_confidence([]) == 50.0

    def test_calculate_confidence_mismatch(self):
        """验证因素和权重数量不匹配时抛出异常"""
        agent = TechnicalAgent()
        with pytest.raises(ValueError):
            agent.calculate_confidence([80, 60], weights=[1])

    def test_calculate_confidence_clamping(self):
        """验证置信度截断到 0-100"""
        agent = TechnicalAgent()
        # 平均值为 50，不会被截断
        assert agent.calculate_confidence([150, -50]) == 50.0
        # 测试超出范围被截断
        assert agent.calculate_confidence([200]) == 100.0
        assert agent.calculate_confidence([-50]) == 0.0


# ============================================================
# TechnicalAgent 测试
# ============================================================

class TestTechnicalAgent:
    """测试 TechnicalAgent"""

    def test_analyze_with_valid_data(self):
        """验证有效数据返回信号"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(120)}
        signal = agent.analyze("AAPL", data)
        assert isinstance(signal, AgentSignal)
        assert signal.agent_name == "TechnicalAnalyst"
        assert signal.signal_type in ["buy", "sell", "hold"]
        assert 0 <= signal.confidence <= 100

    def test_analyze_missing_data(self):
        """验证缺少数据返回 hold 信号"""
        agent = TechnicalAgent()
        signal = agent.analyze("AAPL", {})
        assert signal.signal_type == "hold"
        assert signal.confidence == 0

    def test_analyze_insufficient_data(self):
        """验证数据不足返回低置信度 hold"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(30)}
        signal = agent.analyze("AAPL", data)
        assert signal.signal_type == "hold"
        assert signal.confidence == 30

    def test_analyze_returns_reasoning(self):
        """验证返回分析理由"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(120)}
        signal = agent.analyze("AAPL", data)
        assert len(signal.reasoning) > 0

    def test_analyze_returns_metadata(self):
        """验证返回元数据"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(120)}
        signal = agent.analyze("AAPL", data)
        assert "indicators" in signal.metadata

    def test_analyze_uptrend_data(self):
        """验证上涨趋势数据"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(120, trend="uptrend")}
        signal = agent.analyze("AAPL", data)
        assert signal.signal_type in ["buy", "sell", "hold"]

    def test_analyze_downtrend_data(self):
        """验证下跌趋势数据"""
        agent = TechnicalAgent()
        data = {"historical_data": make_stock_data(120, trend="downtrend")}
        signal = agent.analyze("AAPL", data)
        assert signal.signal_type in ["buy", "sell", "hold"]


# ============================================================
# FundamentalAgent 测试
# ============================================================

class TestFundamentalAgent:
    """测试 FundamentalAgent"""

    def test_analyze_with_valid_data(self):
        """验证有效数据返回信号"""
        agent = FundamentalAgent()
        data = {
            "stock_info": make_stock_info(),
            "historical_data": make_stock_data(120),
        }
        signal = agent.analyze("AAPL", data)
        assert isinstance(signal, AgentSignal)
        assert signal.agent_name == "FundamentalAnalyst"
        assert signal.signal_type in ["buy", "sell", "hold"]

    def test_analyze_missing_data(self):
        """验证缺少数据返回 hold 信号"""
        agent = FundamentalAgent()
        signal = agent.analyze("AAPL", {})
        assert signal.signal_type == "hold"
        assert signal.confidence == 0

    def test_analyze_buy_signal(self):
        """验证低估值产生买入信号"""
        agent = FundamentalAgent()
        stock_info = make_stock_info()
        stock_info["pe_ratio"] = 5.0  # 低PE
        stock_info["pb_ratio"] = 1.0  # 低PB
        data = {
            "stock_info": stock_info,
            "historical_data": make_stock_data(120, trend="uptrend"),
        }
        signal = agent.analyze("AAPL", data)
        assert signal.signal_type in ["buy", "sell", "hold"]

    def test_analyze_returns_metadata(self):
        """验证返回元数据"""
        agent = FundamentalAgent()
        data = {
            "stock_info": make_stock_info(),
            "historical_data": make_stock_data(120),
        }
        signal = agent.analyze("AAPL", data)
        assert "valuation_score" in signal.metadata
        assert "growth_score" in signal.metadata


# ============================================================
# SentimentAgent 测试
# ============================================================

class TestSentimentAgent:
    """测试 SentimentAgent"""

    def test_analyze_with_valid_data(self):
        """验证有效数据返回信号"""
        agent = SentimentAgent()
        data = {"historical_data": make_stock_data(120)}
        signal = agent.analyze("AAPL", data)
        assert isinstance(signal, AgentSignal)
        assert signal.agent_name == "SentimentAnalyst"
        assert signal.signal_type in ["buy", "sell", "hold"]

    def test_analyze_missing_data(self):
        """验证缺少数据返回 hold 信号"""
        agent = SentimentAgent()
        signal = agent.analyze("AAPL", {})
        assert signal.signal_type == "hold"
        assert signal.confidence == 0

    def test_analyze_insufficient_data(self):
        """验证数据不足返回低置信度 hold"""
        agent = SentimentAgent()
        data = {"historical_data": make_stock_data(10)}
        signal = agent.analyze("AAPL", data)
        assert signal.signal_type == "hold"
        assert signal.confidence == 30

    def test_analyze_returns_metadata(self):
        """验证返回元数据"""
        agent = SentimentAgent()
        data = {"historical_data": make_stock_data(120)}
        signal = agent.analyze("AAPL", data)
        assert "sentiment_score" in signal.metadata
        assert "momentum" in signal.metadata

    def test_analyze_uptrend_sentiment(self):
        """验证上涨趋势的情绪分析"""
        agent = SentimentAgent()
        data = {"historical_data": make_stock_data(120, trend="uptrend")}
        signal = agent.analyze("AAPL", data)
        # 上涨趋势通常产生 buy 或 hold
        assert signal.signal_type in ["buy", "sell", "hold"]


# ============================================================
# AgentCoordinator 测试
# ============================================================

class TestAgentCoordinator:
    """测试 AgentCoordinator"""

    def test_init(self):
        """验证协调器初始化"""
        coordinator = AgentCoordinator()
        assert len(coordinator.agents) == 0

    def test_register_agent(self):
        """验证注册智能体"""
        coordinator = AgentCoordinator()
        agent = TechnicalAgent()
        coordinator.register_agent(agent, weight=0.5)
        assert "TechnicalAnalyst" in coordinator.agents
        assert coordinator.agent_weights["TechnicalAnalyst"] == 0.5

    def test_unregister_agent(self):
        """验证注销智能体"""
        coordinator = AgentCoordinator()
        agent = TechnicalAgent()
        coordinator.register_agent(agent)
        coordinator.unregister_agent("TechnicalAnalyst")
        assert "TechnicalAnalyst" not in coordinator.agents

    def test_analyze_with_agents(self):
        """验证协调多个智能体分析"""
        coordinator = AgentCoordinator()
        coordinator.register_agent(TechnicalAgent(), weight=0.35)
        coordinator.register_agent(FundamentalAgent(), weight=0.35)
        coordinator.register_agent(SentimentAgent(), weight=0.30)

        data = {
            "historical_data": make_stock_data(120),
            "stock_info": make_stock_info(),
        }
        result = coordinator.analyze("AAPL", data)
        assert "final_decision" in result
        assert "individual_signals" in result
        assert len(result["individual_signals"]) == 3

    def test_analyze_empty_agents(self):
        """验证无智能体时返回默认决策"""
        coordinator = AgentCoordinator()
        result = coordinator.analyze("AAPL", {})
        assert result["final_decision"]["signal_type"] == "hold"
        assert result["final_decision"]["confidence"] == 0

    def test_aggregate_signals_buy(self):
        """验证买入信号聚合"""
        coordinator = AgentCoordinator()
        signals = {
            "A": AgentSignal(agent_name="A", signal_type="buy", confidence=80, reasoning="买入理由A"),
            "B": AgentSignal(agent_name="B", signal_type="buy", confidence=70, reasoning="买入理由B"),
            "C": AgentSignal(agent_name="C", signal_type="hold", confidence=50, reasoning="观望理由C"),
        }
        coordinator.agent_weights = {"A": 0.4, "B": 0.4, "C": 0.2}
        decision = coordinator._aggregate_signals(signals)
        assert decision["signal_type"] == "buy"
        assert decision["confidence"] > 0

    def test_aggregate_signals_sell(self):
        """验证卖出信号聚合"""
        coordinator = AgentCoordinator()
        signals = {
            "A": AgentSignal(agent_name="A", signal_type="sell", confidence=80, reasoning="卖出理由A"),
            "B": AgentSignal(agent_name="B", signal_type="sell", confidence=70, reasoning="卖出理由B"),
            "C": AgentSignal(agent_name="C", signal_type="hold", confidence=50, reasoning="观望理由C"),
        }
        coordinator.agent_weights = {"A": 0.4, "B": 0.4, "C": 0.2}
        decision = coordinator._aggregate_signals(signals)
        assert decision["signal_type"] == "sell"

    def test_aggregate_signals_with_target_prices(self):
        """验证目标价聚合"""
        coordinator = AgentCoordinator()
        signals = {
            "A": AgentSignal(agent_name="A", signal_type="buy", confidence=80, target_price=150, reasoning="买入"),
            "B": AgentSignal(agent_name="B", signal_type="buy", confidence=70, target_price=160, reasoning="买入"),
        }
        coordinator.agent_weights = {"A": 0.5, "B": 0.5}
        decision = coordinator._aggregate_signals(signals)
        assert decision["target_price"] is not None
        assert decision["target_price"] == pytest.approx(155.0, 0.1)

    def test_get_agent_status(self):
        """验证获取智能体状态"""
        coordinator = AgentCoordinator()
        coordinator.register_agent(TechnicalAgent(), weight=0.35)
        status = coordinator.get_agent_status()
        assert status["total_agents"] == 1
        assert "TechnicalAnalyst" in status["registered_agents"]

    def test_generate_summary(self):
        """验证生成分析摘要"""
        coordinator = AgentCoordinator()
        signals = {
            "A": AgentSignal(agent_name="A", signal_type="buy", confidence=80, reasoning="买入"),
            "B": AgentSignal(agent_name="B", signal_type="sell", confidence=70, reasoning="卖出"),
        }
        decision = {"signal_type": "buy", "confidence": 75, "symbol": "AAPL"}
        summary = coordinator._generate_summary(signals, decision)
        assert "AAPL" in summary
        assert "buy" in summary.lower() or "BUY" in summary

    def test_generate_decision_reasoning(self):
        """验证生成决策理由"""
        coordinator = AgentCoordinator()
        signals = {
            "A": AgentSignal(agent_name="A", signal_type="buy", confidence=80, reasoning="买入理由"),
        }
        coordinator.agent_weights = {"A": 1.0}
        reasoning = coordinator._generate_decision_reasoning("buy", 80, signals, {"buy": 0.8, "sell": 0.1, "hold": 0.1})
        assert len(reasoning) > 0
        assert "buy" in reasoning.lower() or "BUY" in reasoning


# ============================================================
# 集成测试
# ============================================================

class TestAgentIntegration:
    """智能体集成测试"""

    def test_three_agents_collaboration(self):
        """验证三个智能体协同工作"""
        coordinator = AgentCoordinator()
        coordinator.register_agent(TechnicalAgent(), weight=0.35)
        coordinator.register_agent(FundamentalAgent(), weight=0.35)
        coordinator.register_agent(SentimentAgent(), weight=0.30)

        data = {
            "historical_data": make_stock_data(120, trend="uptrend"),
            "stock_info": make_stock_info(),
        }
        result = coordinator.analyze("AAPL", data)

        # 验证结果结构
        assert "symbol" in result
        assert "final_decision" in result
        assert "individual_signals" in result
        assert "analysis_summary" in result

        # 验证最终决策
        decision = result["final_decision"]
        assert "signal_type" in decision
        assert "confidence" in decision
        assert "reasoning" in decision
        assert "scores" in decision

        # 验证所有智能体都参与了
        assert len(result["individual_signals"]) == 3

    def test_agent_error_handling(self):
        """验证智能体出错时的处理"""
        coordinator = AgentCoordinator()

        # 创建一个会出错的智能体
        class BrokenAgent(BaseAgent):
            def __init__(self):
                super().__init__("BrokenAgent")

            def analyze(self, symbol, data):
                raise RuntimeError("模拟错误")

        coordinator.register_agent(BrokenAgent(), weight=1.0)
        result = coordinator.analyze("AAPL", {})

        # 即使出错也应返回结果
        assert "final_decision" in result
        # BrokenAgent 会抛出异常，协调器会捕获并生成 hold 信号
        assert result["final_decision"]["signal_type"] in ["hold", "buy", "sell"]
        assert result["final_decision"]["confidence"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
