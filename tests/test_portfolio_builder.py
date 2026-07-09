import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

from autowealth.factors.schema import FactorScore
from autowealth.portfolio import (
    PortfolioConstraints,
    StockCandidate,
    build_factor_portfolio,
    build_target_weights_from_factor_scores,
)


def make_candidates():
    industries = ["消费", "金融", "公用事业", "制造", "医药"]
    scores = [95, 92, 88, 84, 80, 76, 72, 68, 64, 58, 45]
    candidates = []
    for index, score in enumerate(scores):
        symbol = f"600{index:03d}"
        candidates.append(
            StockCandidate(
                symbol=symbol,
                score=score,
                factor_scores={
                    "value": score - 5,
                    "quality": score,
                    "momentum": score - 10,
                },
                industry=industries[index % len(industries)],
            )
        )
    return candidates


def permissive_constraints(**kwargs):
    defaults = {
        "max_position_weight": 0.2,
        "min_position_weight": 0.01,
        "max_industry_weight": 0.6,
        "max_holdings": 10,
        "min_holdings": 5,
        "cash_weight_min": 0.0,
        "cash_weight_max": 0.4,
        "min_score": 0.0,
    }
    defaults.update(kwargs)
    return PortfolioConstraints(**defaults)


def test_target_weights_sum_does_not_exceed_one():
    result = build_factor_portfolio(
        make_candidates(),
        constraints=permissive_constraints(),
        macro_multiplier=1.0,
    )

    assert sum(result.target_weights.values()) <= 1.0
    assert abs(sum(result.target_weights.values()) + result.cash_weight - 1.0) < 1e-12


def test_max_position_weight_constraint():
    constraints = permissive_constraints(max_position_weight=0.1, max_industry_weight=1.0)
    result = build_factor_portfolio(make_candidates(), constraints=constraints, macro_multiplier=1.0)

    assert result.target_weights
    assert max(result.target_weights.values()) <= 0.1 + 1e-12


def test_max_industry_weight_constraint():
    constraints = permissive_constraints(max_position_weight=0.2, max_industry_weight=0.25)
    result = build_factor_portfolio(make_candidates(), constraints=constraints, macro_multiplier=1.0)

    industry_weights = {}
    for holding in result.holdings:
        industry_weights[holding.industry] = industry_weights.get(holding.industry, 0.0)
        industry_weights[holding.industry] += holding.target_weight

    assert industry_weights
    assert max(industry_weights.values()) <= 0.25 + 1e-12


def test_cash_weight_logic():
    result = build_factor_portfolio(
        make_candidates(),
        constraints=permissive_constraints(cash_weight_min=0.2, cash_weight_max=0.4),
        macro_multiplier=1.2,
    )

    assert result.cash_weight >= 0.2 - 1e-12
    assert sum(result.target_weights.values()) <= 0.8 + 1e-12


def test_macro_multiplier_affects_equity_weight():
    constraints = permissive_constraints(max_position_weight=0.2, max_industry_weight=1.0)
    low_macro = build_factor_portfolio(
        make_candidates(),
        constraints=constraints,
        macro_multiplier=0.8,
    )
    high_macro = build_factor_portfolio(
        make_candidates(),
        constraints=constraints,
        macro_multiplier=1.1,
    )

    assert high_macro.equity_weight > low_macro.equity_weight
    assert low_macro.cash_weight > high_macro.cash_weight


def test_low_score_stock_is_rejected():
    constraints = permissive_constraints(min_score=60)
    result = build_factor_portfolio(make_candidates(), constraints=constraints, macro_multiplier=1.0)

    assert "600010" in result.rejected_symbols
    assert "score below threshold" in result.rejected_symbols["600010"]


def test_output_fields_are_complete():
    result = build_factor_portfolio(
        make_candidates(),
        constraints=permissive_constraints(),
        macro_multiplier=0.9,
    )
    expected_fields = {
        "holdings",
        "target_weights",
        "cash_weight",
        "macro_multiplier",
        "selected_symbols",
        "rejected_symbols",
        "warnings",
        "explanation",
        "constraints",
        "equity_weight",
    }

    assert expected_fields.issubset(result.__dict__.keys())
    assert result.selected_symbols == [holding.symbol for holding in result.holdings]


def test_integration_builds_target_weights_from_factor_scores():
    factor_scores = {
        "600000": FactorScore(
            symbol="600000",
            factor_name="composite",
            score=90,
            raw_values={},
            as_of_date="2024-12-31",
            explanation="Research score.",
        ),
        "600001": FactorScore(
            symbol="600001",
            factor_name="composite",
            score=80,
            raw_values={},
            as_of_date="2024-12-31",
            explanation="Research score.",
        ),
    }
    constraints = permissive_constraints(max_holdings=2, min_holdings=1, max_industry_weight=1.0)

    weights = build_target_weights_from_factor_scores(
        factor_scores,
        industries={"600000": "金融", "600001": "消费"},
        constraints=constraints,
        macro_multiplier=0.8,
    )

    assert weights
    assert sum(weights.values()) <= 1.0

