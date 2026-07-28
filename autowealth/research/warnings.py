"""Stable structured metadata for persisted real-research warnings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    is_forbidden_payload_key,
    is_sensitive_key,
    safe_exception_record,
    validate_bounded_json,
)

STRUCTURED_WARNINGS_SCHEMA_VERSION = 1
STRUCTURED_WARNING_EVIDENCE_MAX_DEPTH = 3
STRUCTURED_WARNING_EVIDENCE_MAX_MAPPING_KEYS = 32
STRUCTURED_WARNING_EVIDENCE_MAX_LIST_ITEMS = 32
STRUCTURED_WARNING_EVIDENCE_MAX_STRING_LENGTH = 512
STRUCTURED_WARNING_EVIDENCE_MAX_JSON_BYTES = 16 * 1024
STRUCTURED_WARNINGS_MAX_JSON_BYTES = 4 * 1024 * 1024


class WarningSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningScope(str, Enum):
    PRICE_PROVIDER = "price_provider"
    BENCHMARK = "benchmark"
    FUNDAMENTAL = "fundamental"
    MACRO = "macro"
    UNIVERSE = "universe"
    FACTOR = "factor"
    PORTFOLIO = "portfolio"


class WarningCode(str, Enum):
    PRICE_PROVIDER_FAILED = "price_provider_failed"
    PRICE_CACHE_UNAVAILABLE = "price_cache_unavailable"
    PRICE_DATA_QUALITY_DEGRADED = "price_data_quality_degraded"
    FUNDAMENTAL_DATA_UNAVAILABLE = "fundamental_data_unavailable"
    FUNDAMENTAL_POINT_IN_TIME_REJECTED = "fundamental_point_in_time_rejected"
    MACRO_DATA_UNAVAILABLE = "macro_data_unavailable"
    UNIVERSE_POINT_IN_TIME_UNVERIFIED = "universe_point_in_time_unverified"
    FACTOR_DATA_INCOMPLETE = "factor_data_incomplete"
    PORTFOLIO_CONSTRUCTION_DEGRADED = "portfolio_construction_degraded"
    BENCHMARK_DATA_UNAVAILABLE = "benchmark_data_unavailable"
    BENCHMARK_PROVIDER_FALLBACK_USED = "benchmark_provider_fallback_used"
    BENCHMARK_CACHE_REJECTED = "benchmark_cache_rejected"


_SOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_ARTIFACT_PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:json|parquet)$")
_WINDOWS_DRIVE_IN_POINTER = re.compile(r"(?i)[A-Z]:[\\/]")
_WINDOWS_DRIVE_RELATIVE_SEGMENT = re.compile(r"(?i)^[A-Z]:")
_INVALID_JSON_POINTER_ESCAPE = re.compile(r"~(?![01])")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f]")
_URI_SCHEME = re.compile(r"(?i)^[a-z][a-z0-9+.-]*://")
_POINTER_URI = re.compile(r"(?i)^/[a-z][a-z0-9+.-]*:(?:/|~1){2}")
_POSIX_ROOT_SEGMENTS = {
    "app",
    "bin",
    "boot",
    "dev",
    "etc",
    "home",
    "media",
    "mnt",
    "opt",
    "private",
    "proc",
    "root",
    "run",
    "srv",
    "sys",
    "tmp",
    "usr",
    "users",
    "var",
    "volumes",
    "workspace",
}
_ARTIFACT_FILENAMES = {
    "config.json",
    "run_manifest.json",
    "metrics.json",
    "benchmark_metrics.json",
    "benchmark_diagnostics.json",
    "warnings.json",
    "docs.json",
    "equity_curve.parquet",
    "benchmark_curve.parquet",
    "holdings.parquet",
    "trades.parquet",
    "factor_snapshots.parquet",
}
_REQUIRED_FIELDS = {"code", "severity", "scope", "message", "source"}
_OPTIONAL_FIELDS = {
    "evidence",
    "affected_symbols",
    "artifact_refs",
    "retryable",
    "user_action",
    "documentation_ref",
}


def _validate_safe_string(value: str, path: str) -> str:
    if contains_absolute_path(value):
        raise ValueError(f"{path} must not contain an absolute path")
    if contains_sensitive_value(value):
        raise ValueError(f"{path} must not contain secret-like content")
    return value


def _validate_artifact_ref(value: str) -> str:
    if len(value) > 769 or value.count("#") > 1:
        raise ValueError("artifact_refs contain an invalid artifact reference")
    artifact_path, separator, pointer = value.partition("#")
    if (
        not artifact_path
        or len(artifact_path) > 256
        or artifact_path not in _ARTIFACT_FILENAMES
        or not _ARTIFACT_PATH_PATTERN.fullmatch(artifact_path)
        or ".." in artifact_path
        or "/" in artifact_path
        or "\\" in artifact_path
        or "://" in artifact_path
        or "%" in artifact_path
        or contains_sensitive_value(artifact_path)
    ):
        raise ValueError("artifact_refs must contain approved relative artifact filenames")
    if not separator:
        return value
    if (
        not pointer
        or len(pointer) > 512
        or not pointer.startswith("/")
        or pointer.startswith("//")
        or "\\" in pointer
        or "%" in pointer
        or _CONTROL_CHARACTER.search(pointer)
        or _WINDOWS_DRIVE_IN_POINTER.search(pointer)
        or _INVALID_JSON_POINTER_ESCAPE.search(pointer)
        or "file://" in pointer.lower()
        or _POINTER_URI.match(pointer)
        or contains_sensitive_value(pointer)
    ):
        raise ValueError("artifact_refs contain an unsafe JSON pointer")
    decoded_segments = [
        segment.replace("~1", "/").replace("~0", "~") for segment in pointer.split("/")[1:]
    ]
    if any(
        contains_absolute_path(segment)
        or contains_sensitive_value(segment)
        or segment.startswith(("//", "\\\\"))
        or _WINDOWS_DRIVE_RELATIVE_SEGMENT.match(segment)
        or _URI_SCHEME.match(segment)
        or segment in {".", ".."}
        or is_sensitive_key(segment)
        or is_forbidden_payload_key(segment)
        for segment in decoded_segments
    ) or (decoded_segments and decoded_segments[0].lower() in _POSIX_ROOT_SEGMENTS):
        raise ValueError("artifact_refs JSON pointer names forbidden payload data")
    return value


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _stable_strings(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise TypeError(f"{field_name} must be a string sequence")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not str or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _optional_text(value: Optional[str], field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string when supplied")
    return _validate_safe_string(value, field_name)


@dataclass(frozen=True)
class StructuredWarning:
    code: WarningCode
    severity: WarningSeverity
    scope: WarningScope
    message: str
    source: str
    evidence: Mapping[str, object] = field(default_factory=dict)
    affected_symbols: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    retryable: Optional[bool] = None
    user_action: Optional[str] = None
    documentation_ref: Optional[str] = None

    def __post_init__(self) -> None:
        try:
            code = self.code if isinstance(self.code, WarningCode) else WarningCode(self.code)
            severity = (
                self.severity
                if isinstance(self.severity, WarningSeverity)
                else WarningSeverity(self.severity)
            )
            scope = self.scope if isinstance(self.scope, WarningScope) else WarningScope(self.scope)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid structured warning enum value: {exc}") from exc
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("message must be a non-empty string")
        if not isinstance(self.source, str) or not _SOURCE_PATTERN.fullmatch(self.source):
            raise ValueError("source must be a non-empty lowercase machine identifier")
        if type(self.evidence) is not dict:
            raise TypeError("evidence must be an exact dict")
        validated_evidence = validate_bounded_json(
            self.evidence,
            field_name="evidence",
            maximum_depth=STRUCTURED_WARNING_EVIDENCE_MAX_DEPTH,
            maximum_mapping_keys=STRUCTURED_WARNING_EVIDENCE_MAX_MAPPING_KEYS,
            maximum_list_items=STRUCTURED_WARNING_EVIDENCE_MAX_LIST_ITEMS,
            maximum_string_length=STRUCTURED_WARNING_EVIDENCE_MAX_STRING_LENGTH,
            maximum_json_bytes=STRUCTURED_WARNING_EVIDENCE_MAX_JSON_BYTES,
        )
        symbols = _stable_strings(self.affected_symbols, "affected_symbols")
        artifact_refs = _stable_strings(self.artifact_refs, "artifact_refs")
        for reference in artifact_refs:
            _validate_artifact_ref(reference)
        if self.retryable is not None and not isinstance(self.retryable, bool):
            raise TypeError("retryable must be bool or None")

        object.__setattr__(self, "code", code)
        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "scope", scope)
        object.__setattr__(self, "evidence", _freeze_json(validated_evidence))
        object.__setattr__(self, "affected_symbols", symbols)
        object.__setattr__(self, "artifact_refs", artifact_refs)
        object.__setattr__(self, "user_action", _optional_text(self.user_action, "user_action"))
        object.__setattr__(
            self,
            "documentation_ref",
            _optional_text(self.documentation_ref, "documentation_ref"),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code.value,
            "severity": self.severity.value,
            "scope": self.scope.value,
            "message": self.message,
            "source": self.source,
        }
        if self.evidence:
            payload["evidence"] = _thaw_json(self.evidence)
        if self.affected_symbols:
            payload["affected_symbols"] = list(self.affected_symbols)
        if self.artifact_refs:
            payload["artifact_refs"] = list(self.artifact_refs)
        if self.retryable is not None:
            payload["retryable"] = self.retryable
        if self.user_action is not None:
            payload["user_action"] = self.user_action
        if self.documentation_ref is not None:
            payload["documentation_ref"] = self.documentation_ref
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StructuredWarning":
        if type(payload) is not dict:
            raise TypeError("structured warning payload must be an exact dict")
        keys = set(payload)
        missing = _REQUIRED_FIELDS - keys
        unknown = keys - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
        if missing:
            raise ValueError(f"structured warning is missing required fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"structured warning contains unknown fields: {sorted(unknown)}")
        affected_symbols = payload.get("affected_symbols", ())
        artifact_refs = payload.get("artifact_refs", ())
        if type(affected_symbols) not in (list, tuple):
            raise TypeError("affected_symbols must be a string sequence")
        if type(artifact_refs) not in (list, tuple):
            raise TypeError("artifact_refs must be a string sequence")
        return cls(
            code=payload["code"],
            severity=payload["severity"],
            scope=payload["scope"],
            message=payload["message"],
            source=payload["source"],
            evidence=payload.get("evidence", {}),
            affected_symbols=tuple(affected_symbols),
            artifact_refs=tuple(artifact_refs),
            retryable=payload.get("retryable"),
            user_action=payload.get("user_action"),
            documentation_ref=payload.get("documentation_ref"),
        )


class StructuredWarningCollector:
    """Build aligned raw and structured warning sequences with exact deduplication."""

    def __init__(self) -> None:
        self._raw_warnings: list[str] = []
        self._structured_warnings: list[StructuredWarning] = []
        self._seen_messages: set[str] = set()
        self._warnings_by_message: dict[str, StructuredWarning] = {}
        self._unclassified_messages: set[str] = set()

    @property
    def raw_warnings(self) -> list[str]:
        return list(self._raw_warnings)

    @property
    def structured_warnings(self) -> list[StructuredWarning]:
        return list(self._structured_warnings)

    def add(
        self,
        message: str,
        *,
        code: WarningCode,
        severity: WarningSeverity,
        scope: WarningScope,
        source: str,
        evidence: Optional[Mapping[str, object]] = None,
        affected_symbols: Sequence[str] = (),
        artifact_refs: Sequence[str] = (),
        retryable: Optional[bool] = None,
        user_action: Optional[str] = None,
        documentation_ref: Optional[str] = None,
    ) -> bool:
        if isinstance(message, str) and message in self._seen_messages:
            return False
        try:
            warning = StructuredWarning(
                code=code,
                severity=severity,
                scope=scope,
                message=message,
                source=source,
                evidence={} if evidence is None else evidence,
                affected_symbols=tuple(affected_symbols),
                artifact_refs=tuple(artifact_refs),
                retryable=retryable,
                user_action=user_action,
                documentation_ref=documentation_ref,
            )
        except (TypeError, ValueError, RecursionError):
            return False
        return self._accept(warning)

    def _accept(self, warning: StructuredWarning) -> bool:
        if warning.message in self._seen_messages:
            return False
        self._seen_messages.add(warning.message)
        self._raw_warnings.append(warning.message)
        self._structured_warnings.append(warning)
        self._warnings_by_message[warning.message] = warning
        return True

    def require_metadata_for(self, messages: Sequence[object]) -> bool:
        """Report whether every accepted raw warning has explicit metadata."""
        return all(
            message in self._seen_messages and message not in self._unclassified_messages
            for message in _normalized_messages(messages)
        )

    def commit_stage(
        self,
        messages: Sequence[object],
        stage_collector: "StructuredWarningCollector",
    ) -> bool:
        """Commit only metadata for raw warnings accepted by the parent stage."""
        complete = True
        for message in _normalized_messages(messages):
            if message in self._unclassified_messages:
                complete = False
                continue
            if message in self._seen_messages:
                continue
            warning = stage_collector._warnings_by_message.get(message)
            if warning is None:
                self._unclassified_messages.add(message)
                complete = False
                continue
            self._accept(warning)
        return complete

    def project(
        self,
        messages: Sequence[object],
    ) -> Optional[tuple[StructuredWarning, ...]]:
        """Project metadata in authoritative raw order, or return None if incomplete."""
        normalized = _normalized_messages(messages)
        if not self.require_metadata_for(normalized):
            return None
        return tuple(self._warnings_by_message[message] for message in normalized)


def _normalized_messages(messages: Sequence[object]) -> list[str]:
    return list(dict.fromkeys(str(message) for message in messages if str(message).strip()))


def validate_structured_warning_sequence(
    warnings: Sequence[str],
    structured_warnings: Sequence[StructuredWarning | Mapping[str, Any]],
    *,
    schema_version: int,
) -> tuple[StructuredWarning, ...]:
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != STRUCTURED_WARNINGS_SCHEMA_VERSION
    ):
        raise ValueError("structured warnings schema version must be 1")
    if type(warnings) not in (list, tuple) or type(structured_warnings) not in (
        list,
        tuple,
    ):
        raise TypeError("warning sequences must be exact lists or tuples")
    normalized = tuple(
        item if type(item) is StructuredWarning else StructuredWarning.from_dict(item)
        for item in structured_warnings
    )
    if any(not isinstance(message, str) for message in warnings):
        raise TypeError("raw warnings must contain strings")
    raw = list(warnings)
    if len(raw) != len(normalized):
        raise ValueError("raw and structured warning counts must match")
    for index, (message, warning) in enumerate(zip(raw, normalized)):
        if warning.message != message:
            raise ValueError(f"structured warning message mismatch at index {index}")
    encoded = json.dumps(
        [warning.to_dict() for warning in normalized],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > STRUCTURED_WARNINGS_MAX_JSON_BYTES:
        raise ValueError("structured warnings exceed the JSON byte limit")
    return normalized


def safe_exception_evidence(exc: BaseException, reason_code: str) -> dict[str, str]:
    """Return bounded exception metadata without paths, credentials, or tracebacks."""
    return safe_exception_record(exc, reason_code)
