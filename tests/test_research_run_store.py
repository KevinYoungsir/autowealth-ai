"""Tests for safe, read-only research artifact access."""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
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
from autowealth.research.warnings import (
    STRUCTURED_WARNINGS_SCHEMA_VERSION,
    StructuredWarning,
    WarningCode,
    WarningScope,
    WarningSeverity,
)
from autowealth.security import (
    REDACTED_ABSOLUTE_PATH,
    REDACTED_SENSITIVE_VALUE,
    REDACTED_TRACEBACK,
    REDACTED_UNSAFE_VALUE,
    sanitize_public_text,
)

RUN_OLD = "20250101T000000Z_aaaaaaaaaa"
RUN_NEW = "20250201T000000Z_bbbbbbbbbb"


class _UnboundedMapping(Mapping):
    def __getitem__(self, key):
        raise AssertionError("custom mapping must not be indexed")

    def __iter__(self):
        raise AssertionError("custom mapping must not be iterated")

    def __len__(self):
        raise AssertionError("custom mapping length must not be trusted")


def _deep_mapping(levels: int = 10) -> dict[str, object]:
    root: dict[str, object] = {}
    cursor = root
    for _ in range(levels):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child
    return root


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


def test_legacy_manifest_without_window_fields_remains_readable(
    runs_root: Path,
) -> None:
    store = ResearchRunStore(runs_root)

    run = store.get_run(RUN_OLD)

    assert "artifact_schema_version" not in run["manifest"]
    assert "research_window" not in run["manifest"]
    assert run["summary"]["run_id"] == RUN_OLD
    assert run["summary"]["run_status"] == "success"


@pytest.mark.parametrize("run_id", ["../outside", "..", "C:/outside", "a/b"])
def test_rejects_path_traversal(runs_root: Path, run_id: str) -> None:
    with pytest.raises(InvalidRunIdError):
        ResearchRunStore(runs_root).get_run(run_id)


def test_reports_corrupt_json(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "run_manifest.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ResearchArtifactDecodeError, match="invalid JSON"):
        ResearchRunStore(runs_root).read_manifest(RUN_OLD)


def test_reports_missing_parquet(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "equity_curve.parquet").unlink()

    with pytest.raises(ResearchArtifactNotFoundError, match="equity_curve"):
        ResearchRunStore(runs_root).read_equity_curve(RUN_OLD)


def test_reports_corrupt_parquet(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "equity_curve.parquet").write_text("not parquet", encoding="utf-8")

    with pytest.raises(ResearchArtifactDecodeError, match="invalid parquet"):
        ResearchRunStore(runs_root).read_equity_curve(RUN_OLD)


def test_preserves_structured_benchmark_unavailable(runs_root: Path) -> None:
    summary = ResearchRunStore(runs_root).get_summary(RUN_NEW)
    benchmark = ResearchRunStore(runs_root).read_benchmark_metrics(RUN_NEW)

    assert summary["benchmark_status"] == "unavailable"
    assert benchmark["000300"]["status"] == "unavailable"
    assert benchmark["000300"]["metrics"] == {}


def test_optional_benchmark_diagnostics_are_backward_compatible(
    runs_root: Path,
) -> None:
    store = ResearchRunStore(runs_root)
    diagnostics = {
        "schema_version": 1,
        "benchmarks": {
            "000300": {
                "status": "unavailable",
                "canonical_symbol": "000300",
                "attempts": [{"reason_code": "provider_exception"}],
            }
        },
    }

    assert store.read_benchmark_diagnostics(RUN_OLD) == {}
    assert store.get_run(RUN_OLD)["benchmark_diagnostics"] == {}

    _write_json(
        runs_root / RUN_NEW / "benchmark_diagnostics.json",
        diagnostics,
    )
    public_diagnostics = json.loads(json.dumps(diagnostics))
    public_benchmark = public_diagnostics["benchmarks"]["000300"]
    public_benchmark.update(
        {
            "attempts_total": 1,
            "attempts_truncated": False,
            "omitted_count": 0,
        }
    )

    assert store.read_benchmark_diagnostics(RUN_NEW) == public_diagnostics
    assert store.get_run(RUN_NEW)["benchmark_diagnostics"] == public_diagnostics


def test_old_unbounded_benchmark_attempts_are_bounded_without_rewriting_disk(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    attempts = [
        {
            "provider": f"fixture_{index:02d}",
            "status": "failed",
            "reason_code": "empty_response",
        }
        for index in range(35)
    ]
    _write_json(
        path,
        {
            "schema_version": 1,
            "benchmarks": {
                "000300": {
                    "status": "unavailable",
                    "attempts": attempts,
                }
            },
        },
    )
    before = path.read_bytes()

    diagnostics = ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW)
    benchmark = diagnostics["benchmarks"]["000300"]

    assert benchmark["status"] == "unavailable"
    assert benchmark["attempts_total"] == 35
    assert benchmark["attempts_truncated"] is True
    assert benchmark["omitted_count"] == 3
    assert "attempt_count" not in benchmark
    assert "omitted_attempt_count" not in benchmark
    assert len(benchmark["attempts"]) == 32
    assert benchmark["attempts"][0]["provider"] == "fixture_00"
    assert benchmark["attempts"][-1]["provider"] == "fixture_31"
    assert path.read_bytes() == before


def test_corrupt_optional_benchmark_diagnostics_do_not_break_run(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    path.write_text("{not-json", encoding="utf-8")
    store = ResearchRunStore(runs_root)

    assert store.read_benchmark_diagnostics(RUN_NEW) == {
        "status": "invalid",
        "reason_code": "invalid_diagnostics",
    }
    assert store.get_run(RUN_NEW)["summary"]["run_status"] == "partial_success"


@pytest.mark.parametrize("payload", [{}, {"schema_version": 1}])
def test_existing_benchmark_diagnostics_without_benchmarks_are_invalid(
    runs_root: Path,
    payload: dict[str, object],
) -> None:
    _write_json(
        runs_root / RUN_NEW / "benchmark_diagnostics.json",
        payload,
    )

    assert ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW) == {
        "status": "invalid",
        "reason_code": "invalid_diagnostics",
    }
    assert ResearchRunStore(runs_root).get_summary(RUN_NEW)["run_status"] == ("partial_success")


def test_non_finite_omitted_benchmark_attempt_makes_diagnostics_invalid(
    runs_root: Path,
) -> None:
    attempts = [{"provider": f"fixture_{index}", "coverage": 1.0} for index in range(35)]
    attempts[-1]["coverage"] = float("nan")
    _write_json(
        runs_root / RUN_NEW / "benchmark_diagnostics.json",
        {"benchmarks": {"000300": {"attempts": attempts}}},
    )

    assert ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW) == {
        "status": "invalid",
        "reason_code": "invalid_diagnostics",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"value": float("nan")},
        _deep_mapping(),
        {
            "schema_version": 1,
            "benchmarks": {
                "000300": {
                    "attempts": [
                        {"provider": f"fixture_{index}", "status": "failed"} for index in range(500)
                    ]
                }
            },
        },
    ],
)
def test_invalid_optional_benchmark_diagnostics_degrade_without_changing_run(
    runs_root: Path,
    payload: dict[str, object],
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    _write_json(path, payload)
    before = path.read_bytes()
    store = ResearchRunStore(runs_root)

    diagnostics = store.read_benchmark_diagnostics(RUN_NEW)

    if "benchmarks" in payload:
        benchmark = diagnostics["benchmarks"]["000300"]
        assert len(benchmark["attempts"]) == 32
        assert benchmark["attempts_total"] == 500
        assert benchmark["attempts_truncated"] is True
        assert benchmark["omitted_count"] == 468
        assert benchmark["attempts"][-1]["provider"] == "fixture_31"
    else:
        assert diagnostics == {
            "status": "invalid",
            "reason_code": "invalid_diagnostics",
        }
    assert store.get_summary(RUN_NEW)["run_status"] == "partial_success"
    assert path.read_bytes() == before


def test_legacy_benchmark_attempt_counters_are_normalized_in_memory_only(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    payload = {
        "schema_version": 1,
        "benchmarks": {
            "000300": {
                "status": "unavailable",
                "attempts": [
                    {"provider": "primary", "status": "failed"},
                    {"provider": "fallback", "status": "failed"},
                ],
                "attempt_count": 2,
                "attempts_truncated": False,
                "omitted_attempt_count": 0,
            }
        },
    }
    _write_json(path, payload)
    before = path.read_bytes()

    public = ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW)
    benchmark = public["benchmarks"]["000300"]

    assert benchmark["attempts_total"] == 2
    assert benchmark["attempts_truncated"] is False
    assert benchmark["omitted_count"] == 0
    assert "attempt_count" not in benchmark
    assert "omitted_attempt_count" not in benchmark
    assert path.read_bytes() == before


def test_legacy_bounded_benchmark_counters_keep_total_and_first_32(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    attempts = [{"provider": f"legacy_{index:02d}", "status": "failed"} for index in range(32)]
    _write_json(
        path,
        {
            "schema_version": 1,
            "benchmarks": {
                "000300": {
                    "attempts": attempts,
                    "attempt_count": 35,
                    "attempts_truncated": True,
                    "omitted_attempt_count": 3,
                }
            },
        },
    )
    before = path.read_bytes()

    benchmark = ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW)["benchmarks"][
        "000300"
    ]

    assert benchmark["attempts"] == attempts
    assert benchmark["attempts_total"] == 35
    assert benchmark["attempts_truncated"] is True
    assert benchmark["omitted_count"] == 3
    assert "attempt_count" not in benchmark
    assert "omitted_attempt_count" not in benchmark
    assert path.read_bytes() == before


def test_matching_new_and_legacy_benchmark_counters_prefer_new_fields(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    _write_json(
        path,
        {
            "schema_version": 1,
            "benchmarks": {
                "000300": {
                    "attempts": [{"provider": "primary", "status": "failed"}],
                    "attempts_total": 1,
                    "attempt_count": 1,
                    "attempts_truncated": False,
                    "omitted_count": 0,
                    "omitted_attempt_count": 0,
                }
            },
        },
    )

    benchmark = ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW)["benchmarks"][
        "000300"
    ]

    assert benchmark["attempts_total"] == 1
    assert benchmark["omitted_count"] == 0
    assert "attempt_count" not in benchmark
    assert "omitted_attempt_count" not in benchmark


@pytest.mark.parametrize(
    "conflicting_fields",
    [
        {"attempts_total": 3, "attempt_count": 2},
        {"attempts_total": 2},
        {"attempts_total": 2, "attempts_truncated": True},
        {"attempts_total": 2, "omitted_count": 1},
        {
            "attempts_total": 2,
            "attempt_count": 2,
            "omitted_count": 0,
            "omitted_attempt_count": 1,
        },
    ],
)
def test_conflicting_benchmark_attempt_counters_return_invalid(
    runs_root: Path,
    conflicting_fields: dict[str, object],
) -> None:
    path = runs_root / RUN_NEW / "benchmark_diagnostics.json"
    payload = {
        "schema_version": 1,
        "benchmarks": {
            "000300": {
                "status": "unavailable",
                "attempts": [
                    {"provider": "primary", "status": "failed"},
                    {"provider": "fallback", "status": "failed"},
                ],
                **conflicting_fields,
            }
        },
    }
    _write_json(path, payload)

    assert ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW) == {
        "status": "invalid",
        "reason_code": "invalid_diagnostics",
    }


def test_new_benchmark_counters_reject_short_persisted_attempt_array(
    runs_root: Path,
) -> None:
    _write_json(
        runs_root / RUN_NEW / "benchmark_diagnostics.json",
        {
            "benchmarks": {
                "000300": {
                    "attempts": [{} for _ in range(31)],
                    "attempts_total": 35,
                    "attempts_truncated": True,
                    "omitted_count": 4,
                }
            }
        },
    )

    assert ResearchRunStore(runs_root).read_benchmark_diagnostics(RUN_NEW) == {
        "status": "invalid",
        "reason_code": "invalid_diagnostics",
    }


def test_benchmark_diagnostic_internal_boundary_rejects_custom_mapping() -> None:
    with pytest.raises(TypeError):
        run_store_module._bound_public_benchmark_diagnostics(_UnboundedMapping())


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_required_metrics_reject_non_finite_json_values(
    runs_root: Path,
    constant: str,
) -> None:
    path = runs_root / RUN_NEW / "metrics.json"
    path.write_text(
        '{"annualized_return":' + constant + ',"total_return":0.1}',
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(ResearchArtifactDecodeError, match="invalid JSON"):
        ResearchRunStore(runs_root).read_metrics(RUN_NEW)

    assert path.read_bytes() == before


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_required_benchmark_metrics_reject_non_finite_json_values(
    runs_root: Path,
    constant: str,
) -> None:
    path = runs_root / RUN_NEW / "benchmark_metrics.json"
    path.write_text(
        '{"000300":{"status":"available","annualized_return":' + constant + "}}",
        encoding="utf-8",
    )

    with pytest.raises(ResearchArtifactDecodeError, match="invalid JSON"):
        ResearchRunStore(runs_root).read_benchmark_metrics(RUN_NEW)


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_optional_macro_non_finite_value_isolated_from_required_manifest(
    runs_root: Path,
    value: float,
) -> None:
    path = runs_root / RUN_NEW / "run_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected_run_status = payload["run_status"]
    payload["macro_validation_diagnostics"] = {"coverage_ratio": value}
    path.write_text(
        json.dumps(payload, allow_nan=True),
        encoding="utf-8",
    )
    before = path.read_bytes()

    manifest = ResearchRunStore(runs_root).read_manifest(RUN_NEW)

    assert manifest["run_status"] == expected_run_status
    assert manifest["macro_validation_diagnostics"] == {"status": "invalid"}
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_required_manifest_non_finite_value_remains_invalid(
    runs_root: Path,
    value: float,
) -> None:
    path = runs_root / RUN_NEW / "run_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["coverage_summary"]["price_coverage_ratio"] = value
    path.write_text(
        json.dumps(payload, allow_nan=True),
        encoding="utf-8",
    )
    before = path.read_bytes()

    with pytest.raises(ResearchArtifactDecodeError, match="safety limits"):
        ResearchRunStore(runs_root).read_manifest(RUN_NEW)

    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "payload",
    [
        {f"key_{index}": index for index in range(65)},
        {"values": list(range(65))},
    ],
)
def test_required_public_artifact_rejects_oversized_container(
    runs_root: Path,
    payload: dict[str, object],
) -> None:
    path = runs_root / RUN_NEW / "run_manifest.json"
    _write_json(path, payload)

    with pytest.raises(ResearchArtifactDecodeError, match="safety limits"):
        ResearchRunStore(runs_root).read_manifest(RUN_NEW)


def test_old_manifest_is_recursively_sanitized_without_rewriting_disk(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "run_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["data_sources"] = [
        {
            "status": "failed",
            "exception_type": "RuntimeError",
            "error": "RuntimeError: confidential provider response",
            "cache_path": r"C:\Users\researcher\price.parquet",
            "metadata": {
                "fallback_path": "D:/private/fundamental.parquet",
                "unc_path": r"\\server\share\benchmark.parquet",
                "posix_path": "/tmp/research/macro.csv",
                "documentation": "https://example.com/research/path",
                "artifact": "benchmark_diagnostics.json#/benchmarks/000300",
                "apiKey": "not-a-real-secret",
            },
        }
    ]
    _write_json(path, payload)
    before = path.read_bytes()

    manifest = ResearchRunStore(runs_root).read_manifest(RUN_NEW)

    source = manifest["data_sources"][0]
    assert source["error"] == "RuntimeError [details redacted]"
    assert source["cache_path"] == REDACTED_ABSOLUTE_PATH
    assert source["metadata"]["fallback_path"] == REDACTED_ABSOLUTE_PATH
    assert source["metadata"]["unc_path"] == REDACTED_ABSOLUTE_PATH
    assert source["metadata"]["posix_path"] == REDACTED_ABSOLUTE_PATH
    assert source["metadata"]["documentation"] == "https://example.com/research/path"
    assert source["metadata"]["artifact"] == "benchmark_diagnostics.json#/benchmarks/000300"
    assert source["metadata"]["apiKey"] == REDACTED_SENSITIVE_VALUE
    assert path.read_bytes() == before


def test_public_parquet_frame_sanitizes_untrusted_text_without_changing_numbers() -> None:
    frame = pd.DataFrame(
        {
            r"C:\private\column": ["value"],
            "apiKey": ["column-secret"],
            "requestHeaders": [{"Authorization": "Bearer header-secret"}],
            "notes": [
                {
                    "cache_path": "/tmp/private.parquet",
                    "token_count": 7,
                }
            ],
            "score": [88.5],
        }
    )

    public = run_store_module._sanitize_public_frame(frame)
    serialized = json.dumps(public.to_dict(orient="records"), ensure_ascii=False)

    assert REDACTED_ABSOLUTE_PATH in public.columns
    assert public["apiKey"].tolist() == [REDACTED_SENSITIVE_VALUE]
    assert public["requestHeaders"].tolist() == [REDACTED_UNSAFE_VALUE]
    assert public["notes"].iloc[0]["cache_path"] == REDACTED_ABSOLUTE_PATH
    assert public["notes"].iloc[0]["token_count"] == 7
    assert public["score"].tolist() == [88.5]
    assert "column-secret" not in serialized
    assert "header-secret" not in serialized
    assert "/tmp/private.parquet" not in serialized
    assert frame.columns[0] == r"C:\private\column"


def test_old_raw_warnings_are_sanitized_without_changing_counts_order_or_disk(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "warnings.json"
    raw = [
        "ordinary warning",
        r"600001 price provider failed: C:\Users\name\cache.parquet",
        "benchmark 000300 unavailable: accessToken=benchmark-secret",
        "macro provider failed: Authorization: Bearer macro-secret",
        "fundamental provider failed: Cookie: session=fundamental-secret",
        (
            "600001 price quality warning: Traceback (most recent call last):\n"
            'File "/tmp/provider.py", line 1\nRuntimeError: failed'
        ),
    ]
    _write_json(path, {"warnings": raw})
    before = path.read_bytes()
    store = ResearchRunStore(runs_root)

    public_payload = store.read_warnings(RUN_NEW)
    summary = aggregate_warnings(public_payload, sample_limit=10, raw_limit=20)

    assert public_payload["warnings"][0] == raw[0]
    assert len(public_payload["warnings"]) == len(raw)
    assert summary["total"] == len(raw)
    assert summary["raw_returned"] == len(raw)
    assert summary["raw_truncated"] is False
    assert summary["categories"]["price_provider"] == 1
    assert summary["categories"]["benchmark"] == 1
    assert summary["categories"]["macro_data"] == 1
    assert summary["categories"]["fundamental_data"] == 1
    assert summary["categories"]["price_quality"] == 1
    serialized = json.dumps(summary, ensure_ascii=False)
    assert "benchmark-secret" not in serialized
    assert "macro-secret" not in serialized
    assert "fundamental-secret" not in serialized
    assert "C:\\Users\\name" not in serialized
    assert "/tmp/provider.py" not in serialized
    assert REDACTED_ABSOLUTE_PATH in serialized
    assert REDACTED_SENSITIVE_VALUE in serialized
    assert REDACTED_TRACEBACK in serialized
    assert path.read_bytes() == before


def test_old_header_warnings_keep_order_categories_samples_and_disk_bytes(
    runs_root: Path,
) -> None:
    path = runs_root / RUN_NEW / "warnings.json"
    raw = [
        "Authorization: Basic basic-secret-value; retry succeeded",
        ("Cookie: session=session-secret-value; " "csrftoken=csrf-secret-value; retry succeeded"),
        (f"apiKey={REDACTED_SENSITIVE_VALUE}" ".appended-secret-value; retry succeeded"),
        "Bearer bearer-secret-value. retry succeeded",
        "ordinary non-sensitive warning",
    ]
    expected = [
        f"Authorization: Basic {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        (
            f"Cookie: session={REDACTED_SENSITIVE_VALUE}; "
            f"csrftoken={REDACTED_SENSITIVE_VALUE}; retry succeeded"
        ),
        f"apiKey={REDACTED_SENSITIVE_VALUE}; retry succeeded",
        f"Bearer {REDACTED_SENSITIVE_VALUE}. retry succeeded",
        raw[-1],
    ]
    _write_json(path, {"warnings": raw})
    before = path.read_bytes()

    public_payload = ResearchRunStore(runs_root).read_warnings(RUN_NEW)
    summary = aggregate_warnings(public_payload, sample_limit=5, raw_limit=5)

    assert list(public_payload["warnings"]) == expected
    assert summary["total"] == len(raw)
    assert summary["raw_warnings"] == expected
    assert summary["raw_returned"] == len(raw)
    assert summary["raw_truncated"] is False
    assert summary["categories"]["system"] == len(raw)
    assert sum(summary["categories"].values()) == len(raw)
    assert summary["samples"] == {"system": expected}
    assert [sanitize_public_text(item) for item in expected] == expected
    assert path.read_bytes() == before


def test_legacy_warning_category_is_preserved_from_pre_redaction_text() -> None:
    public_payload = run_store_module.public_warning_payload(
        {"warnings": ["accessToken=benchmark-secret"]}
    )

    summary = aggregate_warnings(public_payload)

    assert summary["categories"]["benchmark"] == 1
    assert summary["categories"]["system"] == 0
    assert "benchmark-secret" not in summary["raw_warnings"][0]
    assert run_store_module.categorize_warning(summary["raw_warnings"][0]) == "system"
    assert json.loads(json.dumps(public_payload)) == {
        "warnings": ["accessToken=[redacted-sensitive-value]"]
    }
    assert "legacy_category" not in json.dumps(public_payload)
    round_tripped = aggregate_warnings(json.loads(json.dumps(public_payload)))
    assert round_tripped["categories"]["benchmark"] == 0
    assert round_tripped["categories"]["system"] == 1


def test_public_warning_payload_rejects_third_party_string_subclasses() -> None:
    class CustomWarning(str):
        pass

    with pytest.raises(
        ResearchArtifactDecodeError,
        match="only warning strings",
    ):
        run_store_module.public_warning_payload(
            {"warnings": [CustomWarning("benchmark unavailable")]}
        )


def test_warnings_that_redact_to_same_text_are_not_deduplicated_or_misaligned() -> None:
    raw = [
        "benchmark provider failed: apiKey=first-secret",
        "benchmark provider failed: apiKey=second-secret",
    ]
    structured = [
        StructuredWarning(
            code=WarningCode.BENCHMARK_DATA_UNAVAILABLE,
            severity=WarningSeverity.WARNING,
            scope=WarningScope.BENCHMARK,
            message=message,
            source="benchmark_provider_chain",
        ).to_dict()
        for message in raw
    ]

    public_payload = run_store_module.public_warning_payload(
        {
            "warnings": raw,
            "structured_warnings_schema_version": 1,
            "structured_warnings": structured,
        }
    )
    summary = aggregate_warnings(public_payload, sample_limit=2, raw_limit=1)

    assert len(public_payload["warnings"]) == 2
    assert public_payload["warnings"][0] == public_payload["warnings"][1]
    assert summary["total"] == 2
    assert summary["raw_returned"] == 1
    assert summary["raw_truncated"] is True
    assert summary["categories"]["benchmark"] == 2
    assert len(summary["structured_warnings"]) == 2
    assert [warning["message"] for warning in summary["structured_warnings"]] == list(
        public_payload["warnings"]
    )


def test_custom_structured_evidence_is_invalid_without_hiding_raw_warning() -> None:
    raw = ["benchmark 000300 unavailable"]
    payload = {
        "warnings": raw,
        "structured_warnings_schema_version": 1,
        "structured_warnings": [
            {
                "code": "benchmark_data_unavailable",
                "severity": "warning",
                "scope": "benchmark",
                "message": raw[0],
                "source": "benchmark_provider_chain",
                "evidence": _UnboundedMapping(),
            }
        ],
    }

    public = run_store_module.public_warning_payload(payload)
    summary = aggregate_warnings(public)

    assert public["warnings"] == raw
    assert summary["structured_status"] == "invalid"
    assert summary["structured_warnings"] == []
    assert summary["categories"]["benchmark"] == 1


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


def test_valid_structured_warnings_are_additive_to_legacy_summary() -> None:
    raw = [
        "macro data is empty; neutral multiplier used",
        "benchmark 000300 unavailable",
    ]
    structured = [
        StructuredWarning(
            code=WarningCode.MACRO_DATA_UNAVAILABLE,
            severity=WarningSeverity.WARNING,
            scope=WarningScope.MACRO,
            message=raw[0],
            source="macro_provider",
        ).to_dict(),
        StructuredWarning(
            code=WarningCode.BENCHMARK_DATA_UNAVAILABLE,
            severity=WarningSeverity.ERROR,
            scope=WarningScope.BENCHMARK,
            message=raw[1],
            source="benchmark_provider_chain",
            affected_symbols=("000300",),
        ).to_dict(),
    ]

    summary = aggregate_warnings(
        {
            "warnings": raw,
            "structured_warnings_schema_version": STRUCTURED_WARNINGS_SCHEMA_VERSION,
            "structured_warnings": structured,
        }
    )

    assert summary["structured_available"] is True
    assert summary["structured_status"] == "valid"
    assert summary["structured_warnings"] == structured
    assert summary["severity_counts"] == {"info": 0, "warning": 1, "error": 1}
    assert summary["scope_counts"]["macro"] == 1
    assert summary["scope_counts"]["benchmark"] == 1
    assert summary["categories"]["macro_data"] == 1
    assert summary["categories"]["benchmark"] == 1


def test_sensitive_raw_and_structured_messages_are_redacted_in_alignment() -> None:
    raw = [r"600001 price provider failed: C:\private\cache.parquet token=secret"]
    structured = [
        StructuredWarning(
            code=WarningCode.PRICE_PROVIDER_FAILED,
            severity=WarningSeverity.ERROR,
            scope=WarningScope.PRICE_PROVIDER,
            message=raw[0],
            source="price_provider",
        ).to_dict()
    ]

    summary = aggregate_warnings(
        {
            "warnings": raw,
            "structured_warnings_schema_version": 1,
            "structured_warnings": structured,
        }
    )

    assert summary["structured_status"] == "valid"
    assert summary["total"] == 1
    assert summary["categories"]["price_provider"] == 1
    assert summary["raw_warnings"][0] == summary["structured_warnings"][0]["message"]
    assert "C:\\private" not in summary["raw_warnings"][0]
    assert "secret" not in summary["raw_warnings"][0]


def test_legacy_warning_artifact_reports_structured_absent(runs_root: Path) -> None:
    store = ResearchRunStore(runs_root)

    state = store.read_structured_warnings(RUN_OLD)

    assert state == {
        "structured_available": False,
        "structured_status": "absent",
        "structured_warnings_schema_version": None,
        "structured_warnings": [],
    }
    assert aggregate_warnings(store.read_warnings(RUN_OLD))["total"] == 2


@pytest.mark.parametrize(
    "structured_fields",
    [
        {"structured_warnings": []},
        {"structured_warnings_schema_version": 2, "structured_warnings": []},
        {"structured_warnings_schema_version": 1, "structured_warnings": {}},
        {
            "structured_warnings_schema_version": 1,
            "structured_warnings": [],
        },
        {
            "structured_warnings_schema_version": 1,
            "structured_warnings": [
                {
                    "code": "macro_data_unavailable",
                    "severity": "warning",
                    "scope": "macro",
                    "message": "different message",
                    "source": "macro_provider",
                },
                {
                    "code": "benchmark_data_unavailable",
                    "severity": "error",
                    "scope": "benchmark",
                    "message": "benchmark 000300 unavailable",
                    "source": "benchmark_provider_chain",
                },
            ],
        },
        {
            "structured_warnings_schema_version": 1,
            "structured_warnings": [
                {
                    "code": "macro_data_unavailable",
                    "severity": "warning",
                    "scope": "macro",
                    "message": "macro data is empty; neutral multiplier used",
                    "source": "macro_provider",
                    "evidence": {"value": float("nan")},
                },
                {
                    "code": "benchmark_data_unavailable",
                    "severity": "error",
                    "scope": "benchmark",
                    "message": "benchmark 000300 unavailable",
                    "source": "benchmark_provider_chain",
                },
            ],
        },
    ],
)
def test_invalid_structured_fields_do_not_hide_raw_warnings(
    runs_root: Path,
    structured_fields: dict[str, object],
) -> None:
    path = runs_root / RUN_NEW / "warnings.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(structured_fields)
    _write_json(path, payload)

    store = ResearchRunStore(runs_root)
    raw = store.read_warnings(RUN_NEW)["warnings"]
    summary = aggregate_warnings(store.read_warnings(RUN_NEW))

    assert raw == [
        "macro data is empty; neutral multiplier used",
        "benchmark 000300 unavailable",
    ]
    assert summary["structured_status"] == "invalid"
    assert summary["structured_available"] is False
    assert summary["structured_warnings"] == []
    assert summary["severity_counts"] == {"info": 0, "warning": 0, "error": 0}
    assert store.get_summary(RUN_NEW)["run_status"] == "partial_success"


def test_deep_structured_evidence_is_invalid_without_hiding_raw_warning() -> None:
    evidence: dict[str, object] = {}
    cursor = evidence
    for _ in range(1_100):
        nested: dict[str, object] = {}
        cursor["nested"] = nested
        cursor = nested
    raw = ["macro data is empty; neutral multiplier used"]

    summary = aggregate_warnings(
        {
            "warnings": raw,
            "structured_warnings_schema_version": 1,
            "structured_warnings": [
                {
                    "code": "macro_data_unavailable",
                    "severity": "warning",
                    "scope": "macro",
                    "message": raw[0],
                    "source": "macro_provider",
                    "evidence": evidence,
                }
            ],
        }
    )

    assert summary["structured_status"] == "invalid"
    assert summary["structured_available"] is False
    assert summary["structured_warnings"] == []
    assert summary["raw_warnings"] == raw
    assert summary["total"] == 1


def test_oversized_old_structured_evidence_is_invalid_and_raw_remains_readable() -> None:
    raw = ["macro data is empty; neutral multiplier used"]
    payload = {
        "warnings": raw,
        "structured_warnings_schema_version": 1,
        "structured_warnings": [
            {
                "code": "macro_data_unavailable",
                "severity": "warning",
                "scope": "macro",
                "message": raw[0],
                "source": "macro_provider",
                "evidence": {"value": "x" * 513},
            }
        ],
    }

    summary = aggregate_warnings(payload)

    assert summary["structured_status"] == "invalid"
    assert summary["structured_available"] is False
    assert summary["structured_warnings"] == []
    assert summary["raw_warnings"] == raw
    assert summary["total"] == 1


def test_oversized_structured_warning_collection_is_invalid_without_raw_loss() -> None:
    raw = [f"benchmark warning {index}" for index in range(280)]
    evidence = {f"field_{index}": "x" * 500 for index in range(30)}
    structured = [
        {
            "code": "benchmark_data_unavailable",
            "severity": "warning",
            "scope": "benchmark",
            "message": message,
            "source": "benchmark_provider_chain",
            "evidence": evidence,
        }
        for message in raw
    ]
    assert len(json.dumps(structured).encode("utf-8")) > (
        run_store_module.MAX_PUBLIC_STRUCTURED_WARNING_JSON_BYTES
    )

    summary = aggregate_warnings(
        {
            "warnings": raw,
            "structured_warnings_schema_version": 1,
            "structured_warnings": structured,
        }
    )

    assert summary["structured_status"] == "invalid"
    assert summary["structured_warnings"] == []
    assert summary["total"] == len(raw)


def test_missing_warnings_artifact_keeps_required_artifact_error(runs_root: Path) -> None:
    (runs_root / RUN_OLD / "warnings.json").unlink()

    with pytest.raises(ResearchArtifactNotFoundError, match="warnings.json"):
        ResearchRunStore(runs_root).read_warnings(RUN_OLD)


def test_empty_runs_directory_returns_empty_and_latest_is_clear(
    tmp_path: Path,
) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    store = ResearchRunStore(root)

    assert store.list_runs() == []
    with pytest.raises(ResearchRunNotFoundError, match="no research runs"):
        store.get_latest_run()


def test_missing_absolute_runs_directory_is_created_safely(
    tmp_path: Path,
) -> None:
    root = (tmp_path / "mounted" / "research_runs").resolve()
    store = ResearchRunStore(root)

    assert not root.exists()
    assert store.list_runs() == []
    assert root.is_dir()
    assert store.ensure_directory() is True
    assert store.has_runs() is False


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
