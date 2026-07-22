"""Unit tests for structured research warning primitives."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

from autowealth.research.artifacts import write_research_artifacts
from autowealth.research.warnings import (
    STRUCTURED_WARNINGS_SCHEMA_VERSION,
    StructuredWarning,
    StructuredWarningCollector,
    WarningCode,
    WarningScope,
    WarningSeverity,
    safe_exception_evidence,
    validate_structured_warning_sequence,
)


def _warning(**overrides: object) -> StructuredWarning:
    values = {
        "code": WarningCode.PRICE_PROVIDER_FAILED,
        "severity": WarningSeverity.ERROR,
        "scope": WarningScope.PRICE_PROVIDER,
        "message": "600001 price provider failed: offline fixture",
        "source": "price_provider",
        "evidence": {"symbol": "600001", "reason": {"code": "provider_exception"}},
        "affected_symbols": ("600001",),
        "artifact_refs": ("warnings.json#/structured_warnings/0",),
        "retryable": True,
        "user_action": "Review provider availability.",
        "documentation_ref": "docs/structured-warnings.md",
    }
    values.update(overrides)
    return StructuredWarning(**values)


def test_schema_valid_creation_and_json_round_trip():
    warning = _warning()

    restored = StructuredWarning.from_dict(warning.to_dict())

    assert restored == warning
    assert json.loads(warning.to_json()) == warning.to_dict()
    assert warning.evidence["reason"]["code"] == "provider_exception"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("code", ""),
        ("severity", "critical"),
        ("scope", "trading"),
    ],
)
def test_schema_rejects_invalid_required_values(field: str, value: str):
    with pytest.raises((TypeError, ValueError)):
        _warning(**{field: value})


@pytest.mark.parametrize(
    "unsafe",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": Path("relative.parquet")},
        {"value": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        {"value": RuntimeError("offline fixture")},
        {"path": "D:\\private\\research.json"},
        {"path": "failed at /tmp/research.json"},
        {"uri": "read file:///tmp/research.json"},
        {"api_key": "not-a-real-key"},
        {"nested": {"Authorization": "Bearer not-a-real-token"}},
    ],
)
def test_schema_rejects_unsafe_evidence(unsafe: object):
    with pytest.raises((TypeError, ValueError)):
        _warning(evidence=unsafe)


@pytest.mark.parametrize(
    "unsafe",
    [
        {"apiToken": "abc"},
        {"accessToken": "abc"},
        {"refreshToken": "abc"},
        {"clientSecret": "abc"},
        {"apiKey": "abc"},
        {"openaiApiKey": "abc"},
        {"proxyAuthorization": "abc"},
        {"message": "Authorization: Bearer abc"},
        {"message": "Bearer abc"},
        {"message": "failed(/tmp/private.json)"},
        {"message": "C:\\Users\\name\\secret.txt"},
        {"message": "\\\\server\\share\\secret.txt"},
    ],
)
def test_schema_rejects_camel_case_secrets_and_wrapped_absolute_paths(
    unsafe: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _warning(evidence=unsafe)


@pytest.mark.parametrize(
    "safe",
    [
        {"token_count": 128},
        {"authorization_status": "not_required"},
        {"cookie_policy": "disabled"},
        {"secret_rotation_status": "not_applicable"},
        {"password_policy": "not_applicable"},
        {"documentation": "https://example.com/path"},
        {"documentation": "http://example.com/path"},
        {"artifact": "warnings.json"},
        {"artifact": "warnings.json#/structured_warnings/0"},
    ],
)
def test_schema_allows_non_secret_status_fields_urls_and_artifact_refs(
    safe: object,
) -> None:
    warning = _warning(evidence=safe)

    assert warning.evidence


def test_affected_symbols_are_stably_deduplicated():
    warning = _warning(affected_symbols=("600001", "000002", "600001"))

    assert warning.affected_symbols == ("600001", "000002")


def test_artifact_refs_reject_unknown_or_absolute_files():
    with pytest.raises(ValueError, match="artifact filenames"):
        _warning(artifact_refs=("unknown.json",))
    with pytest.raises(ValueError, match="artifact filenames"):
        _warning(artifact_refs=("D:\\private\\warnings.json",))


def test_collector_keeps_raw_and_structured_in_first_seen_order():
    collector = StructuredWarningCollector()
    collector.add(
        "first warning",
        code=WarningCode.MACRO_DATA_UNAVAILABLE,
        severity=WarningSeverity.WARNING,
        scope=WarningScope.MACRO,
        source="macro_provider",
    )
    collector.add(
        "first warning",
        code=WarningCode.BENCHMARK_DATA_UNAVAILABLE,
        severity=WarningSeverity.ERROR,
        scope=WarningScope.BENCHMARK,
        source="benchmark_provider_chain",
    )
    collector.add(
        "second warning",
        code=WarningCode.MACRO_DATA_UNAVAILABLE,
        severity=WarningSeverity.WARNING,
        scope=WarningScope.MACRO,
        source="macro_asof",
    )

    assert collector.raw_warnings == ["first warning", "second warning"]
    assert [item.message for item in collector.structured_warnings] == collector.raw_warnings
    assert [item.code for item in collector.structured_warnings] == [
        WarningCode.MACRO_DATA_UNAVAILABLE,
        WarningCode.MACRO_DATA_UNAVAILABLE,
    ]


def test_collector_reports_raw_stage_warning_without_metadata_without_raising():
    collector = StructuredWarningCollector()

    assert collector.require_metadata_for(["unregistered stage warning"]) is False
    assert collector.project(["unregistered stage warning"]) is None


def test_stage_commit_ignores_metadata_for_raw_warning_rejected_by_parent():
    stage = StructuredWarningCollector()
    run = StructuredWarningCollector()
    stage.add(
        "cache warning discarded after provider failure",
        code=WarningCode.PRICE_CACHE_UNAVAILABLE,
        severity=WarningSeverity.WARNING,
        scope=WarningScope.PRICE_PROVIDER,
        source="price_cache",
    )
    stage.add(
        "provider failure retained by parent",
        code=WarningCode.PRICE_PROVIDER_FAILED,
        severity=WarningSeverity.ERROR,
        scope=WarningScope.PRICE_PROVIDER,
        source="price_provider",
    )

    complete = run.commit_stage(["provider failure retained by parent"], stage)

    assert complete is True
    assert run.raw_warnings == ["provider failure retained by parent"]
    assert [item.message for item in run.structured_warnings] == run.raw_warnings


def test_stage_commit_marks_missing_metadata_incomplete_without_creating_raw_warning():
    stage = StructuredWarningCollector()
    run = StructuredWarningCollector()

    complete = run.commit_stage(["unregistered stage warning"], stage)

    assert complete is False
    assert run.raw_warnings == []
    assert run.project(["unregistered stage warning"]) is None


def test_later_duplicate_metadata_does_not_backfill_first_unclassified_warning():
    run = StructuredWarningCollector()
    missing_stage = StructuredWarningCollector()
    later_stage = StructuredWarningCollector()
    message = "same raw warning"
    assert run.commit_stage([message], missing_stage) is False
    later_stage.add(
        message,
        code=WarningCode.MACRO_DATA_UNAVAILABLE,
        severity=WarningSeverity.WARNING,
        scope=WarningScope.MACRO,
        source="macro_provider",
    )

    assert run.commit_stage([message], later_stage) is False
    assert run.project([message]) is None


def test_sequence_validation_rejects_message_mismatch():
    with pytest.raises(ValueError, match="message"):
        validate_structured_warning_sequence(
            ["raw warning"],
            [
                StructuredWarning(
                    code=WarningCode.MACRO_DATA_UNAVAILABLE,
                    severity=WarningSeverity.WARNING,
                    scope=WarningScope.MACRO,
                    message="different warning",
                    source="macro_provider",
                )
            ],
            schema_version=STRUCTURED_WARNINGS_SCHEMA_VERSION,
        )


def test_sequence_validation_rejects_non_integer_schema_version():
    warning = _warning()

    with pytest.raises(ValueError, match="schema version"):
        validate_structured_warning_sequence(
            [warning.message],
            [warning],
            schema_version=True,
        )


def test_json_output_is_deterministic():
    warning = _warning(evidence={"z": 1, "a": {"y": 2, "b": 3}})

    assert warning.to_json() == warning.to_json()
    assert warning.to_json().index('"a"') < warning.to_json().index('"z"')


def test_exception_evidence_redacts_paths_and_secret_values():
    evidence = safe_exception_evidence(
        RuntimeError(
            "failed(/tmp/private.json) accessToken=not-a-real-token "
            "Authorization: Bearer another-token"
        ),
        "provider_exception",
    )

    warning = _warning(evidence=evidence)

    assert warning.evidence["reason_code"] == "provider_exception"
    assert set(warning.evidence) == {"exception_type", "reason_code", "safe_summary"}
    assert "private" not in warning.evidence["safe_summary"]
    assert "not-a-real-token" not in warning.evidence["safe_summary"]
    assert "another-token" not in warning.evidence["safe_summary"]
    assert "<redacted_path>" in warning.evidence["safe_summary"]
    assert "<redacted_secret>" in warning.evidence["safe_summary"]


def _artifact_arguments() -> dict[str, object]:
    return {
        "config": {},
        "run_manifest": {},
        "metrics": {},
        "benchmark_metrics": {},
        "equity_curve": pd.Series(dtype=float),
        "benchmark_curve": pd.DataFrame(),
        "holdings": pd.DataFrame(),
        "trades": pd.DataFrame(),
        "factor_snapshots": pd.DataFrame(),
    }


def test_artifact_writer_rejects_raw_and_structured_message_mismatch(tmp_path: Path):
    with pytest.raises(ValueError, match="message mismatch"):
        write_research_artifacts(
            tmp_path / "runs",
            **_artifact_arguments(),
            warnings=["raw warning"],
            structured_warnings=[
                StructuredWarning(
                    code=WarningCode.MACRO_DATA_UNAVAILABLE,
                    severity=WarningSeverity.WARNING,
                    scope=WarningScope.MACRO,
                    message="different warning",
                    source="macro_provider",
                )
            ],
            run_id="mismatch_run",
        )

    assert not (tmp_path / "runs" / "mismatch_run").exists()


def test_artifact_writer_keeps_legacy_warning_shape_without_structured_input(
    tmp_path: Path,
):
    pytest.importorskip("pyarrow")
    result = write_research_artifacts(
        tmp_path / "runs",
        **_artifact_arguments(),
        warnings=["legacy warning"],
        run_id="legacy_run",
    )

    payload = json.loads(result.files["warnings.json"].read_text(encoding="utf-8"))
    assert payload == {"warnings": ["legacy warning"]}
