"""
Research pipeline data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from autowealth.portfolio.schema import PortfolioConstraints


RESEARCH_ONLY_EXPLANATION = (
    "This is a research experiment result for analysis and education only; "
    "it is not a trading instruction or a return promise."
)


@dataclass
class ResearchExperimentConfig:
    """
    Configuration for one offline research experiment.
    """

    experiment_name: str
    start_date: str
    end_date: str
    candidate_symbols: List[str]
    constraints: Optional[PortfolioConstraints] = None
    initial_capital: float = 1_000_000.0
    rebalance_frequency: str = "yearly"
    commission: float = 0.0003
    stamp_tax: float = 0.0005
    slippage: float = 0.0002
    explanation: str = RESEARCH_ONLY_EXPLANATION
    warnings: List[str] = field(default_factory=list)


@dataclass
class ResearchPipelineResult:
    """
    Full output of one research pipeline run.
    """

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
    equity_curve: pd.Series
    warnings: List[str]
    explanation: str = RESEARCH_ONLY_EXPLANATION


@dataclass
class ResearchSummary:
    """
    Compact structured research summary.
    """

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
    equity_curve: Optional[pd.Series]
    warnings: List[str]
    explanation: str = RESEARCH_ONLY_EXPLANATION


def scalar_metrics(backtest_result: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Extract scalar backtest metrics for summaries.
    """
    metric_names = [
        "annualized_return",
        "total_return",
        "max_drawdown",
        "volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "turnover",
    ]
    return {name: _to_builtin_scalar(backtest_result.get(name)) for name in metric_names}


def _to_builtin_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            return value
    return value
