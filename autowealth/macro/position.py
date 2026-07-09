"""
Research-level equity position multiplier.
"""

from __future__ import annotations

from typing import Mapping, Optional


BASE_MULTIPLIERS = {
    "recession": 0.6,
    "slowdown": 0.8,
    "uncertain": 0.9,
    "stagflation": 0.75,
    "recovery": 1.0,
    "expansion": 1.1,
    "strong_expansion": 1.2,
}


def equity_position_multiplier(
    regime: str,
    scores: Optional[Mapping[str, float]] = None,
) -> float:
    """
    Calculate a research-only equity position multiplier in the 0.6-1.2 range.
    """
    multiplier = BASE_MULTIPLIERS.get(regime, 0.9)
    if scores:
        external_risk = scores.get("external_risk_score")
        policy = scores.get("policy_score")
        if external_risk is not None and external_risk < 35:
            multiplier -= 0.1
        if policy is not None and policy > 75:
            multiplier += 0.05
        if _strong_environment(regime, scores):
            multiplier = max(multiplier, 1.2)
    return float(max(0.6, min(1.2, multiplier)))


def _strong_environment(regime: str, scores: Mapping[str, float]) -> bool:
    if regime != "expansion":
        return False
    keys = [
        "growth_score",
        "inflation_score",
        "liquidity_score",
        "credit_score",
        "policy_score",
        "external_risk_score",
    ]
    return all(scores.get(key, 0) >= 80 for key in keys)

