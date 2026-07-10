import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

import pandas as pd

from autowealth.macro import (
    classify_macro_regime,
    equity_position_multiplier,
    latest_macro_indicators,
    load_macro_csv,
    score_macro_environment,
)


AS_OF_DATE = "2024-12-31"


def test_expansion_regime_classification():
    indicators = {
        "pmi": 52.5,
        "cpi_yoy": 2.1,
        "ppi_yoy": 1.5,
        "m2_yoy": 10.0,
        "social_financing_yoy": 12.0,
        "ten_year_yield": 2.4,
        "policy_score": 75,
        "external_risk_score": 80,
    }

    regime = classify_macro_regime(indicators, AS_OF_DATE)

    assert regime.regime == "expansion"
    assert "advice" not in regime.explanation.lower()


def test_recession_regime_classification():
    indicators = {
        "pmi": 47.0,
        "cpi_yoy": 0.5,
        "ppi_yoy": -2.0,
        "m2_yoy": 5.5,
        "social_financing_yoy": 6.0,
        "ten_year_yield": 3.6,
        "policy_score": 40,
        "external_risk_score": 45,
    }

    regime = classify_macro_regime(indicators, AS_OF_DATE)

    assert regime.regime == "recession"


def test_stagflation_regime_classification():
    indicators = {
        "pmi": 49.0,
        "cpi_yoy": 7.0,
        "ppi_yoy": 8.0,
        "m2_yoy": 6.0,
        "social_financing_yoy": 9.0,
        "ten_year_yield": 4.0,
        "policy_score": 45,
        "external_risk_score": 50,
    }

    regime = classify_macro_regime(indicators, AS_OF_DATE)

    assert regime.regime == "stagflation"


def test_recovery_regime_classification():
    indicators = {
        "pmi": 50.2,
        "cpi_yoy": 1.5,
        "ppi_yoy": 0.5,
        "m2_yoy": 11.0,
        "social_financing_yoy": 12.0,
        "ten_year_yield": 2.6,
        "policy_score": 70,
        "external_risk_score": 75,
    }

    regime = classify_macro_regime(indicators, AS_OF_DATE)

    assert regime.regime == "recovery"


def test_missing_data_degrades_without_crashing():
    result = score_macro_environment({"pmi": 50.0}, AS_OF_DATE)

    assert result.regime in {"uncertain", "recovery", "slowdown"}
    assert result.warnings
    assert 0 <= result.growth_score <= 100
    assert 0.6 <= result.equity_position_multiplier <= 1.2


def test_equity_position_multiplier_range():
    for regime in ["recession", "slowdown", "uncertain", "recovery", "expansion", "unknown"]:
        multiplier = equity_position_multiplier(regime)
        assert 0.6 <= multiplier <= 1.2


def test_macro_risk_score_fields_are_complete():
    result = score_macro_environment(
        {
            "pmi": 52,
            "cpi_yoy": 2,
            "ppi_yoy": 1,
            "m2_yoy": 10,
            "social_financing_yoy": 11,
            "ten_year_yield": 2.7,
            "policy_score": 70,
            "external_risk_score": 65,
        },
        AS_OF_DATE,
    )

    expected = {
        "as_of_date",
        "growth_score",
        "inflation_score",
        "liquidity_score",
        "credit_score",
        "policy_score",
        "external_risk_score",
        "regime",
        "equity_position_multiplier",
        "explanation",
        "warnings",
    }
    assert expected.issubset(result.__dict__.keys())


def test_load_macro_csv_and_latest_row(tmp_path):
    path = tmp_path / "macro.csv"
    pd.DataFrame(
        [
            {"date": "2024-01-31", "pmi": 49.0, "policy_score": 50},
            {"date": "2024-02-29", "pmi": 51.0, "external_risk_score": 70},
        ]
    ).to_csv(path, index=False)

    loaded = load_macro_csv(path)
    latest = latest_macro_indicators(path)

    assert list(loaded.columns)[0] == "date"
    assert "cpi_yoy" in loaded.columns
    assert latest["date"] == "2024-02-29"
    assert latest["pmi"] == 51.0

