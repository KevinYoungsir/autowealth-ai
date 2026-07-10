"""
Research portfolio construction from factor scores and macro context.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, Optional

from autowealth.macro.position import equity_position_multiplier as regime_multiplier
from autowealth.portfolio.constraints import (
    check_weight_sum,
    validate_constraints,
    validate_holdings_against_constraints,
)
from autowealth.portfolio.ranking import rank_candidates
from autowealth.portfolio.schema import (
    PortfolioBuildResult,
    PortfolioConstraints,
    StockCandidate,
    TargetHolding,
)


def build_factor_portfolio(
    candidates: Iterable[StockCandidate],
    constraints: Optional[PortfolioConstraints] = None,
    macro_regime: Optional[object] = None,
    macro_multiplier: Optional[float] = None,
) -> PortfolioBuildResult:
    """
    Build research target weights from composite factor scores and macro context.
    """
    constraints = constraints or PortfolioConstraints()
    validate_constraints(constraints)

    multiplier = _resolve_macro_multiplier(macro_regime, macro_multiplier)
    equity_budget = _target_equity_weight(multiplier, constraints)
    ranking = rank_candidates(candidates, constraints)
    warnings = list(ranking.warnings)
    rejected = dict(ranking.rejected_symbols)

    allocated_weights, allocation_warnings = _allocate_weights(
        ranking.selected,
        equity_budget,
        constraints,
    )
    warnings.extend(allocation_warnings)

    holdings: list[TargetHolding] = []
    for candidate in ranking.selected:
        weight = allocated_weights.get(candidate.symbol, 0.0)
        if weight < constraints.min_position_weight:
            if weight > 0:
                warnings.append(
                    f"{candidate.symbol} weight below min_position_weight; left as cash"
                )
            rejected[candidate.symbol] = "weight below min_position_weight after constraints"
            continue
        holdings.append(
            TargetHolding(
                symbol=candidate.symbol,
                score=candidate.score,
                factor_scores=candidate.factor_scores,
                industry=candidate.industry,
                target_weight=weight,
            )
        )

    target_weights = {holding.symbol: holding.target_weight for holding in holdings}
    check_weight_sum(target_weights)
    invested_weight = sum(target_weights.values())
    cash_weight = 1.0 - invested_weight

    if cash_weight < constraints.cash_weight_min - 1e-12:
        warnings.append("cash_weight below cash_weight_min after allocation")
    if cash_weight > constraints.cash_weight_max + 1e-12:
        warnings.append("cash_weight above cash_weight_max due to portfolio constraints")

    warnings.extend(validate_holdings_against_constraints(holdings, constraints))
    selected_symbols = [holding.symbol for holding in holdings]

    return PortfolioBuildResult(
        holdings=holdings,
        target_weights=target_weights,
        cash_weight=cash_weight,
        macro_multiplier=multiplier,
        selected_symbols=selected_symbols,
        rejected_symbols=rejected,
        warnings=warnings,
        explanation=(
            "Target weights are research outputs derived from factor scores, macro context and "
            "portfolio constraints; they are not investment advice or trading instructions."
        ),
        constraints=constraints,
        equity_weight=invested_weight,
    )


def _resolve_macro_multiplier(
    macro_regime: Optional[object],
    macro_multiplier: Optional[float],
) -> float:
    if macro_multiplier is not None:
        return float(max(0.6, min(1.2, macro_multiplier)))
    if macro_regime is None:
        return 1.0
    if hasattr(macro_regime, "equity_position_multiplier"):
        return float(max(0.6, min(1.2, getattr(macro_regime, "equity_position_multiplier"))))
    if hasattr(macro_regime, "regime"):
        return regime_multiplier(str(getattr(macro_regime, "regime")))
    return regime_multiplier(str(macro_regime))


def _target_equity_weight(
    macro_multiplier: float,
    constraints: PortfolioConstraints,
) -> float:
    desired = min(1.0, max(0.0, macro_multiplier))
    lower = 1.0 - constraints.cash_weight_max
    upper = 1.0 - constraints.cash_weight_min
    return float(max(lower, min(upper, desired)))


def _allocate_weights(
    selected: list[StockCandidate],
    equity_budget: float,
    constraints: PortfolioConstraints,
) -> tuple[Dict[str, float], list[str]]:
    weights = {candidate.symbol: 0.0 for candidate in selected}
    if not selected or equity_budget <= 0:
        return weights, []

    warnings: list[str] = []
    industry_used = defaultdict(float)
    active = list(selected)
    remaining_budget = equity_budget
    capped_symbols = set()
    capped_industries = set()

    while active and remaining_budget > 1e-12:
        score_sum = sum(max(candidate.score, 1e-9) for candidate in active)
        allocated = 0.0
        next_active: list[StockCandidate] = []

        for candidate in active:
            proposed = remaining_budget * max(candidate.score, 1e-9) / score_sum
            position_room = constraints.max_position_weight - weights[candidate.symbol]
            industry_room = constraints.max_industry_weight - industry_used[candidate.industry]
            room = min(position_room, industry_room)
            allocation = max(0.0, min(proposed, room))

            if allocation > 1e-12:
                weights[candidate.symbol] += allocation
                industry_used[candidate.industry] += allocation
                allocated += allocation

            new_position_room = constraints.max_position_weight - weights[candidate.symbol]
            new_industry_room = constraints.max_industry_weight - industry_used[candidate.industry]
            if new_position_room <= 1e-12:
                capped_symbols.add(candidate.symbol)
            if new_industry_room <= 1e-12:
                capped_industries.add(candidate.industry)
            if min(new_position_room, new_industry_room) > 1e-12:
                next_active.append(candidate)

        if allocated <= 1e-12:
            warnings.append("remaining equity budget could not be allocated under constraints")
            break
        remaining_budget -= allocated
        active = next_active

    for symbol in sorted(capped_symbols):
        warnings.append(f"{symbol} reached max_position_weight")
    for industry in sorted(capped_industries):
        warnings.append(f"{industry} reached max_industry_weight")
    if remaining_budget > 1e-8:
        warnings.append("unallocated equity budget left as cash")

    return weights, warnings

