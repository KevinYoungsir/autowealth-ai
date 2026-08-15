"""Deterministic serial coordination for explicit EOD dataset batches."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
import threading
from typing import Dict, Mapping, Optional, Protocol, Tuple, Type, TypeVar, runtime_checkable

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
)

from .coordinator import (
    EODIncrementalCoordinator,
    EODIncrementalCoordinatorError,
    EODIncrementalUpdateResult,
)
from .planning import EODRevisionPolicy
from .schemas import EODDatasetKey, EODDateRange, EODUpdateRequest
from .versioning import validate_generation_id

MAX_EOD_BATCH_DATASETS = 256

_EnumType = TypeVar("_EnumType", bound=Enum)
_MACHINE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_LOCK_KEY_PATTERN = re.compile(r"^eod-dataset-[0-9a-f]{64}$")
_BATCH_ID_PATTERN = re.compile(r"^batch-[0-9a-f]{64}$")
_SAFE_FAILURE_FALLBACK = "The EOD batch dataset operation failed safely."


def _enum_value(value: object, enum_type: Type[_EnumType], field_name: str) -> _EnumType:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a supported string enum value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {field_name}: {value}") from exc


def _json_text(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_message(value: object) -> str:
    if type(value) is not str or not value:
        return _SAFE_FAILURE_FALLBACK
    if contains_absolute_path(value) or contains_sensitive_value(value):
        return _SAFE_FAILURE_FALLBACK
    sanitized = sanitize_public_text(value)[:512]
    if not sanitized or contains_absolute_path(sanitized) or contains_sensitive_value(sanitized):
        return _SAFE_FAILURE_FALLBACK
    return sanitized


class EODBatchFailurePolicy(str, Enum):
    """Explicit policy for ordinary per-dataset execution failures."""

    STOP_ON_FAILURE = "stop_on_failure"
    CONTINUE_ON_FAILURE = "continue_on_failure"


class EODBatchStatus(str, Enum):
    """Stable aggregate outcomes for one explicit dataset batch."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    FULL_REFRESH_REQUIRED = "full_refresh_required"


class EODBatchDatasetStatus(str, Enum):
    """Stable outcomes for one dataset inside a batch."""

    SUCCESS = "success"
    DRY_RUN = "dry_run"
    FULL_REFRESH_REQUIRED = "full_refresh_required"
    FAILED = "failed"
    SKIPPED = "skipped"


class EODBatchFailureSource(str, Enum):
    """Finite source classification for safe batch failures."""

    BATCH = "batch"
    LOCK = "lock"
    COORDINATOR = "coordinator"


class EODBatchValidationErrorCode(str, Enum):
    """Stable fail-closed validation errors raised before batch execution."""

    EMPTY_BATCH = "empty_batch"
    BATCH_TOO_LARGE = "batch_too_large"
    DUPLICATE_DATASET = "duplicate_dataset"
    COORDINATOR_UNAVAILABLE = "coordinator_unavailable"


_VALIDATION_MESSAGES = {
    EODBatchValidationErrorCode.EMPTY_BATCH: "The EOD batch cannot be empty.",
    EODBatchValidationErrorCode.BATCH_TOO_LARGE: "The EOD batch exceeds the dataset limit.",
    EODBatchValidationErrorCode.DUPLICATE_DATASET: (
        "The EOD batch contains a duplicate dataset identity."
    ),
    EODBatchValidationErrorCode.COORDINATOR_UNAVAILABLE: (
        "The EOD batch has no coordinator for a requested dataset."
    ),
}


class EODBatchValidationError(ValueError):
    """Safe validation error that is raised before any dataset is executed."""

    def __init__(self, code: EODBatchValidationErrorCode) -> None:
        normalized = _enum_value(code, EODBatchValidationErrorCode, "code")
        self.code = normalized
        self.message = _VALIDATION_MESSAGES[normalized]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODBatchDatasetRequest:
    """Explicit inputs for one dataset execution within a batch."""

    dataset: EODDatasetKey
    requested_range: EODDateRange
    revision_policy: Optional[EODRevisionPolicy] = None
    generation_id: Optional[str] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if self.revision_policy is not None and type(self.revision_policy) is not EODRevisionPolicy:
            raise TypeError("revision_policy must be an exact EODRevisionPolicy or None")
        if self.generation_id is not None:
            if type(self.generation_id) is not str:
                raise TypeError("generation_id must be an exact string or None")
            validate_generation_id(self.generation_id)
        if self.created_at is not None:
            if (
                type(self.created_at) is not datetime
                or self.created_at.tzinfo is None
                or self.created_at.utcoffset() is None
            ):
                raise ValueError("created_at must be an exact timezone-aware datetime or None")
            object.__setattr__(self, "created_at", self.created_at.astimezone(timezone.utc))

    @property
    def identity(self) -> Tuple[str, str, str, str, str, str]:
        return self.dataset.identity

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "revision_policy": (
                None if self.revision_policy is None else self.revision_policy.to_dict()
            ),
            "generation_id": self.generation_id,
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODBatchRequest:
    """Validated batch request normalized into canonical dataset order."""

    datasets: Tuple[EODBatchDatasetRequest, ...]
    dry_run: bool = False
    failure_policy: EODBatchFailurePolicy = EODBatchFailurePolicy.STOP_ON_FAILURE

    def __post_init__(self) -> None:
        if type(self.datasets) not in (list, tuple):
            raise TypeError("datasets must be an exact list or exact tuple")
        datasets = tuple(self.datasets)
        if not datasets:
            raise EODBatchValidationError(EODBatchValidationErrorCode.EMPTY_BATCH)
        if len(datasets) > MAX_EOD_BATCH_DATASETS:
            raise EODBatchValidationError(EODBatchValidationErrorCode.BATCH_TOO_LARGE)
        if any(type(item) is not EODBatchDatasetRequest for item in datasets):
            raise TypeError("datasets must contain exact EODBatchDatasetRequest values")
        identities = tuple(item.identity for item in datasets)
        if len(set(identities)) != len(identities):
            raise EODBatchValidationError(EODBatchValidationErrorCode.DUPLICATE_DATASET)
        if type(self.dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")
        failure_policy = _enum_value(
            self.failure_policy,
            EODBatchFailurePolicy,
            "failure_policy",
        )
        object.__setattr__(
            self, "datasets", tuple(sorted(datasets, key=lambda item: item.identity))
        )
        object.__setattr__(self, "failure_policy", failure_policy)

    @property
    def batch_id(self) -> str:
        digest = hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()
        return f"batch-{digest}"

    def to_dict(self) -> dict[str, object]:
        return {
            "datasets": [item.to_dict() for item in self.datasets],
            "dry_run": self.dry_run,
            "failure_policy": self.failure_policy.value,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODBatchDatasetFailure:
    """Bounded public failure without raw dependency exception text."""

    code: str
    source: EODBatchFailureSource
    message: str
    retryable: bool = False
    coordinator_error: Optional[EODIncrementalCoordinatorError] = None

    def __post_init__(self) -> None:
        if type(self.code) is not str or _MACHINE_CODE_PATTERN.fullmatch(self.code) is None:
            raise ValueError("code must be a stable lowercase machine identifier")
        source = _enum_value(self.source, EODBatchFailureSource, "source")
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be a strict boolean")
        if self.coordinator_error is not None:
            if type(self.coordinator_error) is not EODIncrementalCoordinatorError:
                raise TypeError("coordinator_error must be exact or None")
            if source is not EODBatchFailureSource.COORDINATOR:
                raise ValueError("coordinator_error requires coordinator source")
            if (
                self.code != self.coordinator_error.code.value
                or self.retryable is not self.coordinator_error.retryable
            ):
                raise ValueError("failure fields must match coordinator_error")
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "message", _safe_message(self.message))

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "source": self.source.value,
            "message": self.message,
            "retryable": self.retryable,
            "coordinator_error": (
                None if self.coordinator_error is None else self.coordinator_error.to_dict()
            ),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


def eod_dataset_lock_key(dataset: EODDatasetKey) -> str:
    """Return a stable cross-process lock identity without using Python hash()."""

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    serialized = _json_text(list(dataset.identity)).encode("utf-8")
    return f"eod-dataset-{hashlib.sha256(serialized).hexdigest()}"


@runtime_checkable
class EODDatasetLockManager(Protocol):
    """Non-blocking lock contract for canonical EOD dataset keys."""

    def acquire(self, lock_key: str) -> bool: ...

    def release(self, lock_key: str) -> None: ...


class InProcessEODDatasetLockManager:
    """Process-local non-blocking lock registry; it is not a distributed lock."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._held_keys: set[str] = set()

    def acquire(self, lock_key: str) -> bool:
        self._require_lock_key(lock_key)
        with self._guard:
            if lock_key in self._held_keys:
                return False
            self._held_keys.add(lock_key)
            return True

    def release(self, lock_key: str) -> None:
        self._require_lock_key(lock_key)
        with self._guard:
            if lock_key not in self._held_keys:
                raise RuntimeError("dataset lock is not held")
            self._held_keys.remove(lock_key)

    @staticmethod
    def _require_lock_key(lock_key: object) -> str:
        if type(lock_key) is not str or _LOCK_KEY_PATTERN.fullmatch(lock_key) is None:
            raise ValueError("lock_key must be a canonical EOD dataset lock key")
        return lock_key


@dataclass(frozen=True)
class EODBatchDatasetResult:
    """One deterministic dataset outcome inside a batch."""

    request: EODBatchDatasetRequest
    status: EODBatchDatasetStatus
    update_result: Optional[EODIncrementalUpdateResult] = None
    failure: Optional[EODBatchDatasetFailure] = None
    lock_key: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.request) is not EODBatchDatasetRequest:
            raise TypeError("request must be an exact EODBatchDatasetRequest")
        status = _enum_value(self.status, EODBatchDatasetStatus, "status")
        if self.update_result is not None:
            if type(self.update_result) is not EODIncrementalUpdateResult:
                raise TypeError("update_result must be exact or None")
            if (
                self.update_result.dataset != self.request.dataset
                or self.update_result.requested_range != self.request.requested_range
            ):
                raise ValueError("update_result must match the dataset request")
        if self.failure is not None and type(self.failure) is not EODBatchDatasetFailure:
            raise TypeError("failure must be an exact EODBatchDatasetFailure or None")
        if self.lock_key is not None and (
            type(self.lock_key) is not str
            or _LOCK_KEY_PATTERN.fullmatch(self.lock_key) is None
            or self.lock_key != eod_dataset_lock_key(self.request.dataset)
        ):
            raise ValueError("lock_key must match the dataset request")

        if status in (
            EODBatchDatasetStatus.SUCCESS,
            EODBatchDatasetStatus.DRY_RUN,
            EODBatchDatasetStatus.FULL_REFRESH_REQUIRED,
        ):
            if self.update_result is None or self.failure is not None:
                raise ValueError("successful dataset outcomes require only an update_result")
        elif self.failure is None:
            raise ValueError("failed and skipped dataset outcomes require a failure")

        if status is EODBatchDatasetStatus.SUCCESS and (
            self.update_result is None
            or self.update_result.dry_run
            or self.update_result.requires_full_refresh
        ):
            raise ValueError("success requires a non-dry-run non-refresh result")
        if status is EODBatchDatasetStatus.DRY_RUN and (
            self.update_result is None
            or not self.update_result.dry_run
            or self.update_result.requires_full_refresh
        ):
            raise ValueError("dry_run requires a planned non-refresh result")
        if status is EODBatchDatasetStatus.FULL_REFRESH_REQUIRED and (
            self.update_result is None or not self.update_result.requires_full_refresh
        ):
            raise ValueError("full_refresh_required requires a matching update result")
        if status is EODBatchDatasetStatus.SKIPPED and (
            self.update_result is not None or self.lock_key is not None
        ):
            raise ValueError("skipped datasets cannot contain execution state")

        object.__setattr__(self, "status", status)

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request.to_dict(),
            "status": self.status.value,
            "update_result": (None if self.update_result is None else self.update_result.to_dict()),
            "failure": None if self.failure is None else self.failure.to_dict(),
            "lock_key": self.lock_key,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODBatchResult:
    """Aggregate batch result derived exclusively from ordered dataset outcomes."""

    request: EODBatchRequest
    status: EODBatchStatus
    results: Tuple[EODBatchDatasetResult, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not EODBatchRequest:
            raise TypeError("request must be an exact EODBatchRequest")
        status = _enum_value(self.status, EODBatchStatus, "status")
        if type(self.results) not in (list, tuple):
            raise TypeError("results must be an exact list or exact tuple")
        results = tuple(self.results)
        if len(results) != len(self.request.datasets):
            raise ValueError("results must cover every requested dataset")
        if any(type(item) is not EODBatchDatasetResult for item in results):
            raise TypeError("results must contain exact EODBatchDatasetResult values")
        if tuple(item.request for item in results) != self.request.datasets:
            raise ValueError("results must preserve canonical request order")
        categorized_count = sum(
            item.status
            in (
                EODBatchDatasetStatus.SUCCESS,
                EODBatchDatasetStatus.DRY_RUN,
                EODBatchDatasetStatus.FAILED,
                EODBatchDatasetStatus.SKIPPED,
                EODBatchDatasetStatus.FULL_REFRESH_REQUIRED,
            )
            for item in results
        )
        if categorized_count != len(results):  # pragma: no cover - enum is exhaustive.
            raise ValueError("results must have mutually exclusive dataset outcomes")
        if status is not self._derived_status(self.request, results):
            raise ValueError("status must match the dataset outcomes")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "results", results)

    @property
    def batch_id(self) -> str:
        value = self.request.batch_id
        if _BATCH_ID_PATTERN.fullmatch(value) is None:  # pragma: no cover - digest is fixed.
            raise RuntimeError("batch identity is invalid")
        return value

    @property
    def dry_run(self) -> bool:
        return self.request.dry_run

    @property
    def requested_count(self) -> int:
        return len(self.results)

    @property
    def attempted_count(self) -> int:
        return sum(item.status is not EODBatchDatasetStatus.SKIPPED for item in self.results)

    @property
    def success_count(self) -> int:
        return sum(
            item.status in (EODBatchDatasetStatus.SUCCESS, EODBatchDatasetStatus.DRY_RUN)
            for item in self.results
        )

    @property
    def failure_count(self) -> int:
        return sum(item.status is EODBatchDatasetStatus.FAILED for item in self.results)

    @property
    def skipped_count(self) -> int:
        return sum(item.status is EODBatchDatasetStatus.SKIPPED for item in self.results)

    @property
    def full_refresh_required_count(self) -> int:
        return sum(
            item.status is EODBatchDatasetStatus.FULL_REFRESH_REQUIRED for item in self.results
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "status": self.status.value,
            "dry_run": self.dry_run,
            "failure_policy": self.request.failure_policy.value,
            "requested_count": self.requested_count,
            "attempted_count": self.attempted_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "skipped_count": self.skipped_count,
            "full_refresh_required_count": self.full_refresh_required_count,
            "results": [item.to_dict() for item in self.results],
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())

    @staticmethod
    def _derived_status(
        request: EODBatchRequest,
        results: Tuple[EODBatchDatasetResult, ...],
    ) -> EODBatchStatus:
        success_count = sum(
            item.status in (EODBatchDatasetStatus.SUCCESS, EODBatchDatasetStatus.DRY_RUN)
            for item in results
        )
        failure_count = sum(item.status is EODBatchDatasetStatus.FAILED for item in results)
        skipped_count = sum(item.status is EODBatchDatasetStatus.SKIPPED for item in results)
        refresh_count = sum(
            item.status is EODBatchDatasetStatus.FULL_REFRESH_REQUIRED for item in results
        )
        if request.dry_run and failure_count == 0 and skipped_count == 0:
            return EODBatchStatus.DRY_RUN
        if refresh_count == len(results):
            return EODBatchStatus.FULL_REFRESH_REQUIRED
        if success_count == 0 and (failure_count or skipped_count or refresh_count):
            return EODBatchStatus.FAILED
        if failure_count or skipped_count or refresh_count:
            return EODBatchStatus.PARTIAL_SUCCESS
        return EODBatchStatus.SUCCESS


class EODBatchCoordinator:
    """Run explicit datasets serially through existing single-dataset coordinators."""

    def __init__(
        self,
        coordinators: Mapping[EODDatasetKey, EODIncrementalCoordinator],
        lock_manager: EODDatasetLockManager,
    ) -> None:
        if type(coordinators) is not dict or not coordinators:
            raise TypeError("coordinators must be a non-empty exact dict")
        normalized: Dict[EODDatasetKey, EODIncrementalCoordinator] = {}
        for dataset, coordinator in coordinators.items():
            if type(dataset) is not EODDatasetKey:
                raise TypeError("coordinator keys must be exact EODDatasetKey values")
            if type(coordinator) is not EODIncrementalCoordinator:
                raise TypeError("coordinator values must be exact EODIncrementalCoordinator values")
            normalized[dataset] = coordinator
        if not isinstance(lock_manager, EODDatasetLockManager):
            raise TypeError("lock_manager must implement EODDatasetLockManager")
        self._coordinators = normalized
        self._lock_manager = lock_manager

    def run(self, request: EODBatchRequest) -> EODBatchResult:
        """Execute one canonical batch without retries or parallel provider calls."""

        if type(request) is not EODBatchRequest:
            raise TypeError("request must be an exact EODBatchRequest")
        if any(item.dataset not in self._coordinators for item in request.datasets):
            raise EODBatchValidationError(EODBatchValidationErrorCode.COORDINATOR_UNAVAILABLE)

        outcomes = []
        stop = False
        for dataset_request in request.datasets:
            if stop:
                outcomes.append(self._skipped_result(dataset_request))
                continue
            outcome = self._run_dataset(dataset_request, request.dry_run)
            outcomes.append(outcome)
            if (
                outcome.status is EODBatchDatasetStatus.FAILED
                and request.failure_policy is EODBatchFailurePolicy.STOP_ON_FAILURE
            ):
                stop = True

        normalized_outcomes = tuple(outcomes)
        status = EODBatchResult._derived_status(request, normalized_outcomes)
        return EODBatchResult(request=request, status=status, results=normalized_outcomes)

    def _run_dataset(
        self,
        request: EODBatchDatasetRequest,
        dry_run: bool,
    ) -> EODBatchDatasetResult:
        coordinator = self._coordinators[request.dataset]
        update_request = EODUpdateRequest(
            dataset=request.dataset,
            requested_range=request.requested_range,
            dry_run=dry_run,
        )
        if dry_run:
            return self._execute_coordinator(coordinator, request, update_request, None)

        lock_key = eod_dataset_lock_key(request.dataset)
        try:
            acquired = self._lock_manager.acquire(lock_key)
        except Exception:
            return self._failed_result(
                request,
                "lock_acquisition_failed",
                EODBatchFailureSource.LOCK,
                "The EOD dataset lock could not be acquired safely.",
                lock_key=lock_key,
            )
        if type(acquired) is not bool:
            return self._failed_result(
                request,
                "lock_contract_violation",
                EODBatchFailureSource.LOCK,
                "The EOD dataset lock returned an invalid acquisition result.",
                lock_key=lock_key,
            )
        if not acquired:
            return self._failed_result(
                request,
                "lock_unavailable",
                EODBatchFailureSource.LOCK,
                "The EOD dataset is already being updated.",
                lock_key=lock_key,
            )

        outcome: Optional[EODBatchDatasetResult] = None
        release_failed = False
        try:
            outcome = self._execute_coordinator(coordinator, request, update_request, lock_key)
        finally:
            try:
                self._lock_manager.release(lock_key)
            except Exception:
                release_failed = True
        if release_failed:
            return self._failed_result(
                request,
                "lock_release_failed",
                EODBatchFailureSource.LOCK,
                "The EOD dataset lock could not be released safely.",
                lock_key=lock_key,
                update_result=None if outcome is None else outcome.update_result,
            )
        if outcome is None:  # pragma: no cover - BaseException exits after finally.
            raise RuntimeError("dataset outcome is unavailable")
        return outcome

    @staticmethod
    def _execute_coordinator(
        coordinator: EODIncrementalCoordinator,
        request: EODBatchDatasetRequest,
        update_request: EODUpdateRequest,
        lock_key: Optional[str],
    ) -> EODBatchDatasetResult:
        try:
            update_result = coordinator.execute(
                update_request,
                revision_policy=request.revision_policy,
                generation_id=request.generation_id,
                created_at=request.created_at,
            )
        except EODIncrementalCoordinatorError as exc:
            failure = EODBatchDatasetFailure(
                code=exc.code.value,
                source=EODBatchFailureSource.COORDINATOR,
                message=exc.message,
                retryable=exc.retryable,
                coordinator_error=exc,
            )
            return EODBatchDatasetResult(
                request=request,
                status=EODBatchDatasetStatus.FAILED,
                failure=failure,
                lock_key=lock_key,
            )

        status = (
            EODBatchDatasetStatus.FULL_REFRESH_REQUIRED
            if update_result.requires_full_refresh
            else (
                EODBatchDatasetStatus.DRY_RUN
                if update_result.dry_run
                else EODBatchDatasetStatus.SUCCESS
            )
        )
        return EODBatchDatasetResult(
            request=request,
            status=status,
            update_result=update_result,
            lock_key=lock_key,
        )

    @staticmethod
    def _failed_result(
        request: EODBatchDatasetRequest,
        code: str,
        source: EODBatchFailureSource,
        message: str,
        *,
        lock_key: Optional[str] = None,
        update_result: Optional[EODIncrementalUpdateResult] = None,
    ) -> EODBatchDatasetResult:
        return EODBatchDatasetResult(
            request=request,
            status=EODBatchDatasetStatus.FAILED,
            update_result=update_result,
            failure=EODBatchDatasetFailure(
                code=code,
                source=source,
                message=message,
            ),
            lock_key=lock_key,
        )

    @staticmethod
    def _skipped_result(request: EODBatchDatasetRequest) -> EODBatchDatasetResult:
        return EODBatchDatasetResult(
            request=request,
            status=EODBatchDatasetStatus.SKIPPED,
            failure=EODBatchDatasetFailure(
                code="stopped_after_failure",
                source=EODBatchFailureSource.BATCH,
                message="The dataset was skipped after an earlier batch failure.",
            ),
        )


__all__ = [
    "EODBatchCoordinator",
    "EODBatchDatasetFailure",
    "EODBatchDatasetRequest",
    "EODBatchDatasetResult",
    "EODBatchDatasetStatus",
    "EODBatchFailurePolicy",
    "EODBatchFailureSource",
    "EODBatchRequest",
    "EODBatchResult",
    "EODBatchStatus",
    "EODBatchValidationError",
    "EODBatchValidationErrorCode",
    "EODDatasetLockManager",
    "InProcessEODDatasetLockManager",
    "MAX_EOD_BATCH_DATASETS",
    "eod_dataset_lock_key",
]
