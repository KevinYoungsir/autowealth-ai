"""Opt-in smoke test for public A-share data providers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from autowealth.research.real_pipeline import (
    RealDataAccessError,
    run_real_data_research,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("AUTOWEALTH_RUN_REAL_DATA_SMOKE") != "1",
        reason="set AUTOWEALTH_RUN_REAL_DATA_SMOKE=1 to access public data sources",
    ),
]


def test_real_data_short_window_smoke(tmp_path: Path) -> None:
    pytest.importorskip("akshare")
    config = {
        "experiment_name": "opt_in_real_data_smoke",
        "start_date": "2023-01-03",
        "end_date": "2023-06-30",
        "candidate_symbols": ["600519", "000001"],
        "rebalance_frequency": "yearly",
        "initial_capital": 100_000,
        "commission": 0.0003,
        "stamp_tax": 0.0005,
        "slippage": 0.0002,
        "price_adjust": "none",
        "factor_weights": {
            "value": 0.25,
            "quality": 0.25,
            "momentum": 0.20,
            "low_vol": 0.15,
            "overbought_oversold": 0.15,
        },
        "portfolio_constraints": {
            "max_position_weight": 0.60,
            "min_position_weight": 0.01,
            "max_industry_weight": 1.0,
            "max_holdings": 2,
            "min_holdings": 1,
            "cash_weight_min": 0.0,
            "cash_weight_max": 0.5,
            "min_score": 0.0,
        },
        "benchmark_symbols": ["000300"],
        "macro_csv_path": str(
            Path("configs/macro_data_template.csv").resolve()
        ),
        "cache_directory": str(tmp_path / "cache"),
        "output_directory": str(tmp_path / "runs"),
    }
    config_path = tmp_path / "real_data_smoke.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    try:
        result = run_real_data_research(config_path)
    except RealDataAccessError as exc:
        pytest.skip(f"public data source is unavailable: {exc}")

    assert not result.equity_curve.empty
    assert result.run_directory.exists()
    assert result.target_weights_by_date
