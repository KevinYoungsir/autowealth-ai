"""Synchronous durable EOD operation worker for one intentional writer process."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import threading
from typing import Callable, Optional, Tuple

from .batch import (
    EODBatchCoordinator,
    EODBatchDatasetRequest,
    EODBatchFailurePolicy,
    EODBatchRequest,
    EODBatchResult,
    EODBatchStatus,
    InProcessEODDatasetLockManager,
)
from .full_refresh import (
    EODFullRefreshExecutor,
    EODFullRefreshRequest,
    EODFullRefreshResult,
    EODFullRefreshStatus,
)
from .job_repository import (
    EODOperationJobRepositoryError,
    EODOperationJobRepositoryErrorCode,
    EODOperationRepositoryHealth,
    EODOperationRepositoryHealthStatus,
)
from .maintenance import (
    EODRepositoryMaintenanceExecutor,
    EODRepositoryMaintenanceRequest,
    EODRepositoryMaintenanceResult,
    EODRepositoryMaintenanceStatus,
)
from .operation_catalog import (
    EODOperationCatalog,
    EODOperationCatalogError,
    EODOperationCatalogErrorCode,
)
from .operation_control import (
    EODCheckpointStage,
    EODLeaseControlState,
    EODLeaseController,
    EODOperationControlError,
    EODOperationWorkerConfig,
    EODUTCClock,
    SystemEODUTCClock,
    eod_generation_id,
    run_eod_checkpoint,
)
from .operations import (
    EODFullRefreshOperationPayload,
    EODIncrementalBatchOperationPayload,
    EODIncrementalSingleOperationPayload,
    EODMaintenanceOperationPayload,
    EODOperationFailurePolicy,
    EODOperationFailureSummary,
    EODOperationJob,
    EODOperationResultSummary,
    EODOperationType,
    validate_worker_id,
)
from .schemas import EODDatasetKey


class EODOperationWorkerStatus(str, Enum):
    NO_WORK = "no_work"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    WORKER_UNSAFE = "worker_unsafe"
    WORKER_FATAL = "worker_fatal"


@dataclass(frozen=True)
class EODOperationWorkerResult:
    status: EODOperationWorkerStatus
    job_id: Optional[str] = None
    diagnostic: Optional[str] = None


class _OperationExecutionFailed(RuntimeError):
    def __init__(self, code: str, stage: str) -> None:
        self.code = code
        self.stage = stage
        super().__init__("The EOD operation failed safely.")


class EODOperationWorker:
    def __init__(
        self,
        job_repository: object,
        catalog: EODOperationCatalog,
        *,
        operations_root: object,
        worker_id: str,
        lock_manager: InProcessEODDatasetLockManager,
        config: Optional[EODOperationWorkerConfig] = None,
        clock: Optional[EODUTCClock] = None,
        thread_factory: Callable[..., threading.Thread] = threading.Thread,
    ) -> None:
        _require_job_repository(job_repository)
        if type(catalog) is not EODOperationCatalog:
            raise TypeError("catalog must be an exact EODOperationCatalog")
        root_type = type(catalog.entries[0].runtime.config.repository_root)
        if type(operations_root) is not root_type or not operations_root.is_absolute():
            raise ValueError("operations_root must be an explicit absolute Path")
        if type(lock_manager) is not InProcessEODDatasetLockManager:
            raise TypeError("lock_manager must be one shared InProcessEODDatasetLockManager")
        if config is None:
            config = EODOperationWorkerConfig()
        if type(config) is not EODOperationWorkerConfig:
            raise TypeError("config must be an exact EODOperationWorkerConfig")
        if clock is None:
            clock = SystemEODUTCClock()
        if not callable(getattr(clock, "now", None)):
            raise TypeError("clock must implement EODUTCClock")
        if not callable(thread_factory):
            raise TypeError("thread_factory must be callable")
        _require_separate_roots(operations_root, catalog)
        self._jobs = job_repository
        self._catalog = catalog
        self._worker_id = validate_worker_id(worker_id)
        self._locks = lock_manager
        self._config = config
        self._clock = clock
        self._thread_factory = thread_factory

    def run_one(self) -> EODOperationWorkerResult:
        health = self._inspect_health()
        if health.status is EODOperationRepositoryHealthStatus.ABSENT:
            return EODOperationWorkerResult(EODOperationWorkerStatus.NO_WORK)
        if health.status is EODOperationRepositoryHealthStatus.INVALID:
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_FATAL,
                diagnostic="repository_invalid",
            )
        try:
            self._jobs.mark_expired_running_abandoned(now=self._now(), limit=256)
        except Exception:
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_FATAL,
                diagnostic="recovery_failed",
            )
        try:
            job = self._jobs.claim_next(
                worker_id=self._worker_id,
                now=self._now(),
                lease_seconds=self._config.lease_duration_seconds,
            )
        except Exception:
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_FATAL,
                diagnostic="claim_failed",
            )
        if job is None:
            return EODOperationWorkerResult(EODOperationWorkerStatus.NO_WORK)
        if type(job) is not EODOperationJob:
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_FATAL,
                diagnostic="claim_failed",
            )

        control = EODLeaseController(job)
        heartbeat_stop = threading.Event()
        heartbeat = self._start_heartbeat(control, heartbeat_stop)
        if heartbeat is None:
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_UNSAFE,
                job_id=job.job_id,
                diagnostic=control.reason_code or "heartbeat_start_failed",
            )

        result = None
        failure = None
        try:
            generation_ids = self._preflight(job)
            try:
                domain_result = self._execute_domain(job, generation_ids, control)
            except _OperationExecutionFailed as exc:
                failure = self._failure(job, exc.code, exc.stage)
            except EODOperationControlError:
                raise
            except Exception:
                code, stage = _execution_failure(job.request.operation_type)
                failure = self._failure(job, code, stage)
            else:
                try:
                    result = self._map_result(job, domain_result, generation_ids)
                except _OperationExecutionFailed as exc:
                    failure = self._failure(job, exc.code, exc.stage)
                except Exception:
                    failure = self._failure(job, "result_mapping_failed", "result_mapping")
        except EODOperationCatalogError as exc:
            failure = self._catalog_failure(job, exc)
        except EODOperationControlError:
            self._stop_heartbeat(control, heartbeat_stop, heartbeat)
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_UNSAFE,
                job_id=job.job_id,
                diagnostic=control.reason_code or "lease_control_failure",
            )

        return self._finish(job, control, heartbeat_stop, heartbeat, result, failure)

    def run_forever(self, stop_event: threading.Event) -> None:
        if not callable(getattr(stop_event, "wait", None)) or not callable(
            getattr(stop_event, "is_set", None)
        ):
            raise TypeError("stop_event must provide wait and is_set")
        while not stop_event.is_set():
            outcome = self.run_one()
            if outcome.status in (
                EODOperationWorkerStatus.WORKER_UNSAFE,
                EODOperationWorkerStatus.WORKER_FATAL,
            ):
                return
            if outcome.status is EODOperationWorkerStatus.NO_WORK:
                stop_event.wait(self._config.poll_interval_seconds)

    def _inspect_health(self) -> EODOperationRepositoryHealth:
        try:
            health = self._jobs.inspect_health()
        except Exception:
            return EODOperationRepositoryHealth(
                EODOperationRepositoryHealthStatus.INVALID,
                reason_code="persistence_failure",
            )
        if type(health) is not EODOperationRepositoryHealth:
            return EODOperationRepositoryHealth(
                EODOperationRepositoryHealthStatus.INVALID,
                reason_code="invalid_health_contract",
            )
        return health

    def _start_heartbeat(
        self,
        control: EODLeaseController,
        stop_event: threading.Event,
    ) -> Optional[threading.Thread]:
        try:
            thread = self._thread_factory(
                target=self._heartbeat_loop,
                args=(control, stop_event),
                name="autowealth-eod-operation-heartbeat",
                daemon=True,
            )
            if not all(callable(getattr(thread, name, None)) for name in ("start", "join")):
                raise TypeError("heartbeat thread contract is invalid")
            thread.start()
            return thread
        except Exception:
            control.mark_unsafe("heartbeat_start_failed")
            stop_event.set()
            return None

    def _heartbeat_loop(
        self,
        control: EODLeaseController,
        stop_event: threading.Event,
    ) -> None:
        while not stop_event.wait(self._config.heartbeat_interval_seconds):
            if not self._renew(control):
                return

    def _renew(self, control: EODLeaseController) -> bool:
        job = control.job
        try:
            renewed = self._jobs.renew_lease(
                job.job_id,
                worker_id=job.worker_id,
                claim_version=job.claim_version,
                now=self._now(),
                lease_seconds=self._config.heartbeat_interval_seconds,
            )
            control.update_ownership(renewed)
            return True
        except EODOperationJobRepositoryError as exc:
            control.mark_unsafe(_lease_reason(exc.code))
        except Exception:
            control.mark_unsafe("lease_control_failure")
        return False

    def _preflight(self, job: EODOperationJob) -> dict[EODDatasetKey, str]:
        datasets = _operation_datasets(job)
        for dataset in datasets:
            self._catalog.require_enabled(dataset)
        if job.request.execution_context != self._catalog.execution_context:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.MIXED_CALENDAR_IDENTITY)
        generation_ids = (
            {}
            if job.request.operation_type is EODOperationType.MAINTENANCE
            else {dataset: eod_generation_id(job, dataset) for dataset in datasets}
        )
        if len(set(generation_ids.values())) != len(generation_ids):
            raise RuntimeError("generation identity collision")
        return generation_ids

    def _execute_domain(
        self,
        job: EODOperationJob,
        generation_ids: dict[EODDatasetKey, str],
        checkpoint: EODLeaseController,
    ) -> object:
        payload = job.request.payload
        if isinstance(payload, EODIncrementalSingleOperationPayload):
            batch = self._batch((payload.dataset,))
            result = batch.run(
                _single_batch_request(payload, job, generation_ids), checkpoint=checkpoint
            )
            if result.status is EODBatchStatus.FAILED:
                raise _OperationExecutionFailed("incremental_execution_failed", "incremental")
            return result
        if isinstance(payload, EODIncrementalBatchOperationPayload):
            batch = self._batch(payload.datasets)
            request = EODBatchRequest(
                datasets=tuple(
                    EODBatchDatasetRequest(
                        dataset=dataset,
                        requested_range=payload.requested_range,
                        revision_policy=payload.revision_policy,
                        generation_id=generation_ids[dataset],
                        created_at=job.started_at,
                    )
                    for dataset in payload.datasets
                ),
                dry_run=payload.dry_run,
                failure_policy=(
                    EODBatchFailurePolicy.STOP_ON_FAILURE
                    if payload.failure_policy is EODOperationFailurePolicy.STOP_ON_FAILURE
                    else EODBatchFailurePolicy.CONTINUE_ON_FAILURE
                ),
            )
            result = batch.run(request, checkpoint=checkpoint)
            if result.status is EODBatchStatus.FAILED:
                raise _OperationExecutionFailed("batch_execution_failed", "batch")
            return result
        if isinstance(payload, EODFullRefreshOperationPayload):
            entry = self._catalog.require_enabled(payload.dataset)
            executor = EODFullRefreshExecutor(
                entry.runtime.repository,
                entry.runtime.provider_chain,
                entry.runtime.calendar,
                self._locks,
            )
            return executor.execute(
                EODFullRefreshRequest(payload.dataset, payload.requested_range, payload.dry_run),
                revision_policy=payload.revision_policy,
                generation_id=generation_ids[payload.dataset],
                created_at=job.started_at,
                checkpoint=checkpoint,
            )
        if isinstance(payload, EODMaintenanceOperationPayload):
            entry = self._catalog.require_enabled(payload.dataset)
            executor = EODRepositoryMaintenanceExecutor(entry.runtime.repository, self._locks)
            return executor.execute(
                EODRepositoryMaintenanceRequest(
                    dataset=payload.dataset,
                    dry_run=payload.dry_run,
                    cleanup_staging=payload.cleanup_staging,
                    cleanup_pointer_temps=payload.cleanup_pointer_temps,
                ),
                checkpoint=checkpoint,
            )
        raise RuntimeError("unsupported operation payload")

    def _batch(
        self,
        datasets: Tuple[EODDatasetKey, ...],
    ) -> EODBatchCoordinator:
        return EODBatchCoordinator(
            {
                dataset: self._catalog.require_enabled(dataset).runtime.coordinator
                for dataset in datasets
            },
            self._locks,
        )

    def _map_result(
        self,
        job: EODOperationJob,
        domain_result: object,
        generation_ids: dict[EODDatasetKey, str],
    ) -> EODOperationResultSummary:
        if type(domain_result) is EODBatchResult:
            code = {
                EODBatchStatus.SUCCESS: "success",
                EODBatchStatus.DRY_RUN: "dry_run",
                EODBatchStatus.PARTIAL_SUCCESS: "partial_success",
                EODBatchStatus.FULL_REFRESH_REQUIRED: "full_refresh_required",
            }.get(domain_result.status)
            if code is None:
                raise _OperationExecutionFailed(
                    (
                        "incremental_execution_failed"
                        if job.request.operation_type is EODOperationType.INCREMENTAL_SINGLE
                        else "batch_execution_failed"
                    ),
                    (
                        "incremental"
                        if job.request.operation_type is EODOperationType.INCREMENTAL_SINGLE
                        else "batch"
                    ),
                )
            summaries = tuple(
                {
                    "dataset": item.request.dataset.to_dict(),
                    "status": item.status.value,
                    "generation_id": generation_ids[item.request.dataset],
                    "published": bool(item.update_result and item.update_result.published),
                    "row_count": 0 if item.update_result is None else item.update_result.row_count,
                }
                for item in domain_result.results
            )
        elif type(domain_result) is EODFullRefreshResult:
            code = {
                EODFullRefreshStatus.FULL_REFRESH_PLANNED: "dry_run",
                EODFullRefreshStatus.FULL_REFRESH_PUBLISHED: "success",
                EODFullRefreshStatus.UNCHANGED_CONTENT: "success",
                EODFullRefreshStatus.NOT_ELIGIBLE: "full_refresh_not_eligible",
            }[domain_result.status]
            summaries = (
                {
                    "dataset": domain_result.request.dataset.to_dict(),
                    "status": domain_result.status.value,
                    "generation_id": generation_ids[domain_result.request.dataset],
                    "published": domain_result.published,
                    "row_count": domain_result.row_count,
                },
            )
        elif type(domain_result) is EODRepositoryMaintenanceResult:
            code = {
                EODRepositoryMaintenanceStatus.EMPTY: "maintenance_empty",
                EODRepositoryMaintenanceStatus.INSPECTED: "maintenance_inspected",
                EODRepositoryMaintenanceStatus.CLEANED: "maintenance_cleaned",
                EODRepositoryMaintenanceStatus.BLOCKED: "maintenance_blocked",
            }[domain_result.status]
            summaries = (
                {
                    "dataset": domain_result.request.dataset.to_dict(),
                    "status": domain_result.status.value,
                    "deleted_count": len(domain_result.deleted_artifacts),
                    "warning_codes": [item.value for item in domain_result.warnings],
                },
            )
        else:
            raise RuntimeError("unsupported operation result")
        return EODOperationResultSummary(
            result_code=code,
            dataset_summaries=summaries,
            metadata={"operation_type": job.request.operation_type.value},
        )

    def _finish(
        self,
        job: EODOperationJob,
        control: EODLeaseController,
        stop_event: threading.Event,
        heartbeat: threading.Thread,
        result: Optional[EODOperationResultSummary],
        failure: Optional[EODOperationFailureSummary],
    ) -> EODOperationWorkerResult:
        if not self._stop_heartbeat(control, stop_event, heartbeat):
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_UNSAFE,
                job_id=job.job_id,
                diagnostic=control.reason_code or "heartbeat_shutdown_failed",
            )
        if not self._renew(control):
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_UNSAFE,
                job_id=job.job_id,
                diagnostic=control.reason_code or "lease_control_failure",
            )
        try:
            run_eod_checkpoint(
                control,
                EODCheckpointStage.BEFORE_TERMINAL_TRANSITION,
            )
            owned = control.job
            if result is not None:
                self._jobs.complete(
                    job.job_id,
                    worker_id=owned.worker_id,
                    claim_version=owned.claim_version,
                    result=result,
                    now=self._now(),
                )
                status = EODOperationWorkerStatus.JOB_COMPLETED
            elif failure is not None:
                self._jobs.fail(
                    job.job_id,
                    worker_id=owned.worker_id,
                    claim_version=owned.claim_version,
                    failure=failure,
                    now=self._now(),
                )
                status = EODOperationWorkerStatus.JOB_FAILED
            else:
                raise RuntimeError("terminal outcome is unavailable")
            control.mark_terminal()
            return EODOperationWorkerResult(status, job_id=job.job_id)
        except Exception:
            control.mark_unsafe("terminal_transition_failed")
            return EODOperationWorkerResult(
                EODOperationWorkerStatus.WORKER_UNSAFE,
                job_id=job.job_id,
                diagnostic="terminal_transition_failed",
            )

    @staticmethod
    def _stop_heartbeat(
        control: EODLeaseController,
        stop_event: threading.Event,
        heartbeat: threading.Thread,
    ) -> bool:
        stop_event.set()
        try:
            heartbeat.join()
            if callable(getattr(heartbeat, "is_alive", None)) and heartbeat.is_alive():
                raise RuntimeError("heartbeat thread did not stop")
        except Exception:
            control.mark_unsafe("heartbeat_shutdown_failed")
        return control.state is EODLeaseControlState.ACTIVE

    @staticmethod
    def _failure(
        job: EODOperationJob,
        code: str,
        stage: str,
    ) -> EODOperationFailureSummary:
        return EODOperationFailureSummary(
            error_code=code,
            stage=stage,
            safe_message="The EOD operation failed safely.",
            retryable=False,
            datasets=_operation_datasets(job),
        )

    @classmethod
    def _catalog_failure(
        cls,
        job: EODOperationJob,
        error: EODOperationCatalogError,
    ) -> EODOperationFailureSummary:
        code = (
            error.code.value
            if error.code
            in (
                EODOperationCatalogErrorCode.DATASET_NOT_IN_CATALOG,
                EODOperationCatalogErrorCode.DATASET_DISABLED,
            )
            else "execution_context_mismatch"
        )
        return cls._failure(job, code, "catalog")

    def _now(self) -> datetime:
        value = self._clock.now()
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("clock must return an exact timezone-aware datetime")
        return value.astimezone(timezone.utc)


def _single_batch_request(
    payload: EODIncrementalSingleOperationPayload,
    job: EODOperationJob,
    generation_ids: dict[EODDatasetKey, str],
) -> EODBatchRequest:
    return EODBatchRequest(
        datasets=(
            EODBatchDatasetRequest(
                dataset=payload.dataset,
                requested_range=payload.requested_range,
                revision_policy=payload.revision_policy,
                generation_id=generation_ids[payload.dataset],
                created_at=job.started_at,
            ),
        ),
        dry_run=payload.dry_run,
    )


def _operation_datasets(job: EODOperationJob) -> Tuple[EODDatasetKey, ...]:
    payload = job.request.payload
    if isinstance(payload, EODIncrementalBatchOperationPayload):
        return payload.datasets
    return (payload.dataset,)


def _execution_failure(operation_type: EODOperationType) -> Tuple[str, str]:
    return {
        EODOperationType.INCREMENTAL_SINGLE: ("incremental_execution_failed", "incremental"),
        EODOperationType.INCREMENTAL_BATCH: ("batch_execution_failed", "batch"),
        EODOperationType.FULL_REFRESH: ("full_refresh_execution_failed", "full_refresh"),
        EODOperationType.MAINTENANCE: ("maintenance_execution_failed", "maintenance"),
    }[operation_type]


def _lease_reason(code: EODOperationJobRepositoryErrorCode) -> str:
    return {
        EODOperationJobRepositoryErrorCode.LEASE_CONFLICT: "lease_conflict",
        EODOperationJobRepositoryErrorCode.PERSISTENCE_BUSY: "lease_persistence_busy",
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE: "lease_persistence_failure",
    }.get(code, "lease_control_failure")


def _require_job_repository(repository: object) -> None:
    methods = (
        "inspect_health",
        "mark_expired_running_abandoned",
        "claim_next",
        "renew_lease",
        "complete",
        "fail",
    )
    if any(not callable(getattr(repository, name, None)) for name in methods):
        raise TypeError("job_repository must implement the durable job Repository contract")


def _require_separate_roots(operations_root: object, catalog: EODOperationCatalog) -> None:
    operation = _lexical_root(operations_root)
    for entry in catalog.entries:
        generation = _lexical_root(entry.runtime.config.repository_root)
        common_length = min(len(operation), len(generation))
        if operation[:common_length] == generation[:common_length]:
            raise ValueError("operation and generation roots must be separate and non-nested")


def _lexical_root(value: object) -> Tuple[str, ...]:
    parts = value.parts  # type: ignore[attr-defined]
    if any(part in (".", "..") for part in parts):
        raise ValueError("repository roots must not contain relative path segments")
    return tuple(part.casefold() for part in parts)


__all__ = [
    "EODOperationWorker",
    "EODOperationWorkerResult",
    "EODOperationWorkerStatus",
]
