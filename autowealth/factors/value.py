"""
Value factor scoring.
"""

from __future__ import annotations

from typing import Mapping, Optional

from autowealth.factors.schema import (
    FactorScore,
    average_available,
    get_metric,
    missing_warnings,
    score_higher_better,
    score_lower_better,
)


def value_factor(
    symbol: str,
    financial_data: Mapping[str, object],
    as_of_date: str,
) -> FactorScore:
    """
    Score valuation using PE, PB, dividend yield and valuation percentile.
    """
    raw_values = {
        "pe": get_metric(financial_data, "pe", "PE", "price_earnings"),
        "pb": get_metric(financial_data, "pb", "PB", "price_book"),
        "dividend_yield": get_metric(financial_data, "dividend_yield", "dy"),
        "valuation_percentile": get_metric(
            financial_data, "valuation_percentile", "valuation_pct", "pe_percentile"
        ),
    }
    component_scores = {
        "pe": score_lower_better(_positive_or_none(raw_values["pe"]), 8, 60),
        "pb": score_lower_better(_positive_or_none(raw_values["pb"]), 0.8, 8),
        "dividend_yield": score_higher_better(raw_values["dividend_yield"], 0, 0.06),
        "valuation_percentile": score_lower_better(raw_values["valuation_percentile"], 0.1, 0.9),
    }
    warnings = missing_warnings(raw_values)
    return FactorScore(
        symbol=symbol,
        factor_name="value",
        score=average_available(component_scores),
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation="Value score compares valuation level and dividend yield for research screening only.",
        warnings=warnings,
    )


def _positive_or_none(value: Optional[float]) -> Optional[float]:
    if value is None or value <= 0:
        return None
    return value

