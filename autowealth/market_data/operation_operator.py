"""Explicit application boundary for durable EOD operator commands."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import importlib
from typing import Callable, Mapping, Optional, Tuple

Path = importlib.import_module("pathlib").Path

from .batch import InProcessEODDatasetLockManager
from .composition import ProviderFactory, load_eod_production_config
from .job_repository import LocalEODOperationJobRepository
from .operation_catalog import EODOperationCatalog, build_eod_operation_catalog
from .operation_control import EODOperationWorkerConfig, SystemEODUTCClock
from .operation_worker import EODOperationWorker, EODOperationWorkerResult
from .operations import (
    EODFullRefreshOperationPayload,
    EODIncrementalBatchOperationPayload,
    EODIncrementalSingleOperationPayload,
    EODMaintenanceOperationPayload,
    EODOperationFailurePolicy,
    EODOperationJob,
    EODOperationJobStatus,
    EODOperationRequest,
    EODOperationSubmission,
    EODOperationType,
    validate_eod_operation_job_id,
    validate_worker_id,
)
from .operator_config import EODOperatorConfig
from .planning import EODRevisionPolicy
from .providers import EODRevisionStrategy
from .schemas import EODDatasetKey, EODDateRange


class EODOperationOperatorErrorCode(str, Enum):
    INVALID_INPUT = "invalid_input"
    DUPLICATE_DATASET = "duplicate_dataset"
    DUPLICATE_SELECTOR = "duplicate_selector"
    STORAGE_IDENTITY_NOT_FOUND = "storage_identity_not_found"
    DATASET_DISABLED = "dataset_disabled"
    ROOTS_NOT_SEPARATE = "roots_not_separate"
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    JOB_NOT_FOUND = "job_not_found"
    RETRY_STATUS_INVALID = "retry_status_invalid"
    RETRY_CONTEXT_STALE = "retry_context_stale"
    EXECUTE_CONFIRMATION_REQUIRED = "execute_confirmation_required"


_MESSAGES = {
    EODOperationOperatorErrorCode.INVALID_INPUT: "The EOD operator input is invalid.",
    EODOperationOperatorErrorCode.DUPLICATE_DATASET: "The operator catalog contains a duplicate dataset.",
    EODOperationOperatorErrorCode.DUPLICATE_SELECTOR: "The dataset selector contains a duplicate value.",
    EODOperationOperatorErrorCode.STORAGE_IDENTITY_NOT_FOUND: "The requested storage identity is unavailable.",
    EODOperationOperatorErrorCode.DATASET_DISABLED: "The requested dataset is disabled.",
    EODOperationOperatorErrorCode.ROOTS_NOT_SEPARATE: "Operation and generation storage roots must be separate.",
    EODOperationOperatorErrorCode.CATALOG_UNAVAILABLE: "The EOD operation catalog is unavailable.",
    EODOperationOperatorErrorCode.JOB_NOT_FOUND: "The requested EOD operation job was not found.",
    EODOperationOperatorErrorCode.RETRY_STATUS_INVALID: "The EOD operation job is not eligible for retry.",
    EODOperationOperatorErrorCode.RETRY_CONTEXT_STALE: "The EOD operation execution context is stale.",
    EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED: "Explicit execution confirmation is required.",
}


class EODOperationOperatorError(ValueError):
    def __init__(self, code: EODOperationOperatorErrorCode) -> None:
        if type(code) is not EODOperationOperatorErrorCode:
            raise TypeError("code must be an exact EODOperationOperatorErrorCode")
        self.code = code
        self.message = _MESSAGES[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


class EODOperationOperator:
    """Compose existing operation contracts without scheduling or implicit execution."""

    def __init__(
        self,
        config: EODOperatorConfig,
        *,
        provider_factories: Optional[Mapping[str, ProviderFactory]] = None,
        clock: Optional[object] = None,
        worker_factory: Callable[..., EODOperationWorker] = EODOperationWorker,
    ) -> None:
        if type(config) is not EODOperatorConfig:
            raise TypeError("config must be an exact EODOperatorConfig")
        if provider_factories is not None and type(provider_factories) is not dict:
            raise TypeError("provider_factories must be an exact dict or None")
        if clock is None:
            clock = SystemEODUTCClock()
        if not callable(getattr(clock, "now", None)):
            raise TypeError("clock must provide now()")
        if not callable(worker_factory):
            raise TypeError("worker_factory must be callable")
        self._config = config
        self._provider_factories = provider_factories
        self._clock = clock
        self._worker_factory = worker_factory

    def catalog_inspect(self) -> dict[str, object]:
        catalog = self._catalog()
        return {
            "calendar_identity": catalog.calendar_identity,
            "execution_config_fingerprint": catalog.execution_config_fingerprint,
            "datasets": [
                {
                    "dataset": entry.dataset.to_dict(),
                    "storage_identity": entry.storage_identity,
                    "enabled": entry.enabled,
                    "provider_identities": [
                        {"provider_name": name, "provider_version": version}
                        for name, version in entry.provider_identities
                    ],
                    "calendar_identity": entry.calendar_identity,
                }
                for entry in catalog.entries
            ],
        }

    def jobs_health(self) -> dict[str, object]:
        return self._repository().inspect_health().to_dict()

    def jobs_list(
        self,
        *,
        limit: int = 50,
        statuses: Optional[Tuple[EODOperationJobStatus, ...]] = None,
        operation_types: Optional[Tuple[EODOperationType, ...]] = None,
    ) -> dict[str, object]:
        jobs = self._repository().list_recent(
            limit=limit,
            statuses=statuses,
            operation_types=operation_types,
        )
        return {"jobs": [job.to_dict() for job in jobs]}

    def jobs_show(self, job_id: str) -> dict[str, object]:
        safe_id = _job_id(job_id)
        job = self._repository().get(safe_id)
        if job is None:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.JOB_NOT_FOUND)
        return {"job": job.to_dict()}

    def submit_incremental_single(
        self,
        *,
        storage_identity: str,
        requested_range: EODDateRange,
        revision_policy: EODRevisionPolicy,
        dry_run: bool,
        execute: bool,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, object]:
        mode = _execution_mode(dry_run, execute)
        catalog = self._catalog()
        dataset = self._entry(catalog, storage_identity).dataset
        request = EODOperationRequest(
            operation_type=EODOperationType.INCREMENTAL_SINGLE,
            execution_context=catalog.execution_context,
            payload=EODIncrementalSingleOperationPayload(
                dataset=dataset,
                requested_range=_range(requested_range),
                revision_policy=_revision(revision_policy),
                dry_run=mode,
            ),
        )
        return _submission(self._submit(request, idempotency_key=idempotency_key))

    def submit_incremental_batch(
        self,
        *,
        storage_identities: Tuple[str, ...],
        all_enabled: bool,
        requested_range: EODDateRange,
        revision_policy: EODRevisionPolicy,
        failure_policy: EODOperationFailurePolicy,
        dry_run: bool,
        execute: bool,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, object]:
        mode = _execution_mode(dry_run, execute)
        catalog = self._catalog()
        datasets = self._datasets(catalog, storage_identities, all_enabled)
        request = EODOperationRequest(
            operation_type=EODOperationType.INCREMENTAL_BATCH,
            execution_context=catalog.execution_context,
            payload=EODIncrementalBatchOperationPayload(
                datasets=datasets,
                requested_range=_range(requested_range),
                revision_policy=_revision(revision_policy),
                dry_run=mode,
                failure_policy=failure_policy,
            ),
        )
        return _submission(self._submit(request, idempotency_key=idempotency_key))

    def submit_full_refresh(
        self,
        *,
        storage_identity: str,
        requested_range: EODDateRange,
        dry_run: bool,
        execute: bool,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, object]:
        mode = _execution_mode(dry_run, execute)
        catalog = self._catalog()
        dataset = self._entry(catalog, storage_identity).dataset
        request = EODOperationRequest(
            operation_type=EODOperationType.FULL_REFRESH,
            execution_context=catalog.execution_context,
            payload=EODFullRefreshOperationPayload(
                dataset=dataset,
                requested_range=_range(requested_range),
                revision_policy=EODRevisionPolicy(EODRevisionStrategy.FULL_REFRESH_REQUIRED),
                dry_run=mode,
            ),
        )
        return _submission(self._submit(request, idempotency_key=idempotency_key))

    def submit_maintenance(
        self,
        *,
        storage_identity: str,
        dry_run: bool,
        execute: bool,
        cleanup_staging: bool = True,
        cleanup_pointer_temps: bool = True,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, object]:
        mode = _execution_mode(dry_run, execute)
        catalog = self._catalog()
        dataset = self._entry(catalog, storage_identity).dataset
        request = EODOperationRequest(
            operation_type=EODOperationType.MAINTENANCE,
            execution_context=catalog.execution_context,
            payload=EODMaintenanceOperationPayload(
                dataset=dataset,
                dry_run=mode,
                cleanup_staging=cleanup_staging,
                cleanup_pointer_temps=cleanup_pointer_temps,
            ),
        )
        return _submission(self._submit(request, idempotency_key=idempotency_key))

    def jobs_retry(
        self,
        job_id: str,
        *,
        execute: bool,
        idempotency_key: Optional[str] = None,
    ) -> dict[str, object]:
        if type(execute) is not bool:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
        predecessor = self._repository().get(_job_id(job_id))
        if predecessor is None:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.JOB_NOT_FOUND)
        if predecessor.status not in (
            EODOperationJobStatus.FAILED,
            EODOperationJobStatus.ABANDONED,
        ):
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.RETRY_STATUS_INVALID)
        if not predecessor.request.payload.dry_run and not execute:
            raise EODOperationOperatorError(
                EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED
            )
        catalog = self._catalog()
        if predecessor.request.execution_context != catalog.execution_context:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.RETRY_CONTEXT_STALE)
        submission = self._repository().submit(
            predecessor.request,
            now=self._now(),
            idempotency_key=idempotency_key,
            retry_of_job_id=predecessor.job_id,
        )
        return _submission(submission)

    def worker_run_one(self, *, worker_id: str, execute: bool) -> EODOperationWorkerResult:
        if type(execute) is not bool or not execute:
            raise EODOperationOperatorError(
                EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED
            )
        try:
            safe_worker_id = validate_worker_id(worker_id)
        except (TypeError, ValueError):
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT) from None
        catalog = self._catalog()
        worker = self._worker_factory(
            self._repository(),
            catalog,
            operations_root=self._config.operations_root,
            worker_id=safe_worker_id,
            lock_manager=InProcessEODDatasetLockManager(),
            config=EODOperationWorkerConfig(),
            clock=self._clock,
        )
        result = worker.run_one()
        if type(result) is not EODOperationWorkerResult:
            raise RuntimeError("worker returned an invalid result")
        return result

    def _catalog(self) -> EODOperationCatalog:
        try:
            configs = tuple(
                load_eod_production_config(item.production_config) for item in self._config.datasets
            )
            datasets = tuple(config.dataset for config in configs)
            if len(set(datasets)) != len(datasets):
                raise EODOperationOperatorError(EODOperationOperatorErrorCode.DUPLICATE_DATASET)
            for config in configs:
                _separate_roots(self._config.operations_root, config.repository_root)
            storage = {
                config.dataset: item.storage_identity
                for config, item in zip(configs, self._config.datasets)
            }
            enabled = {
                config.dataset: item.enabled for config, item in zip(configs, self._config.datasets)
            }
            return build_eod_operation_catalog(
                configs,
                storage_identities=storage,
                enabled=enabled,
                provider_factories=self._provider_factories,
            )
        except EODOperationOperatorError:
            raise
        except Exception:
            raise EODOperationOperatorError(
                EODOperationOperatorErrorCode.CATALOG_UNAVAILABLE
            ) from None

    def _entry(self, catalog: EODOperationCatalog, storage_identity: str):
        matches = tuple(
            entry for entry in catalog.entries if entry.storage_identity == storage_identity
        )
        if len(matches) != 1:
            raise EODOperationOperatorError(
                EODOperationOperatorErrorCode.STORAGE_IDENTITY_NOT_FOUND
            )
        if not matches[0].enabled:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.DATASET_DISABLED)
        return matches[0]

    def _datasets(
        self,
        catalog: EODOperationCatalog,
        storage_identities: Tuple[str, ...],
        all_enabled: bool,
    ) -> Tuple[EODDatasetKey, ...]:
        if type(storage_identities) not in (list, tuple) or type(all_enabled) is not bool:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
        selectors = tuple(storage_identities)
        if len(set(selectors)) != len(selectors):
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.DUPLICATE_SELECTOR)
        if all_enabled == bool(selectors):
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
        entries = (
            tuple(entry for entry in catalog.entries if entry.enabled)
            if all_enabled
            else tuple(self._entry(catalog, value) for value in selectors)
        )
        if not entries:
            raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
        return tuple(sorted((entry.dataset for entry in entries), key=lambda item: item.identity))

    def _repository(self) -> LocalEODOperationJobRepository:
        return LocalEODOperationJobRepository(self._config.operations_root)

    def _submit(
        self,
        request: EODOperationRequest,
        *,
        idempotency_key: Optional[str],
    ) -> EODOperationSubmission:
        return self._repository().submit(
            request,
            now=self._now(),
            idempotency_key=idempotency_key,
        )

    def _now(self) -> datetime:
        value = self._clock.now()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return an exact timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _execution_mode(dry_run: object, execute: object) -> bool:
    if type(dry_run) is not bool or type(execute) is not bool or dry_run == execute:
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
    return dry_run


def _range(value: object) -> EODDateRange:
    if type(value) is not EODDateRange:
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
    return value


def _revision(value: object) -> EODRevisionPolicy:
    if type(value) is not EODRevisionPolicy:
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT)
    return value


def _job_id(value: object) -> str:
    try:
        return validate_eod_operation_job_id(value)
    except (TypeError, ValueError):
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.INVALID_INPUT) from None


def _submission(value: EODOperationSubmission) -> dict[str, object]:
    return {"submission_status": value.status.value, "job": value.job.to_dict()}


def _separate_roots(operations_root: Path, generation_root: Path) -> None:
    operation = _root_parts(operations_root)
    generation = _root_parts(generation_root)
    common = min(len(operation), len(generation))
    if operation[:common] == generation[:common]:
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.ROOTS_NOT_SEPARATE)


def _root_parts(value: Path) -> Tuple[str, ...]:
    if (
        not isinstance(value, Path)
        or not value.is_absolute()
        or any(part in (".", "..") for part in value.parts)
    ):
        raise EODOperationOperatorError(EODOperationOperatorErrorCode.ROOTS_NOT_SEPARATE)
    return tuple(part.casefold() for part in value.parts)


__all__ = [
    "EODOperationOperator",
    "EODOperationOperatorError",
    "EODOperationOperatorErrorCode",
]
