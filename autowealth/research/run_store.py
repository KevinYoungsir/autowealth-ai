"""Read-only access to persisted real-research run artifacts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Optional

import pandas as pd

from autowealth.security import (
    DEFAULT_PUBLIC_SANITIZATION_LIMITS,
    PublicSanitizationError,
    PublicSanitizationLimits,
    REDACTED_SENSITIVE_VALUE,
    REDACTED_UNSAFE_VALUE,
    is_forbidden_payload_key,
    is_sensitive_key,
    sanitize_public_payload,
    sanitize_public_text,
)
from autowealth.research.warnings import (
    STRUCTURED_WARNINGS_MAX_JSON_BYTES,
    STRUCTURED_WARNINGS_SCHEMA_VERSION,
    WarningScope,
    WarningSeverity,
    validate_structured_warning_sequence,
)
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
MAX_PUBLIC_BENCHMARK_DIAGNOSTIC_ATTEMPTS = 32
MAX_RESEARCH_ARTIFACT_JSON_BYTES = 4 * 1024 * 1024
MAX_PUBLIC_WARNING_ITEMS = 4096
MAX_PUBLIC_WARNING_STRING_CHARS = 1024 * 1024
MAX_PUBLIC_STRUCTURED_WARNING_JSON_BYTES = STRUCTURED_WARNINGS_MAX_JSON_BYTES
METRICS_PUBLIC_SANITIZATION_LIMITS = PublicSanitizationLimits(
    max_mapping_items=512,
    max_sequence_items=64,
    max_nodes=8192,
    max_string_length=4096,
    max_total_string_chars=131072,
    max_json_bytes=262144,
)
OPTIONAL_MACRO_DIAGNOSTICS_PUBLIC_SANITIZATION_LIMITS = PublicSanitizationLimits(
    max_json_bytes=16 * 1024,
)
INVALID_BENCHMARK_DIAGNOSTICS = {
    "status": "invalid",
    "reason_code": "invalid_diagnostics",
}
INVALID_MACRO_VALIDATION_DIAGNOSTICS = {"status": "invalid"}

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


class _PublicWarningText(str):
    """Safe public text carrying only its pre-redaction legacy category."""

    legacy_category: str

    def __new__(cls, value: str, legacy_category: str) -> "_PublicWarningText":
        instance = super().__new__(cls, value)
        instance.legacy_category = legacy_category
        return instance


def _reject_non_finite_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant is not allowed: {value}")


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
        filename = JSON_ARTIFACTS["manifest"]
        payload = self._read_json(run_id, filename)
        missing = object()
        macro_diagnostics = payload.pop("macro_validation_diagnostics", missing)
        try:
            manifest = sanitize_public_payload(payload)
        except PublicSanitizationError as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} exceeds public safety limits"
            ) from exc
        if type(manifest) is not dict:  # pragma: no cover - _read_json enforces this.
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} must contain a JSON object"
            )
        if macro_diagnostics is missing:
            return manifest
        try:
            public_diagnostics = sanitize_public_payload(
                macro_diagnostics,
                limits=OPTIONAL_MACRO_DIAGNOSTICS_PUBLIC_SANITIZATION_LIMITS,
            )
        except PublicSanitizationError:
            public_diagnostics = dict(INVALID_MACRO_VALIDATION_DIAGNOSTICS)
        manifest["macro_validation_diagnostics"] = public_diagnostics
        return manifest

    def read_metrics(self, run_id: str) -> dict[str, Any]:
        return self._read_public_json(
            run_id,
            JSON_ARTIFACTS["metrics"],
            limits=METRICS_PUBLIC_SANITIZATION_LIMITS,
            reject_non_finite=True,
        )

    def read_benchmark_metrics(self, run_id: str) -> dict[str, Any]:
        return self._read_public_json(
            run_id,
            JSON_ARTIFACTS["benchmark_metrics"],
            reject_non_finite=True,
        )

    def read_benchmark_diagnostics(self, run_id: str) -> dict[str, Any]:
        try:
            bounded = _bound_public_benchmark_diagnostics(
                self._read_json(
                    run_id,
                    JSON_ARTIFACTS["benchmark_diagnostics"],
                    reject_non_finite=True,
                )
            )
            sanitized = sanitize_public_payload(bounded)
            if type(sanitized) is not dict:  # pragma: no cover - bounded is exact dict.
                raise PublicSanitizationError("benchmark diagnostics did not remain a JSON object")
            return sanitized
        except ResearchArtifactNotFoundError:
            return {}
        except (
            PublicSanitizationError,
            ResearchArtifactDecodeError,
            TypeError,
            ValueError,
            RecursionError,
        ):
            return dict(INVALID_BENCHMARK_DIAGNOSTICS)

    def read_warnings(self, run_id: str) -> dict[str, Any]:
        return public_warning_payload(self._read_json(run_id, JSON_ARTIFACTS["warnings"]))

    def read_structured_warnings(self, run_id: str) -> dict[str, Any]:
        """Return validated structured warning metadata without weakening raw reads."""
        return _public_structured_warning_state(self._read_json(run_id, JSON_ARTIFACTS["warnings"]))

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

    def _read_json(
        self,
        run_id: str,
        filename: str,
        *,
        reject_non_finite: bool = False,
    ) -> dict[str, Any]:
        path = self._artifact_path(run_id, filename)
        try:
            if path.stat().st_size > MAX_RESEARCH_ARTIFACT_JSON_BYTES:
                raise ResearchArtifactDecodeError(
                    f"{filename} for run {run_id} exceeds the artifact size limit"
                )
            text = path.read_text(encoding="utf-8")
            value = json.loads(
                text,
                parse_constant=(_reject_non_finite_json_constant if reject_non_finite else None),
            )
        except ResearchArtifactDecodeError:
            raise
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} contains invalid JSON"
            ) from exc
        except OSError as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} could not be read"
            ) from exc
        if type(value) is not dict:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} must contain a JSON object"
            )
        return value

    def _read_public_json(
        self,
        run_id: str,
        filename: str,
        *,
        limits: PublicSanitizationLimits = DEFAULT_PUBLIC_SANITIZATION_LIMITS,
        reject_non_finite: bool = False,
    ) -> dict[str, Any]:
        try:
            value = sanitize_public_payload(
                self._read_json(
                    run_id,
                    filename,
                    reject_non_finite=reject_non_finite,
                ),
                limits=limits,
            )
        except PublicSanitizationError as exc:
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} exceeds public safety limits"
            ) from exc
        if type(value) is not dict:  # pragma: no cover - _read_json enforces this.
            raise ResearchArtifactDecodeError(
                f"{filename} for run {run_id} must contain a JSON object"
            )
        return value

    def _read_parquet(self, run_id: str, filename: str) -> pd.DataFrame:
        path = self._artifact_path(run_id, filename)
        try:
            return _sanitize_public_frame(pd.read_parquet(path))
        except (
            ImportError,
            OSError,
            PublicSanitizationError,
            RecursionError,
            TypeError,
            ValueError,
        ) as exc:
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


def _sanitize_public_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = pd.DataFrame(frame).copy()
    original_columns = list(result.columns)
    public_columns: list[str] = []
    for column in original_columns:
        public_column = sanitize_public_text(str(column))
        if public_column in public_columns:
            suffix = 2
            while f"{public_column}_{suffix}" in public_columns:
                suffix += 1
            public_column = f"{public_column}_{suffix}"
        public_columns.append(public_column)
    result.columns = public_columns

    for original_column, public_column in zip(original_columns, public_columns):
        if is_sensitive_key(str(original_column)):
            result[public_column] = REDACTED_SENSITIVE_VALUE
            continue
        if is_forbidden_payload_key(str(original_column)):
            result[public_column] = REDACTED_UNSAFE_VALUE
            continue
        if pd.api.types.is_object_dtype(result[public_column]) or pd.api.types.is_string_dtype(
            result[public_column]
        ):
            result[public_column] = result[public_column].map(_sanitize_public_cell)
    return result


def _sanitize_public_cell(value: object) -> object:
    if value is None or type(value) in (bool, int, float, str, dict, list):
        try:
            return sanitize_public_payload(value)
        except PublicSanitizationError:
            return REDACTED_UNSAFE_VALUE
    if isinstance(value, pd.Timestamp):
        return value
    if isinstance(value, (bytes, Path, BaseException, Mapping, list, tuple)):
        try:
            return sanitize_public_payload(value)
        except PublicSanitizationError:
            return REDACTED_UNSAFE_VALUE
    return REDACTED_UNSAFE_VALUE


def _bound_public_benchmark_diagnostics(
    diagnostics: Mapping[str, Any],
) -> dict[str, Any]:
    if type(diagnostics) is not dict:
        raise TypeError("benchmark diagnostics must be an exact dict")
    if len(diagnostics) > DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_mapping_items:
        raise PublicSanitizationError("benchmark diagnostics exceed the mapping width limit")
    result = diagnostics.copy()
    if "benchmarks" not in result:
        raise ValueError("benchmark diagnostics must contain benchmarks")
    benchmarks = result["benchmarks"]
    if type(benchmarks) is not dict:
        raise TypeError("benchmark diagnostics benchmarks must be an exact dict")
    if len(benchmarks) > DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_mapping_items:
        raise PublicSanitizationError("benchmark diagnostics exceed the benchmark width limit")
    bounded_benchmarks: dict[str, object] = {}
    for symbol, value in benchmarks.items():
        if type(symbol) is not str or type(value) is not dict:
            raise TypeError("benchmark diagnostic entries must be exact JSON objects")
        if len(value) > DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_mapping_items:
            raise PublicSanitizationError(
                "benchmark diagnostic entry exceeds the mapping width limit"
            )
        diagnostic = value.copy()
        attempts = diagnostic.get("attempts")
        if "attempts" in diagnostic and type(attempts) is not list:
            raise TypeError("benchmark diagnostic attempts must be an exact list")
        if type(attempts) is list:
            published_attempts = attempts[:MAX_PUBLIC_BENCHMARK_DIAGNOSTIC_ATTEMPTS]
            if any(type(attempt) is not dict for attempt in published_attempts):
                raise TypeError("benchmark attempts must be exact JSON objects")

            new_counter_fields = {
                "attempts_total",
                "attempts_truncated",
                "omitted_count",
            }
            present_new_fields = new_counter_fields.intersection(diagnostic)
            has_new_counter_names = "attempts_total" in diagnostic or "omitted_count" in diagnostic
            if has_new_counter_names and present_new_fields != new_counter_fields:
                raise ValueError("benchmark new attempt counters must be complete")
            new_total = _diagnostic_counter(
                diagnostic,
                "attempts_total",
            )
            old_total = _diagnostic_counter(
                diagnostic,
                "attempt_count",
            )
            if new_total is not None and old_total is not None and new_total != old_total:
                raise ValueError("benchmark attempt totals conflict")
            attempts_total = (
                new_total
                if new_total is not None
                else old_total if old_total is not None else len(attempts)
            )
            if attempts_total < len(attempts):
                raise ValueError("benchmark attempt total is below the stored attempt count")
            if has_new_counter_names and len(attempts) != min(
                attempts_total,
                MAX_PUBLIC_BENCHMARK_DIAGNOSTIC_ATTEMPTS,
            ):
                raise ValueError("benchmark new attempts array conflicts with the public cap")

            omitted_count = attempts_total - len(published_attempts)
            expected_truncated = omitted_count > 0
            persisted_truncated = diagnostic.get("attempts_truncated")
            if persisted_truncated is not None and type(persisted_truncated) is not bool:
                raise TypeError("benchmark attempts_truncated must be bool")
            if type(persisted_truncated) is bool and persisted_truncated != expected_truncated:
                raise ValueError("benchmark attempts_truncated conflicts with counts")

            new_omitted = _diagnostic_counter(diagnostic, "omitted_count")
            old_omitted = _diagnostic_counter(
                diagnostic,
                "omitted_attempt_count",
            )
            if new_omitted is not None and new_omitted != omitted_count:
                raise ValueError("benchmark omitted_count conflicts with counts")
            if old_omitted is not None and old_omitted != omitted_count:
                raise ValueError("benchmark omitted attempt count conflicts with counts")

            diagnostic["attempts"] = published_attempts
            diagnostic["attempts_total"] = attempts_total
            diagnostic["attempts_truncated"] = expected_truncated
            diagnostic["omitted_count"] = omitted_count
        elif any(
            field_name in diagnostic
            for field_name in (
                "attempts_total",
                "attempt_count",
                "attempts_truncated",
                "omitted_count",
                "omitted_attempt_count",
            )
        ):
            raise ValueError("benchmark attempt counters require an attempts list")
        diagnostic.pop("attempt_count", None)
        diagnostic.pop("omitted_attempt_count", None)
        if len(diagnostic) > DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_mapping_items:
            raise PublicSanitizationError(
                "benchmark diagnostic entry exceeds the public mapping width limit"
            )
        bounded_benchmarks[symbol] = diagnostic
    result["benchmarks"] = bounded_benchmarks
    return result


def _public_structured_warning_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    state = structured_warning_state(payload)
    if state["structured_status"] != "valid":
        return state
    safe_messages = [_sanitize_public_warning_text(item) for item in _warning_values(payload)]
    safe_structured: list[dict[str, Any]] = []
    try:
        for index, warning in enumerate(state["structured_warnings"]):
            sanitized = sanitize_public_payload(warning)
            if type(sanitized) is not dict:  # pragma: no cover - validated above.
                return _invalid_structured_warning_state()
            sanitized["message"] = safe_messages[index]
            safe_structured.append(sanitized)
        encoded = json.dumps(
            safe_structured,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > MAX_PUBLIC_STRUCTURED_WARNING_JSON_BYTES:
            return _invalid_structured_warning_state()
    except (PublicSanitizationError, TypeError, ValueError, RecursionError):
        return _invalid_structured_warning_state()
    return {
        **state,
        "structured_warnings": safe_structured,
    }


def public_warning_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a safe warning artifact view without modifying persisted bytes."""
    if type(payload) is not dict:
        raise ResearchArtifactDecodeError("warnings.json must contain a JSON object")
    if len(payload) > DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_mapping_items:
        raise ResearchArtifactDecodeError("warnings.json exceeds public safety limits")
    warnings = [
        _PublicWarningText(
            _sanitize_public_warning_text(item),
            categorize_warning(item),
        )
        for item in _warning_values(payload)
    ]
    state = _public_structured_warning_state(payload)
    base_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"warnings", "structured_warnings"}
    }
    try:
        sanitized = sanitize_public_payload(base_payload)
    except PublicSanitizationError as exc:
        raise ResearchArtifactDecodeError("warnings.json exceeds public safety limits") from exc
    if type(sanitized) is not dict:  # pragma: no cover - exact dict above.
        raise ResearchArtifactDecodeError("warnings.json must contain a JSON object")
    sanitized["warnings"] = warnings
    if state["structured_status"] == "valid":
        sanitized["structured_warnings_schema_version"] = STRUCTURED_WARNINGS_SCHEMA_VERSION
        sanitized["structured_warnings"] = state["structured_warnings"]
    elif state["structured_status"] == "invalid":
        # Keep the public payload invalid without returning unsafe optional content.
        sanitized["structured_warnings_schema_version"] = None
        sanitized["structured_warnings"] = []
    return sanitized


def aggregate_warnings(
    payload: Mapping[str, Any],
    *,
    sample_limit: int = 3,
    raw_limit: int = 20,
) -> dict[str, Any]:
    """Group warnings without changing the persisted warnings artifact."""
    if sample_limit < 0 or raw_limit < 0:
        raise ValueError("warning limits must be non-negative")
    if type(payload) is not dict:
        raise ResearchArtifactDecodeError("warnings.json must contain a JSON object")
    warnings = _warning_values(payload)
    public_warnings = [_sanitize_public_warning_text(warning) for warning in warnings]
    categories = {category: 0 for category in WARNING_CATEGORIES}
    samples: dict[str, list[str]] = {}
    for warning, public_warning in zip(warnings, public_warnings):
        category = getattr(warning, "legacy_category", categorize_warning(warning))
        if category not in categories:
            category = "system"
        categories[category] += 1
        category_samples = samples.setdefault(category, [])
        if len(category_samples) < sample_limit:
            category_samples.append(public_warning)
    structured = _public_structured_warning_state(payload)
    severity_counts = {severity.value: 0 for severity in WarningSeverity}
    scope_counts = {scope.value: 0 for scope in WarningScope}
    for warning in structured["structured_warnings"]:
        severity_counts[str(warning["severity"])] += 1
        scope_counts[str(warning["scope"])] += 1
    return {
        "total": len(warnings),
        "categories": categories,
        "samples": samples,
        "raw_warnings": public_warnings[:raw_limit],
        "raw_returned": min(len(warnings), raw_limit),
        "raw_truncated": len(warnings) > raw_limit,
        **structured,
        "severity_counts": severity_counts,
        "scope_counts": scope_counts,
    }


def structured_warning_state(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate additive structured fields while preserving legacy raw warnings."""
    if type(payload) is not dict:
        return _invalid_structured_warning_state()
    has_version = "structured_warnings_schema_version" in payload
    has_warnings = "structured_warnings" in payload
    if not has_version and not has_warnings:
        return {
            "structured_available": False,
            "structured_status": "absent",
            "structured_warnings_schema_version": None,
            "structured_warnings": [],
        }
    if not has_version or not has_warnings:
        return _invalid_structured_warning_state()

    version = payload.get("structured_warnings_schema_version")
    values = payload.get("structured_warnings")
    if type(values) is not list:
        return _invalid_structured_warning_state()
    if len(values) > MAX_PUBLIC_WARNING_ITEMS:
        return _invalid_structured_warning_state()
    try:
        normalized = validate_structured_warning_sequence(
            _warning_values(payload),
            values,
            schema_version=version,
        )
    except (TypeError, ValueError, RecursionError):
        return _invalid_structured_warning_state()
    return {
        "structured_available": True,
        "structured_status": "valid",
        "structured_warnings_schema_version": STRUCTURED_WARNINGS_SCHEMA_VERSION,
        "structured_warnings": [warning.to_dict() for warning in normalized],
    }


def _invalid_structured_warning_state() -> dict[str, Any]:
    return {
        "structured_available": False,
        "structured_status": "invalid",
        "structured_warnings_schema_version": None,
        "structured_warnings": [],
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
    if type(values) is not list:
        raise ResearchArtifactDecodeError("warnings.json must contain a warnings list")
    if len(values) > MAX_PUBLIC_WARNING_ITEMS:
        raise ResearchArtifactDecodeError("warnings.json exceeds the warning count limit")
    result: list[str] = []
    total_chars = 0
    for value in values:
        if type(value) is str or type(value) is _PublicWarningText:
            warning = value
        else:
            raise ResearchArtifactDecodeError("warnings.json must contain only warning strings")
        total_chars += len(warning)
        if total_chars > MAX_PUBLIC_WARNING_STRING_CHARS:
            raise ResearchArtifactDecodeError("warnings.json exceeds the warning text budget")
        result.append(warning)
    return result


def _sanitize_public_warning_text(value: str) -> str:
    if type(value) is _PublicWarningText:
        value = str(value)
    elif type(value) is not str:
        raise ResearchArtifactDecodeError("warnings.json must contain only warning strings")
    try:
        sanitized = sanitize_public_payload(value)
    except PublicSanitizationError as exc:
        raise ResearchArtifactDecodeError("warnings.json contains an oversized warning") from exc
    if type(sanitized) is not str:  # pragma: no cover - value is a string.
        raise ResearchArtifactDecodeError("warnings.json contains an invalid warning")
    return sanitized


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


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _diagnostic_counter(
    diagnostic: Mapping[str, Any],
    field_name: str,
) -> Optional[int]:
    if field_name not in diagnostic:
        return None
    value = diagnostic[field_name]
    if type(value) is not int or value < 0:
        raise TypeError(f"benchmark {field_name} must be a non-negative integer")
    return value


def _optional_float(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed
