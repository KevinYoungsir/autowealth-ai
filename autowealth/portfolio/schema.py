"""
Research portfolio construction data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class StockCandidate:
    """
    Candidate stock with composite factor score for research portfolio building.
    """

    symbol: str
    score: float
    factor_scores: Dict[str, float] = field(default_factory=dict)
    industry: str = "unknown"
    explanation: str = "Research candidate derived from factor scores; not investment advice."
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.score = float(max(0.0, min(100.0, self.score)))
        if not self.industry:
            self.industry = "unknown"


@dataclass
class PortfolioConstraints:
    """
    Portfolio construction constraints for research target weights.
    """

    max_position_weight: float = 0.08
    min_position_weight: float = 0.01
    max_industry_weight: float = 0.25
    max_holdings: int = 30
    min_holdings: int = 5
    cash_weight_min: float = 0.0
    cash_weight_max: float = 0.4
    min_score: float = 0.0


@dataclass
class TargetHolding:
    """
    Target holding weight generated for research.
    """

    symbol: str
    score: float
    factor_scores: Dict[str, float]
    industry: str
    target_weight: float
    explanation: str = "Target weight is a research output, not a trading instruction."
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.target_weight = float(max(0.0, self.target_weight))


@dataclass
class PortfolioBuildResult:
    """
    Result of research portfolio construction.
    """

    holdings: List[TargetHolding]
    target_weights: Dict[str, float]
    cash_weight: float
    macro_multiplier: float
    selected_symbols: List[str]
    rejected_symbols: Dict[str, str]
    warnings: List[str]
    explanation: str
    constraints: PortfolioConstraints
    equity_weight: Optional[float] = None

    def __post_init__(self) -> None:
        self.cash_weight = float(max(0.0, min(1.0, self.cash_weight)))
        if self.equity_weight is None:
            self.equity_weight = float(sum(self.target_weights.values()))

