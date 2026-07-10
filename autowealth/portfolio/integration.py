"""
Lightweight integration helpers for research portfolio construction.
"""

from __future__ import annotations

from typing import Mapping, Optional

from autowealth.factors.schema import CompositeFactorScore, FactorScore
from autowealth.portfolio.builder import build_factor_portfolio
from autowealth.portfolio.schema import PortfolioBuildResult, PortfolioConstraints, StockCandidate


def build_target_weights_from_factor_scores(
    factor_scores: Mapping[str, object],
    industries: Optional[Mapping[str, str]] = None,
    constraints: Optional[PortfolioConstraints] = None,
    macro_multiplier: float = 1.0,
) -> dict[str, float]:
    """
    Build a target-weights dictionary from factor score objects without network access.
    """
    result = build_portfolio_from_factor_scores(
        factor_scores=factor_scores,
        industries=industries,
        constraints=constraints,
        macro_multiplier=macro_multiplier,
    )
    return result.target_weights


def build_portfolio_from_factor_scores(
    factor_scores: Mapping[str, object],
    industries: Optional[Mapping[str, str]] = None,
    constraints: Optional[PortfolioConstraints] = None,
    macro_multiplier: float = 1.0,
) -> PortfolioBuildResult:
    """
    Convert factor score objects into candidates and build research target weights.
    """
    industries = industries or {}
    candidates = [
        _candidate_from_score(symbol, score, industries.get(symbol, "unknown"))
        for symbol, score in factor_scores.items()
    ]
    return build_factor_portfolio(
        candidates=candidates,
        constraints=constraints or PortfolioConstraints(),
        macro_multiplier=macro_multiplier,
    )


def _candidate_from_score(symbol: str, score_object: object, industry: str) -> StockCandidate:
    score = float(getattr(score_object, "score", score_object))
    factor_scores = {}
    if isinstance(score_object, CompositeFactorScore):
        factor_scores = {
            name: factor.score for name, factor in score_object.factor_scores.items()
        }
    elif isinstance(score_object, FactorScore):
        factor_scores = {score_object.factor_name: score_object.score}
    elif hasattr(score_object, "raw_values") and isinstance(getattr(score_object, "raw_values"), dict):
        factor_scores = dict(getattr(score_object, "raw_values"))
    return StockCandidate(
        symbol=symbol,
        score=score,
        factor_scores=factor_scores,
        industry=industry,
    )

