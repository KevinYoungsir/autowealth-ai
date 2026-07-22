"""Stable structured metadata for persisted real-research warnings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

STRUCTURED_WARNINGS_SCHEMA_VERSION = 1


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
_ARTIFACT_REF_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:json|parquet)(?:#(?:/[^#]*)?)?$"
)
_ARTIFACT_FILENAMES = {
    "config.json",
    "run_manifest.json",
    "metrics.json",
    "benchmark_metrics.json",
    "benchmark_diagnostics.json",
    "warnings.json",
    "equity_curve.parquet",
    "benchmark_curve.parquet",
    "holdings.parquet",
    "trades.parquet",
    "factor_snapshots.parquet",
}
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?<![a-z0-9])[a-z]:[\\/]")
_WINDOWS_PATH_VALUE = re.compile(r"(?i)(?<![a-z0-9])[a-z]:[\\/][^,;\r\n)\]}\"']*")
_UNC_PATH_VALUE = re.compile(r"\\\\[^,;\r\n)\]}\"']+")
_POSIX_PATH_VALUE = re.compile(r"(?<![:/\w])/(?![/\s])[^,;\r\n)\]}\"']*")
_SECRET_LABEL = (
    r"(?:authorization|proxy[_ .-]?authorization|api[_ .-]?(?:key|token)|"
    r"access[_ .-]?token|refresh[_ .-]?token|client[_ .-]?secret|"
    r"bearer[_ .-]?token|set[_ .-]?cookie|cookie|password|passwd|"
    r"private[_ .-]?key|secret)"
)
_SECRET_ASSIGNMENT = re.compile(rf"(?i)\b{_SECRET_LABEL}\b\s*[:=]")
_SECRET_VALUE = re.compile(rf"(?i)\b{_SECRET_LABEL}\b\s*[:=]\s*[^,;]+")
_BEARER_VALUE = re.compile(r"(?i)\bbearer\s+[^,;\s]+")
_SECRET_KEYS = {
    "authorization",
    "proxy_authorization",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "credential",
    "credentials",
    "private_key",
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


def _secret_key(value: str) -> bool:
    separated = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    separated = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", separated)
    normalized = re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")
    return normalized in _SECRET_KEYS or any(
        normalized.endswith(f"_{suffix}")
        for suffix in (
            "api_key",
            "token",
            "secret",
            "password",
            "private_key",
            "cookie",
        )
    )


def _contains_absolute_path(value: str) -> bool:
    stripped = value.strip()
    if _ARTIFACT_REF_PATTERN.fullmatch(stripped):
        return False
    return bool(
        stripped.startswith(("/", "\\\\"))
        or "file://" in value.lower()
        or _WINDOWS_ABSOLUTE_PATH.search(value)
        or _UNC_PATH_VALUE.search(value)
        or _POSIX_PATH_VALUE.search(value)
    )


def _validate_safe_string(value: str, path: str) -> str:
    if _contains_absolute_path(value):
        raise ValueError(f"{path} must not contain an absolute path")
    if _SECRET_ASSIGNMENT.search(value) or _BEARER_VALUE.search(value):
        raise ValueError(f"{path} must not contain secret-like content")
    return value


def _validated_json_value(value: object, path: str) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return _validate_safe_string(value, path) if isinstance(value, str) else value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must contain only finite floats")
        return value
    if isinstance(value, list):
        return [_validated_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} keys must be strings")
            if _secret_key(key):
                raise ValueError(f"{path} contains a secret-like key")
            result[key] = _validated_json_value(item, f"{path}.{key}")
        return result
    raise TypeError(f"{path} contains a non-JSON-safe value: {type(value).__name__}")


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
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be a string sequence")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
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
        if not isinstance(self.evidence, Mapping):
            raise TypeError("evidence must be a mapping")
        validated_evidence = _validated_json_value(dict(self.evidence), "evidence")
        symbols = _stable_strings(self.affected_symbols, "affected_symbols")
        artifact_refs = _stable_strings(self.artifact_refs, "artifact_refs")
        for reference in artifact_refs:
            filename = reference.split("#", 1)[0]
            if (
                not _ARTIFACT_REF_PATTERN.fullmatch(reference)
                or filename not in _ARTIFACT_FILENAMES
            ):
                raise ValueError(
                    "artifact_refs must contain artifact filenames and JSON pointers only"
                )
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
        if not isinstance(payload, Mapping):
            raise TypeError("structured warning payload must be a mapping")
        keys = set(payload)
        missing = _REQUIRED_FIELDS - keys
        unknown = keys - _REQUIRED_FIELDS - _OPTIONAL_FIELDS
        if missing:
            raise ValueError(f"structured warning is missing required fields: {sorted(missing)}")
        if unknown:
            raise ValueError(f"structured warning contains unknown fields: {sorted(unknown)}")
        affected_symbols = payload.get("affected_symbols", ())
        artifact_refs = payload.get("artifact_refs", ())
        if not isinstance(affected_symbols, (list, tuple)):
            raise TypeError("affected_symbols must be a string sequence")
        if not isinstance(artifact_refs, (list, tuple)):
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
    if isinstance(warnings, (str, bytes)) or isinstance(structured_warnings, (str, bytes)):
        raise TypeError("warning sequences must not be strings")
    normalized = tuple(
        item if isinstance(item, StructuredWarning) else StructuredWarning.from_dict(item)
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
    json.dumps(
        [warning.to_dict() for warning in normalized],
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
    )
    return normalized


def safe_exception_evidence(exc: BaseException, reason_code: str) -> dict[str, str]:
    """Return bounded exception metadata without paths, credentials, or tracebacks."""
    summary = str(exc).replace("\r", " ").replace("\n", " ")
    summary = _WINDOWS_PATH_VALUE.sub("<redacted_path>", summary)
    summary = _UNC_PATH_VALUE.sub("<redacted_path>", summary)
    summary = _POSIX_PATH_VALUE.sub("<redacted_path>", summary)
    summary = _SECRET_VALUE.sub("<redacted_secret>", summary)
    summary = _BEARER_VALUE.sub("<redacted_secret>", summary)
    summary = re.sub(
        r"(?i)traceback\s*\(most recent call last\)\s*:",
        "<redacted_traceback>",
        summary,
    )
    summary = summary[:240].strip() or "provider operation failed"
    return {
        "exception_type": type(exc).__name__,
        "reason_code": reason_code,
        "safe_summary": summary,
    }
