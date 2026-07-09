"""
Macro regime classification.
"""

from __future__ import annotations

from typing import Mapping

from autowealth.macro.schema import MacroRegime
from autowealth.macro.scoring import macro_dimension_scores


def classify_macro_regime(
    indicators: Mapping[str, object],
    as_of_date: str,
) -> MacroRegime:
    """
    Classify macro regime from structured indicators.

    The result is a research state judgment only and is not investment advice.
    """
    scores, warnings = macro_dimension_scores(indicators)
    growth = scores["growth_score"]
    inflation = scores["inflation_score"]
    liquidity = scores["liquidity_score"]
    credit = scores["credit_score"]

    if len(warnings) >= 5:
        regime = "uncertain"
    elif growth < 35 and credit < 45:
        regime = "recession"
    elif growth < 45 and inflation < 40:
        regime = "stagflation"
    elif growth < 50 and (liquidity < 50 or credit < 50):
        regime = "slowdown"
    elif 45 <= growth < 60 and (liquidity >= 55 or credit >= 55):
        regime = "recovery"
    elif growth >= 60 and inflation >= 45 and liquidity >= 45:
        regime = "expansion"
    else:
        regime = "uncertain"

    explanation = (
        f"Macro regime classified as {regime} from growth, inflation, liquidity and credit "
        "scores for research explanation only."
    )
    return MacroRegime(
        as_of_date=as_of_date,
        regime=regime,
        growth_score=growth,
        inflation_score=scores["inflation_score"],
        liquidity_score=liquidity,
        credit_score=credit,
        policy_score=scores["policy_score"],
        external_risk_score=scores["external_risk_score"],
        explanation=explanation,
        warnings=warnings,
        indicators={key: _safe_float(value) for key, value in indicators.items()},
    )


def _safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

