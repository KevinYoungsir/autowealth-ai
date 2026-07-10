"""
Factor score data structures and shared scoring helpers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional


@dataclass
class FactorScore:
    """
    Standard score object for a single factor.

    ``score`` is always clipped to the 0-100 range. ``explanation`` describes
    the research signal only and must not contain investment advice.
    """

    symbol: str
    factor_name: str
    score: float
    raw_values: Dict[str, Optional[float]]
    as_of_date: str
    explanation: str
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.score = clip_score(self.score)


@dataclass
class CompositeFactorScore:
    """
    Weighted composite score across multiple factors.
    """

    symbol: str
    score: float
    factor_scores: Dict[str, FactorScore]
    weights: Dict[str, float]
    raw_values: Dict[str, float]
    as_of_date: str
    explanation: str
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.score = clip_score(self.score)


def clip_score(value: float) -> float:
    """
    Clip a numeric score into the 0-100 range.
    """
    if value is None:
        return 0.0
    return float(max(0.0, min(100.0, value)))


def score_higher_better(value: Optional[float], low: float, high: float) -> Optional[float]:
    """
    Score a metric where higher values are better.
    """
    if value is None:
        return None
    if high == low:
        return 50.0
    return clip_score((value - low) / (high - low) * 100)


def score_lower_better(value: Optional[float], low: float, high: float) -> Optional[float]:
    """
    Score a metric where lower values are better.
    """
    if value is None:
        return None
    if high == low:
        return 50.0
    return clip_score((high - value) / (high - low) * 100)


def score_center_better(value: Optional[float], center: float, tolerance: float) -> Optional[float]:
    """
    Score a metric where values closer to a center are better.
    """
    if value is None:
        return None
    if tolerance <= 0:
        return 50.0
    distance = abs(value - center)
    return clip_score(100 - distance / tolerance * 100)


def average_available(scores: Mapping[str, Optional[float]]) -> float:
    """
    Average non-missing score components.
    """
    available = [score for score in scores.values() if score is not None]
    if not available:
        return 50.0
    return clip_score(sum(available) / len(available))


def get_metric(data: Mapping[str, object], *names: str) -> Optional[float]:
    """
    Fetch the first available numeric metric from a mapping.
    """
    for name in names:
        if name not in data:
            continue
        value = data[name]
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def missing_warnings(raw_values: Mapping[str, Optional[float]]) -> List[str]:
    """
    Build warnings for missing factor inputs.
    """
    return [f"missing {name}; score degraded" for name, value in raw_values.items() if value is None]

