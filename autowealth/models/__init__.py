"""
数据模型模块 - 定义所有Pydantic数据模型
"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """交易信号类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"


class TimeHorizon(str, Enum):
    """投资时间周期"""
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    AGGRESSIVE = "aggressive"


class StockInfo(BaseModel):
    """股票基本信息"""
    symbol: str
    name: str = "N/A"
    sector: str = "N/A"
    industry: str = "N/A"
    market_cap: float = 0
    pe_ratio: float = 0
    pb_ratio: float = 0
    dividend_yield: float = 0
    fifty_two_week_high: float = 0
    fifty_two_week_low: float = 0
    average_volume: int = 0
    website: str = ""
    description: str = ""


class AgentSignal(BaseModel):
    """智能体信号"""
    agent_name: str
    signal_type: SignalType = SignalType.HOLD
    confidence: float = Field(default=50.0, ge=0, le=100)
    reasoning: str = ""
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FinalDecision(BaseModel):
    """最终决策"""
    signal_type: SignalType = SignalType.HOLD
    confidence: float = Field(default=0.0, ge=0, le=100)
    reasoning: str = ""
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    scores: Dict[str, float] = Field(default_factory=dict)
    signal_details: List[Dict[str, Any]] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """分析结果"""
    symbol: str
    success: bool = True
    error: Optional[str] = None
    decision: Optional[FinalDecision] = None
    individual_signals: Dict[str, AgentSignal] = Field(default_factory=dict)
    summary: str = ""
    stock_info: Dict[str, Any] = Field(default_factory=dict)
    technical_analysis: Optional[Dict[str, Any]] = None
    fundamental_analysis: Optional[Dict[str, Any]] = None


class BatchResult(BaseModel):
    """批量分析结果"""
    results: Dict[str, AnalysisResult] = Field(default_factory=dict)
    recommendations: Dict[str, List[tuple]] = Field(default_factory=dict)
    summary: Dict[str, int] = Field(default_factory=dict)


class Holding(BaseModel):
    """持仓信息"""
    symbol: str
    quantity: int = 0
    cost_basis: float = 0.0


class PortfolioHolding(BaseModel):
    """投资组合持仓分析"""
    symbol: str
    quantity: int
    current_price: float
    holding_value: float
    cost_basis: float
    gain_loss: float
    return_pct: float = 0.0
    decision: Optional[Dict[str, Any]] = None


class PortfolioResult(BaseModel):
    """投资组合分析结果"""
    holdings: List[PortfolioHolding] = Field(default_factory=list)
    total_value: float = 0.0
    total_gain_loss: float = 0.0
    return_pct: float = 0.0


class MarketIndex(BaseModel):
    """市场指数信息"""
    symbol: str
    price: float
    change_pct: float
    volume: float = 0


class MarketOverview(BaseModel):
    """市场概览"""
    success: bool = True
    error: Optional[str] = None
    indices: Dict[str, MarketIndex] = Field(default_factory=dict)
