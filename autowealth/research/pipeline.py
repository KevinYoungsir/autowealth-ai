"""
Offline research pipeline orchestration.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional

import pandas as pd

from autowealth.backtest import PortfolioBacktester
from autowealth.factors.schema import CompositeFactorScore, FactorScore
from autowealth.macro.position import equity_position_multiplier
from autowealth.portfolio import PortfolioConstraints, StockCandidate, build_factor_portfolio
from autowealth.research.schema import (
    RESEARCH_ONLY_EXPLANATION,
    ResearchPipelineResult,
    scalar_metrics,
)


def run_research_pipeline(
    candidate_symbols: Iterable[str],
    factor_scores: Mapping[str, object],
    price_data: Mapping[str, pd.DataFrame],
    start_date: str,
    end_date: str,
    macro_regime: Optional[object] = None,
    macro_multiplier: Optional[float] = None,
    portfolio_constraints: Optional[PortfolioConstraints] = None,
    industries: Optional[Mapping[str, str]] = None,
    experiment_name: str = "offline_research_experiment",
    initial_capital: float = 1_000_000.0,
    rebalance_frequency: str = "yearly",
    commission: float = 0.0003,
    stamp_tax: float = 0.0005,
    slippage: float = 0.0002,
) -> ResearchPipelineResult:
    """
    Run one offline research experiment from precomputed inputs.

    This function does not fetch live data, optimize parameters or search for
    maximum-return portfolios.
    """
    candidate_symbols = [str(symbol) for symbol in candidate_symbols]
    industries = industries or {}
    constraints = portfolio_constraints or PortfolioConstraints()

    candidates, missing_score_rejections, candidate_warnings = _build_candidates(
        candidate_symbols,
        factor_scores,
        industries,
    )
    multiplier = _resolve_macro_multiplier(macro_regime, macro_multiplier)
    portfolio_result = build_factor_portfolio(
        candidates=candidates,
        constraints=constraints,
        macro_regime=macro_regime,
        macro_multiplier=macro_multiplier,
    )
    rejected_symbols = dict(missing_score_rejections)
    rejected_symbols.update(portfolio_result.rejected_symbols)

    backtester = PortfolioBacktester(
        initial_capital=initial_capital,
        start_date=start_date,
        end_date=end_date,
        rebalance_frequency=rebalance_frequency,
        commission=commission,
        stamp_tax=stamp_tax,
        slippage=slippage,
        cash_weight=portfolio_result.cash_weight,
        max_position_weight=constraints.max_position_weight,
    )
    backtest_result = backtester.run(portfolio_result.target_weights, price_data=price_data)

    warnings = []
    warnings.extend(candidate_warnings)
    warnings.extend(portfolio_result.warnings)
    warnings.extend(_missing_price_warnings(portfolio_result.selected_symbols, price_data))

    return ResearchPipelineResult(
        experiment_name=experiment_name,
        start_date=start_date,
        end_date=end_date,
        candidate_symbols=candidate_symbols,
        selected_symbols=portfolio_result.selected_symbols,
        rejected_symbols=rejected_symbols,
        factor_summary=_factor_summary(candidates, factor_scores),
        macro_summary=_macro_summary(macro_regime, multiplier),
        target_weights=portfolio_result.target_weights,
        backtest_metrics=scalar_metrics(backtest_result),
        equity_curve=backtest_result["equity_curve"],
        warnings=warnings,
        explanation=RESEARCH_ONLY_EXPLANATION,
    )


def _build_candidates(
    candidate_symbols: Iterable[str],
    factor_scores: Mapping[str, object],
    industries: Mapping[str, str],
) -> tuple[list[StockCandidate], Dict[str, str], list[str]]:
    candidates = []
    rejected: Dict[str, str] = {}
    warnings: list[str] = []
    for symbol in candidate_symbols:
        if symbol not in factor_scores:
            rejected[symbol] = "missing precomputed factor score"
            warnings.append(f"{symbol} missing precomputed factor score")
            continue
        score_object = factor_scores[symbol]
        candidates.append(_candidate_from_score(symbol, score_object, industries.get(symbol, "unknown")))
    return candidates, rejected, warnings


def _candidate_from_score(symbol: str, score_object: object, industry: str) -> StockCandidate:
    score = float(getattr(score_object, "score", score_object))
    factor_score_values = _factor_score_values(score_object)
    warnings = list(getattr(score_object, "warnings", []))
    return StockCandidate(
        symbol=symbol,
        score=score,
        factor_scores=factor_score_values,
        industry=industry,
        warnings=warnings,
    )


def _factor_score_values(score_object: object) -> Dict[str, float]:
    if isinstance(score_object, CompositeFactorScore):
        return {name: score.score for name, score in score_object.factor_scores.items()}
    if isinstance(score_object, FactorScore):
        return {score_object.factor_name: score_object.score}
    if hasattr(score_object, "factor_scores"):
        values = getattr(score_object, "factor_scores")
        if isinstance(values, dict):
            return {str(key): float(value) for key, value in values.items()}
    return {}


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
        return equity_position_multiplier(str(getattr(macro_regime, "regime")))
    return equity_position_multiplier(str(macro_regime))


def _factor_summary(candidates: list[StockCandidate], factor_scores: Mapping[str, object]) -> Dict[str, Any]:
    scores = [candidate.score for candidate in candidates]
    by_symbol = {candidate.symbol: candidate.score for candidate in candidates}
    return {
        "candidate_count": len(factor_scores),
        "scored_candidate_count": len(candidates),
        "mean_score": sum(scores) / len(scores) if scores else None,
        "min_score": min(scores) if scores else None,
        "max_score": max(scores) if scores else None,
        "scores_by_symbol": by_symbol,
    }


def _macro_summary(macro_regime: Optional[object], multiplier: float) -> Dict[str, Any]:
    summary = {"equity_position_multiplier": multiplier}
    if macro_regime is None:
        summary["regime"] = "not_provided"
        return summary
    for field in [
        "regime",
        "growth_score",
        "inflation_score",
        "liquidity_score",
        "credit_score",
        "policy_score",
        "external_risk_score",
    ]:
        if hasattr(macro_regime, field):
            summary[field] = getattr(macro_regime, field)
    return summary


def _missing_price_warnings(selected_symbols: Iterable[str], price_data: Mapping[str, pd.DataFrame]) -> list[str]:
    return [f"{symbol} missing price_data" for symbol in selected_symbols if symbol not in price_data]

