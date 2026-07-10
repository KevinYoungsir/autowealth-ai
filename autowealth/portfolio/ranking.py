"""
Candidate ranking for research portfolio construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from autowealth.portfolio.schema import PortfolioConstraints, StockCandidate


@dataclass
class RankingResult:
    selected: List[StockCandidate]
    rejected_symbols: Dict[str, str]
    warnings: List[str]


def rank_candidates(
    candidates: Iterable[StockCandidate],
    constraints: PortfolioConstraints,
    score_threshold: Optional[float] = None,
) -> RankingResult:
    """
    Sort candidates by composite score and apply score and count filters.
    """
    threshold = constraints.min_score if score_threshold is None else float(score_threshold)
    rejected: Dict[str, str] = {}
    warnings: List[str] = []
    deduped: Dict[str, StockCandidate] = {}

    for candidate in candidates:
        if candidate.symbol in deduped:
            existing = deduped[candidate.symbol]
            if candidate.score > existing.score:
                rejected[candidate.symbol] = "duplicate symbol replaced by higher score candidate"
                deduped[candidate.symbol] = candidate
            else:
                rejected[candidate.symbol] = "duplicate symbol with lower score"
            continue
        deduped[candidate.symbol] = candidate

    ranked = sorted(deduped.values(), key=lambda item: item.score, reverse=True)
    eligible: List[StockCandidate] = []
    for candidate in ranked:
        if candidate.score < threshold:
            rejected[candidate.symbol] = f"score below threshold {threshold:.2f}"
        else:
            eligible.append(candidate)

    selected = eligible[: constraints.max_holdings]
    for candidate in eligible[constraints.max_holdings :]:
        rejected[candidate.symbol] = f"outside top {constraints.max_holdings} by composite_score"

    if len(selected) < constraints.min_holdings:
        warnings.append(
            f"selected holdings below min_holdings ({len(selected)} < {constraints.min_holdings})"
        )

    return RankingResult(selected=selected, rejected_symbols=rejected, warnings=warnings)

