"""
Composite factor score calculation.
"""

from __future__ import annotations

from typing import Mapping

from autowealth.factors.schema import CompositeFactorScore, FactorScore, clip_score


def combine_factor_scores(
    symbol: str,
    factor_scores: Mapping[str, FactorScore],
    weights: Mapping[str, float],
    as_of_date: str,
    normalize_weights: bool = True,
) -> CompositeFactorScore:
    """
    Combine single-factor scores into a weighted composite score.
    """
    if not factor_scores:
        raise ValueError("factor_scores cannot be empty")
    if not weights:
        raise ValueError("weights cannot be empty")

    missing = set(weights) - set(factor_scores)
    if missing:
        raise ValueError(f"missing factor scores for weights: {sorted(missing)}")

    normalized_weights = {name: float(weight) for name, weight in weights.items()}
    if any(weight < 0 for weight in normalized_weights.values()):
        raise ValueError("factor weights cannot be negative")

    weight_sum = sum(normalized_weights.values())
    if weight_sum <= 0:
        raise ValueError("factor weight sum must be positive")
    if abs(weight_sum - 1.0) > 1e-12:
        if not normalize_weights:
            raise ValueError("factor weight sum must equal 1")
        normalized_weights = {
            name: weight / weight_sum for name, weight in normalized_weights.items()
        }

    raw_values = {name: clip_score(factor_scores[name].score) for name in normalized_weights}
    composite = sum(raw_values[name] * normalized_weights[name] for name in normalized_weights)
    warnings = []
    for name in normalized_weights:
        warnings.extend(f"{name}: {warning}" for warning in factor_scores[name].warnings)

    return CompositeFactorScore(
        symbol=symbol,
        score=composite,
        factor_scores={name: factor_scores[name] for name in normalized_weights},
        weights=normalized_weights,
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation="Composite factor score is a weighted research score and does not constitute investment advice.",
        warnings=warnings,
    )

