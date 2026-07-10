"""
Portfolio constraint validation and helpers.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from autowealth.portfolio.schema import PortfolioConstraints, TargetHolding


def validate_constraints(constraints: PortfolioConstraints) -> None:
    """
    Validate portfolio construction constraints.
    """
    if constraints.max_position_weight <= 0 or constraints.max_position_weight > 1:
        raise ValueError("max_position_weight must be between 0 and 1")
    if constraints.min_position_weight < 0 or constraints.min_position_weight > 1:
        raise ValueError("min_position_weight must be between 0 and 1")
    if constraints.min_position_weight > constraints.max_position_weight:
        raise ValueError("min_position_weight cannot exceed max_position_weight")
    if constraints.max_industry_weight <= 0 or constraints.max_industry_weight > 1:
        raise ValueError("max_industry_weight must be between 0 and 1")
    if constraints.max_holdings <= 0:
        raise ValueError("max_holdings must be positive")
    if constraints.min_holdings <= 0:
        raise ValueError("min_holdings must be positive")
    if constraints.min_holdings > constraints.max_holdings:
        raise ValueError("min_holdings cannot exceed max_holdings")
    if constraints.cash_weight_min < 0 or constraints.cash_weight_min > 1:
        raise ValueError("cash_weight_min must be between 0 and 1")
    if constraints.cash_weight_max < 0 or constraints.cash_weight_max > 1:
        raise ValueError("cash_weight_max must be between 0 and 1")
    if constraints.cash_weight_min > constraints.cash_weight_max:
        raise ValueError("cash_weight_min cannot exceed cash_weight_max")
    if constraints.min_score < 0 or constraints.min_score > 100:
        raise ValueError("min_score must be between 0 and 100")


def check_weight_sum(target_weights: Mapping[str, float]) -> None:
    """
    Ensure target weights do not exceed 1.
    """
    total = sum(float(weight) for weight in target_weights.values())
    if total > 1 + 1e-12:
        raise ValueError("target weight sum cannot exceed 1")


def validate_holdings_against_constraints(
    holdings: Iterable[TargetHolding],
    constraints: PortfolioConstraints,
) -> list[str]:
    """
    Return warnings for holdings that violate constraints.
    """
    warnings: list[str] = []
    industry_weights = defaultdict(float)
    total_weight = 0.0

    for holding in holdings:
        total_weight += holding.target_weight
        industry_weights[holding.industry] += holding.target_weight
        if holding.target_weight > constraints.max_position_weight + 1e-12:
            warnings.append(f"{holding.symbol} exceeds max_position_weight")
        if 0 < holding.target_weight < constraints.min_position_weight - 1e-12:
            warnings.append(f"{holding.symbol} is below min_position_weight")

    if total_weight > 1 + 1e-12:
        warnings.append("target weight sum exceeds 1")
    for industry, weight in industry_weights.items():
        if weight > constraints.max_industry_weight + 1e-12:
            warnings.append(f"{industry} exceeds max_industry_weight")
    return warnings

