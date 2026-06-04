"""
AutoWealth AI - 数据模型测试

测试所有 Pydantic 数据模型的创建、验证和序列化。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pydantic import ValidationError

from autowealth.models import (
    AgentSignal,
    AnalysisResult,
    BatchResult,
    FinalDecision,
    Holding,
    MarketIndex,
    MarketOverview,
    PortfolioHolding,
    PortfolioResult,
    RiskLevel,
    SignalType,
    StockInfo,
    TimeHorizon,
)


# ============================================================
# SignalType / TimeHorizon / RiskLevel 枚举测试
# ============================================================

class TestEnums:
    """测试枚举类型"""

    def test_signal_type_values(self):
        """验证 SignalType 枚举值"""
        assert SignalType.BUY == "buy"
        assert SignalType.SELL == "sell"
        assert SignalType.HOLD == "hold"
        assert SignalType.WATCH == "watch"

    def test_time_horizon_values(self):
        """验证 TimeHorizon 枚举值"""
        assert TimeHorizon.SHORT == "short"
        assert TimeHorizon.MEDIUM == "medium"
        assert TimeHorizon.LONG == "long"

    def test_risk_level_values(self):
        """验证 RiskLevel 枚举值"""
        assert RiskLevel.LOW == "low"
        assert RiskLevel.MODERATE == "moderate"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.AGGRESSIVE == "aggressive"


# ============================================================
# StockInfo 测试
# ============================================================

class TestStockInfo:
    """测试 StockInfo 模型"""

    def test_stock_info_default_values(self):
        """验证默认值的 StockInfo 创建"""
        info = StockInfo(symbol="AAPL")
        assert info.symbol == "AAPL"
        assert info.name == "N/A"
        assert info.market_cap == 0
        assert info.pe_ratio == 0

    def test_stock_info_full_values(self):
        """验证完整字段的 StockInfo 创建"""
        info = StockInfo(
            symbol="AAPL",
            name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            market_cap=3000000000000.0,
            pe_ratio=25.5,
            pb_ratio=8.2,
            dividend_yield=0.005,
            fifty_two_week_high=200.0,
            fifty_two_week_low=150.0,
            average_volume=50000000,
        )
        assert info.name == "Apple Inc."
        assert info.pe_ratio == 25.5

    def test_stock_info_missing_required(self):
        """验证缺少必需字段时抛出 ValidationError"""
        with pytest.raises(ValidationError):
            StockInfo()  # symbol 是必需的


# ============================================================
# AgentSignal 测试
# ============================================================

class TestAgentSignal:
    """测试 AgentSignal 模型"""

    def test_agent_signal_default(self):
        """验证默认值的 AgentSignal 创建"""
        signal = AgentSignal(agent_name="TestAgent")
        assert signal.agent_name == "TestAgent"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 50.0
        assert signal.reasoning == ""

    def test_agent_signal_full(self):
        """验证完整字段的 AgentSignal 创建"""
        signal = AgentSignal(
            agent_name="TechnicalAnalyst",
            signal_type=SignalType.BUY,
            confidence=85.5,
            reasoning="MACD金叉形成",
            target_price=150.0,
            stop_loss=135.0,
            time_horizon=TimeHorizon.SHORT,
            metadata={"rsi": 65.0},
        )
        assert signal.confidence == 85.5
        assert signal.target_price == 150.0

    def test_agent_signal_confidence_range(self):
        """验证 confidence 超出范围时抛出 ValidationError"""
        with pytest.raises(ValidationError):
            AgentSignal(agent_name="Test", confidence=150)
        with pytest.raises(ValidationError):
            AgentSignal(agent_name="Test", confidence=-10)

    def test_agent_signal_confidence_boundary(self):
        """验证 confidence 边界值"""
        signal_min = AgentSignal(agent_name="Test", confidence=0)
        signal_max = AgentSignal(agent_name="Test", confidence=100)
        assert signal_min.confidence == 0
        assert signal_max.confidence == 100


# ============================================================
# FinalDecision 测试
# ============================================================

class TestFinalDecision:
    """测试 FinalDecision 模型"""

    def test_final_decision_default(self):
        """验证默认值的 FinalDecision 创建"""
        decision = FinalDecision()
        assert decision.signal_type == SignalType.HOLD
        assert decision.confidence == 0.0

    def test_final_decision_with_scores(self):
        """验证带评分的 FinalDecision 创建"""
        decision = FinalDecision(
            signal_type=SignalType.BUY,
            confidence=78.5,
            reasoning="综合评分优秀",
            scores={"buy": 0.7, "sell": 0.1, "hold": 0.2},
            signal_details=[
                {"agent": "Technical", "signal": "buy", "confidence": 80, "weight": 0.35}
            ],
        )
        assert decision.scores["buy"] == 0.7
        assert len(decision.signal_details) == 1


# ============================================================
# AnalysisResult 测试
# ============================================================

class TestAnalysisResult:
    """测试 AnalysisResult 模型"""

    def test_analysis_result_default(self):
        """验证默认值的 AnalysisResult 创建"""
        result = AnalysisResult(symbol="AAPL")
        assert result.symbol == "AAPL"
        assert result.success is True
        assert result.error is None

    def test_analysis_result_with_decision(self):
        """验证带决策的 AnalysisResult 创建"""
        decision = FinalDecision(signal_type=SignalType.BUY, confidence=80)
        result = AnalysisResult(
            symbol="AAPL",
            success=True,
            decision=decision,
            individual_signals={
                "Technical": AgentSignal(agent_name="Technical", signal_type=SignalType.BUY, confidence=85)
            },
        )
        assert result.decision.confidence == 80
        assert "Technical" in result.individual_signals


# ============================================================
# BatchResult 测试
# ============================================================

class TestBatchResult:
    """测试 BatchResult 模型"""

    def test_batch_result_default(self):
        """验证默认值的 BatchResult 创建"""
        result = BatchResult()
        assert result.results == {}
        assert result.recommendations == {}
        assert result.summary == {}

    def test_batch_result_with_data(self):
        """验证带数据的 BatchResult 创建"""
        result = BatchResult(
            results={"AAPL": AnalysisResult(symbol="AAPL")},
            recommendations={"buy": [("AAPL", 85.0)]},
            summary={"total": 1, "success": 1, "buy_count": 1, "sell_count": 0, "hold_count": 0},
        )
        assert result.summary["total"] == 1


# ============================================================
# Holding / PortfolioHolding / PortfolioResult 测试
# ============================================================

class TestPortfolioModels:
    """测试投资组合相关模型"""

    def test_holding_default(self):
        """验证默认值的 Holding 创建"""
        holding = Holding(symbol="AAPL")
        assert holding.quantity == 0
        assert holding.cost_basis == 0.0

    def test_holding_full(self):
        """验证完整字段的 Holding 创建"""
        holding = Holding(symbol="AAPL", quantity=100, cost_basis=150.0)
        assert holding.quantity == 100
        assert holding.cost_basis == 150.0

    def test_portfolio_holding(self):
        """验证 PortfolioHolding 创建"""
        ph = PortfolioHolding(
            symbol="AAPL",
            quantity=100,
            current_price=160.0,
            holding_value=16000.0,
            cost_basis=150.0,
            gain_loss=1000.0,
            return_pct=6.67,
        )
        assert ph.gain_loss == 1000.0

    def test_portfolio_result(self):
        """验证 PortfolioResult 创建"""
        pr = PortfolioResult(
            holdings=[
                PortfolioHolding(symbol="AAPL", quantity=100, current_price=160.0, holding_value=16000.0, cost_basis=150.0, gain_loss=1000.0),
            ],
            total_value=16000.0,
            total_gain_loss=1000.0,
            return_pct=6.67,
        )
        assert pr.total_value == 16000.0


# ============================================================
# MarketIndex / MarketOverview 测试
# ============================================================

class TestMarketModels:
    """测试市场相关模型"""

    def test_market_index(self):
        """验证 MarketIndex 创建"""
        idx = MarketIndex(symbol="SPY", price=450.0, change_pct=1.25, volume=50000000)
        assert idx.symbol == "SPY"
        assert idx.change_pct == 1.25

    def test_market_overview_default(self):
        """验证默认值的 MarketOverview 创建"""
        overview = MarketOverview()
        assert overview.success is True
        assert overview.indices == {}

    def test_market_overview_with_data(self):
        """验证带数据的 MarketOverview 创建"""
        overview = MarketOverview(
            success=True,
            indices={
                "SPY": MarketIndex(symbol="SPY", price=450.0, change_pct=1.25),
                "QQQ": MarketIndex(symbol="QQQ", price=380.0, change_pct=-0.5),
            },
        )
        assert len(overview.indices) == 2
        assert overview.indices["SPY"].price == 450.0


# ============================================================
# 模型序列化测试
# ============================================================

class TestModelSerialization:
    """测试模型序列化和反序列化"""

    def test_stock_info_dict_roundtrip(self):
        """验证 StockInfo 字典往返序列化"""
        original = StockInfo(symbol="AAPL", name="Apple", pe_ratio=25.0)
        data = original.model_dump()
        restored = StockInfo(**data)
        assert restored.symbol == "AAPL"
        assert restored.pe_ratio == 25.0

    def test_agent_signal_json_roundtrip(self):
        """验证 AgentSignal JSON 序列化"""
        original = AgentSignal(
            agent_name="Test",
            signal_type=SignalType.BUY,
            confidence=75.0,
            target_price=100.0,
        )
        json_str = original.model_dump_json()
        assert "Test" in json_str
        assert "buy" in json_str

    def test_nested_model_serialization(self):
        """验证嵌套模型序列化"""
        result = AnalysisResult(
            symbol="AAPL",
            decision=FinalDecision(signal_type=SignalType.BUY, confidence=80),
        )
        data = result.model_dump()
        assert data["symbol"] == "AAPL"
        assert data["decision"]["confidence"] == 80


# ============================================================
# 边界情况测试
# ============================================================

class TestModelEdgeCases:
    """测试模型边界情况"""

    def test_empty_string_symbol(self):
        """验证空字符串 symbol"""
        info = StockInfo(symbol="")
        assert info.symbol == ""

    def test_very_large_numbers(self):
        """验证极大数值"""
        info = StockInfo(symbol="AAPL", market_cap=1e15)
        assert info.market_cap == 1e15

    def test_negative_values(self):
        """验证负数值（模型允许但业务逻辑可能不允许）"""
        info = StockInfo(symbol="AAPL", pe_ratio=-5.0)
        assert info.pe_ratio == -5.0

    def test_none_optional_fields(self):
        """验证可选字段为 None"""
        signal = AgentSignal(agent_name="Test", target_price=None, stop_loss=None)
        assert signal.target_price is None
        assert signal.stop_loss is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
