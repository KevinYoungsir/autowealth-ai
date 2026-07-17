"""Deterministic, read-only reports built from persisted research artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from autowealth.research.run_store import ResearchRunStore, aggregate_warnings


REPORT_SOURCE_ARTIFACTS = (
    "run_manifest.json",
    "metrics.json",
    "benchmark_metrics.json",
    "warnings.json",
    "holdings.parquet",
    "factor_snapshots.parquet",
    "trades.parquet",
)

RESEARCH_BOUNDARY = (
    "This report is for research and education only. It is not investment "
    "advice, a trading instruction, or a return promise; historical results "
    "do not determine future performance."
)


@dataclass(frozen=True)
class _ArtifactInputs:
    manifest: dict[str, Any]
    metrics: dict[str, Any]
    benchmark_metrics: dict[str, Any]
    warnings_payload: dict[str, Any]
    holdings: pd.DataFrame
    factor_snapshots: pd.DataFrame
    trades: pd.DataFrame


def _read_artifacts(store: ResearchRunStore, run_id: str) -> _ArtifactInputs:
    """Read every required report artifact without changing persisted files."""
    return _ArtifactInputs(
        manifest=store.read_manifest(run_id),
        metrics=store.read_metrics(run_id),
        benchmark_metrics=store.read_benchmark_metrics(run_id),
        warnings_payload=store.read_warnings(run_id),
        holdings=store.read_holdings(run_id),
        factor_snapshots=store.read_factor_snapshots(run_id),
        trades=store.read_trades(run_id),
    )


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item).strip()]


def _optional_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_scalar(value: object) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            return str(value)
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _numeric_summary(values: object) -> dict[str, float | int | None]:
    series = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if series.empty:
        return {"count": 0, "minimum": None, "mean": None, "maximum": None}
    return {
        "count": int(len(series)),
        "minimum": float(series.min()),
        "mean": float(series.mean()),
        "maximum": float(series.max()),
    }


def _section(
    status: str,
    summary: str,
    *,
    evidence: Mapping[str, Any] | None = None,
    observations: list[str] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "summary": summary,
        "evidence": dict(evidence or {}),
        "observations": list(observations or []),
        "limitations": list(limitations or []),
    }


def _benchmark_status(benchmark_metrics: Mapping[str, Any]) -> str:
    if not benchmark_metrics:
        return "unavailable"
    statuses = []
    for value in benchmark_metrics.values():
        entry = _mapping(value)
        statuses.append(
            "unavailable"
            if entry.get("status") == "unavailable"
            else "available"
        )
    if all(status == "available" for status in statuses):
        return "available"
    if all(status == "unavailable" for status in statuses):
        return "unavailable"
    return "partial"


def _benchmark_review(
    benchmark_metrics: Mapping[str, Any],
    manifest_status: object,
) -> tuple[str, dict[str, Any]]:
    artifact_status = _benchmark_status(benchmark_metrics)
    persisted_status = str(manifest_status or artifact_status)
    statuses = {persisted_status, artifact_status}
    if "unavailable" in statuses:
        status = "unavailable"
    elif "partial" in statuses:
        status = "partial"
    else:
        status = "available"
    unavailable: dict[str, str] = {}
    entries: dict[str, Any] = {}
    for symbol, value in benchmark_metrics.items():
        entry = _mapping(value)
        entries[str(symbol)] = entry
        if entry.get("status") == "unavailable":
            unavailable[str(symbol)] = str(
                entry.get("reason") or "No benchmark reason was persisted."
            )
    summary = (
        "The persisted benchmark is unavailable; no benchmark return is "
        "inferred or fabricated."
        if status == "unavailable"
        else "Persisted benchmark metrics are available for deterministic review."
        if status == "available"
        else "Only part of the requested benchmark set is available."
    )
    return status, _section(
        status,
        summary,
        evidence={
            "manifest_status": persisted_status,
            "artifact_status": artifact_status,
            "entries": entries,
            "unavailable_reasons": unavailable,
        },
        limitations=(
            ["Relative performance cannot be assessed while the benchmark is unavailable."]
            if status != "available"
            else []
        ),
    )


def _holdings_evidence(frame: pd.DataFrame) -> dict[str, Any]:
    data = pd.DataFrame(frame).copy()
    weight_columns = [
        str(column)
        for column in data.columns
        if str(column).endswith("_weight") and str(column) != "cash_weight"
    ]
    counts = []
    for _, row in data.iterrows():
        counts.append(
            sum(
                (_optional_float(row.get(column)) or 0.0) > 0.0
                for column in weight_columns
            )
        )
    date_column = "date" if "date" in data else "rebalance_date"
    dates = (
        pd.to_datetime(data[date_column], errors="coerce").dropna()
        if date_column in data
        else pd.Series(dtype="datetime64[ns]")
    )
    return {
        "record_count": int(len(data)),
        "rebalance_count": int(dates.nunique()) if not dates.empty else 0,
        "latest_rebalance_date": (
            pd.Timestamp(dates.max()).isoformat() if not dates.empty else None
        ),
        "holding_count_latest": counts[-1] if counts else 0,
        "holding_count_minimum": min(counts) if counts else 0,
        "holding_count_maximum": max(counts) if counts else 0,
        "cash_weight": _numeric_summary(
            data["cash_weight"] if "cash_weight" in data else []
        ),
        "weight_column_count": len(weight_columns),
    }


def _factor_evidence(
    frame: pd.DataFrame,
    coverage: Mapping[str, Any],
) -> dict[str, Any]:
    data = pd.DataFrame(frame).copy()
    symbols = (
        sorted({str(value) for value in data["symbol"].dropna()})
        if "symbol" in data
        else []
    )
    dates = (
        pd.to_datetime(data["rebalance_date"], errors="coerce").dropna()
        if "rebalance_date" in data
        else pd.Series(dtype="datetime64[ns]")
    )
    availability: dict[str, dict[str, int]] = {}
    for column in data.columns:
        name = str(column)
        if not name.endswith("_available"):
            continue
        values = data[column].fillna(False)
        available_count = int((values == True).sum())  # noqa: E712
        availability[name[: -len("_available")]] = {
            "available_count": available_count,
            "missing_count": int(len(data) - available_count),
        }
    warning_count = 0
    if "warnings" in data:
        warning_count = int(
            data["warnings"].fillna("").astype(str).str.strip().ne("").sum()
        )
    selected_count = None
    if "selected" in data:
        selected_count = int((data["selected"].fillna(False) == True).sum())  # noqa: E712
    return {
        "record_count": int(len(data)),
        "symbol_count": len(symbols),
        "symbols": symbols,
        "rebalance_count": int(dates.nunique()) if not dates.empty else 0,
        "latest_rebalance_date": (
            pd.Timestamp(dates.max()).isoformat() if not dates.empty else None
        ),
        "composite_score": _numeric_summary(
            data["composite_score"] if "composite_score" in data else []
        ),
        "selected_record_count": selected_count,
        "snapshot_warning_count": warning_count,
        "availability_from_snapshots": availability,
        "coverage_overall": dict(coverage),
    }


def _trade_evidence(frame: pd.DataFrame) -> dict[str, Any]:
    data = pd.DataFrame(frame).copy()
    side_counts = (
        {
            str(key): int(value)
            for key, value in data["side"].fillna("unknown").value_counts().items()
        }
        if "side" in data
        else {}
    )
    symbols = (
        sorted({str(value) for value in data["symbol"].dropna()})
        if "symbol" in data
        else []
    )
    return {
        "record_count": int(len(data)),
        "symbol_count": len(symbols),
        "side_counts": side_counts,
        "trade_value": _numeric_summary(
            data["trade_value"] if "trade_value" in data else []
        ),
        "cost": _numeric_summary(data["cost"] if "cost" in data else []),
        "total_trade_value": (
            float(pd.to_numeric(data["trade_value"], errors="coerce").sum())
            if "trade_value" in data
            else 0.0
        ),
        "total_cost": (
            float(pd.to_numeric(data["cost"], errors="coerce").sum())
            if "cost" in data
            else 0.0
        ),
    }


def _performance_review(metrics: Mapping[str, Any]) -> dict[str, Any]:
    core_names = (
        "annualized_return",
        "total_return",
        "max_drawdown",
        "volatility",
        "sharpe_ratio",
        "calmar_ratio",
        "turnover",
    )
    core_metrics = {
        name: _optional_float(metrics.get(name)) for name in core_names
    }
    available_count = sum(value is not None for value in core_metrics.values())
    observations = [
        f"{name}={value:.6f}"
        for name, value in core_metrics.items()
        if value is not None
    ]
    return _section(
        "available" if available_count else "unavailable",
        (
            "Performance values are reproduced from metrics.json and are not "
            "re-estimated by the report endpoint."
            if available_count
            else "No persisted core performance metric is available."
        ),
        evidence={
            "core_metrics": core_metrics,
            "annual_returns": _mapping(metrics.get("annual_returns")),
            "monthly_returns": _mapping(metrics.get("monthly_returns")),
            "annual_return_method": metrics.get("annual_return_method"),
            "excluded_partial_years": _strings(
                metrics.get("excluded_partial_years")
            ),
        },
        observations=observations,
        limitations=[
            "Metrics reflect the persisted backtest period, assumptions and data coverage only."
        ],
    )


def _macro_review(
    coverage: Mapping[str, Any],
    factor_snapshots: pd.DataFrame,
) -> dict[str, Any]:
    observation_count = _optional_int(coverage.get("macro_observation_count")) or 0
    data = pd.DataFrame(factor_snapshots)
    regimes = []
    if "macro_regime" in data:
        regimes = sorted(
            {
                str(value)
                for value in data["macro_regime"].dropna()
                if str(value).strip()
            }
        )
    available_dates = []
    if "macro_available_date" in data:
        available_dates = sorted(
            {
                str(_json_scalar(value))
                for value in data["macro_available_date"].dropna()
            }
        )
    status = "available" if observation_count > 0 else "neutral_fallback"
    summary = (
        "Persisted macro observations were available to the research run."
        if observation_count > 0
        else "No persisted macro observation was available; the run disclosed a neutral fallback."
    )
    return _section(
        status,
        summary,
        evidence={
            "macro_observation_count": observation_count,
            "regimes_in_factor_snapshots": regimes,
            "macro_available_dates": available_dates,
        },
        limitations=(
            ["Macro-cycle interpretation is limited because no as-of observation was persisted."]
            if observation_count == 0
            else []
        ),
    )


def _risk_flags(
    *,
    run_status: str,
    benchmark_status: str,
    warning_count: int,
    reported_warning_count: int | None,
    coverage: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []

    def add(
        code: str,
        category: str,
        severity: str,
        title: str,
        description: str,
        evidence: Mapping[str, Any],
        review_focus: str,
    ) -> None:
        flags.append(
            {
                "code": code,
                "category": category,
                "severity": severity,
                "title": title,
                "description": description,
                "evidence": dict(evidence),
                "review_focus": review_focus,
            }
        )

    if run_status != "success":
        add(
            "run_not_complete",
            "run_status",
            "high" if run_status == "failed" else "medium",
            "Research run is not complete",
            f"The persisted run_status is {run_status} and must remain visible.",
            {
                "run_status": run_status,
                "reasons": _strings(manifest.get("run_status_reasons")),
            },
            "Resolve or explicitly accept every persisted run-status reason before comparison.",
        )
    if benchmark_status != "available":
        add(
            "benchmark_not_available",
            "benchmark",
            "medium",
            "Benchmark comparison is incomplete",
            f"The persisted benchmark status is {benchmark_status}.",
            {"benchmark_status": benchmark_status},
            "Restore a compatible benchmark artifact before drawing relative-performance conclusions.",
        )
    if warning_count:
        add(
            "persisted_warnings",
            "data_quality",
            "high" if warning_count >= 100 else "medium",
            "Persisted warnings require review",
            f"The run contains {warning_count} persisted warnings.",
            {
                "warning_count": warning_count,
                "manifest_warning_count": reported_warning_count,
            },
            "Review warning categories and original warning text; do not infer missing observations.",
        )
    if reported_warning_count is not None and reported_warning_count != warning_count:
        add(
            "warning_count_mismatch",
            "consistency",
            "medium",
            "Warning counts differ",
            "The manifest warning count differs from warnings.json.",
            {
                "manifest_warning_count": reported_warning_count,
                "actual_warning_count": warning_count,
            },
            "Reconcile artifact generation before treating the run as internally consistent.",
        )

    price_coverage = _optional_float(coverage.get("price_coverage_ratio"))
    if price_coverage is not None and price_coverage < 1.0:
        add(
            "incomplete_price_coverage",
            "price_data",
            "high" if price_coverage < 0.5 else "medium",
            "Candidate price coverage is incomplete",
            f"Persisted price coverage is {price_coverage:.2%}.",
            {
                "price_coverage_ratio": price_coverage,
                "failed_price_symbols": _strings(
                    coverage.get("failed_price_symbols")
                ),
            },
            "Assess how excluded symbols alter universe representativeness and portfolio concentration.",
        )

    if (_optional_int(coverage.get("macro_observation_count")) or 0) == 0:
        add(
            "macro_neutral_fallback",
            "macro_data",
            "medium",
            "Macro input used a neutral fallback",
            "No macro observation was persisted for the run.",
            {"macro_observation_count": 0},
            "Treat macro-regime interpretation as unavailable, not neutral evidence.",
        )

    constraints = _mapping(
        _mapping(manifest.get("config_summary")).get("portfolio_constraints")
    )
    min_holdings = _optional_int(constraints.get("min_holdings"))
    holdings_counts = _mapping(coverage.get("holdings_count_by_rebalance"))
    below_minimum = {
        str(date): int(count)
        for date, count in holdings_counts.items()
        if min_holdings is not None and int(count) < min_holdings
    }
    if below_minimum:
        add(
            "holdings_below_minimum",
            "portfolio_constraints",
            "medium",
            "One or more rebalances are below min_holdings",
            "Persisted holding counts do not satisfy the configured minimum.",
            {"min_holdings": min_holdings, "below_minimum": below_minimum},
            "Review concentration and the data exclusions that reduced eligible holdings.",
        )

    factor_coverage = _mapping(coverage.get("factor_coverage_overall"))
    threshold = _optional_float(coverage.get("factor_coverage_threshold")) or 0.8
    insufficient = {
        str(name): _mapping(values)
        for name, values in factor_coverage.items()
        if (_optional_float(_mapping(values).get("coverage_ratio")) or 0.0)
        < threshold
    }
    if insufficient:
        add(
            "insufficient_factor_coverage",
            "factor_data",
            "medium",
            "Configured factor coverage is insufficient",
            "At least one persisted factor coverage ratio is below the run threshold.",
            {"threshold": threshold, "factors": insufficient},
            "Use saved availability and effective weights; never replace missing factors with fabricated values.",
        )
    return flags


def _counterarguments(
    *,
    coverage: Mapping[str, Any],
    benchmark_status: str,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    arguments = [
        {
            "topic": "Universe representativeness",
            "argument": (
                "A fixed or incompletely covered universe can make the historical "
                "portfolio look more robust than a point-in-time investable universe."
            ),
            "evidence_needed": [
                "historical constituent membership",
                "delisting and ST history",
                "failed-symbol attribution",
            ],
            "affected_assumptions": ["survivorship bias", "investable universe"],
            "research_value": "Tests whether results depend on today's surviving securities.",
        },
        {
            "topic": "Data availability and factor degradation",
            "argument": (
                "Factor scores based on reduced inputs may not be comparable across "
                "symbols or rebalance dates even when weights are re-normalized."
            ),
            "evidence_needed": [
                "factor coverage by rebalance",
                "effective composite weights",
                "point-in-time fundamental availability",
            ],
            "affected_assumptions": ["factor comparability", "missing-data handling"],
            "research_value": "Separates model behavior from changing data coverage.",
        },
        {
            "topic": "Execution realism",
            "argument": (
                "Persisted trades do not prove that all historical orders were executable "
                "under exact suspension, price-limit and liquidity conditions."
            ),
            "evidence_needed": [
                "historical suspension state",
                "price-limit state",
                "capacity and volume constraints",
            ],
            "affected_assumptions": ["fill availability", "transaction-cost realism"],
            "research_value": "Challenges whether backtest fills could have occurred as modeled.",
        },
    ]
    if benchmark_status != "available":
        arguments.append(
            {
                "topic": "Missing benchmark context",
                "argument": (
                    "Absolute performance cannot establish relative value when the "
                    "requested benchmark is unavailable."
                ),
                "evidence_needed": ["compatible benchmark curve", "benchmark metrics"],
                "affected_assumptions": ["relative performance", "market regime comparison"],
                "research_value": "Prevents absolute returns from being interpreted without market context.",
            }
        )
    if (_optional_int(coverage.get("macro_observation_count")) or 0) == 0:
        arguments.append(
            {
                "topic": "Macro regime not observed",
                "argument": (
                    "A neutral fallback is an absence-of-data treatment, not evidence "
                    "that the macro environment was neutral."
                ),
                "evidence_needed": ["as-of macro observations", "publication dates"],
                "affected_assumptions": ["macro multiplier", "regime interpretation"],
                "research_value": "Avoids assigning economic meaning to a fallback value.",
            }
        )
    survivor = str(manifest.get("survivorship_bias_risk") or "")
    if survivor:
        arguments[0]["persisted_evidence"] = survivor
    return arguments


def build_real_research_report(
    store: ResearchRunStore,
    run_id: str,
) -> dict[str, Any]:
    """Build a deterministic report from one immutable research run."""
    inputs = _read_artifacts(store, run_id)
    manifest = inputs.manifest
    metrics = inputs.metrics
    coverage = _mapping(manifest.get("coverage_summary"))
    run_status = str(manifest.get("run_status") or "partial_success")
    run_status_reasons = _strings(manifest.get("run_status_reasons"))

    warning_summary = aggregate_warnings(
        inputs.warnings_payload,
        sample_limit=3,
        raw_limit=1_000_000,
    )
    warnings = list(warning_summary["raw_warnings"])
    warning_count = len(warnings)
    reported_warning_count = _optional_int(coverage.get("warning_count"))

    benchmark_status, benchmark_review = _benchmark_review(
        inputs.benchmark_metrics,
        coverage.get("benchmark_status"),
    )
    factor_coverage = _mapping(coverage.get("factor_coverage_overall"))
    factor_evidence = _factor_evidence(
        inputs.factor_snapshots,
        factor_coverage,
    )
    factor_threshold = (
        _optional_float(coverage.get("factor_coverage_threshold")) or 0.8
    )
    insufficient_factors = {
        str(name): _mapping(values)
        for name, values in factor_coverage.items()
        if (_optional_float(_mapping(values).get("coverage_ratio")) or 0.0)
        < factor_threshold
    }
    factor_record_count = int(factor_evidence["record_count"])
    factor_status = (
        "unavailable"
        if factor_record_count == 0
        else "insufficient_coverage"
        if insufficient_factors
        else "available"
    )
    factor_review = _section(
        factor_status,
        (
            "The persisted factor snapshot artifact contains no records."
            if factor_record_count == 0
            else "Persisted factor snapshots contain one or more coverage ratios "
            "below the configured threshold. Missing values are not converted "
            "into fabricated scores by this report."
            if insufficient_factors
            else "Persisted factor snapshots and coverage are available for review."
        ),
        evidence={
            **factor_evidence,
            "coverage_threshold": factor_threshold,
            "insufficient_factors": insufficient_factors,
            "coverage_by_rebalance": _mapping(
                coverage.get("factor_coverage_by_rebalance")
            ),
        },
        limitations=[
            "Factor comparability depends on point-in-time input coverage and saved effective weights."
        ],
    )

    holdings_evidence = _holdings_evidence(inputs.holdings)
    trade_evidence = _trade_evidence(inputs.trades)
    actual_categories = dict(warning_summary["categories"])
    data_quality_status = (
        "warnings_present" if warning_count else "no_persisted_warnings"
    )
    data_quality_review = _section(
        data_quality_status,
        (
            f"The run contains {warning_count} persisted warnings; all original "
            "warning strings are included in this response."
            if warning_count
            else "warnings.json contains no persisted warning strings."
        ),
        evidence={
            "warning_count": warning_count,
            "manifest_warning_count": reported_warning_count,
            "warning_categories": actual_categories,
            "warning_samples": dict(warning_summary["samples"]),
            "warnings": warnings,
            "price_coverage_ratio": _optional_float(
                coverage.get("price_coverage_ratio")
            ),
            "requested_symbols": _strings(coverage.get("requested_symbols")),
            "successful_price_symbols": _strings(
                coverage.get("successful_price_symbols")
            ),
            "failed_price_symbols": _strings(
                coverage.get("failed_price_symbols")
            ),
            "holdings": holdings_evidence,
            "trades": trade_evidence,
            "source_artifacts": list(REPORT_SOURCE_ARTIFACTS),
        },
        limitations=_strings(manifest.get("point_in_time_limitations")),
    )

    risk_flags = _risk_flags(
        run_status=run_status,
        benchmark_status=benchmark_status,
        warning_count=warning_count,
        reported_warning_count=reported_warning_count,
        coverage=coverage,
        manifest=manifest,
    )
    performance_review = _performance_review(metrics)
    macro_review = _macro_review(coverage, inputs.factor_snapshots)

    executive_summary = _section(
        run_status,
        (
            f"Run {run_id} is preserved as {run_status}. The report is a "
            "deterministic review of persisted artifacts and does not replace "
            "the underlying research evidence."
        ),
        evidence={
            "run_id": run_id,
            "manifest_run_id": manifest.get("run_id"),
            "run_status": run_status,
            "run_status_reasons": run_status_reasons,
            "benchmark_status": benchmark_status,
            "warning_count": warning_count,
            "price_coverage_ratio": _optional_float(
                coverage.get("price_coverage_ratio")
            ),
            "macro_observation_count": (
                _optional_int(coverage.get("macro_observation_count")) or 0
            ),
            "rebalance_count": _optional_int(coverage.get("rebalance_count")),
        },
        observations=[
            f"run_status={run_status}",
            f"benchmark_status={benchmark_status}",
            f"warning_count={warning_count}",
        ],
        limitations=run_status_reasons,
    )

    point_in_time_limitations = _strings(
        manifest.get("point_in_time_limitations")
    )
    survivorship_bias_risk = str(
        manifest.get("survivorship_bias_risk") or ""
    )
    boundary_limitations = list(point_in_time_limitations)
    if survivorship_bias_risk:
        boundary_limitations.append(survivorship_bias_risk)

    return {
        "run_id": run_id,
        "data_source": "real_artifacts",
        "generated_mode": "deterministic",
        "run_status": run_status,
        "benchmark_status": benchmark_status,
        "warning_count": warning_count,
        "executive_summary": executive_summary,
        "performance_review": performance_review,
        "risk_flags": risk_flags,
        "factor_review": factor_review,
        "benchmark_review": benchmark_review,
        "macro_review": macro_review,
        "data_quality_review": data_quality_review,
        "counterarguments": _counterarguments(
            coverage=coverage,
            benchmark_status=benchmark_status,
            manifest=manifest,
        ),
        "research_boundaries": _section(
            "research_only",
            RESEARCH_BOUNDARY,
            evidence={
                "read_only": True,
                "artifacts_modified": False,
                "deepseek_called": False,
                "trading_executed": False,
                "parameter_optimization_performed": False,
                "generated_mode": "deterministic",
                "source_artifacts": list(REPORT_SOURCE_ARTIFACTS),
            },
            limitations=boundary_limitations,
        ),
    }
