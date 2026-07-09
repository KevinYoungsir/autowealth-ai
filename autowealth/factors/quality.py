"""
Quality factor scoring.
"""

from __future__ import annotations

from typing import Mapping

from autowealth.factors.schema import (
    FactorScore,
    average_available,
    get_metric,
    missing_warnings,
    score_higher_better,
    score_lower_better,
)


def quality_factor(
    symbol: str,
    financial_data: Mapping[str, object],
    as_of_date: str,
) -> FactorScore:
    """
    Score business quality using profitability, cash flow quality and leverage.
    """
    raw_values = {
        "roe": get_metric(financial_data, "roe", "ROE"),
        "gross_margin": get_metric(financial_data, "gross_margin", "毛利率"),
        "net_margin": get_metric(financial_data, "net_margin", "净利率"),
        "operating_cash_flow_quality": get_metric(
            financial_data,
            "operating_cash_flow_quality",
            "ocf_quality",
            "operating_cash_flow_to_net_income",
        ),
        "debt_to_asset": get_metric(financial_data, "debt_to_asset", "asset_liability_ratio"),
    }
    component_scores = {
        "roe": score_higher_better(raw_values["roe"], 0.0, 0.25),
        "gross_margin": score_higher_better(raw_values["gross_margin"], 0.1, 0.6),
        "net_margin": score_higher_better(raw_values["net_margin"], 0.02, 0.25),
        "operating_cash_flow_quality": score_higher_better(
            raw_values["operating_cash_flow_quality"], 0.5, 1.5
        ),
        "debt_to_asset": score_lower_better(raw_values["debt_to_asset"], 0.2, 0.8),
    }
    return FactorScore(
        symbol=symbol,
        factor_name="quality",
        score=average_available(component_scores),
        raw_values=raw_values,
        as_of_date=as_of_date,
        explanation="Quality score summarizes profitability, cash conversion and leverage for research only.",
        warnings=missing_warnings(raw_values),
    )

