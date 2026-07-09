"""
Research pipeline reporting helpers.
"""

from __future__ import annotations

from typing import Dict

from autowealth.research.schema import RESEARCH_ONLY_EXPLANATION, ResearchPipelineResult, ResearchSummary


def summarize_research_result(result: ResearchPipelineResult) -> ResearchSummary:
    """
    Build a compact structured research summary.
    """
    metrics = dict(result.backtest_metrics)
    summary_metrics = {
        "holding_count": len(result.selected_symbols),
        "cash_weight": 1.0 - sum(result.target_weights.values()),
        "annualized_return": metrics.get("annualized_return"),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "calmar_ratio": metrics.get("calmar_ratio"),
    }
    summary_metrics.update(metrics)

    factor_distribution = _factor_distribution(result.factor_summary)
    macro_summary = dict(result.macro_summary)
    macro_summary.setdefault("regime", "not_provided")

    return ResearchSummary(
        experiment_name=result.experiment_name,
        start_date=result.start_date,
        end_date=result.end_date,
        candidate_symbols=result.candidate_symbols,
        selected_symbols=result.selected_symbols,
        rejected_symbols=result.rejected_symbols,
        factor_summary=factor_distribution,
        macro_summary=macro_summary,
        target_weights=result.target_weights,
        backtest_metrics=summary_metrics,
        equity_curve=result.equity_curve,
        warnings=result.warnings[:10],
        explanation=RESEARCH_ONLY_EXPLANATION,
    )


def _factor_distribution(factor_summary: Dict[str, object]) -> Dict[str, object]:
    scores_by_symbol = factor_summary.get("scores_by_symbol", {}) or {}
    scores = list(scores_by_symbol.values())
    distribution = dict(factor_summary)
    if scores:
        distribution["score_buckets"] = {
            "gte_80": sum(1 for score in scores if score >= 80),
            "60_to_80": sum(1 for score in scores if 60 <= score < 80),
            "lt_60": sum(1 for score in scores if score < 60),
        }
    else:
        distribution["score_buckets"] = {"gte_80": 0, "60_to_80": 0, "lt_60": 0}
    return distribution

