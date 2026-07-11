"""Tests for safe, read-only research artifact access."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

import autowealth.research.run_store as run_store_module
from autowealth.research.run_store import (
    InvalidRunIdError,
    ResearchArtifactDecodeError,
    ResearchArtifactNotFoundError,
    ResearchRunNotFoundError,
    ResearchRunStore,
    aggregate_warnings,
)


RUN_OLD = "20250101T000000Z_aaaaaaaaaa"
RUN_NEW = "20250201T000000Z_bbbbbbbbbb"


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    pytest.importorskip("pyarrow")
    root = tmp_path / "research_runs"
    _write_run(root, RUN_OLD, "2025-01-01T00:00:00+00:00")
    _write_run(
        root,
        RUN_NEW,
        "2025-02-01T00:00:00+00:00",
        benchmark_unavailable=True,
    )
    return root


def test_lists_runs_in_descending_time_order(runs_root: Path) -> None:
    store = ResearchRunStore(runs_root)

    runs = store.list_runs()

    assert [run["run_id"] for run in runs] == [RUN_NEW, RUN_OLD]
    assert store.list_runs(limit=1)[0]["run_id"] == RUN_NEW


def test_gets_latest_and_specific_run(runs_root: Path) -> None:
    store = ResearchRunStore(runs_root)

    latest = store.get_latest_run()
    specific = store.get_run(RUN_OLD)

    assert latest["summary"]["run_id"] == RUN_NEW
    assert specific["manifest"]["experiment_name"] == "fixture research"
    assert specific["metrics"]["annualized_return"] == 0.12


@pytest.mark.parametrize("run_id", ["../outside", "..", "C:/outside", "a/b"])
def test_rejects_path_traversal(runs_root: Path, run_id: str) -> None:
    with pytest.raises(InvalidRunIdError):
        ResearchRunStore(runs_root).get_run(run_id)


def test_reports_corrupt_json(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "run_manifest.json").write_text(
        "{not-json", encoding="utf-8"
    )

    with pytest.raises(ResearchArtifactDecodeError, match="invalid JSON"):
        ResearchRunStore(runs_root).read_manifest(RUN_OLD)


def test_reports_missing_parquet(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "equity_curve.parquet").unlink()

    with pytest.raises(ResearchArtifactNotFoundError, match="equity_curve"):
        ResearchRunStore(runs_root).read_equity_curve(RUN_OLD)


def test_reports_corrupt_parquet(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "equity_curve.parquet").write_text(
        "not parquet", encoding="utf-8"
    )

    with pytest.raises(ResearchArtifactDecodeError, match="invalid parquet"):
        ResearchRunStore(runs_root).read_equity_curve(RUN_OLD)


def test_preserves_structured_benchmark_unavailable(runs_root: Path) -> None:
    summary = ResearchRunStore(runs_root).get_summary(RUN_NEW)
    benchmark = ResearchRunStore(runs_root).read_benchmark_metrics(RUN_NEW)

    assert summary["benchmark_status"] == "unavailable"
    assert benchmark["000300"]["status"] == "unavailable"
    assert benchmark["000300"]["metrics"] == {}


def test_aggregates_warning_categories_without_changing_source() -> None:
    warnings = {
        "warnings": [
            "600519 price provider failed: endpoint unavailable",
            "600519 price quality warning: date has gaps",
            "fundamental source is not verified point-in-time",
            "macro data is empty; neutral multiplier used",
            "fixed universe may contain survivorship bias",
            "selected holdings below min_holdings",
            "factor warning: missing pe",
            "benchmark 000300 unavailable",
        ]
    }

    summary = aggregate_warnings(warnings, sample_limit=1, raw_limit=2)

    assert summary["total"] == 8
    assert summary["categories"]["price_provider"] == 1
    assert summary["categories"]["price_quality"] == 1
    assert summary["categories"]["point_in_time"] == 1
    assert summary["categories"]["macro_data"] == 1
    assert summary["categories"]["universe_bias"] == 1
    assert summary["categories"]["portfolio_constraints"] == 1
    assert summary["categories"]["factor_coverage"] == 1
    assert summary["categories"]["benchmark"] == 1
    assert summary["raw_returned"] == 2
    assert summary["raw_truncated"] is True
    assert warnings["warnings"][0].startswith("600519")


def test_empty_runs_directory_returns_empty_and_latest_is_clear(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    store = ResearchRunStore(root)

    assert store.list_runs() == []
    with pytest.raises(ResearchRunNotFoundError, match="no research runs"):
        store.get_latest_run()


def test_module_import_does_not_scan_disk(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("run store scanned disk during import")

    monkeypatch.setattr(Path, "iterdir", fail)
    importlib.reload(run_store_module)


def _write_run(
    root: Path,
    run_id: str,
    run_time: str,
    *,
    benchmark_unavailable: bool = False,
) -> None:
    run = root / run_id
    run.mkdir(parents=True)
    benchmark_status = "unavailable" if benchmark_unavailable else "available"
    manifest = {
        "run_id": run_id,
        "run_time": run_time,
        "experiment_name": "fixture research",
        "run_status": "partial_success" if benchmark_unavailable else "success",
        "data_range": {"start_date": "2024-01-01", "end_date": "2025-12-31"},
        "config_summary": {"portfolio_constraints": {"min_holdings": 2}},
        "coverage_summary": {
            "benchmark_status": benchmark_status,
            "warning_count": 2,
            "price_coverage_ratio": 0.8,
            "macro_observation_count": 0,
            "holdings_count_by_rebalance": {"2025-01-02": 2},
            "factor_coverage_by_rebalance": {},
            "factor_coverage_overall": {
                "value": {
                    "available_count": 4,
                    "missing_count": 1,
                    "coverage_ratio": 0.8,
                }
            },
        },
    }
    metrics = {
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
        "annualized_return": 0.12,
        "total_return": 0.25,
        "max_drawdown": -0.18,
        "sharpe_ratio": 0.9,
        "calmar_ratio": 0.66,
        "turnover": 0.4,
        "annual_returns": {"2024": 0.1, "2025": 0.13},
        "monthly_returns": {"2025-01": 0.01},
    }
    benchmark = (
        {
            "000300": {
                "status": "unavailable",
                "symbol": "000300",
                "reason": "fixture unavailable",
                "metrics": {},
            }
        }
        if benchmark_unavailable
        else {"000300": {"annualized_return": 0.08, "max_drawdown": -0.2}}
    )
    warnings = {
        "warnings": [
            "macro data is empty; neutral multiplier used",
            "benchmark 000300 unavailable" if benchmark_unavailable else "system note",
        ]
    }
    _write_json(run / "run_manifest.json", manifest)
    _write_json(run / "metrics.json", metrics)
    _write_json(run / "benchmark_metrics.json", benchmark)
    _write_json(run / "warnings.json", warnings)

    dates = pd.to_datetime(["2024-01-02", "2024-12-31", "2025-12-31"])
    pd.DataFrame({"date": dates, "equity": [1_000_000, 1_100_000, 1_250_000]}).to_parquet(
        run / "equity_curve.parquet", index=False
    )
    benchmark_frame = pd.DataFrame({"date": dates})
    if not benchmark_unavailable:
        benchmark_frame["000300"] = [1_000_000, 1_050_000, 1_160_000]
    benchmark_frame.to_parquet(run / "benchmark_curve.parquet", index=False)
    pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-02")],
            "equity": [1_100_000],
            "cash": [220_000],
            "cash_weight": [0.2],
            "600001_shares": [1000.0],
            "600001_weight": [0.4],
            "000002_shares": [2000.0],
            "000002_weight": [0.4],
        }
    ).to_parquet(run / "holdings.parquet", index=False)
    pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-02")],
            "symbol": ["600001"],
            "side": ["buy"],
            "shares": [1000.0],
            "price": [10.0],
            "trade_value": [10_000.0],
            "cost": [5.0],
        }
    ).to_parquet(run / "trades.parquet", index=False)
    pd.DataFrame(
        {
            "rebalance_date": [pd.Timestamp("2025-01-02")],
            "symbol": ["600001"],
            "composite_score": [70.0],
            "composite_weights": ['{"value": 1.0}'],
            "value_available": [True],
            "value_score": [70.0],
            "warnings": [""],
        }
    ).to_parquet(run / "factor_snapshots.parquet", index=False)


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
