"""Offline tests for the point-in-time real-data research pipeline."""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

import autowealth.research.real_pipeline as real_pipeline_module
import autowealth.research.artifacts as artifacts_module
from autowealth.backtest.metrics import annual_returns
from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.cache import ParquetCache
from autowealth.data.fundamental_provider import (
    AShareFundamentalProvider,
    FundamentalProviderResult,
)
from autowealth.data.fundamental_schema import (
    latest_fundamental_asof,
    validate_fundamental_history,
)
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.index_provider_chain import IndexProviderChain
from autowealth.data.quality import check_price_quality
from autowealth.data.universe import UniverseSnapshot
from autowealth.research.artifacts import REQUIRED_ARTIFACT_FILES, write_research_artifacts
from autowealth.research.real_pipeline import (
    RealResearchError,
    load_real_research_config,
    run_real_data_research,
)
from autowealth.research.run_store import ResearchRunStore, aggregate_warnings
from autowealth.research.warnings import (
    StructuredWarning,
    WarningCode,
    WarningScope,
    WarningSeverity,
)
from autowealth.security import contains_absolute_path

BENCHMARK_METRICS = {
    "annualized_return",
    "total_return",
    "max_drawdown",
    "volatility",
    "sharpe_ratio",
    "calmar_ratio",
}


def _price_frame(symbol: str) -> pd.DataFrame:
    dates = pd.bdate_range("2008-01-02", "2020-01-10")
    offset = 0.0 if symbol.endswith("1") else 8.0
    trend = np.linspace(0.0, 45.0, len(dates))
    cycle = np.sin(np.arange(len(dates)) / 40.0) * 1.5
    close = 40.0 + offset + trend + cycle
    volume = np.full(len(dates), 1_000_000.0)
    if symbol == "600001":
        volume[250] = 0.0
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
        self.windows: list[tuple[str, str, str]] = []

    def get_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "none",
    ) -> pd.DataFrame:
        self.calls.append(symbol)
        self.windows.append((symbol, start_date, end_date))
        return _price_frame(symbol)


class MockFundamentalProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.windows: list[tuple[str, str, str]] = []

    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        self.calls.append(symbol)
        self.windows.append((symbol, start_date, end_date))
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


class UnverifiedUniverseProvider(MockUniverseProvider):
    def get_universe(self, as_of_date: str) -> UniverseSnapshot:
        self.calls.append(as_of_date)
        return UniverseSnapshot(
            as_of_date=as_of_date,
            symbols=list(self.symbols),
            source="mock_fixed_universe",
            point_in_time=False,
            warnings=["mock universe is not verified point-in-time"],
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

    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(symbol)
        frame = _price_frame(symbol)
        return frame[
            pd.to_datetime(frame["date"]).between(
                pd.Timestamp(start_date),
                pd.Timestamp(end_date),
                inclusive="both",
            )
        ].reset_index(drop=True)


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
    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(symbol)
        raise RuntimeError("mock benchmark endpoint unavailable")


class NamedFailingIndexProvider(MockIndexProvider):
    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.provider_name = f"benchmark_failure_{index:02d}"
        self.endpoint = f"offline_endpoint_{index:02d}"

    @property
    def expected_reason_code(self) -> str:
        return "empty_response" if self.index % 2 == 0 else "provider_exception"

    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(symbol)
        if self.index % 2:
            raise RuntimeError("offline benchmark fixture failure")
        return pd.DataFrame()


class FailingFundamentalProvider(MockFundamentalProvider):
    def __init__(self, failed_symbol: str) -> None:
        super().__init__()
        self.failed_symbol = failed_symbol

    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        if symbol == self.failed_symbol:
            self.calls.append(symbol)
            raise RuntimeError("mock fundamental endpoint unavailable")
        return super().get_fundamentals(symbol, start_date, end_date)


class EmptyMacroProvider:
    def get_macro_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame()


class InvalidShadowMacroProvider:
    def get_macro_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "date": "2009-12-01",
                    "available_date": None,
                    "pmi": 51.0,
                    "source": "invalid_shadow_macro",
                }
            ]
        )


class MissingValuationFundamentalProvider(MockFundamentalProvider):
    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        result = super().get_fundamentals(symbol, start_date, end_date)
        result.data[["pe", "pb", "dividend_yield"]] = pd.NA
        return result


SENSITIVE_PROVIDER_ERROR = (
    "C:\\Users\\researcher\\cache.parquet "
    "\\\\server\\share\\provider.json /tmp/provider-response.json "
    "apiKey=key-secret accessToken=access-secret clientSecret=client-secret "
    "Authorization: Bearer auth-secret Cookie: cookie-secret\n"
    "Traceback (most recent call last):\n"
    'File "D:\\private\\provider.py", line 1\n'
    "RuntimeError at 0x7FFABCDEF123"
)


class SensitiveFailingPriceProvider(MockPriceProvider):
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
            raise RuntimeError(SENSITIVE_PROVIDER_ERROR)
        return super().get_daily(symbol, start_date, end_date, adjust)


class SensitiveFailingFundamentalProvider(MockFundamentalProvider):
    def __init__(self, failed_symbol: str) -> None:
        super().__init__()
        self.failed_symbol = failed_symbol

    def get_fundamentals(
        self, symbol: str, start_date: str, end_date: str
    ) -> FundamentalProviderResult:
        if symbol == self.failed_symbol:
            self.calls.append(symbol)
            raise RuntimeError(SENSITIVE_PROVIDER_ERROR)
        return super().get_fundamentals(symbol, start_date, end_date)


class SensitiveFailingMacroProvider:
    def get_macro_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        raise RuntimeError(SENSITIVE_PROVIDER_ERROR)


class SensitiveFailingIndexProvider(MockIndexProvider):
    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(symbol)
        raise RuntimeError(SENSITIVE_PROVIDER_ERROR)


def _write_config(
    tmp_path: Path,
    frequency: str,
    history_lookback: object = None,
) -> Path:
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
    if history_lookback is not None:
        config["history_lookback"] = history_lookback
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


def _run_shadow_case(
    tmp_path: Path,
    *,
    enabled: bool,
    macro_provider: object = None,
):
    tmp_path.mkdir(parents=True, exist_ok=True)
    symbols = ["600001", "000002"]
    return run_real_data_research(
        _write_config(tmp_path, "yearly"),
        price_provider=MockPriceProvider(),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(symbols),
        macro_provider=macro_provider or MockMacroProvider(),
        index_provider=MockIndexProvider(),
        run_time=datetime(2025, 1, 1, tzinfo=timezone.utc),
        git_commit="test-commit",
        macro_validation_enabled=enabled,
    )


def _capture_macro_asof_outputs(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    captured: list[dict[str, object]] = []
    original = real_pipeline_module._macro_asof

    def capture(*args: object, **kwargs: object):
        result = original(*args, **kwargs)
        score, multiplier = result[0], result[1]
        captured.append(
            {
                "score": asdict(score) if score is not None else None,
                "multiplier": multiplier,
            }
        )
        return result

    monkeypatch.setattr(real_pipeline_module, "_macro_asof", capture)
    return captured


def _assert_shadow_business_outputs_equal(left, right) -> None:
    assert left.run_status == right.run_status
    assert left.warnings == right.warnings
    assert left.structured_warnings == right.structured_warnings
    assert left.coverage_summary["warning_count"] == right.coverage_summary["warning_count"]
    assert left.metrics == right.metrics
    assert left.benchmark_metrics == right.benchmark_metrics
    assert left.target_weights_by_date == right.target_weights_by_date
    pd.testing.assert_series_equal(left.equity_curve, right.equity_curve)
    pd.testing.assert_frame_equal(left.benchmark_curve, right.benchmark_curve)
    pd.testing.assert_frame_equal(left.factor_snapshots, right.factor_snapshots)
    for artifact_name in ("holdings.parquet", "trades.parquet"):
        pd.testing.assert_frame_equal(
            pd.read_parquet(left.artifacts.files[artifact_name]),
            pd.read_parquet(right.artifacts.files[artifact_name]),
        )
    left_manifest = json.loads(
        left.artifacts.files["run_manifest.json"].read_text(encoding="utf-8")
    )
    right_manifest = json.loads(
        right.artifacts.files["run_manifest.json"].read_text(encoding="utf-8")
    )
    assert left_manifest["run_status_reasons"] == right_manifest["run_status_reasons"]


def _nested_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [
            item for key, child in value.items() for item in [str(key), *_nested_strings(child)]
        ]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _nested_strings(child)]
    return []


def test_warning_sanitization_degrades_to_raw_only_without_failing() -> None:
    raw = [r"price provider failed: C:\private\cache.parquet"]

    safe, structured = real_pipeline_module._sanitize_warning_outputs(raw, ())

    assert safe == ["price provider failed: [redacted-absolute-path]"]
    assert structured is None


def test_oversized_structured_warning_projection_degrades_to_raw_only() -> None:
    raw = [f"benchmark warning {index}" for index in range(280)]
    evidence = {f"field_{index}": "x" * 500 for index in range(30)}
    structured = tuple(
        StructuredWarning(
            code=WarningCode.BENCHMARK_DATA_UNAVAILABLE,
            severity=WarningSeverity.WARNING,
            scope=WarningScope.BENCHMARK,
            message=message,
            source="benchmark_provider_chain",
            evidence=evidence,
        )
        for message in raw
    )

    safe, projected = real_pipeline_module._sanitize_warning_outputs(
        raw,
        structured,
    )

    assert safe == raw
    assert projected is None


def test_baseline_config_parses() -> None:
    config = load_real_research_config("configs/a_share_15y_baseline.yaml")

    assert config.start_date == "2010-01-04"
    assert config.end_date == "2024-12-31"
    assert config.rebalance_frequency == "yearly"
    assert len(config.candidate_symbols) >= 5
    assert config.price_adjust == "none"
    assert config.history_lookback.price_calendar_days == 450
    assert config.history_lookback.fundamental_years == 5


def test_config_normalizes_and_deduplicates_benchmark_names(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, "yearly")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["benchmark_symbols"] = ["沪深 300", "000300"]
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    config = load_real_research_config(config_path)

    assert config.benchmark_symbols == ["000300"]


def test_legacy_config_uses_safe_history_lookback_defaults(tmp_path: Path) -> None:
    config = load_real_research_config(_write_config(tmp_path, "yearly"))

    assert config.history_lookback.price_calendar_days == 450
    assert config.history_lookback.fundamental_years == 5


def test_history_lookback_parses_explicit_values(tmp_path: Path) -> None:
    config = load_real_research_config(
        _write_config(
            tmp_path,
            "yearly",
            {"price_calendar_days": 500, "fundamental_years": 7},
        )
    )

    assert config.history_lookback.price_calendar_days == 500
    assert config.history_lookback.fundamental_years == 7


@pytest.mark.parametrize(
    "history_lookback",
    [
        {"price_calendar_days": -1, "fundamental_years": 5},
        {"price_calendar_days": 450.0, "fundamental_years": 5},
        {"price_calendar_days": 450, "fundamental_years": "5"},
    ],
)
def test_history_lookback_rejects_negative_or_non_integer_values(
    tmp_path: Path,
    history_lookback: object,
) -> None:
    with pytest.raises(RealResearchError, match="non-negative integer"):
        load_real_research_config(_write_config(tmp_path, "yearly", history_lookback))


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


def test_missing_available_date_is_not_point_in_time_eligible() -> None:
    data = _fundamental_frame("600001").iloc[[0]].copy()
    data["available_date"] = pd.NaT

    assert latest_fundamental_asof(data, "600001", "2010-01-04") is None


def test_available_date_before_report_date_is_invalidated_with_warning() -> None:
    data = _fundamental_frame("600001").iloc[[0]].copy()
    data["report_date"] = "2009-12-31"
    data["available_date"] = "2009-12-01"

    validated, warnings = validate_fundamental_history(data)

    assert validated["available_date"].isna().all()
    assert any("available_date earlier than report_date" in warning for warning in warnings)
    assert latest_fundamental_asof(validated, "600001", "2010-01-04") is None


def test_duplicate_fundamental_reports_use_auditable_latest_fetched_rule() -> None:
    first = _fundamental_frame("600001").iloc[[0]].copy()
    second = first.copy()
    first["fetched_at"] = "2024-01-01T00:00:00Z"
    second["fetched_at"] = "2025-01-01T00:00:00Z"
    first["roe"] = 0.1
    second["roe"] = 0.2

    validated, warnings = validate_fundamental_history(
        pd.concat([first, second], ignore_index=True)
    )

    assert len(validated) == 1
    assert validated.iloc[0]["roe"] == 0.2
    assert any("duplicate fundamental rows" in warning for warning in warnings)


def test_yearly_pipeline_is_point_in_time_and_writes_complete_artifacts(
    tmp_path: Path,
) -> None:
    result, prices, fundamentals, universe, indexes = _run_offline(tmp_path, "yearly")

    rebalance_years = [int(date[:4]) for date in result.target_weights_by_date]
    assert rebalance_years == list(range(2010, 2021))
    assert set(prices.calls) == {"600001", "000002"}
    assert set(fundamentals.calls) == {"600001", "000002"}
    assert {
        (symbol, result.config.price_fetch_start_date, result.config.end_date)
        for symbol in result.config.candidate_symbols
    } == set(prices.windows)
    assert {
        (
            symbol,
            result.config.fundamental_fetch_start_date,
            result.config.end_date,
        )
        for symbol in result.config.candidate_symbols
    } == set(fundamentals.windows)
    assert len(universe.calls) == len(result.target_weights_by_date)
    assert indexes.calls == ["000300"]

    snapshots = result.factor_snapshots.copy()
    snapshot_dates = pd.to_datetime(snapshots["execution_date"])
    signal_dates = pd.to_datetime(snapshots["signal_date"])
    assert (signal_dates < snapshot_dates).all()
    assert (pd.to_datetime(snapshots["rebalance_date"]) == snapshot_dates).all()
    available_dates = pd.to_datetime(snapshots["fundamental_available_date"])
    assert (available_dates <= signal_dates).all()
    first_period = snapshots[snapshot_dates == pd.Timestamp("2010-01-04")]
    assert set(pd.to_datetime(first_period["signal_date"])) == {pd.Timestamp("2010-01-01")}
    assert set(first_period["fundamental_available_date"]) == {"2009-04-30"}

    artifact_names = {path.name for path in result.run_directory.iterdir()}
    assert REQUIRED_ARTIFACT_FILES <= artifact_names
    assert "benchmark_diagnostics.json" in artifact_names
    warning_payload = json.loads(
        result.artifacts.files["warnings.json"].read_text(encoding="utf-8")
    )
    assert warning_payload["warnings"] == result.warnings
    assert warning_payload["structured_warnings_schema_version"] == 1
    assert warning_payload["structured_warnings"] == result.structured_warnings
    assert len(result.structured_warnings) == len(result.warnings)
    assert [warning["message"] for warning in result.structured_warnings] == result.warnings
    assert len(result.warnings) == len(set(result.warnings))
    assert any("published after" in warning for warning in result.warnings)
    assert any("zero-volume" in warning for warning in result.warnings)
    assert any("mock provider warning" in warning for warning in result.warnings)

    assert "000300" in result.benchmark_metrics
    assert BENCHMARK_METRICS <= set(result.benchmark_metrics["000300"])
    assert not result.benchmark_curve.empty
    benchmark_diagnostics = json.loads(
        result.artifacts.files["benchmark_diagnostics.json"].read_text(encoding="utf-8")
    )
    assert benchmark_diagnostics["schema_version"] == 1
    assert benchmark_diagnostics["benchmarks"]["000300"]["status"] == "success"
    assert benchmark_diagnostics["benchmarks"]["000300"]["attempts"]
    assert not result.equity_curve.empty
    assert "2010" in result.metrics["annual_returns"]
    assert result.metrics["annual_return_method"].startswith("first_valid_equity_to_year_end")
    assert result.equity_curve.index.min() >= pd.Timestamp(result.config.start_date)
    assert all(int(year) >= 2010 for year in result.metrics["annual_returns"])
    assert all(int(month[:4]) >= 2010 for month in result.metrics["monthly_returns"])

    trades = pd.read_parquet(result.artifacts.files["trades.parquet"])
    holdings = pd.read_parquet(result.artifacts.files["holdings.parquet"])
    assert pd.to_datetime(trades["date"]).min() >= pd.Timestamp("2010-01-04")
    assert pd.to_datetime(holdings["date"]).min() >= pd.Timestamp("2010-01-04")

    manifest = json.loads(result.artifacts.files["run_manifest.json"].read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == "2.0"
    assert manifest["research_window"] == manifest["metrics_window"]
    assert manifest["fetch_windows"]["prices"]["start_date"] == (
        result.config.price_fetch_start_date
    )
    assert manifest["fetch_windows"]["fundamentals"]["start_date"] == (
        result.config.fundamental_fetch_start_date
    )
    assert manifest["signal_execution_policy"]["signal_lag_trading_days"] == 1
    assert manifest["factor_lookbacks"]["max_drawdown"]["minimum_observations"] == 253
    assert "benchmark_diagnostics.json" in manifest["artifact_files"]
    assert manifest["artifact_summary"]["benchmark_diagnostics"] == {
        "schema_version": 1,
        "benchmark_count": 1,
        "success_count": 1,
        "unavailable_count": 0,
    }

    config_artifact = json.loads(result.artifacts.files["config.json"].read_text(encoding="utf-8"))
    assert config_artifact["history_lookback"] == {
        "price_calendar_days": 450,
        "fundamental_years": 5,
    }
    assert config_artifact["macro_csv_path"] == result.config.macro_csv_path.name
    assert config_artifact["cache_directory"] == result.config.cache_directory.name
    assert config_artifact["output_directory"] == result.config.output_directory.name
    for artifact_name in (
        "config.json",
        "run_manifest.json",
        "benchmark_diagnostics.json",
        "warnings.json",
    ):
        artifact_payload = json.loads(
            result.artifacts.files[artifact_name].read_text(encoding="utf-8")
        )
        assert not any(contains_absolute_path(value) for value in _nested_strings(artifact_payload))
    assert result.run_status == "success"


def test_five_year_pipeline_generates_five_year_schedule(tmp_path: Path) -> None:
    result, *_ = _run_offline(tmp_path, "five_year")

    rebalance_years = [int(date[:4]) for date in result.target_weights_by_date]
    assert rebalance_years == [2010, 2015, 2020]
    assert result.metrics["rebalance_frequency"] == "five_year"


def test_shadow_macro_validation_enabled_and_disabled_preserve_business_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_outputs = _capture_macro_asof_outputs(monkeypatch)
    enabled = _run_shadow_case(tmp_path / "enabled", enabled=True)
    enabled_macro_outputs = list(macro_outputs)
    macro_outputs.clear()
    disabled = _run_shadow_case(tmp_path / "disabled", enabled=False)
    disabled_macro_outputs = list(macro_outputs)

    _assert_shadow_business_outputs_equal(enabled, disabled)
    assert enabled_macro_outputs == disabled_macro_outputs

    enabled_manifest = json.loads(
        enabled.artifacts.files["run_manifest.json"].read_text(encoding="utf-8")
    )
    disabled_manifest = json.loads(
        disabled.artifacts.files["run_manifest.json"].read_text(encoding="utf-8")
    )
    diagnostics = enabled_manifest["macro_validation_diagnostics"]
    assert diagnostics["validation_mode"] == "shadow"
    assert diagnostics["status"] == "valid"
    assert "macro_validation_diagnostics" not in disabled_manifest
    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "raw_rows" not in serialized
    assert str(tmp_path) not in serialized


def test_invalid_shadow_macro_diagnostics_do_not_change_raw_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_outputs = _capture_macro_asof_outputs(monkeypatch)
    enabled = _run_shadow_case(
        tmp_path / "enabled",
        enabled=True,
        macro_provider=InvalidShadowMacroProvider(),
    )
    enabled_macro_outputs = list(macro_outputs)
    macro_outputs.clear()
    disabled = _run_shadow_case(
        tmp_path / "disabled",
        enabled=False,
        macro_provider=InvalidShadowMacroProvider(),
    )
    disabled_macro_outputs = list(macro_outputs)

    _assert_shadow_business_outputs_equal(enabled, disabled)
    assert enabled_macro_outputs == disabled_macro_outputs
    manifest = json.loads(enabled.artifacts.files["run_manifest.json"].read_text(encoding="utf-8"))
    diagnostics = manifest["macro_validation_diagnostics"]
    assert diagnostics["status"] == "invalid"
    assert diagnostics["reason_codes"] == ["missing_available_date"]
    assert diagnostics["rejected_counts"] == {"missing_available_date": 1}


def test_shadow_validator_exception_is_non_blocking_and_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    macro_outputs = _capture_macro_asof_outputs(monkeypatch)
    baseline = _run_shadow_case(tmp_path / "baseline", enabled=False)
    baseline_macro_outputs = list(macro_outputs)
    macro_outputs.clear()

    def fail_validation(*args: object, **kwargs: object) -> object:
        raise RuntimeError("token=secret C:\\private\\macro.csv")

    monkeypatch.setattr(real_pipeline_module, "validate_macro_observations", fail_validation)
    result = _run_shadow_case(tmp_path / "exception", enabled=True)

    _assert_shadow_business_outputs_equal(result, baseline)
    assert macro_outputs == baseline_macro_outputs
    manifest = json.loads(result.artifacts.files["run_manifest.json"].read_text(encoding="utf-8"))
    diagnostics = manifest["macro_validation_diagnostics"]
    assert diagnostics["status"] == "invalid"
    assert diagnostics["exception_type"] == "RuntimeError"
    serialized = json.dumps(diagnostics)
    assert "secret" not in serialized
    assert "private" not in serialized


def test_unregistered_raw_warning_degrades_to_raw_only_without_changing_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline_path = tmp_path / "baseline"
    incomplete_path = tmp_path / "incomplete"
    baseline_path.mkdir()
    incomplete_path.mkdir()
    baseline, *_ = _run_offline(baseline_path, "yearly")
    original_load_macro_data = real_pipeline_module._load_macro_data
    unregistered = "unregistered stage warning preserved verbatim"

    def load_macro_with_unregistered_warning(config, provider, warning_collector=None):
        frame, source, warnings = original_load_macro_data(
            config,
            provider,
            warning_collector,
        )
        return frame, source, [*warnings, unregistered]

    monkeypatch.setattr(
        real_pipeline_module,
        "_load_macro_data",
        load_macro_with_unregistered_warning,
    )
    result, *_ = _run_offline(incomplete_path, "yearly")

    warning_payload = json.loads(
        result.artifacts.files["warnings.json"].read_text(encoding="utf-8")
    )
    assert warning_payload == {"warnings": result.warnings}
    assert unregistered in result.warnings
    assert result.warnings.count(unregistered) == 1
    assert result.coverage_summary["warning_count"] == len(result.warnings)
    assert len(result.warnings) == len(baseline.warnings) + 1
    assert result.structured_warnings == []
    assert result.run_status == baseline.run_status
    assert result.metrics == baseline.metrics
    pd.testing.assert_series_equal(result.equity_curve, baseline.equity_curve)
    pd.testing.assert_frame_equal(result.benchmark_curve, baseline.benchmark_curve)
    assert ResearchRunStore(result.run_directory.parent).read_structured_warnings(
        result.run_id
    ) == {
        "structured_available": False,
        "structured_status": "absent",
        "structured_warnings_schema_version": None,
        "structured_warnings": [],
    }


def test_benchmark_fallback_warning_does_not_change_success_status(tmp_path: Path) -> None:
    symbols = ["600001", "000002"]
    fallback = MockIndexProvider()
    chain = IndexProviderChain([FailingIndexProvider(), fallback])

    result = run_real_data_research(
        _write_config(tmp_path, "yearly"),
        price_provider=MockPriceProvider(),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(symbols),
        macro_provider=MockMacroProvider(),
        index_provider=chain,
        git_commit="test-commit",
    )

    assert result.run_status == "success"
    assert not result.benchmark_curve.empty
    fallback_warnings = [
        warning
        for warning in result.structured_warnings
        if warning["code"] == "benchmark_provider_fallback_used"
    ]
    assert fallback_warnings
    assert fallback_warnings[0]["scope"] == "benchmark"
    assert fallback_warnings[0]["evidence"]["provider"] == "FailingIndexProvider"


def test_35_plus_benchmark_attempts_keep_warning_enrichment_exact(
    tmp_path: Path,
) -> None:
    symbols = ["600001", "000002"]
    failures = [NamedFailingIndexProvider(index) for index in range(35)]
    success = MockIndexProvider()
    success.provider_name = "benchmark_success"
    success.endpoint = "offline_success_endpoint"
    chain = IndexProviderChain([*failures, success])

    result = run_real_data_research(
        _write_config(tmp_path, "yearly"),
        price_provider=MockPriceProvider(),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(symbols),
        macro_provider=MockMacroProvider(),
        index_provider=chain,
        git_commit="test-commit",
    )

    raw_attempt_warnings = [
        warning
        for warning in result.warnings
        if warning.startswith("benchmark 000300 provider attempt ")
    ]
    structured_attempt_warnings = [
        warning
        for warning in result.structured_warnings
        if warning["source"] == "benchmark_provider_chain"
        and warning["code"] == "benchmark_provider_fallback_used"
        and warning["message"].startswith("benchmark 000300 provider attempt ")
    ]

    assert result.run_status == "success"
    assert len(raw_attempt_warnings) == len(failures)
    assert len(structured_attempt_warnings) == len(failures)
    for index, (provider, raw, structured) in enumerate(
        zip(failures, raw_attempt_warnings, structured_attempt_warnings)
    ):
        expected = (
            "benchmark 000300 provider attempt "
            f"{provider.provider_name}/{provider.endpoint} failed: "
            f"{provider.expected_reason_code}"
        )
        assert raw == expected
        assert structured["message"] == expected
        assert structured["evidence"]["provider"] == provider.provider_name
        assert structured["evidence"]["reason_code"] == provider.expected_reason_code
        assert result.warnings.index(raw) < len(result.warnings)
        assert failures[index].calls == ["000300"]

    assert success.calls == ["000300"]
    diagnostics = json.loads(
        result.artifacts.files["benchmark_diagnostics.json"].read_text(encoding="utf-8")
    )["benchmarks"]["000300"]
    assert diagnostics["attempts_total"] == 36
    assert diagnostics["attempts_truncated"] is True
    assert diagnostics["omitted_count"] == 4
    assert len(diagnostics["attempts"]) == 32
    assert [attempt["provider"] for attempt in diagnostics["attempts"]] == [
        provider.provider_name for provider in failures[:32]
    ]
    assert failures[32].provider_name not in {
        attempt["provider"] for attempt in diagnostics["attempts"]
    }
    assert success.provider_name not in {attempt["provider"] for attempt in diagnostics["attempts"]}
    assert "attempt_count" not in diagnostics
    assert "omitted_attempt_count" not in diagnostics


def test_diagnostics_write_failure_does_not_publish_partial_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_write_json = artifacts_module._write_json

    def fail_diagnostics(path: Path, value: object) -> None:
        if path.name == "benchmark_diagnostics.json":
            raise OSError("simulated diagnostics write failure")
        original_write_json(path, value)

    monkeypatch.setattr(artifacts_module, "_write_json", fail_diagnostics)
    output = tmp_path / "runs"
    run_id = "atomic_failure_run"

    with pytest.raises(OSError, match="simulated diagnostics write failure"):
        write_research_artifacts(
            output,
            config={},
            run_manifest={},
            metrics={},
            benchmark_metrics={},
            benchmark_diagnostics={"schema_version": 1, "benchmarks": {}},
            equity_curve=pd.Series(dtype=float),
            benchmark_curve=pd.DataFrame(),
            holdings=pd.DataFrame(),
            trades=pd.DataFrame(),
            factor_snapshots=pd.DataFrame(),
            warnings=[],
            run_id=run_id,
        )

    assert not (output / run_id).exists()
    assert list(output.glob(f".{run_id}.*.staging")) == []


def test_execution_date_close_is_not_passed_to_price_factors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    observed: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    original = real_pipeline_module.overbought_oversold_factor

    def recording_factor(symbol, price_data, as_of_date):
        observed.append(
            (
                pd.Timestamp(as_of_date),
                pd.to_datetime(price_data["date"]).max(),
            )
        )
        return original(symbol, price_data, as_of_date)

    monkeypatch.setattr(
        real_pipeline_module,
        "overbought_oversold_factor",
        recording_factor,
    )
    result, *_ = _run_offline(tmp_path, "yearly")

    assert observed
    assert all(max_price_date <= signal_date for signal_date, max_price_date in observed)
    execution_by_signal = {
        pd.Timestamp(row.signal_date): pd.Timestamp(row.execution_date)
        for row in result.factor_snapshots.itertuples()
    }
    assert all(signal_date < execution_by_signal[signal_date] for signal_date, _ in observed)


def test_signal_date_uses_prior_aligned_trading_bar_not_calendar_day() -> None:
    aligned_dates = pd.DatetimeIndex(pd.to_datetime(["2009-12-31", "2010-01-04", "2010-01-05"]))

    signal_date = real_pipeline_module._signal_date_before(
        aligned_dates,
        pd.Timestamp("2010-01-04"),
    )

    assert signal_date == pd.Timestamp("2009-12-31")


def test_aligned_dates_require_real_bars_for_every_loaded_symbol() -> None:
    first = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"]),
            "close": [10.0, 10.1, 10.2],
        }
    )
    second = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-04"]),
            "close": [20.0, 20.2],
        }
    )

    aligned = real_pipeline_module._aligned_trading_dates(
        {"600001": first, "000002": second},
        "2024-01-02",
        "2024-01-04",
    )

    assert aligned.tolist() == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-04"),
    ]


def test_execution_without_prior_signal_date_remains_cash(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        "yearly",
        {"price_calendar_days": 0, "fundamental_years": 5},
    )
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    raw["end_date"] = "2010-12-31"
    config_path.write_text(
        yaml.safe_dump(raw, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    result = run_real_data_research(
        config_path,
        price_provider=MockPriceProvider(),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(raw["candidate_symbols"]),
        macro_provider=MockMacroProvider(),
        index_provider=MockIndexProvider(),
        git_commit="test-commit",
    )

    first_weights = next(iter(result.target_weights_by_date.values()))
    assert sum(first_weights.values()) == 0.0
    assert result.factor_snapshots["signal_date"].isna().all()
    assert not result.factor_snapshots["selected"].any()
    assert any("no aligned signal date" in warning for warning in result.warnings)
    assert result.equity_curve.nunique() == 1


def test_price_cache_key_uses_fetch_window_and_incomplete_cache_is_preserved(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path, "yearly")
    config = load_real_research_config(config_path)
    cache = ParquetCache(config.cache_directory / "prices")
    incomplete = _price_frame("600001")
    incomplete = incomplete[incomplete["date"] >= pd.Timestamp(config.start_date)].reset_index(
        drop=True
    )
    cache_path = cache.write(
        incomplete,
        "600001",
        config.price_fetch_start_date,
        config.end_date,
        config.price_adjust,
    )
    original_bytes = cache_path.read_bytes()
    price_provider = MockPriceProvider()

    result = run_real_data_research(
        config_path,
        price_provider=price_provider,
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(config.candidate_symbols),
        macro_provider=MockMacroProvider(),
        index_provider=MockIndexProvider(),
        git_commit="test-commit",
    )

    assert f"_{pd.Timestamp(config.price_fetch_start_date):%Y%m%d}_" in cache_path.name
    assert "600001" in price_provider.calls
    assert cache_path.read_bytes() == original_bytes
    assert any("price cache does not cover fetch window" in warning for warning in result.warnings)


def test_price_cache_warning_is_discarded_when_provider_later_fails(
    tmp_path: Path,
) -> None:
    config_path = _write_partial_config(tmp_path)
    config = load_real_research_config(config_path)
    cache = ParquetCache(config.cache_directory / "prices")
    incomplete = _price_frame("600003")
    incomplete = incomplete[incomplete["date"] >= pd.Timestamp(config.start_date)].reset_index(
        drop=True
    )
    cache.write(
        incomplete,
        "600003",
        config.price_fetch_start_date,
        config.end_date,
        config.price_adjust,
    )

    result = run_real_data_research(
        config_path,
        price_provider=FailingPriceProvider("600003"),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=MockUniverseProvider(config.candidate_symbols),
        macro_provider=MockMacroProvider(),
        index_provider=MockIndexProvider(),
        git_commit="test-commit",
    )

    assert not any(
        warning.startswith("600003 price cache does not cover fetch window")
        for warning in result.warnings
    )
    assert "600003 price provider failed: RuntimeError [details redacted]" in result.warnings
    assert result.coverage_summary["warning_count"] == len(result.warnings)


def test_fundamental_cache_warning_is_discarded_when_provider_later_fails(
    tmp_path: Path,
) -> None:
    config_path = _write_partial_config(tmp_path)
    config = load_real_research_config(config_path)
    cache_directory = config.cache_directory / "fundamentals"
    cache_directory.mkdir(parents=True, exist_ok=True)
    cache_path = cache_directory / (
        f"600003_{pd.Timestamp(config.fundamental_fetch_start_date):%Y%m%d}_"
        f"{pd.Timestamp(config.end_date):%Y%m%d}.parquet"
    )
    cache_path.write_bytes(b"not parquet")

    result = run_real_data_research(
        config_path,
        price_provider=MockPriceProvider(),
        fundamental_provider=FailingFundamentalProvider("600003"),
        universe_provider=MockUniverseProvider(config.candidate_symbols),
        macro_provider=MockMacroProvider(),
        index_provider=MockIndexProvider(),
        git_commit="test-commit",
    )

    assert not any(
        warning.startswith("600003 fundamental cache unreadable") for warning in result.warnings
    )
    assert "600003 fundamental provider failed: RuntimeError [details redacted]" in result.warnings
    assert result.coverage_summary["warning_count"] == len(result.warnings)


def test_partial_coverage_sets_status_and_structures_benchmark_failure(
    tmp_path: Path,
) -> None:
    result = run_real_data_research(
        _write_partial_config(tmp_path),
        price_provider=FailingPriceProvider("600003"),
        fundamental_provider=MockFundamentalProvider(),
        universe_provider=UnverifiedUniverseProvider(["600001", "000002", "600003"]),
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
    assert all(count < 3 for count in coverage["holdings_count_by_rebalance"].values())
    assert coverage["warning_count"] == len(result.warnings)

    manifest = json.loads(result.artifacts.files["run_manifest.json"].read_text(encoding="utf-8"))
    assert manifest["run_status"] == "partial_success"
    assert manifest["coverage_summary"] == coverage

    benchmark_payload = json.loads(
        result.artifacts.files["benchmark_metrics.json"].read_text(encoding="utf-8")
    )
    benchmark_entry = benchmark_payload["000300"]
    assert benchmark_entry["status"] == "unavailable"
    assert benchmark_entry["symbol"] == "000300"
    assert benchmark_entry["reason"] == "RuntimeError [details redacted]"
    assert benchmark_entry["metrics"] == {}
    assert benchmark_entry["reason_code"] == "provider_exception"
    assert benchmark_entry["diagnostics_available"] is True

    structured = result.structured_warnings
    assert [item["message"] for item in structured] == result.warnings
    scopes = {item["scope"] for item in structured}
    assert {
        "price_provider",
        "benchmark",
        "fundamental",
        "macro",
        "universe",
        "factor",
        "portfolio",
    } <= scopes
    benchmark_warning = next(
        item for item in structured if item["code"] == "benchmark_data_unavailable"
    )
    assert benchmark_warning["affected_symbols"] == ["000300"]
    assert benchmark_warning["artifact_refs"] == ["benchmark_diagnostics.json#/benchmarks/000300"]
    assert benchmark_warning["evidence"]["canonical_symbol"] == "000300"
    assert result.run_status == "partial_success"


def test_sensitive_provider_failures_are_safe_in_every_new_json_artifact(
    tmp_path: Path,
) -> None:
    config_path = _write_partial_config(tmp_path)
    config = load_real_research_config(config_path)
    result = run_real_data_research(
        config_path,
        price_provider=SensitiveFailingPriceProvider("600003"),
        fundamental_provider=SensitiveFailingFundamentalProvider("000002"),
        universe_provider=UnverifiedUniverseProvider(config.candidate_symbols),
        macro_provider=SensitiveFailingMacroProvider(),
        index_provider=SensitiveFailingIndexProvider(),
        git_commit="test-commit",
    )

    assert result.run_status == "partial_success"
    assert result.coverage_summary["warning_count"] == len(result.warnings)
    assert [item["message"] for item in result.structured_warnings] == result.warnings
    warning_summary = aggregate_warnings({"warnings": result.warnings}, raw_limit=1_000)
    assert warning_summary["total"] == len(result.warnings)
    assert warning_summary["categories"]["price_provider"] >= 1
    assert warning_summary["categories"]["fundamental_data"] >= 1
    assert warning_summary["categories"]["macro_data"] >= 1
    assert warning_summary["categories"]["benchmark"] >= 1

    json_artifacts = [
        "config.json",
        "run_manifest.json",
        "metrics.json",
        "benchmark_metrics.json",
        "benchmark_diagnostics.json",
        "warnings.json",
    ]
    forbidden_fragments = (
        "C:\\Users\\researcher",
        "\\\\server\\share",
        "/tmp/provider-response.json",
        "key-secret",
        "access-secret",
        "client-secret",
        "auth-secret",
        "cookie-secret",
        "Traceback",
        "0x7FFABCDEF123",
    )
    for artifact_name in json_artifacts:
        payload = json.loads(result.artifacts.files[artifact_name].read_text(encoding="utf-8"))
        serialized = json.dumps(payload, ensure_ascii=False)
        assert all(fragment not in serialized for fragment in forbidden_fragments)
        assert not any(contains_absolute_path(value) for value in _nested_strings(payload))

    metadata_files = list(config.cache_directory.rglob("*.meta.json"))
    assert metadata_files
    for metadata_path in metadata_files:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert not any(contains_absolute_path(value) for value in _nested_strings(payload))


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


def test_factor_coverage_availability_uses_scored_raw_inputs() -> None:
    one_point = _price_frame("600001").iloc[[0]].copy()
    score = real_pipeline_module.low_vol_factor(
        "600001",
        one_point,
        "2010-01-04",
    )

    assert score.raw_values["annualized_volatility"] is None
    assert score.raw_values["max_drawdown"] is None
    assert not real_pipeline_module._factor_score_available(score)


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
    assert any("excluded unavailable factors" in warning for warning in result.warnings)


def test_import_does_not_initialize_network_providers(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("provider initialized during module import")

    monkeypatch.setattr(AShareDataProvider, "__init__", fail)
    monkeypatch.setattr(AShareFundamentalProvider, "__init__", fail)
    monkeypatch.setattr(AShareIndexProvider, "__init__", fail)

    module = importlib.import_module("autowealth.research.real_pipeline")
    importlib.reload(module)
