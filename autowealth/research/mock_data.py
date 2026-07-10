"""
Mock inputs for offline research pipeline tests and examples.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from autowealth.factors.schema import FactorScore
from autowealth.macro.schema import MacroRiskScore
from autowealth.portfolio.schema import PortfolioConstraints


def mock_candidate_symbols() -> List[str]:
    return ["600519", "000001", "600036", "600900", "000858", "300750", "600000"]


def mock_industries() -> Dict[str, str]:
    return {
        "600519": "消费",
        "000001": "金融",
        "600036": "金融",
        "600900": "公用事业",
        "000858": "消费",
        "300750": "制造",
        "600000": "金融",
    }


def mock_factor_scores() -> Dict[str, FactorScore]:
    scores = {
        "600519": 92,
        "000001": 78,
        "600036": 84,
        "600900": 82,
        "000858": 75,
        "300750": 88,
        "600000": 45,
    }
    return {
        symbol: FactorScore(
            symbol=symbol,
            factor_name="composite",
            score=score,
            raw_values={"mock_composite": float(score)},
            as_of_date="2024-12-31",
            explanation="Mock research factor score for offline pipeline testing.",
        )
        for symbol, score in scores.items()
    }


def mock_macro_regime() -> MacroRiskScore:
    return MacroRiskScore(
        as_of_date="2024-12-31",
        growth_score=70,
        inflation_score=72,
        liquidity_score=65,
        credit_score=68,
        policy_score=70,
        external_risk_score=75,
        regime="expansion",
        equity_position_multiplier=1.1,
        explanation="Mock macro regime for offline research testing.",
        warnings=[],
        indicators={"pmi": 52.0},
    )


def mock_price_data(symbols: List[str] | None = None) -> Dict[str, pd.DataFrame]:
    symbols = symbols or mock_candidate_symbols()
    dates = pd.bdate_range("2020-01-02", "2024-12-31")
    data = {}
    for index, symbol in enumerate(symbols):
        base = 20 + index * 8
        close = []
        volume = []
        for day, _ in enumerate(dates):
            drift = 1 + 0.00025 * day
            wave = 1 + ((day % 40) - 20) / 5000
            close.append(base * drift * wave)
            volume.append(1_000_000 + index * 50_000 + (day % 21) * 2_000)
        data[symbol] = pd.DataFrame(
            {
                "date": dates,
                "open": close,
                "high": [price * 1.01 for price in close],
                "low": [price * 0.99 for price in close],
                "close": close,
                "volume": volume,
                "amount": [price * 10_000 for price in close],
                "amplitude": 2.0,
                "pct_change": 0.1,
                "change": 0.1,
                "turnover": 0.5,
            }
        )
    return data


def mock_portfolio_constraints() -> PortfolioConstraints:
    return PortfolioConstraints(
        max_position_weight=0.18,
        min_position_weight=0.01,
        max_industry_weight=0.35,
        max_holdings=6,
        min_holdings=3,
        cash_weight_min=0.05,
        cash_weight_max=0.4,
        min_score=60,
    )

