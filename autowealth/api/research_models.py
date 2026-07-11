"""
Pydantic models for the research-only FastAPI surface.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

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
    research_runs_available: bool
    latest_run_available: bool


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


class FactorCoverageRecord(BaseModel):
    available_count: int = 0
    missing_count: int = 0
    coverage_ratio: float = 0.0


class ResearchRunSummary(BaseModel):
    run_id: str
    run_time: str
    experiment_name: str
    run_status: Literal["success", "partial_success", "failed"]
    start_date: str
    end_date: str
    annualized_return: Optional[float] = None
    total_return: Optional[float] = None
    max_drawdown: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    benchmark_status: str
    warning_count: int
    price_coverage_ratio: Optional[float] = None
    factor_coverage_overall: Dict[str, FactorCoverageRecord] = Field(
        default_factory=dict
    )


class ResearchRunListResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    count: int
    runs: List[ResearchRunSummary]


class WarningSummary(BaseModel):
    total: int
    categories: Dict[str, int]
    samples: Dict[str, List[str]]
    raw_warnings: List[str] = Field(default_factory=list)
    raw_returned: int = 0
    raw_truncated: bool = False


class ResearchRunDetailResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    summary: ResearchRunSummary
    manifest: Dict[str, Any]
    metrics: Dict[str, Any]
    benchmark_metrics: Dict[str, Any]
    warning_summary: WarningSummary


class EquityCurvePoint(BaseModel):
    date: str
    equity: float


class ResearchEquityCurveResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    total_points: int
    returned_points: int
    downsample: int
    points: List[EquityCurvePoint]


class ResearchBenchmarkCurveResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    status: str
    reasons: Dict[str, str] = Field(default_factory=dict)
    total_points: int = 0
    returned_points: int = 0
    downsample: int
    points: List[Dict[str, Any]] = Field(default_factory=list)


class HoldingRecord(BaseModel):
    rebalance_date: str
    symbol: str
    weight: float
    shares: Optional[float] = None
    cash_weight: Optional[float] = None
    cash: Optional[float] = None
    equity: Optional[float] = None


class ResearchHoldingsResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    records: List[HoldingRecord]
    returned: int
    min_holdings: Optional[int] = None
    holdings_count_by_rebalance: Dict[str, int] = Field(default_factory=dict)


class TradeRecord(BaseModel):
    date: str
    symbol: str
    side: str
    shares: float
    price: float
    trade_value: float
    cost: float


class ResearchTradesResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    records: List[TradeRecord]
    returned: int


class ResearchFactorsResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    records: List[Dict[str, Any]]
    returned: int
    coverage_by_rebalance: Dict[str, Any] = Field(default_factory=dict)
    coverage_overall: Dict[str, FactorCoverageRecord] = Field(default_factory=dict)


class ResearchWarningsResponse(BaseModel):
    data_source: Literal["real_artifacts"] = "real_artifacts"
    run_id: str
    summary: WarningSummary


class ResearchAPIErrorResponse(BaseModel):
    code: str
    message: str
