"""Deterministic, read-only reports built from persisted research artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import pandas as pd

from autowealth.i18n import (
    DEFAULT_REPORT_LOCALE,
    SupportedLocale,
    message,
    present_persisted_text,
)
from autowealth.i18n.warning_presenter import present_warnings
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


def _localized_strings(
    value: object,
    locale: SupportedLocale,
) -> list[str]:
    return [present_persisted_text(item, locale) for item in _strings(value)]


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
    locale: SupportedLocale,
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
                entry.get("reason")
                or message(locale, "benchmark_reason_missing")
            )
    summary_key = {
        "unavailable": "benchmark_unavailable_summary",
        "available": "benchmark_available_summary",
        "partial": "benchmark_partial_summary",
    }[status]
    return status, _section(
        status,
        message(locale, summary_key),
        evidence={
            "manifest_status": persisted_status,
            "artifact_status": artifact_status,
            "entries": entries,
            "unavailable_reasons": unavailable,
        },
        limitations=(
            [message(locale, "benchmark_relative_limitation")]
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


def _performance_review(
    metrics: Mapping[str, Any],
    locale: SupportedLocale,
) -> dict[str, Any]:
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
        message(
            locale,
            "performance_observation",
            label=message(locale, f"metric_{name}"),
            name=name,
            value=value,
        )
        for name, value in core_metrics.items()
        if value is not None
    ]
    return _section(
        "available" if available_count else "unavailable",
        message(
            locale,
            "performance_available_summary"
            if available_count
            else "performance_unavailable_summary",
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
        limitations=[message(locale, "performance_limitation")],
    )


def _macro_review(
    coverage: Mapping[str, Any],
    factor_snapshots: pd.DataFrame,
    locale: SupportedLocale,
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
    summary = message(
        locale,
        "macro_available_summary"
        if observation_count > 0
        else "macro_neutral_summary",
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
            [message(locale, "macro_missing_limitation")]
            if observation_count == 0
            else []
        ),
    )


def _risk_flags(
    *,
    locale: SupportedLocale,
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
            message(locale, "risk_run_title"),
            message(
                locale,
                "risk_run_description",
                run_status=run_status,
            ),
            {
                "run_status": run_status,
                "reasons": _strings(manifest.get("run_status_reasons")),
            },
            message(locale, "risk_run_review"),
        )
    if benchmark_status != "available":
        add(
            "benchmark_not_available",
            "benchmark",
            "medium",
            message(locale, "risk_benchmark_title"),
            message(
                locale,
                "risk_benchmark_description",
                benchmark_status=benchmark_status,
            ),
            {"benchmark_status": benchmark_status},
            message(locale, "risk_benchmark_review"),
        )
    if warning_count:
        add(
            "persisted_warnings",
            "data_quality",
            "high" if warning_count >= 100 else "medium",
            message(locale, "risk_warnings_title"),
            message(
                locale,
                "risk_warnings_description",
                warning_count=warning_count,
            ),
            {
                "warning_count": warning_count,
                "manifest_warning_count": reported_warning_count,
            },
            message(locale, "risk_warnings_review"),
        )
    if reported_warning_count is not None and reported_warning_count != warning_count:
        add(
            "warning_count_mismatch",
            "consistency",
            "medium",
            message(locale, "risk_warning_mismatch_title"),
            message(locale, "risk_warning_mismatch_description"),
            {
                "manifest_warning_count": reported_warning_count,
                "actual_warning_count": warning_count,
            },
            message(locale, "risk_warning_mismatch_review"),
        )

    price_coverage = _optional_float(coverage.get("price_coverage_ratio"))
    if price_coverage is not None and price_coverage < 1.0:
        add(
            "incomplete_price_coverage",
            "price_data",
            "high" if price_coverage < 0.5 else "medium",
            message(locale, "risk_price_title"),
            message(
                locale,
                "risk_price_description",
                price_coverage=price_coverage,
            ),
            {
                "price_coverage_ratio": price_coverage,
                "failed_price_symbols": _strings(
                    coverage.get("failed_price_symbols")
                ),
            },
            message(locale, "risk_price_review"),
        )

    if (_optional_int(coverage.get("macro_observation_count")) or 0) == 0:
        add(
            "macro_neutral_fallback",
            "macro_data",
            "medium",
            message(locale, "risk_macro_title"),
            message(locale, "risk_macro_description"),
            {"macro_observation_count": 0},
            message(locale, "risk_macro_review"),
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
            message(locale, "risk_holdings_title"),
            message(locale, "risk_holdings_description"),
            {"min_holdings": min_holdings, "below_minimum": below_minimum},
            message(locale, "risk_holdings_review"),
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
            message(locale, "risk_factor_title"),
            message(locale, "risk_factor_description"),
            {"threshold": threshold, "factors": insufficient},
            message(locale, "risk_factor_review"),
        )
    return flags


def _counterarguments(
    *,
    locale: SupportedLocale,
    coverage: Mapping[str, Any],
    benchmark_status: str,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    arguments = [
        {
            "topic": message(locale, "counter_universe_topic"),
            "argument": message(locale, "counter_universe_argument"),
            "evidence_needed": [
                message(locale, "counter_universe_evidence_1"),
                message(locale, "counter_universe_evidence_2"),
                message(locale, "counter_universe_evidence_3"),
            ],
            "affected_assumptions": [
                message(locale, "counter_universe_assumption_1"),
                message(locale, "counter_universe_assumption_2"),
            ],
            "research_value": message(locale, "counter_universe_value"),
        },
        {
            "topic": message(locale, "counter_factor_topic"),
            "argument": message(locale, "counter_factor_argument"),
            "evidence_needed": [
                message(locale, "counter_factor_evidence_1"),
                message(locale, "counter_factor_evidence_2"),
                message(locale, "counter_factor_evidence_3"),
            ],
            "affected_assumptions": [
                message(locale, "counter_factor_assumption_1"),
                message(locale, "counter_factor_assumption_2"),
            ],
            "research_value": message(locale, "counter_factor_value"),
        },
        {
            "topic": message(locale, "counter_execution_topic"),
            "argument": message(locale, "counter_execution_argument"),
            "evidence_needed": [
                message(locale, "counter_execution_evidence_1"),
                message(locale, "counter_execution_evidence_2"),
                message(locale, "counter_execution_evidence_3"),
            ],
            "affected_assumptions": [
                message(locale, "counter_execution_assumption_1"),
                message(locale, "counter_execution_assumption_2"),
            ],
            "research_value": message(locale, "counter_execution_value"),
        },
    ]
    if benchmark_status != "available":
        arguments.append(
            {
                "topic": message(locale, "counter_benchmark_topic"),
                "argument": message(locale, "counter_benchmark_argument"),
                "evidence_needed": [
                    message(locale, "counter_benchmark_evidence_1"),
                    message(locale, "counter_benchmark_evidence_2"),
                ],
                "affected_assumptions": [
                    message(locale, "counter_benchmark_assumption_1"),
                    message(locale, "counter_benchmark_assumption_2"),
                ],
                "research_value": message(locale, "counter_benchmark_value"),
            }
        )
    if (_optional_int(coverage.get("macro_observation_count")) or 0) == 0:
        arguments.append(
            {
                "topic": message(locale, "counter_macro_topic"),
                "argument": message(locale, "counter_macro_argument"),
                "evidence_needed": [
                    message(locale, "counter_macro_evidence_1"),
                    message(locale, "counter_macro_evidence_2"),
                ],
                "affected_assumptions": [
                    message(locale, "counter_macro_assumption_1"),
                    message(locale, "counter_macro_assumption_2"),
                ],
                "research_value": message(locale, "counter_macro_value"),
            }
        )
    survivor = str(manifest.get("survivorship_bias_risk") or "")
    if survivor:
        arguments[0]["persisted_evidence"] = present_persisted_text(
            survivor,
            locale,
        )
        arguments[0]["persisted_evidence_source"] = survivor
    return arguments


def build_real_research_report(
    store: ResearchRunStore,
    run_id: str,
    locale: SupportedLocale = DEFAULT_REPORT_LOCALE,
) -> dict[str, Any]:
    """Build a deterministic report from one immutable research run."""
    inputs = _read_artifacts(store, run_id)
    manifest = inputs.manifest
    metrics = inputs.metrics
    coverage = _mapping(manifest.get("coverage_summary"))
    run_status = str(manifest.get("run_status") or "partial_success")
    run_status_reasons = _strings(manifest.get("run_status_reasons"))
    localized_run_status_reasons = _localized_strings(
        manifest.get("run_status_reasons"),
        locale,
    )

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
        locale,
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
        message(
            locale,
            "factor_empty_summary"
            if factor_record_count == 0
            else "factor_insufficient_summary"
            if insufficient_factors
            else "factor_available_summary",
        ),
        evidence={
            **factor_evidence,
            "coverage_threshold": factor_threshold,
            "insufficient_factors": insufficient_factors,
            "coverage_by_rebalance": _mapping(
                coverage.get("factor_coverage_by_rebalance")
            ),
        },
        limitations=[message(locale, "factor_limitation")],
    )

    holdings_evidence = _holdings_evidence(inputs.holdings)
    trade_evidence = _trade_evidence(inputs.trades)
    actual_categories = dict(warning_summary["categories"])
    warning_presentations = present_warnings(warnings, locale)
    data_quality_status = (
        "warnings_present" if warning_count else "no_persisted_warnings"
    )
    data_quality_review = _section(
        data_quality_status,
        message(
            locale,
            "data_quality_warnings_summary"
            if warning_count
            else "data_quality_empty_summary",
            warning_count=warning_count,
        ),
        evidence={
            "warning_count": warning_count,
            "manifest_warning_count": reported_warning_count,
            "warning_categories": actual_categories,
            "warning_samples": dict(warning_summary["samples"]),
            "warnings": warnings,
            "warning_presentations": warning_presentations,
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
            "source_point_in_time_limitations": _strings(
                manifest.get("point_in_time_limitations")
            ),
        },
        limitations=_localized_strings(
            manifest.get("point_in_time_limitations"),
            locale,
        ),
    )

    risk_flags = _risk_flags(
        locale=locale,
        run_status=run_status,
        benchmark_status=benchmark_status,
        warning_count=warning_count,
        reported_warning_count=reported_warning_count,
        coverage=coverage,
        manifest=manifest,
    )
    performance_review = _performance_review(metrics, locale)
    macro_review = _macro_review(coverage, inputs.factor_snapshots, locale)

    executive_summary = _section(
        run_status,
        message(
            locale,
            "executive_summary",
            run_id=run_id,
            run_status=run_status,
        ),
        evidence={
            "run_id": run_id,
            "manifest_run_id": manifest.get("run_id"),
            "run_status": run_status,
            "run_status_reasons": run_status_reasons,
            "localized_run_status_reasons": localized_run_status_reasons,
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
            message(
                locale,
                "observation_run_status",
                run_status=run_status,
            ),
            message(
                locale,
                "observation_benchmark_status",
                benchmark_status=benchmark_status,
            ),
            message(
                locale,
                "observation_warning_count",
                warning_count=warning_count,
            ),
        ],
        limitations=localized_run_status_reasons,
    )

    point_in_time_limitations = _strings(
        manifest.get("point_in_time_limitations")
    )
    survivorship_bias_risk = str(
        manifest.get("survivorship_bias_risk") or ""
    )
    boundary_limitations = [
        present_persisted_text(item, locale)
        for item in point_in_time_limitations
    ]
    if survivorship_bias_risk:
        boundary_limitations.append(
            present_persisted_text(survivorship_bias_risk, locale)
        )

    return {
        "run_id": run_id,
        "locale": locale,
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
            locale=locale,
            coverage=coverage,
            benchmark_status=benchmark_status,
            manifest=manifest,
        ),
        "research_boundaries": _section(
            "research_only",
            message(locale, "research_boundary"),
            evidence={
                "read_only": True,
                "artifacts_modified": False,
                "deepseek_called": False,
                "trading_executed": False,
                "parameter_optimization_performed": False,
                "generated_mode": "deterministic",
                "source_artifacts": list(REPORT_SOURCE_ARTIFACTS),
                "source_point_in_time_limitations": point_in_time_limitations,
                "source_survivorship_bias_risk": survivorship_bias_risk,
            },
            limitations=boundary_limitations,
        ),
    }
