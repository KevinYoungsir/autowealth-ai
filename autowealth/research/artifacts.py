"""Durable artifacts for reproducible real-data research runs."""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Union

import pandas as pd

PathLike = Union[str, Path]

REQUIRED_ARTIFACT_FILES = {
    "config.json",
    "run_manifest.json",
    "metrics.json",
    "benchmark_metrics.json",
    "equity_curve.parquet",
    "benchmark_curve.parquet",
    "holdings.parquet",
    "trades.parquet",
    "factor_snapshots.parquet",
    "warnings.json",
}
OPTIONAL_ARTIFACT_FILES = {"benchmark_diagnostics.json"}


@dataclass(frozen=True)
class ResearchArtifactSet:
    run_id: str
    run_directory: Path
    files: dict[str, Path]


def create_run_id(run_time: Optional[datetime] = None) -> str:
    """Create a sortable, collision-resistant research run identifier."""
    timestamp = (run_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:10]}"


def current_git_commit(repository_root: Optional[PathLike] = None) -> str:
    """Return the current Git commit, or ``unknown`` outside a Git checkout."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(repository_root) if repository_root else None,
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def write_research_artifacts(
    output_directory: PathLike,
    *,
    config: Mapping[str, Any],
    run_manifest: Mapping[str, Any],
    metrics: Mapping[str, Any],
    benchmark_metrics: Mapping[str, Any],
    equity_curve: pd.Series,
    benchmark_curve: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    factor_snapshots: pd.DataFrame,
    warnings: list[str],
    benchmark_diagnostics: Optional[Mapping[str, Any]] = None,
    run_id: Optional[str] = None,
    run_time: Optional[datetime] = None,
) -> ResearchArtifactSet:
    """Write the complete artifact contract for one research run."""
    created_at = (run_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    resolved_run_id = run_id or create_run_id(created_at)
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)
    final_run_directory = output_path / resolved_run_id
    if final_run_directory.exists():
        raise FileExistsError(f"research run already exists: {resolved_run_id}")
    run_directory = output_path / f".{resolved_run_id}.{uuid.uuid4().hex}.staging"
    run_directory.mkdir(parents=False, exist_ok=False)

    manifest = dict(run_manifest)
    manifest.setdefault("run_id", resolved_run_id)
    manifest.setdefault("run_time", created_at.isoformat())

    files = {
        "config.json": run_directory / "config.json",
        "run_manifest.json": run_directory / "run_manifest.json",
        "metrics.json": run_directory / "metrics.json",
        "benchmark_metrics.json": run_directory / "benchmark_metrics.json",
        "equity_curve.parquet": run_directory / "equity_curve.parquet",
        "benchmark_curve.parquet": run_directory / "benchmark_curve.parquet",
        "holdings.parquet": run_directory / "holdings.parquet",
        "trades.parquet": run_directory / "trades.parquet",
        "factor_snapshots.parquet": run_directory / "factor_snapshots.parquet",
        "warnings.json": run_directory / "warnings.json",
    }
    if benchmark_diagnostics is not None:
        files["benchmark_diagnostics.json"] = run_directory / "benchmark_diagnostics.json"

    try:
        _write_artifact_payloads(
            files,
            config=config,
            manifest=manifest,
            metrics=metrics,
            benchmark_metrics=benchmark_metrics,
            benchmark_diagnostics=benchmark_diagnostics,
            equity_curve=equity_curve,
            benchmark_curve=benchmark_curve,
            holdings=holdings,
            trades=trades,
            factor_snapshots=factor_snapshots,
            warnings=warnings,
        )
    except Exception:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise

    expected = set(REQUIRED_ARTIFACT_FILES)
    if benchmark_diagnostics is not None:
        expected.update(OPTIONAL_ARTIFACT_FILES)
    missing = expected - {path.name for path in run_directory.iterdir()}
    if missing:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise RuntimeError(f"research artifact write incomplete: {sorted(missing)}")
    try:
        run_directory.replace(final_run_directory)
    except Exception:
        shutil.rmtree(run_directory, ignore_errors=True)
        raise
    published_files = {name: final_run_directory / path.name for name, path in files.items()}
    return ResearchArtifactSet(
        run_id=resolved_run_id,
        run_directory=final_run_directory,
        files=published_files,
    )


def _write_artifact_payloads(
    files: Mapping[str, Path],
    *,
    config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    metrics: Mapping[str, Any],
    benchmark_metrics: Mapping[str, Any],
    benchmark_diagnostics: Optional[Mapping[str, Any]],
    equity_curve: pd.Series,
    benchmark_curve: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    factor_snapshots: pd.DataFrame,
    warnings: list[str],
) -> None:
    _write_json(files["config.json"], config)
    _write_json(files["run_manifest.json"], manifest)
    _write_json(files["metrics.json"], metrics)
    _write_json(files["benchmark_metrics.json"], benchmark_metrics)
    _write_json(files["warnings.json"], {"warnings": warnings})
    if benchmark_diagnostics is not None:
        _write_json(
            files["benchmark_diagnostics.json"],
            benchmark_diagnostics,
        )
    _equity_frame(equity_curve).to_parquet(
        files["equity_curve.parquet"],
        index=False,
    )
    _benchmark_frame(benchmark_curve).to_parquet(
        files["benchmark_curve.parquet"],
        index=False,
    )
    _nonempty_schema(
        holdings,
        ["date", "equity", "cash", "cash_weight"],
    ).to_parquet(files["holdings.parquet"], index=False)
    _nonempty_schema(
        trades,
        ["date", "symbol", "side", "shares", "price", "trade_value", "cost"],
    ).to_parquet(files["trades.parquet"], index=False)
    _nonempty_schema(
        factor_snapshots,
        [
            "rebalance_date",
            "signal_date",
            "execution_date",
            "symbol",
            "composite_score",
            "fundamental_report_date",
            "fundamental_available_date",
            "macro_available_date",
            "warnings",
        ],
    ).to_parquet(files["factor_snapshots.parquet"], index=False)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(_json_ready(value), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def _json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _json_ready(value.item())
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is pd.NA or (
        value is not None and not isinstance(value, (str, bytes)) and _is_na(value)
    ):
        return None
    return value


def _is_na(value: Any) -> bool:
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, bool) else False


def _equity_frame(equity_curve: pd.Series) -> pd.DataFrame:
    series = pd.Series(equity_curve, name="equity")
    frame = series.rename_axis("date").reset_index()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _benchmark_frame(benchmark_curve: pd.DataFrame) -> pd.DataFrame:
    frame = pd.DataFrame(benchmark_curve).copy()
    if frame.index.name or isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.rename_axis("date").reset_index()
    if "date" not in frame.columns:
        frame.insert(0, "date", pd.Series(dtype="datetime64[ns]"))
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _nonempty_schema(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy()
    for column in columns:
        if column not in frame.columns:
            frame[column] = pd.Series(dtype="object")
    return frame
