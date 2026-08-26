"""Durable, side-effect-free contracts for queued EOD operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
import hashlib
import json
import re
import secrets
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Type, TypeVar, Union

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
    validate_bounded_json,
)

from .planning import EODRevisionPolicy
from .providers import EODRevisionStrategy
from .schemas import EODDatasetKey, EODDateRange, EODStructuredWarning

EOD_OPERATION_SCHEMA_VERSION = 1
EOD_OPERATION_JOB_SCHEMA_VERSION = 1
MAX_EOD_OPERATION_DATASETS = 256
MAX_EOD_OPERATION_WARNINGS = 256
MAX_EOD_OPERATION_RECORD_BYTES = 256 * 1024

_EnumType = TypeVar("_EnumType", bound=Enum)
_FINGERPRINT_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_JOB_ID_PATTERN = re.compile(r"^job-[0-9]{8}T[0-9]{12}Z-[0-9a-f]{32}$")
_MACHINE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}$")
_WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,63}$")


class EODOperationType(str, Enum):
    INCREMENTAL_SINGLE = "incremental_single"
    INCREMENTAL_BATCH = "incremental_batch"
    FULL_REFRESH = "full_refresh"
    MAINTENANCE = "maintenance"


class EODOperationJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class EODOperationSubmissionStatus(str, Enum):
    CREATED = "created"
    EXISTING_ACTIVE = "existing_active"
    IDEMPOTENT_REPLAY = "idempotent_replay"


class EODOperationFailurePolicy(str, Enum):
    STOP_ON_FAILURE = "stop_on_failure"
    CONTINUE_ON_FAILURE = "continue_on_failure"


def _enum_value(value: object, enum_type: Type[_EnumType], field_name: str) -> _EnumType:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a supported string enum value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {field_name}: {value}") from exc


def _exact_fields(payload: object, expected: frozenset[str], field_name: str) -> dict:
    if type(payload) is not dict:
        raise TypeError(f"{field_name} must be an exact dict")
    if frozenset(payload) != expected or not all(type(key) is str for key in payload):
        raise ValueError(f"{field_name} fields are invalid")
    return payload


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fingerprint(payload: object) -> str:
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _bounded_text(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe bounded identifier")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        raise ValueError(f"{field_name} must not contain paths or credentials")
    return value


def _utc_datetime(value: object, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be an exact timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _datetime_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _date_from_text(value: object, field_name: str) -> date:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must use canonical ISO date serialization")
    return parsed


def _strict_value_from_dict(payload: object, value_type: type, field_name: str):
    if type(payload) is not dict:
        raise TypeError(f"{field_name} must be an exact dict")
    value = value_type(**payload)
    if value.to_dict() != payload:
        raise ValueError(f"{field_name} is not canonical")
    return value


def _dataset_from_dict(payload: object) -> EODDatasetKey:
    return _strict_value_from_dict(payload, EODDatasetKey, "dataset")


def _range_from_dict(payload: object) -> EODDateRange:
    values = _exact_fields(payload, frozenset({"start_date", "end_date"}), "requested_range")
    return EODDateRange(
        _date_from_text(values["start_date"], "start_date"),
        _date_from_text(values["end_date"], "end_date"),
    )


def _revision_from_dict(payload: object) -> EODRevisionPolicy:
    return _strict_value_from_dict(payload, EODRevisionPolicy, "revision_policy")


def _freeze_json(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    return value


def _bounded_json_dict(value: object, field_name: str) -> Mapping[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{field_name} must be an exact dict")
    normalized = validate_bounded_json(
        value,
        field_name=field_name,
        maximum_depth=3,
        maximum_mapping_keys=32,
        maximum_list_items=32,
        maximum_string_length=512,
        maximum_json_bytes=16 * 1024,
    )
    if type(normalized) is not dict:  # pragma: no cover - guarded above.
        raise TypeError(f"{field_name} normalization must remain a dict")
    return _freeze_json(normalized)  # type: ignore[return-value]


def _safe_message(value: object, fallback: str) -> str:
    if type(value) is not str or not value:
        raise ValueError("safe_message must be non-empty text")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        return fallback
    sanitized = sanitize_public_text(value)[:512]
    if not sanitized or contains_absolute_path(sanitized) or contains_sensitive_value(sanitized):
        return fallback
    return sanitized


def _range_payload(requested_range: object, revision_policy: object, dry_run: object) -> None:
    if type(requested_range) is not EODDateRange:
        raise TypeError("requested_range must be an exact EODDateRange")
    if type(revision_policy) is not EODRevisionPolicy:
        raise TypeError("revision_policy must be an exact EODRevisionPolicy")
    if type(dry_run) is not bool:
        raise ValueError("dry_run must be a strict boolean")


def _dataset_tuple(value: object, *, required: bool) -> Tuple[EODDatasetKey, ...]:
    if type(value) not in (list, tuple):
        raise TypeError("datasets must be an exact list or exact tuple")
    datasets = tuple(value)
    if len(datasets) > MAX_EOD_OPERATION_DATASETS or (required and not datasets):
        message = (
            "datasets must contain between 1 and 256 values"
            if required
            else "datasets exceeds the 256-item limit"
        )
        raise ValueError(message)
    if any(type(item) is not EODDatasetKey for item in datasets):
        raise TypeError("datasets must contain exact EODDatasetKey values")
    identities = tuple(item.identity for item in datasets)
    if len(set(identities)) != len(identities):
        raise ValueError("datasets must not contain duplicate identities")
    return tuple(sorted(datasets, key=lambda item: item.identity))


@dataclass(frozen=True)
class EODOperationExecutionContext:
    calendar_identity: str
    execution_config_fingerprint: str

    def __post_init__(self) -> None:
        _bounded_text(self.calendar_identity, "calendar_identity", _SAFE_ID_PATTERN)
        fingerprint = self.execution_config_fingerprint
        if type(fingerprint) is not str or _FINGERPRINT_PATTERN.fullmatch(fingerprint) is None:
            raise ValueError("execution_config_fingerprint must be sha256:<64 lowercase hex>")

    def to_dict(self) -> dict[str, object]:
        return {
            "calendar_identity": self.calendar_identity,
            "execution_config_fingerprint": self.execution_config_fingerprint,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "EODOperationExecutionContext":
        values = _exact_fields(
            payload,
            frozenset({"calendar_identity", "execution_config_fingerprint"}),
            "execution_context",
        )
        return cls(**values)


@dataclass(frozen=True)
class _EODDatasetRangeOperationPayload:
    dataset: EODDatasetKey
    requested_range: EODDateRange
    revision_policy: EODRevisionPolicy
    dry_run: bool = False

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        _range_payload(self.requested_range, self.revision_policy, self.dry_run)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "revision_policy": self.revision_policy.to_dict(),
            "dry_run": self.dry_run,
        }


@dataclass(frozen=True)
class EODIncrementalSingleOperationPayload(_EODDatasetRangeOperationPayload):
    pass


@dataclass(frozen=True)
class EODIncrementalBatchOperationPayload:
    datasets: Tuple[EODDatasetKey, ...]
    requested_range: EODDateRange
    revision_policy: EODRevisionPolicy
    dry_run: bool = False
    failure_policy: EODOperationFailurePolicy = EODOperationFailurePolicy.STOP_ON_FAILURE

    def __post_init__(self) -> None:
        datasets = _dataset_tuple(self.datasets, required=True)
        _range_payload(self.requested_range, self.revision_policy, self.dry_run)
        failure_policy = _enum_value(
            self.failure_policy, EODOperationFailurePolicy, "failure_policy"
        )
        object.__setattr__(self, "datasets", datasets)
        object.__setattr__(self, "failure_policy", failure_policy)

    def to_dict(self) -> dict[str, object]:
        return {
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "requested_range": self.requested_range.to_dict(),
            "revision_policy": self.revision_policy.to_dict(),
            "dry_run": self.dry_run,
            "failure_policy": self.failure_policy.value,
        }


@dataclass(frozen=True)
class EODFullRefreshOperationPayload(_EODDatasetRangeOperationPayload):
    def __post_init__(self) -> None:
        super().__post_init__()
        if self.revision_policy.strategy is not EODRevisionStrategy.FULL_REFRESH_REQUIRED:
            raise ValueError("full_refresh requires the full_refresh_required revision strategy")


@dataclass(frozen=True)
class EODMaintenanceOperationPayload:
    dataset: EODDatasetKey
    dry_run: bool = True
    cleanup_staging: bool = True
    cleanup_pointer_temps: bool = True

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        for field_name in ("dry_run", "cleanup_staging", "cleanup_pointer_temps"):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"{field_name} must be a strict boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "dry_run": self.dry_run,
            "cleanup_staging": self.cleanup_staging,
            "cleanup_pointer_temps": self.cleanup_pointer_temps,
        }


EODOperationPayload = Union[
    EODIncrementalSingleOperationPayload,
    EODIncrementalBatchOperationPayload,
    EODFullRefreshOperationPayload,
    EODMaintenanceOperationPayload,
]


_PAYLOAD_TYPES = {
    EODOperationType.INCREMENTAL_SINGLE: EODIncrementalSingleOperationPayload,
    EODOperationType.INCREMENTAL_BATCH: EODIncrementalBatchOperationPayload,
    EODOperationType.FULL_REFRESH: EODFullRefreshOperationPayload,
    EODOperationType.MAINTENANCE: EODMaintenanceOperationPayload,
}


@dataclass(frozen=True)
class EODOperationRequest:
    operation_type: EODOperationType
    execution_context: EODOperationExecutionContext
    payload: EODOperationPayload
    schema_version: int = EOD_OPERATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != EOD_OPERATION_SCHEMA_VERSION
        ):
            raise ValueError("schema_version is unsupported")
        operation_type = _enum_value(self.operation_type, EODOperationType, "operation_type")
        if type(self.execution_context) is not EODOperationExecutionContext:
            raise TypeError("execution_context must be exact EODOperationExecutionContext")
        if type(self.payload) is not _PAYLOAD_TYPES[operation_type]:
            raise TypeError("payload type does not match operation_type")
        object.__setattr__(self, "operation_type", operation_type)

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "operation_type": self.operation_type.value,
            "execution_context": self.execution_context.to_dict(),
            "payload": self.payload.to_dict(),
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> "EODOperationRequest":
        values = _exact_fields(
            payload,
            frozenset({"schema_version", "operation_type", "execution_context", "payload"}),
            "operation_request",
        )
        operation_type = _enum_value(values["operation_type"], EODOperationType, "operation_type")
        return cls(
            schema_version=values["schema_version"],
            operation_type=operation_type,
            execution_context=EODOperationExecutionContext.from_dict(values["execution_context"]),
            payload=_payload_from_dict(operation_type, values["payload"]),
        )

    @classmethod
    def from_json(cls, value: object) -> "EODOperationRequest":
        if type(value) is not str:
            raise TypeError("operation request JSON must be text")
        try:
            payload = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("operation request JSON is invalid") from exc
        request = cls.from_dict(payload)
        if request.to_json() != value:
            raise ValueError("operation request JSON is not canonical")
        return request


def _payload_from_dict(operation_type: EODOperationType, payload: object) -> EODOperationPayload:
    fields = {"dataset", "requested_range", "revision_policy", "dry_run"}
    if operation_type is EODOperationType.INCREMENTAL_BATCH:
        fields = {"datasets", "requested_range", "revision_policy", "dry_run", "failure_policy"}
    elif operation_type is EODOperationType.MAINTENANCE:
        fields = {"dataset", "dry_run", "cleanup_staging", "cleanup_pointer_temps"}
    values = dict(_exact_fields(payload, frozenset(fields), "payload"))
    if operation_type is EODOperationType.MAINTENANCE:
        values["dataset"] = _dataset_from_dict(values["dataset"])
    else:
        values["requested_range"] = _range_from_dict(values["requested_range"])
        values["revision_policy"] = _revision_from_dict(values["revision_policy"])
        if operation_type is EODOperationType.INCREMENTAL_BATCH:
            if type(values["datasets"]) not in (list, tuple):
                raise TypeError("datasets must be an exact list or exact tuple")
            values["datasets"] = tuple(_dataset_from_dict(item) for item in values["datasets"])
        else:
            values["dataset"] = _dataset_from_dict(values["dataset"])
    return _PAYLOAD_TYPES[operation_type](**values)


def _dataset_summaries(value: object) -> Tuple[Mapping[str, object], ...]:
    if type(value) not in (list, tuple):
        raise TypeError("dataset_summaries must be an exact list or exact tuple")
    summaries = tuple(value)
    if len(summaries) > MAX_EOD_OPERATION_DATASETS:
        raise ValueError("dataset_summaries exceeds the 256-item limit")
    normalized = tuple(
        _bounded_json_dict(item, f"dataset_summaries[{index}]")
        for index, item in enumerate(summaries)
    )
    size = len(_canonical_json([_thaw_json(item) for item in normalized]).encode("utf-8"))
    if size > 128 * 1024:
        raise ValueError("dataset_summaries exceeds the JSON byte limit")
    return normalized


def _warning_tuple(value: object) -> Tuple[EODStructuredWarning, ...]:
    if type(value) not in (list, tuple):
        raise TypeError("warnings must be an exact list or exact tuple")
    warnings = tuple(value)
    if len(warnings) > MAX_EOD_OPERATION_WARNINGS:
        raise ValueError("warnings exceeds the 256-item limit")
    if any(type(item) is not EODStructuredWarning for item in warnings):
        raise TypeError("warnings must contain exact EODStructuredWarning values")
    return warnings


@dataclass(frozen=True)
class EODOperationResultSummary:
    result_code: str
    dataset_summaries: Tuple[Mapping[str, object], ...] = ()
    warnings: Tuple[EODStructuredWarning, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _bounded_text(self.result_code, "result_code", _MACHINE_CODE_PATTERN)
        object.__setattr__(self, "dataset_summaries", _dataset_summaries(self.dataset_summaries))
        object.__setattr__(self, "warnings", _warning_tuple(self.warnings))
        object.__setattr__(self, "metadata", _bounded_json_dict(self.metadata, "metadata"))

    def to_dict(self) -> dict[str, object]:
        return {
            "result_code": self.result_code,
            "dataset_summaries": [_thaw_json(item) for item in self.dataset_summaries],
            "warnings": [item.to_dict() for item in self.warnings],
            "metadata": _thaw_json(self.metadata),
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class EODOperationFailureSummary:
    error_code: str
    stage: str
    safe_message: str
    retryable: bool
    datasets: Tuple[EODDatasetKey, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _bounded_text(self.error_code, "error_code", _MACHINE_CODE_PATTERN)
        _bounded_text(self.stage, "stage", _MACHINE_CODE_PATTERN)
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be a strict boolean")
        datasets = _dataset_tuple(self.datasets, required=False)
        message = _safe_message(self.safe_message, "The EOD operation failed safely.")
        object.__setattr__(self, "safe_message", message)
        object.__setattr__(self, "datasets", datasets)
        object.__setattr__(self, "details", _bounded_json_dict(self.details, "details"))

    def to_dict(self) -> dict[str, object]:
        return {
            "error_code": self.error_code,
            "stage": self.stage,
            "safe_message": self.safe_message,
            "retryable": self.retryable,
            "datasets": [item.to_dict() for item in self.datasets],
            "details": _thaw_json(self.details),
        }

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


def generate_eod_operation_job_id(now: datetime) -> str:
    normalized = _utc_datetime(now, "now")
    return f"job-{normalized.strftime('%Y%m%dT%H%M%S%fZ')}-{secrets.token_hex(16)}"


def validate_eod_operation_job_id(value: object, field_name: str = "job_id") -> str:
    if type(value) is not str or _JOB_ID_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} has an invalid format")
    return value


def validate_operation_fingerprint(value: object) -> str:
    if type(value) is not str or _FINGERPRINT_PATTERN.fullmatch(value) is None:
        raise ValueError("operation_fingerprint must be sha256:<64 lowercase hex>")
    return value


def validate_worker_id(value: object) -> str:
    return _bounded_text(value, "worker_id", _WORKER_ID_PATTERN)


@dataclass(frozen=True)
class EODOperationJob:
    job_id: str
    request: EODOperationRequest
    operation_fingerprint: str
    status: EODOperationJobStatus
    created_at: datetime
    retry_of_job_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    claim_version: Optional[int] = None
    lease_expires_at: Optional[datetime] = None
    result: Optional[EODOperationResultSummary] = None
    failure: Optional[EODOperationFailureSummary] = None
    schema_version: int = EOD_OPERATION_JOB_SCHEMA_VERSION
    record_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != EOD_OPERATION_JOB_SCHEMA_VERSION
        ):
            raise ValueError("job schema_version is unsupported")
        validate_eod_operation_job_id(self.job_id)
        if type(self.request) is not EODOperationRequest:
            raise TypeError("request must be an exact EODOperationRequest")
        fingerprint = validate_operation_fingerprint(self.operation_fingerprint)
        if fingerprint != self.request.fingerprint:
            raise ValueError("operation_fingerprint does not match request")
        status = _enum_value(self.status, EODOperationJobStatus, "status")
        created_at = _utc_datetime(self.created_at, "created_at")
        retry_of = (
            None
            if self.retry_of_job_id is None
            else validate_eod_operation_job_id(self.retry_of_job_id, "retry_of_job_id")
        )
        if retry_of == self.job_id:
            raise ValueError("retry_of_job_id cannot reference the same job")
        started_at = self._optional_time(self.started_at, "started_at")
        finished_at = self._optional_time(self.finished_at, "finished_at")
        lease_expires_at = self._optional_time(self.lease_expires_at, "lease_expires_at")
        worker_id = None if self.worker_id is None else validate_worker_id(self.worker_id)
        claim_version = self.claim_version
        if claim_version is not None and (
            isinstance(claim_version, bool) or type(claim_version) is not int or claim_version < 1
        ):
            raise ValueError("claim_version must be a positive exact integer or None")
        if self.result is not None and type(self.result) is not EODOperationResultSummary:
            raise TypeError("result must be exact EODOperationResultSummary or None")
        if self.failure is not None and type(self.failure) is not EODOperationFailureSummary:
            raise TypeError("failure must be exact EODOperationFailureSummary or None")
        for name, value in (
            ("status", status),
            ("created_at", created_at),
            ("retry_of_job_id", retry_of),
            ("started_at", started_at),
            ("finished_at", finished_at),
            ("worker_id", worker_id),
            ("claim_version", claim_version),
            ("lease_expires_at", lease_expires_at),
        ):
            object.__setattr__(self, name, value)
        self._validate_lifecycle()
        expected_sha = _fingerprint(self.logical_record_dict())
        if self.record_sha256 is not None and self.record_sha256 != expected_sha:
            raise ValueError("record_sha256 does not match the logical job record")
        object.__setattr__(self, "record_sha256", expected_sha)
        if len(self.to_json().encode("utf-8")) > MAX_EOD_OPERATION_RECORD_BYTES:
            raise ValueError("logical job record exceeds the 256 KiB limit")

    @staticmethod
    def _optional_time(value: object, field_name: str) -> Optional[datetime]:
        return None if value is None else _utc_datetime(value, field_name)

    def _validate_lifecycle(self) -> None:
        if self.status is EODOperationJobStatus.QUEUED:
            invalid = any(
                value is not None
                for value in (
                    self.started_at,
                    self.finished_at,
                    self.worker_id,
                    self.claim_version,
                    self.lease_expires_at,
                    self.result,
                    self.failure,
                )
            )
        elif self.status is EODOperationJobStatus.RUNNING:
            invalid = (
                self.started_at is None
                or self.worker_id is None
                or self.claim_version is None
                or self.lease_expires_at is None
                or self.started_at < self.created_at
                or self.lease_expires_at <= self.started_at
                or self.finished_at is not None
                or self.result is not None
                or self.failure is not None
            )
        else:
            required = (self.started_at, self.finished_at, self.worker_id, self.claim_version)
            invalid = (
                any(value is None for value in required)
                or self.started_at < self.created_at
                or self.finished_at < self.started_at
                or self.lease_expires_at is not None
                or (
                    self.status is EODOperationJobStatus.COMPLETED
                    and (self.result is None or self.failure is not None)
                )
                or (
                    self.status is not EODOperationJobStatus.COMPLETED
                    and (self.failure is None or self.result is not None)
                )
            )
        if invalid:
            raise ValueError(f"{self.status.value} job lifecycle fields are inconsistent")

    def logical_record_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "request": self.request.to_dict(),
            "operation_fingerprint": self.operation_fingerprint,
            "retry_of_job_id": self.retry_of_job_id,
            "status": self.status.value,
            "created_at": _datetime_text(self.created_at),
            "started_at": None if self.started_at is None else _datetime_text(self.started_at),
            "finished_at": None if self.finished_at is None else _datetime_text(self.finished_at),
            "worker_id": self.worker_id,
            "claim_version": self.claim_version,
            "lease_expires_at": (
                None if self.lease_expires_at is None else _datetime_text(self.lease_expires_at)
            ),
            "result": None if self.result is None else self.result.to_dict(),
            "failure": None if self.failure is None else self.failure.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.logical_record_dict(), "record_sha256": self.record_sha256}

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class EODOperationSubmission:
    status: EODOperationSubmissionStatus
    job: EODOperationJob

    def __post_init__(self) -> None:
        status = _enum_value(self.status, EODOperationSubmissionStatus, "status")
        if type(self.job) is not EODOperationJob:
            raise TypeError("job must be an exact EODOperationJob")
        object.__setattr__(self, "status", status)

    def to_dict(self) -> dict[str, object]:
        return {"status": self.status.value, "job": self.job.to_dict()}
