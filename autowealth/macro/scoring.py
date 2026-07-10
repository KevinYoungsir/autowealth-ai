"""
Macro dimension scoring.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

from autowealth.macro.schema import MacroRiskScore, clip_score
from autowealth.macro.position import equity_position_multiplier


def score_macro_environment(indicators: Mapping[str, object], as_of_date: str) -> MacroRiskScore:
    """
    Score macro dimensions and classify regime from structured indicators.
    """
    from autowealth.macro.regime import classify_macro_regime

    scores, warnings = macro_dimension_scores(indicators)
    regime = classify_macro_regime(indicators, as_of_date=as_of_date)
    multiplier = equity_position_multiplier(regime.regime, scores)
    combined_warnings = warnings + regime.warnings

    return MacroRiskScore(
        as_of_date=as_of_date,
        growth_score=scores["growth_score"],
        inflation_score=scores["inflation_score"],
        liquidity_score=scores["liquidity_score"],
        credit_score=scores["credit_score"],
        policy_score=scores["policy_score"],
        external_risk_score=scores["external_risk_score"],
        regime=regime.regime,
        equity_position_multiplier=multiplier,
        explanation=(
            "Macro score summarizes growth, inflation, liquidity, credit, policy and external "
            "risk conditions for research explanation only."
        ),
        warnings=combined_warnings,
        indicators={key: _get_metric(indicators, key) for key in indicators},
    )


def macro_dimension_scores(indicators: Mapping[str, object]) -> Tuple[Dict[str, float], List[str]]:
    """
    Calculate 0-100 scores for macro dimensions.
    """
    warnings: List[str] = []
    pmi = _metric_or_warning(indicators, "pmi", warnings)
    cpi_yoy = _metric_or_warning(indicators, "cpi_yoy", warnings)
    ppi_yoy = _metric_or_warning(indicators, "ppi_yoy", warnings)
    m2_yoy = _metric_or_warning(indicators, "m2_yoy", warnings)
    social_financing_yoy = _metric_or_warning(indicators, "social_financing_yoy", warnings)
    ten_year_yield = _metric_or_warning(indicators, "ten_year_yield", warnings)
    policy = _metric_or_warning(indicators, "policy_score", warnings)
    external_risk = _metric_or_warning(indicators, "external_risk_score", warnings)

    growth = _score_pmi(pmi)
    inflation = _score_inflation(cpi_yoy, ppi_yoy)
    liquidity = _score_liquidity(m2_yoy, ten_year_yield)
    credit = _score_credit(social_financing_yoy)

    return (
        {
            "growth_score": growth,
            "inflation_score": inflation,
            "liquidity_score": liquidity,
            "credit_score": credit,
            "policy_score": clip_score(policy),
            "external_risk_score": clip_score(external_risk),
        },
        warnings,
    )


def _score_pmi(pmi: Optional[float]) -> float:
    if pmi is None:
        return 50.0
    return clip_score((pmi - 45.0) / 10.0 * 100.0)


def _score_inflation(cpi_yoy: Optional[float], ppi_yoy: Optional[float]) -> float:
    components = []
    if cpi_yoy is not None:
        components.append(_center_score(cpi_yoy, center=2.2, tolerance=4.5))
    if ppi_yoy is not None:
        components.append(_center_score(ppi_yoy, center=1.5, tolerance=7.0))
    if not components:
        return 50.0
    return clip_score(sum(components) / len(components))


def _score_liquidity(m2_yoy: Optional[float], ten_year_yield: Optional[float]) -> float:
    components = []
    if m2_yoy is not None:
        components.append(clip_score((m2_yoy - 5.0) / 8.0 * 100.0))
    if ten_year_yield is not None:
        components.append(clip_score((4.5 - ten_year_yield) / 2.5 * 100.0))
    if not components:
        return 50.0
    return clip_score(sum(components) / len(components))


def _score_credit(social_financing_yoy: Optional[float]) -> float:
    if social_financing_yoy is None:
        return 50.0
    return clip_score((social_financing_yoy - 5.0) / 10.0 * 100.0)


def _center_score(value: float, center: float, tolerance: float) -> float:
    return clip_score(100.0 - abs(value - center) / tolerance * 100.0)


def _metric_or_warning(
    indicators: Mapping[str, object],
    name: str,
    warnings: List[str],
) -> Optional[float]:
    value = _get_metric(indicators, name)
    if value is None:
        warnings.append(f"missing {name}; score degraded")
    return value


def _get_metric(indicators: Mapping[str, object], name: str) -> Optional[float]:
    if name not in indicators:
        return None
    value = indicators[name]
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

