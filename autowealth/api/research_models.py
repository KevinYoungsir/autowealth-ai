"""
Pydantic models for the research-only FastAPI surface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


RESEARCH_API_VERSION = "0.1.0"
RESEARCH_API_EXPLANATION = (
    "Research API output is for analysis and education only; it is not a "
    "trading instruction, investment advice or return promise."
)


class ResearchHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    mock_mode: bool


class PriceBarInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    date: str
    close: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    amplitude: Optional[float] = None
    pct_change: Optional[float] = None
    change: Optional[float] = None
    turnover: Optional[float] = None


class ResearchFactorScoreInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    score: float = Field(..., ge=0.0, le=100.0)
    factor_name: str = "composite"
    factor_scores: Dict[str, float] = Field(default_factory=dict)
    raw_values: Dict[str, Optional[float]] = Field(default_factory=dict)
    as_of_date: Optional[str] = None
    explanation: str = "Precomputed research factor score supplied to the API."
    warnings: List[str] = Field(default_factory=list)


class PortfolioConstraintsInput(BaseModel):
    max_position_weight: float = 0.08
    min_position_weight: float = 0.01
    max_industry_weight: float = 0.25
    max_holdings: int = 30
    min_holdings: int = 5
    cash_weight_min: float = 0.0
    cash_weight_max: float = 0.4
    min_score: float = 0.0


class ResearchRunRequest(BaseModel):
    experiment_name: str = "api_research_experiment"
    start_date: str
    end_date: str
    candidate_symbols: List[str]
    factor_scores: Dict[str, Union[float, ResearchFactorScoreInput]]
    price_data: Dict[str, List[PriceBarInput]]
    macro_multiplier: Optional[float] = None
    constraints: PortfolioConstraintsInput = Field(default_factory=PortfolioConstraintsInput)
    industries: Dict[str, str] = Field(default_factory=dict)
    initial_capital: float = 1_000_000.0
    rebalance_frequency: str = "yearly"
    commission: float = 0.0003
    stamp_tax: float = 0.0005
    slippage: float = 0.0002


class EquityPoint(BaseModel):
    date: str
    equity: float


class ResearchPipelineResultPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    experiment_name: str
    start_date: str
    end_date: str
    candidate_symbols: List[str]
    selected_symbols: List[str]
    rejected_symbols: Dict[str, str]
    factor_summary: Dict[str, Any]
    macro_summary: Dict[str, Any]
    target_weights: Dict[str, float]
    backtest_metrics: Dict[str, Any]
    equity_curve: List[EquityPoint]
    warnings: List[str]
    explanation: str = RESEARCH_API_EXPLANATION


class ResearchSummaryPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    experiment_name: str
    start_date: str
    end_date: str
    candidate_symbols: List[str]
    selected_symbols: List[str]
    rejected_symbols: Dict[str, str]
    factor_summary: Dict[str, Any]
    macro_summary: Dict[str, Any]
    target_weights: Dict[str, float]
    backtest_metrics: Dict[str, Any]
    equity_curve: List[EquityPoint]
    warnings: List[str]
    explanation: str = RESEARCH_API_EXPLANATION


class ResearchDemoResponse(BaseModel):
    mock_mode: bool
    result: ResearchPipelineResultPayload
    summary: ResearchSummaryPayload
    explanation: str = RESEARCH_API_EXPLANATION


class DeepSeekMockReportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    research_note: Dict[str, Any]
    risk_flags: List[Dict[str, Any]]
    counter_arguments: List[Dict[str, Any]]
    validation_result: Dict[str, Any]
    metadata: Dict[str, Any]
    warnings: List[str]
