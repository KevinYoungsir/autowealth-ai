"""
Macro regime data structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


SUPPORTED_REGIMES = {
    "expansion",
    "slowdown",
    "recession",
    "recovery",
    "stagflation",
    "uncertain",
}


@dataclass
class MacroIndicator:
    """
    Single macro indicator observation.
    """

    name: str
    value: Optional[float]
    as_of_date: str
    source: str = "local_csv"
    warning: Optional[str] = None


@dataclass
class MacroRegime:
    """
    Macro cycle classification for research explanation.
    """

    as_of_date: str
    regime: str
    growth_score: float
    inflation_score: float
    liquidity_score: float
    credit_score: float
    policy_score: float
    external_risk_score: float
    explanation: str
    warnings: List[str] = field(default_factory=list)
    indicators: Dict[str, Optional[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.regime not in SUPPORTED_REGIMES:
            raise ValueError(f"unsupported macro regime: {self.regime}")
        self.growth_score = clip_score(self.growth_score)
        self.inflation_score = clip_score(self.inflation_score)
        self.liquidity_score = clip_score(self.liquidity_score)
        self.credit_score = clip_score(self.credit_score)
        self.policy_score = clip_score(self.policy_score)
        self.external_risk_score = clip_score(self.external_risk_score)


@dataclass
class MacroRiskScore:
    """
    Combined macro score used for research-level risk explanation.
    """

    as_of_date: str
    growth_score: float
    inflation_score: float
    liquidity_score: float
    credit_score: float
    policy_score: float
    external_risk_score: float
    regime: str
    equity_position_multiplier: float
    explanation: str
    warnings: List[str] = field(default_factory=list)
    indicators: Dict[str, Optional[float]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.growth_score = clip_score(self.growth_score)
        self.inflation_score = clip_score(self.inflation_score)
        self.liquidity_score = clip_score(self.liquidity_score)
        self.credit_score = clip_score(self.credit_score)
        self.policy_score = clip_score(self.policy_score)
        self.external_risk_score = clip_score(self.external_risk_score)
        self.equity_position_multiplier = float(
            max(0.6, min(1.2, self.equity_position_multiplier))
        )


def clip_score(value: Optional[float]) -> float:
    """
    Clip macro score into the 0-100 range.
    """
    if value is None:
        return 50.0
    return float(max(0.0, min(100.0, value)))

