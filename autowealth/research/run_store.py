"""Read-only access to persisted real-research run artifacts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd

from autowealth.research.run_store_errors import (
    InvalidRunIdError,
    ResearchArtifactDecodeError,
    ResearchArtifactNotFoundError,
    ResearchRunNotFoundError,
    ResearchRunStoreError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESEARCH_RUNS_DIRECTORY = Path("data/research_runs")
SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

JSON_ARTIFACTS = {
    "manifest": "run_manifest.json",
    "metrics": "metrics.json",
    "benchmark_metrics": "benchmark_metrics.json",
    "benchmark_diagnostics": "benchmark_diagnostics.json",
    "warnings": "warnings.json",
}
PARQUET_ARTIFACTS = {
    "equity_curve": "equity_curve.parquet",
    "benchmark_curve": "benchmark_curve.parquet",
    "holdings": "holdings.parquet",
    "trades": "trades.parquet",
    "factor_snapshots": "factor_snapshots.parquet",
}

WARNING_CATEGORIES = (
    "price_provider",
    "price_quality",
    "fundamental_data",
    "point_in_time",
    "macro_data",
    "universe_bias",
    "portfolio_constraints",
    "factor_coverage",
    "benchmark",
    "system",
)


class ResearchRunStore:
    """Read artifacts below one configured research-runs root directory."""

    def __init__(self, root_directory: Optional[str | Path] = None):
        configured = root_directory
        if configured is None:
            configured = os.getenv(
                "RESEARCH_RUNS_DIRECTORY",
                str(DEFAULT_RESEARCH_RUNS_DIRECTORY),
            )
        root = Path(configured)
        if not root.is_absolute():
            root = PROJECT_ROOT / root
        self._root = root.resolve(strict=False)

    @property
    def root_directory(self) -> Path:
        return self._root

    def ensure_directory(self) -> bool:
        """Create the configured root when possible without exposing its path."""
        if self._root.exists():
            if not self._root.is_dir():
                raise ResearchRunStoreError("configured research runs location is not a directory")
            return True
        try:
            self._root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return self._root.is_dir()

    def has_runs(self) -> bool:
        """Return whether at least one safely named run directory is present."""
        if not self.ensure_directory():
            return False
        return any(
            candidate.is_dir()
            and not candidate.is_symlink()
            and SAFE_RUN_ID.fullmatch(candidate.name)
            for candidate in self._root.iterdir()
        )

    def list_runs(self, limit: Optional[int] = None) -> list[dict[str, Any]]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        if not self.ensure_directory():
            return []

        summaries = []
        for candidate in self._root.iterdir():
            if (
                not candidate.is_dir()
                or candidate.is_symlink()
                or not SAFE_RUN_ID.fullmatch(candidate.name)
            ):
                continue
            summaries.append(self.get_summary(candidate.name))
        summaries.sort(key=_summary_sort_key, reverse=True)
        return summaries[:limit] if limit is not None else summaries

    def get_latest_run(self) -> dict[str, Any]:
        summaries = self.list_runs(limit=1)
        if not summaries:
            raise ResearchRunNotFoundError("no research runs are available")
        return self.get_run(str(summaries[0]["run_id"]))

    def get_run(self, run_id: str) -> dict[str, Any]:
        summary = self.get_summary(run_id)
        return {
            "summary": summary,
            "manifest": self.read_manifest(run_id),
            "metrics": self.read_metrics(run_id),
            "benchmark_metrics": self.read_benchmark_metrics(run_id),
            "benchmark_diagnostics": self.read_benchmark_diagnostics(run_id),
            "warnings": self.read_warnings(run_id),
        }

    def get_summary(self, run_id: str) -> dict[str, Any]:
        manifest = self.read_manifest(run_id)
        metrics = self.read_metrics(run_id)
        benchmarks = self.read_benchmark_metrics(run_id)
        warnings = self.read_warnings(run_id)
        coverage = _mapping(manifest.get("coverage_summary"))
        data_range = _mapping(manifest.get("data_range"))
        return {
            "run_id": run_id,
            "run_time": str(manifest.get("run_time") or ""),
            "experiment_name": str(manifest.get("experiment_name") or run_id),
            "run_status": str(manifest.get("run_status") or "partial_success"),
            "start_date": str(data_range.get("start_date") or metrics.get("start_date") or ""),
            "end_date": str(data_range.get("end_date") or metrics.get("end_date") or ""),
            "annualized_return": _optional_float(metrics.get("annualized_return")),
            "total_return": _optional_float(metrics.get("total_return")),
            "max_drawdown": _optional_float(metrics.get("max_drawdown")),
            "sharpe_ratio": _optional_float(metrics.get("sharpe_ratio")),
            "benchmark_status": str(
                coverage.get("benchmark_status") or _benchmark_status(benchmarks)
            ),
            "warning_count": int(coverage.get("warning_count") or len(_warning_values(warnings))),
            "price_coverage_ratio": _optional_float(coverage.get("price_coverage_ratio")),
            "factor_coverage_overall": _mapping(coverage.get("factor_coverage_overall")),
        }

    def read_manifest(self, run_id: str) -> dict[str, Any]:
        return self._read_json(run_id, JSON_ARTIFACTS["manifest"])

    def read_metrics(self, run_id: str) -> dict[str, Any]:
        return self._read_json(run_id, JSON_ARTIFACTS["metrics"])

    def read_benchmark_metrics(self, run_id: str) -> dict[str, Any]:
        return self._read_json(run_id, JSON_ARTIFACTS["benchmark_metrics"])

    def read_benchmark_diagnostics(self, run_id: str) -> dict[str, Any]:
        try:
            return self._read_json(
                run_id,
                JSON_ARTIFACTS["benchmark_diagnostics"],
            )
        except ResearchArtifactNotFoundError:
            return {}

    def read_warnings(self, run_id: str) -> dict[str, Any]:
        return self._read_json(run_id, JSON_ARTIFACTS["warnings"])

    def read_equity_curve(self, run_id: str) -> pd.DataFrame:
        return self._read_parquet(run_id, PARQUET_ARTIFACTS["equity_curve"])

    def read_benchmark_curve(self, run_id: str) -> pd.DataFrame:
        return self._read_parquet(run_id, PARQUET_ARTIFACTS["benchmark_curve"])

    def read_holdings(self, run_id: str) -> pd.DataFrame:
        return self._read_parquet(run_id, PARQUET_ARTIFACTS["holdings"])

    def read_trades(self, run_id: str) -> pd.DataFrame:
        return self._read_parquet(run_id, PARQUET_ARTIFACTS["trades"])

    def read_factor_snapshots(self, run_id: str) -> pd.DataFrame:
        return self._read_parquet(run_id, PARQUET_ARTIFACTS["factor_snapshots"])

    def _read_json(self, run_id: str, filename: str) -> dict[str, Any]:
        path = self._artifact_path(run_id, filename)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} contains invalid JSON"
            ) from exc
        except OSError as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} could not be read"
            ) from exc
        if not isinstance(value, dict):
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} must contain a JSON object"
            )
        return value

    def _read_parquet(self, run_id: str, filename: str) -> pd.DataFrame:
        path = self._artifact_path(run_id, filename)
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} contains invalid parquet data"
            ) from exc

    def _artifact_path(self, run_id: str, filename: str) -> Path:
        run_directory = self._run_directory(run_id)
        candidate = (run_directory / filename).resolve(strict=False)
        if candidate.parent != run_directory:
            raise ResearchRunStoreError("artifact path escaped the configured run")
        if not candidate.exists() or not candidate.is_file():
            raise ResearchArtifactNotFoundError(f"{filename} is missing for run {run_id}")
        return candidate

    def _run_directory(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not SAFE_RUN_ID.fullmatch(run_id):
            raise InvalidRunIdError("run_id has an invalid format")
        candidate = (self._root / run_id).resolve(strict=False)
        if candidate.parent != self._root:
            raise InvalidRunIdError("run_id escapes the configured runs directory")
        if not candidate.exists() or not candidate.is_dir():
            raise ResearchRunNotFoundError(f"research run {run_id} was not found")
        return candidate


def aggregate_warnings(
    payload: Mapping[str, Any],
    *,
    sample_limit: int = 3,
    raw_limit: int = 20,
) -> dict[str, Any]:
    """Group warnings without changing the persisted warnings artifact."""
    if sample_limit < 0 or raw_limit < 0:
        raise ValueError("warning limits must be non-negative")
    warnings = _warning_values(payload)
    categories = {category: 0 for category in WARNING_CATEGORIES}
    samples: dict[str, list[str]] = {}
    for warning in warnings:
        category = categorize_warning(warning)
        categories[category] += 1
        category_samples = samples.setdefault(category, [])
        if len(category_samples) < sample_limit:
            category_samples.append(warning)
    return {
        "total": len(warnings),
        "categories": categories,
        "samples": samples,
        "raw_warnings": warnings[:raw_limit],
        "raw_returned": min(len(warnings), raw_limit),
        "raw_truncated": len(warnings) > raw_limit,
    }


def categorize_warning(warning: str) -> str:
    text = str(warning).lower()
    if "benchmark" in text:
        return "benchmark"
    if "price provider" in text or "price endpoint" in text:
        return "price_provider"
    if any(
        token in text
        for token in (
            "price quality",
            "zero-volume",
            "no bar on rebalance",
            "suspended",
            "untradeable",
            "date has gaps",
        )
    ):
        return "price_quality"
    if "macro" in text or "neutral multiplier" in text:
        return "macro_data"
    if "universe" in text or "survivorship" in text:
        return "universe_bias"
    if any(
        token in text
        for token in (
            "min_holdings",
            "max_position_weight",
            "max_industry_weight",
            "cash_weight",
            "industry classification",
            "unallocated equity",
            "target holdings",
        )
    ):
        return "portfolio_constraints"
    if any(
        token in text
        for token in (
            "point-in-time",
            "available_date",
            "published after",
            "future-report",
        )
    ):
        return "point_in_time"
    if "fundamental" in text or any(
        token in text for token in ("historical pe", "historical pb", "dividend_yield")
    ):
        return "fundamental_data"
    if any(
        token in text
        for token in (
            "factor warning",
            "excluded unavailable factors",
            "missing pe",
            "missing pb",
            "missing roe",
            "beta scoring",
            "factor coverage",
        )
    ):
        return "factor_coverage"
    return "system"


def _warning_values(payload: Mapping[str, Any]) -> list[str]:
    values = payload.get("warnings", [])
    if not isinstance(values, list):
        raise ResearchArtifactDecodeError("warnings.json must contain a warnings list")
    return [str(value) for value in values]


def _benchmark_status(benchmarks: Mapping[str, Any]) -> str:
    if not benchmarks:
        return "unavailable"
    statuses = [
        (
            "unavailable"
            if isinstance(value, Mapping) and value.get("status") == "unavailable"
            else "available"
        )
        for value in benchmarks.values()
    ]
    if all(status == "available" for status in statuses):
        return "available"
    if all(status == "unavailable" for status in statuses):
        return "unavailable"
    return "partial"


def _summary_sort_key(summary: Mapping[str, Any]) -> tuple[str, str]:
    return str(summary.get("run_time") or ""), str(summary.get("run_id") or "")


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_float(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed
