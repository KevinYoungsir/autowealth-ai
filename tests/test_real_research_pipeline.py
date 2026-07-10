"""Offline tests for the point-in-time real-data research pipeline."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from autowealth.backtest.metrics import annual_returns
from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.fundamental_provider import (
    AShareFundamentalProvider,
    FundamentalProviderResult,
)
from autowealth.data.fundamental_schema import latest_fundamental_asof
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.quality import check_price_quality
from autowealth.data.universe import UniverseSnapshot
from autowealth.research.artifacts import REQUIRED_ARTIFACT_FILES
from autowealth.research.real_pipeline import (
    load_real_research_config,
    run_real_data_research,
)


BENCHMARK_METRICS = {
    "annualized_return",
    "total_return",
    "max_drawdown",
    "volatility",
    "sharpe_ratio",
    "calmar_ratio",
}


def _price_frame(symbol: str) -> pd.DataFrame:
    dates = pd.bdate_range("2010-01-04", "2020-01-10")
    offset = 0.0 if symbol.endswith("1") else 8.0
    trend = np.linspace(0.0, 45.0, len(dates))
    cycle = np.sin(np.arange(len(dates)) / 40.0) * 1.5
    close = 40.0 + offset + trend + cycle
    volume = np.full(len(dates), 1_000_000.0)
    if symbol == "600001":
        volume[0] = 0.0
    return pd.DataFrame(
        {
            "date": dates,
            "open": close * 0.998,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": volume,
            "amount": close * volume,
        }
    )


def _fundamental_frame(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "report_date": "2008-12-31",
                "available_date": "2009-04-30",
                "pe": 28.0,
                "pb": 3.0,
                "dividend_yield": 0.02,
                "roe": 0.13,
                "gross_margin": 0.35,
                "net_margin": 0.12,
                "debt_ratio": 0.45,
                "operating_cash_flow": 120.0,
                "net_profit": 100.0,
                "source": "mock_fundamental",
                "fetched_at": "2025-01-01T00:00:00Z",
            },
            {
                "symbol": symbol,
                "report_date": "2009-12-31",
                "available_date": "2010-04-30",
                "pe": 1.0,
                "pb": 0.5,
                "dividend_yield": 0.08,
                "roe": 0.30,
                "gross_margin": 0.60,
                "net_margin": 0.30,
                "debt_ratio": 0.20,
                "operating_cash_flow": 300.0,
                "net_profit": 200.0,
                "source": "mock_fundamental",
                "fetched_at": "2025-01-01T00:00:00Z",
            },
            {
                "symbol": symbol,
                "report_date": "2020-12-31",
                "available_date": "2021-04-30",
                "pe": 2.0,
                "pb": 0.8,
                "dividend_yield": 0.07,
                "roe": 0.28,
                "gross_margin": 0.55,
                "net_margin": 0.25,
                "debt_ratio": 0.25,
                "operating_cash_flow": 350.0,
                "net_profit": 220.0,
                "source": "mock_fundamental",
                "fetched_at": "2025-01-01T00:00:00Z",
            },
        ]
    )


class MockPriceProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "none",
    ) -> pd.DataFrame:
        self.calls.append(symbol)
        return _price_frame(symbol)


class MockFundamentalProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        self.calls.append(symbol)
        return FundamentalProviderResult(
            data=_fundamental_frame(symbol),
            source="mock_fundamental",
            point_in_time=True,
            warnings=["mock provider warning for test"],
        )


class MockUniverseProvider:
    def __init__(self, symbols: list[str]) -> None:
        self.symbols = symbols
        self.calls: list[str] = []

    def get_universe(self, as_of_date: str) -> UniverseSnapshot:
        self.calls.append(as_of_date)
        return UniverseSnapshot(
            as_of_date=as_of_date,
            symbols=list(self.symbols),
            source="mock_historical_universe",
            point_in_time=True,
        )


class MockMacroProvider:
    def get_macro_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2009-12-01",
                    "available_date": "2010-01-02",
                    "pmi": 51.0,
                    "cpi_yoy": 2.0,
                    "ppi_yoy": 1.0,
                    "m2_yoy": 11.0,
                    "social_financing_yoy": 10.0,
                    "ten_year_yield": 3.0,
                    "usd_cny": 6.8,
                    "policy_score": 60.0,
                    "external_risk_score": 65.0,
                    "source": "mock_macro",
                },
                {
                    "date": "2010-01-01",
                    "available_date": "2010-02-01",
                    "pmi": 52.0,
                    "cpi_yoy": 2.2,
                    "ppi_yoy": 1.2,
                    "m2_yoy": 12.0,
                    "social_financing_yoy": 11.0,
                    "ten_year_yield": 3.1,
                    "usd_cny": 6.7,
                    "policy_score": 65.0,
                    "external_risk_score": 70.0,
                    "source": "mock_macro",
                },
            ]
        )


class MockIndexProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        self.calls.append(symbol)
        return _price_frame(symbol)


class FailingPriceProvider(MockPriceProvider):
    def __init__(self, failed_symbol: str) -> None:
        super().__init__()
        self.failed_symbol = failed_symbol

    def get_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "none",
    ) -> pd.DataFrame:
        if symbol == self.failed_symbol:
            self.calls.append(symbol)
            raise RuntimeError("mock price endpoint unavailable")
        return super().get_daily(symbol, start_date, end_date, adjust)


class FailingIndexProvider(MockIndexProvider):
    def get_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        self.calls.append(symbol)
        raise RuntimeError("mock benchmark endpoint unavailable")


class EmptyMacroProvider:
    def get_macro_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()


class MissingValuationFundamentalProvider(MockFundamentalProvider):
    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        result = super().get_fundamentals(symbol, start_date, end_date)
        result.data[["pe", "pb", "dividend_yield"]] = pd.NA
        return result


def _write_config(tmp_path: Path, frequency: str) -> Path:
    config = {
        "experiment_name": f"offline_{frequency}_research",
        "start_date": "2010-01-04",
        "end_date": "2020-01-10",
        "candidate_symbols": ["600001", "000002"],
        "rebalance_frequency": frequency,
        "initial_capital": 1_000_000,
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
        "macro_csv_path": str(tmp_path / "unused_macro.csv"),
        "cache_directory": str(tmp_path / "cache"),
        "output_directory": str(tmp_path / "runs"),
    }
    path = tmp_path / f"{frequency}.yaml"
    path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _write_partial_config(tmp_path: Path) -> Path:
    path = _write_config(tmp_path, "yearly")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["candidate_symbols"] = ["600001", "000002", "600003"]
    config["portfolio_constraints"]["max_holdings"] = 3
    config["portfolio_constraints"]["min_holdings"] = 3
    path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def _run_offline(tmp_path: Path, frequency: str):
    symbols = ["600001", "000002"]
    price_provider = MockPriceProvider()
    fundamental_provider = MockFundamentalProvider()
    universe_provider = MockUniverseProvider(symbols)
    index_provider = MockIndexProvider()
    result = run_real_data_research(
        _write_config(tmp_path, frequency),
        price_provider=price_provider,
        fundamental_provider=fundamental_provider,
        universe_provider=universe_provider,
        macro_provider=MockMacroProvider(),
        index_provider=index_provider,
        git_commit="test-commit",
    )
    return result, price_provider, fundamental_provider, universe_provider, index_provider


def test_baseline_config_parses() -> None:
    config = load_real_research_config("configs/a_share_15y_baseline.yaml")

    assert config.start_date == "2010-01-04"
    assert config.end_date == "2024-12-31"
    assert config.rebalance_frequency == "yearly"
    assert len(config.candidate_symbols) >= 5
    assert config.price_adjust == "none"


def test_available_date_blocks_future_fundamental_rows() -> None:
    data = _fundamental_frame("600001")

    first = latest_fundamental_asof(data, "600001", "2010-01-04")
    after_release = latest_fundamental_asof(data, "600001", "2010-05-03")

    assert first is not None
    assert first.available_date == "2009-04-30"
    assert first.pe == 28.0
    assert after_release is not None
    assert after_release.available_date == "2010-04-30"
    assert after_release.pe == 1.0


def test_yearly_pipeline_is_point_in_time_and_writes_complete_artifacts(
    tmp_path: Path,
) -> None:
    result, prices, fundamentals, universe, indexes = _run_offline(
        tmp_path, "yearly"
    )

    rebalance_years = [int(date[:4]) for date in result.target_weights_by_date]
    assert rebalance_years == list(range(2010, 2021))
    assert set(prices.calls) == {"600001", "000002"}
    assert set(fundamentals.calls) == {"600001", "000002"}
    assert len(universe.calls) == len(result.target_weights_by_date)
    assert indexes.calls == ["000300"]

    snapshots = result.factor_snapshots.copy()
    snapshot_dates = pd.to_datetime(snapshots["rebalance_date"])
    available_dates = pd.to_datetime(snapshots["fundamental_available_date"])
    assert (available_dates <= snapshot_dates).all()
    first_period = snapshots[snapshot_dates == pd.Timestamp("2010-01-04")]
    assert set(first_period["fundamental_available_date"]) == {"2009-04-30"}

    artifact_names = {path.name for path in result.run_directory.iterdir()}
    assert REQUIRED_ARTIFACT_FILES <= artifact_names
    warning_payload = json.loads(
        result.artifacts.files["warnings.json"].read_text(encoding="utf-8")
    )
    assert warning_payload["warnings"] == result.warnings
    assert any("published after" in warning for warning in result.warnings)
    assert any("zero-volume" in warning for warning in result.warnings)
    assert any("mock provider warning" in warning for warning in result.warnings)

    assert "000300" in result.benchmark_metrics
    assert BENCHMARK_METRICS <= set(result.benchmark_metrics["000300"])
    assert not result.benchmark_curve.empty
    assert not result.equity_curve.empty
    assert "2010" in result.metrics["annual_returns"]
    assert result.metrics["annual_return_method"].startswith(
        "first_valid_equity_to_year_end"
    )
    assert result.run_status == "success"


def test_five_year_pipeline_generates_five_year_schedule(tmp_path: Path) -> None:
    result, *_ = _run_offline(tmp_path, "five_year")

    rebalance_years = [int(date[:4]) for date in result.target_weights_by_date]
    assert rebalance_years == [2010, 2015, 2020]
    assert result.metrics["rebalance_frequency"] == "five_year"


def test_partial_coverage_sets_status_and_structures_benchmark_failure(
    tmp_path: Path,
) -> None:
    result = run_real_data_research(
        _write_partial_config(tmp_path),
        price_provider=FailingPriceProvider("600003"),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(
            ["600001", "000002", "600003"]
        ),
        macro_provider=EmptyMacroProvider(),
        index_provider=FailingIndexProvider(),
        git_commit="test-commit",
    )

    coverage = result.coverage_summary
    assert result.run_status == "partial_success"
    assert coverage["requested_symbols"] == ["600001", "000002", "600003"]
    assert coverage["successful_price_symbols"] == ["000002", "600001"]
    assert coverage["failed_price_symbols"] == ["600003"]
    assert coverage["price_coverage_ratio"] == 2 / 3
    assert coverage["benchmark_status"] == "unavailable"
    assert coverage["macro_observation_count"] == 0
    assert coverage["rebalance_count"] == len(result.target_weights_by_date)
    assert all(
        count < 3 for count in coverage["holdings_count_by_rebalance"].values()
    )
    assert coverage["warning_count"] == len(result.warnings)

    manifest = json.loads(
        result.artifacts.files["run_manifest.json"].read_text(encoding="utf-8")
    )
    assert manifest["run_status"] == "partial_success"
    assert manifest["coverage_summary"] == coverage

    benchmark_payload = json.loads(
        result.artifacts.files["benchmark_metrics.json"].read_text(
            encoding="utf-8"
        )
    )
    assert benchmark_payload["000300"] == {
        "status": "unavailable",
        "symbol": "000300",
        "reason": "mock benchmark endpoint unavailable",
        "metrics": {},
    }


def test_annual_returns_include_first_valid_year() -> None:
    dates = pd.bdate_range("2024-01-02", "2025-12-31")
    equity = pd.Series(
        [100.0 + index * 0.1 for index in range(len(dates))],
        index=dates,
    )

    returns = annual_returns(equity)

    assert returns.index.year.tolist() == [2024, 2025]
    first_year = equity[equity.index.year == 2024]
    expected_first = first_year.iloc[-1] / first_year.iloc[0] - 1
    assert abs(returns.iloc[0] - expected_first) < 1e-12


def test_normal_extended_holiday_is_not_a_severe_price_gap() -> None:
    dates = pd.bdate_range("2024-02-01", "2024-02-29")
    holiday = (dates >= "2024-02-09") & (dates <= "2024-02-16")
    dates = dates[~holiday]
    close = [10.0 + index * 0.01 for index in range(len(dates))]
    frame = pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "volume": 1_000_000,
        }
    )

    report = check_price_quality(frame)

    assert not any("gaps exceeding" in warning for warning in report.warnings)


def test_missing_valuation_factor_is_excluded_and_weights_are_renormalized(
    tmp_path: Path,
) -> None:
    symbols = ["600001", "000002"]
    result = run_real_data_research(
        _write_config(tmp_path, "yearly"),
        price_provider=MockPriceProvider(),
        fundamental_provider=MissingValuationFundamentalProvider(),
        universe_provider=MockUniverseProvider(symbols),
        macro_provider=MockMacroProvider(),
        index_provider=MockIndexProvider(),
        git_commit="test-commit",
    )

    snapshots = result.factor_snapshots
    assert result.run_status == "partial_success"
    assert not snapshots["value_available"].any()
    assert snapshots["value_score"].isna().all()
    for serialized_weights in snapshots["composite_weights"]:
        weights = json.loads(serialized_weights)
        assert "value" not in weights
        assert abs(sum(weights.values()) - 1.0) < 1e-12
    for period in result.coverage_summary["factor_coverage_by_rebalance"].values():
        assert period["value"] == {
            "available_count": 0,
            "missing_count": 2,
            "coverage_ratio": 0.0,
        }
    assert result.coverage_summary["factor_coverage_overall"]["value"] == {
        "available_count": 0,
        "missing_count": len(snapshots),
        "coverage_ratio": 0.0,
    }
    assert any(
        "excluded unavailable factors" in warning for warning in result.warnings
    )


def test_import_does_not_initialize_network_providers(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("provider initialized during module import")

    monkeypatch.setattr(AShareDataProvider, "__init__", fail)
    monkeypatch.setattr(AShareFundamentalProvider, "__init__", fail)
    monkeypatch.setattr(AShareIndexProvider, "__init__", fail)

    module = importlib.import_module("autowealth.research.real_pipeline")
    importlib.reload(module)
