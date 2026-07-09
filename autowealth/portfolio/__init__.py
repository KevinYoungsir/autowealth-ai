"""
A 股研究用组合构建模块。
"""

from autowealth.portfolio.builder import build_factor_portfolio
from autowealth.portfolio.constraints import (
    check_weight_sum,
    validate_constraints,
    validate_holdings_against_constraints,
)
from autowealth.portfolio.integration import (
    build_portfolio_from_factor_scores,
    build_target_weights_from_factor_scores,
)
from autowealth.portfolio.ranking import RankingResult, rank_candidates
from autowealth.portfolio.schema import (
    PortfolioBuildResult,
    PortfolioConstraints,
    StockCandidate,
    TargetHolding,
)

__all__ = [
    "PortfolioBuildResult",
    "PortfolioConstraints",
    "RankingResult",
    "StockCandidate",
    "TargetHolding",
    "build_factor_portfolio",
    "build_portfolio_from_factor_scores",
    "build_target_weights_from_factor_scores",
    "check_weight_sum",
    "rank_candidates",
    "validate_constraints",
    "validate_holdings_against_constraints",
]

