"""Unit tests for structured research warning primitives."""

from collections import UserDict, defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone
import json
from pathlib import Path

import pandas as pd
import pytest

from autowealth.research.artifacts import write_research_artifacts
from autowealth.research.warnings import (
    STRUCTURED_WARNING_EVIDENCE_MAX_DEPTH,
    STRUCTURED_WARNING_EVIDENCE_MAX_JSON_BYTES,
    STRUCTURED_WARNING_EVIDENCE_MAX_LIST_ITEMS,
    STRUCTURED_WARNING_EVIDENCE_MAX_MAPPING_KEYS,
    STRUCTURED_WARNING_EVIDENCE_MAX_STRING_LENGTH,
    STRUCTURED_WARNINGS_SCHEMA_VERSION,
    StructuredWarning,
    StructuredWarningCollector,
    WarningCode,
    WarningScope,
    WarningSeverity,
    safe_exception_evidence,
    validate_structured_warning_sequence,
)
from autowealth.security import validate_bounded_json


class _CustomEvidence:
    pass


class _CustomList(list):
    def __iter__(self):
        raise AssertionError("list subclasses must not be iterated")

    def __len__(self):
        raise AssertionError("list subclass length must not be trusted")


class _CustomTuple(tuple):
    def __iter__(self):
        raise AssertionError("tuple subclasses must not be iterated")

    def __len__(self):
        raise AssertionError("tuple subclass length must not be trusted")


class _UnboundedEvidence(Mapping):
    def __getitem__(self, key):
        raise AssertionError("custom evidence must not be indexed")

    def __iter__(self):
        raise AssertionError("custom evidence must not be iterated")

    def __len__(self):
        raise AssertionError("custom evidence length must not be trusted")


class _UnboundedSequence(Sequence):
    def __getitem__(self, index):
        raise AssertionError("custom sequence must not be indexed")

    def __len__(self):
        raise AssertionError("custom sequence length must not be trusted")


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
        {"value": date(2025, 1, 1)},
        {"value": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        {"value": RuntimeError("offline fixture")},
        {"value": b"offline fixture"},
        {"value": _CustomEvidence()},
        {"value": {"not", "json"}},
        {"value": frozenset({"not", "json"})},
        {"value": (item for item in range(2))},
        {"exception": "RuntimeError: raw provider response"},
        {"rawException": "RuntimeError: raw provider response"},
        {"providerResponse": {"status": 500, "body": "raw response"}},
        {"D:\\private\\field": "value"},
        {"Authorization: Bearer key-secret": "value"},
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
    "evidence",
    [
        UserDict({"value": 1}),
        defaultdict(int, {"value": 1}),
        _UnboundedEvidence(),
        {"values": _CustomList([1, 2])},
        {"values": _CustomTuple((1, 2))},
        {"values": _UnboundedSequence()},
        {"values": (item for item in range(2))},
    ],
)
def test_evidence_rejects_non_exact_containers_without_expanding_them(
    evidence: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        _warning(evidence=evidence)


def test_evidence_accepts_exact_tuple_and_normalizes_it_deterministically() -> None:
    warning = _warning(evidence={"values": (1, {"nested": [2, 3]})})

    assert warning.to_dict()["evidence"] == {"values": [1, {"nested": [2, 3]}]}
    assert StructuredWarning.from_dict(warning.to_dict()) == warning


def _validate_evidence_value(value: object) -> object:
    return validate_bounded_json(
        value,
        field_name="evidence",
        maximum_depth=STRUCTURED_WARNING_EVIDENCE_MAX_DEPTH,
        maximum_mapping_keys=STRUCTURED_WARNING_EVIDENCE_MAX_MAPPING_KEYS,
        maximum_list_items=STRUCTURED_WARNING_EVIDENCE_MAX_LIST_ITEMS,
        maximum_string_length=STRUCTURED_WARNING_EVIDENCE_MAX_STRING_LENGTH,
        maximum_json_bytes=STRUCTURED_WARNING_EVIDENCE_MAX_JSON_BYTES,
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (7, 7),
        ((1, 2), [1, 2]),
        ({"depth_1": [1]}, {"depth_1": [1]}),
        ({"depth_1": [{"depth_2": 2}]}, {"depth_1": [{"depth_2": 2}]}),
        (
            {"depth_1": [{"depth_2": (1, 2)}]},
            {"depth_1": [{"depth_2": [1, 2]}]},
        ),
    ],
    ids=["scalar-root", "tuple-root", "depth-1", "depth-2", "depth-3"],
)
def test_evidence_depth_zero_through_three_is_allowed(
    value: object,
    expected: object,
) -> None:
    assert _validate_evidence_value(value) == expected


def test_evidence_depth_four_is_rejected() -> None:
    value = {"depth_1": [{"depth_2": ([{"depth_4": 4}],)}]}

    with pytest.raises(ValueError, match="maximum nesting depth"):
        _validate_evidence_value(value)


def test_evidence_list_and_tuple_have_equivalent_depth_and_normalization() -> None:
    list_value = {"depth_1": [{"depth_2": (1, 2)}]}
    tuple_value = {"depth_1": ({"depth_2": [1, 2]},)}

    assert _validate_evidence_value(list_value) == _validate_evidence_value(tuple_value)


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


@pytest.mark.parametrize(
    "reference",
    [
        "warnings.json",
        "warnings.json#/structured_warnings/0",
        "benchmark_diagnostics.json#/attempts/1",
        "run_manifest.json#/macro_validation_diagnostics",
        "docs.json#/a~1b/~0value",
    ],
)
def test_artifact_refs_allow_safe_relative_files_and_json_pointers(
    reference: str,
) -> None:
    assert _warning(artifact_refs=(reference,)).artifact_refs == (reference,)


@pytest.mark.parametrize(
    "reference",
    [
        r"warnings.json#/C:\private\file",
        "warnings.json#/C:/private/file",
        "warnings.json#/C:private",
        "warnings.json#//server/share/file",
        "warnings.json#/tmp/private/file",
        "warnings.json#/Users/private/file",
        "warnings.json#/mnt/private/file",
        "warnings.json#/~1home~1service~1secret",
        "warnings.json#/file://private",
        "warnings.json#/https://example.com/private",
        "warnings.json#/https:~1~1example.com/private",
        "warnings.json#/apiKey/value",
        "warnings.json#/apiKey=abc",
        "warnings.json#/Authorization:Bearer abc",
        "warnings.json#/traceback",
        "warnings.json#/../secret",
        "warnings.json#/a%2Fb",
        "warnings.json#/bad~2escape",
        "../warnings.json#/x",
        r"C:\warnings.json#/x",
        "https://example.com/warnings.json#/x",
        "../docs.json#/x",
        r"C:\docs.json#/x",
        "https://example.com/docs.json#/x",
        r"docs.json#/C:\private\file",
        "docs.json#/apiKey=abc",
        "docs.json#/bad~2escape",
    ],
)
def test_artifact_refs_reject_unsafe_paths_and_json_pointers(
    reference: str,
) -> None:
    with pytest.raises(ValueError, match="artifact_refs"):
        _warning(artifact_refs=(reference,))


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


def test_exception_evidence_omits_raw_exception_text():
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
    assert warning.evidence["safe_summary"] == "RuntimeError [details redacted]"
    assert len(warning.evidence["safe_summary"]) <= 256


@pytest.mark.parametrize(
    "evidence",
    [
        {"level_1": {"level_2": {"level_3": {"level_4": {}}}}},
        {f"key_{index}": index for index in range(33)},
        {"values": list(range(33))},
        {"value": "x" * 513},
        {"x" * 513: "value"},
    ],
    ids=[
        "depth-4",
        "33-keys",
        "33-list-items",
        "513-character-string",
        "513-character-key",
    ],
)
def test_evidence_rejects_explicit_capacity_overflow(evidence: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        _warning(evidence=evidence)


def _evidence_at_json_byte_limit() -> dict[str, str]:
    evidence = {f"k{index:02d}": "x" * 500 for index in range(32)}
    for index in range(7):
        evidence[f"k{index:02d}"] += "x" * 12
    evidence["k07"] += "x" * 11
    encoded = json.dumps(
        evidence,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(encoded) == STRUCTURED_WARNING_EVIDENCE_MAX_JSON_BYTES
    return evidence


def test_evidence_capacity_boundaries_pass_exactly() -> None:
    evidence = _evidence_at_json_byte_limit()

    warning = _warning(evidence=evidence)

    assert STRUCTURED_WARNING_EVIDENCE_MAX_DEPTH == 3
    assert STRUCTURED_WARNING_EVIDENCE_MAX_MAPPING_KEYS == 32
    assert STRUCTURED_WARNING_EVIDENCE_MAX_LIST_ITEMS == 32
    assert STRUCTURED_WARNING_EVIDENCE_MAX_STRING_LENGTH == 512
    assert len(warning.evidence) == 32


def test_evidence_rejects_total_json_above_16_kib_without_truncating() -> None:
    evidence = _evidence_at_json_byte_limit()
    evidence["k08"] += "x"

    with pytest.raises(ValueError, match="16384-byte"):
        _warning(evidence=evidence)


def test_evidence_exact_container_and_string_limits_pass() -> None:
    warning = _warning(
        evidence={
            **{f"key_{index}": index for index in range(30)},
            "nested": {"level_2": {"value": "x" * 512}},
            "values": list(range(32)),
        }
    )

    assert warning.evidence["nested"]["level_2"]["value"] == "x" * 512
    assert list(warning.evidence["values"]) == list(range(32))


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
