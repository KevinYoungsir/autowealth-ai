from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import threading
from typing import Optional

import pytest

import autowealth.market_data.operation_worker as worker_module
from autowealth.market_data.batch import (
    EODBatchDatasetStatus,
    EODBatchFailurePolicy,
    EODBatchStatus,
    InProcessEODDatasetLockManager,
)
from autowealth.market_data.composition import (
    AKSHARE_EQUITY_PROVIDER,
    EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
    EODProductionConfig,
    EODRuntimeStack,
)
from autowealth.market_data.full_refresh import EODFullRefreshStatus
from autowealth.market_data.job_repository import (
    EODOperationJobRepositoryError,
    EODOperationJobRepositoryErrorCode,
    EODOperationRepositoryHealth,
    EODOperationRepositoryHealthStatus,
    LocalEODOperationJobRepository,
)
from autowealth.market_data.local_calendar import (
    EOD_CALENDAR_SCHEMA_VERSION,
    MARKET_TIMEZONE,
    VersionedLocalTradingCalendar,
)
from autowealth.market_data.maintenance import EODRepositoryMaintenanceStatus
from autowealth.market_data.operation_catalog import EODOperationCatalog, EODOperationCatalogEntry
from autowealth.market_data.operation_control import (
    EODCheckpointStage,
    EODLeaseControlState,
    EODLeaseController,
    EODOperationWorkerConfig,
    eod_generation_id,
)
from autowealth.market_data.operation_worker import (
    EODOperationWorker,
    EODOperationWorkerResult,
    EODOperationWorkerStatus,
)
from autowealth.market_data.operations import (
    EODFullRefreshOperationPayload,
    EODIncrementalBatchOperationPayload,
    EODIncrementalSingleOperationPayload,
    EODMaintenanceOperationPayload,
    EODOperationExecutionContext,
    EODOperationFailurePolicy,
    EODOperationFailureSummary,
    EODOperationJob,
    EODOperationJobStatus,
    EODOperationRequest,
    EODOperationType,
    generate_eod_operation_job_id,
)
from autowealth.market_data.planning import EODRevisionPolicy
from autowealth.market_data.provider_resilience import (
    EODProviderRateLimitPolicy,
    EODProviderRetryPolicy,
)
from autowealth.market_data.providers import EODProviderCapability, EODRevisionStrategy
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)
from autowealth.market_data.versioning import validate_generation_id

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 28, 8, tzinfo=timezone.utc)
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)


class OfflineProvider:
    provider_name = AKSHARE_EQUITY_PROVIDER
    provider_version = "fixture-v1"
    endpoint_name = "offline"

    def __init__(self, selected: EODDatasetKey) -> None:
        self.fetch_calls = 0
        self.capabilities = (
            EODProviderCapability(
                market=selected.market,
                venue=selected.venue,
                asset_type=selected.asset_type,
                frequency=selected.frequency,
                adjustment_type=selected.adjustment_type,
                revision_strategy=EODRevisionStrategy.APPEND_ONLY,
            ),
        )

    def fetch(self, request):
        self.fetch_calls += 1
        raise AssertionError("worker unit tests must not contact providers")


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


class PassiveThread:
    def __init__(self, events, **kwargs) -> None:
        self.events = events

    def start(self) -> None:
        self.events.append("heartbeat_start")

    def join(self) -> None:
        self.events.append("heartbeat_join")

    def is_alive(self) -> bool:
        return False


class FakeJobRepository:
    def __init__(
        self,
        jobs=(),
        *,
        health: EODOperationRepositoryHealthStatus = EODOperationRepositoryHealthStatus.HEALTHY,
    ) -> None:
        self.health = health
        self.jobs = {job.job_id: job for job in jobs}
        self.queue = [job.job_id for job in jobs]
        self.events = []
        self.renew_seconds = []
        self.renew_error = None
        self.complete_error = None
        self.expired_remaining = 0
        self.recovery_counts = []

    def inspect_health(self) -> EODOperationRepositoryHealth:
        self.events.append("inspect_health")
        if self.health is EODOperationRepositoryHealthStatus.ABSENT:
            return EODOperationRepositoryHealth(self.health)
        if self.health is EODOperationRepositoryHealthStatus.INVALID:
            return EODOperationRepositoryHealth(self.health, reason_code="corrupt_record")
        return EODOperationRepositoryHealth(self.health, schema_version=1)

    def mark_expired_running_abandoned(self, *, now: datetime, limit: int = 256):
        count = min(self.expired_remaining, limit)
        self.expired_remaining -= count
        self.recovery_counts.append(count)
        self.events.append("recover")
        abandoned = []
        for job_id, job in tuple(self.jobs.items()):
            if (
                len(abandoned) < limit
                and job.status is EODOperationJobStatus.RUNNING
                and job.lease_expires_at <= now
            ):
                failure = EODOperationFailureSummary(
                    "lease_expired",
                    "lease",
                    "The EOD operation lease expired before completion.",
                    True,
                )
                terminal = replace(
                    job,
                    status=EODOperationJobStatus.ABANDONED,
                    finished_at=now,
                    lease_expires_at=None,
                    failure=failure,
                    record_sha256=None,
                )
                self.jobs[job_id] = terminal
                abandoned.append(terminal)
        return tuple(abandoned)

    def claim_next(self, *, worker_id: str, now: datetime, lease_seconds: int):
        self.events.append("claim")
        while self.queue:
            job_id = self.queue.pop(0)
            job = self.jobs[job_id]
            if job.status is not EODOperationJobStatus.QUEUED:
                continue
            claimed = replace(
                job,
                status=EODOperationJobStatus.RUNNING,
                started_at=now,
                worker_id=worker_id,
                claim_version=1,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
                record_sha256=None,
            )
            self.jobs[job_id] = claimed
            return claimed
        return None

    def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        claim_version: int,
        now: datetime,
        lease_seconds: int,
    ) -> EODOperationJob:
        self.events.append("renew")
        self.renew_seconds.append(lease_seconds)
        if isinstance(self.renew_error, EODOperationJobRepositoryErrorCode):
            raise EODOperationJobRepositoryError(self.renew_error)
        if self.renew_error is not None:
            raise self.renew_error
        job = self.jobs[job_id]
        if (
            job.status is not EODOperationJobStatus.RUNNING
            or job.worker_id != worker_id
            or job.claim_version != claim_version
            or job.lease_expires_at <= now
        ):
            raise EODOperationJobRepositoryError(EODOperationJobRepositoryErrorCode.LEASE_CONFLICT)
        renewed = replace(
            job,
            lease_expires_at=job.lease_expires_at + timedelta(seconds=lease_seconds),
            record_sha256=None,
        )
        self.jobs[job_id] = renewed
        return renewed

    def complete(self, job_id: str, *, worker_id, claim_version, result, now):
        self.events.append("complete")
        if self.complete_error is not None:
            raise self.complete_error
        job = self.jobs[job_id]
        terminal = replace(
            job,
            status=EODOperationJobStatus.COMPLETED,
            finished_at=now,
            lease_expires_at=None,
            result=result,
            record_sha256=None,
        )
        self.jobs[job_id] = terminal
        return terminal

    def fail(self, job_id: str, *, worker_id, claim_version, failure, now):
        self.events.append("fail")
        job = self.jobs[job_id]
        terminal = replace(
            job,
            status=EODOperationJobStatus.FAILED,
            finished_at=now,
            lease_expires_at=None,
            failure=failure,
            record_sha256=None,
        )
        self.jobs[job_id] = terminal
        return terminal

    def get(self, job_id: str) -> EODOperationJob:
        return self.jobs[job_id]


class FakeBatchResult:
    def __init__(self, status: EODBatchStatus, datasets) -> None:
        self.status = status
        self.results = tuple(
            SimpleNamespace(
                request=SimpleNamespace(dataset=selected),
                status=(
                    EODBatchDatasetStatus.DRY_RUN
                    if status is EODBatchStatus.DRY_RUN
                    else (
                        EODBatchDatasetStatus.FULL_REFRESH_REQUIRED
                        if status is EODBatchStatus.FULL_REFRESH_REQUIRED
                        else EODBatchDatasetStatus.SUCCESS
                    )
                ),
                update_result=SimpleNamespace(
                    published=status is EODBatchStatus.SUCCESS,
                    row_count=1,
                ),
            )
            for selected in datasets
        )


class FakeFullRefreshResult:
    def __init__(self, status: EODFullRefreshStatus, selected: EODDatasetKey) -> None:
        self.status = status
        self.request = SimpleNamespace(dataset=selected)
        self.published = status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
        self.row_count = 3


class FakeMaintenanceResult:
    def __init__(self, status: EODRepositoryMaintenanceStatus, selected: EODDatasetKey) -> None:
        self.status = status
        self.request = SimpleNamespace(dataset=selected)
        self.deleted_artifacts = (
            ("candidate",) if status is EODRepositoryMaintenanceStatus.CLEANED else ()
        )
        self.warnings = ()


class StubWorker(EODOperationWorker):
    def __init__(self, *args, response=None, **kwargs) -> None:
        self.response = response
        self.execution_count = 0
        self.execution_jobs = []
        self.generation_ids = []
        super().__init__(*args, **kwargs)

    def _execute_domain(self, job, generation_ids, checkpoint):
        self.execution_count += 1
        self.execution_jobs.append(job)
        self.generation_ids.append(dict(generation_ids))
        if isinstance(self.response, BaseException):
            raise self.response
        if callable(self.response):
            return self.response(job, generation_ids, checkpoint)
        return self.response


class CaptureBatch:
    def __init__(self, status: EODBatchStatus) -> None:
        self.status = status
        self.requests = []

    def run(self, request, *, checkpoint=None):
        self.requests.append((request, checkpoint))
        return FakeBatchResult(self.status, tuple(item.dataset for item in request.datasets))


class CaptureBatchWorker(StubWorker):
    def __init__(self, *args, batch: CaptureBatch, **kwargs) -> None:
        self.capture_batch = batch
        super().__init__(*args, **kwargs)

    def _batch(self, datasets):
        return self.capture_batch

    def _execute_domain(self, job, generation_ids, checkpoint):
        return EODOperationWorker._execute_domain(self, job, generation_ids, checkpoint)


def dataset(symbol: str = "600000.SH") -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        Venue.SSE if symbol.endswith(".SH") else Venue.SZSE,
        AssetType.EQUITY,
        symbol,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


def write_calendar(tmp_path: Path) -> Path:
    path = tmp_path / "calendar.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": EOD_CALENDAR_SCHEMA_VERSION,
                "calendar_id": "cn_a_share_worker_fixture",
                "calendar_version": "fixture-v1",
                "timezone": MARKET_TIMEZONE,
                "coverage_start": DAY_1.isoformat(),
                "coverage_end": DAY_2.isoformat(),
                "days": [
                    {"trade_date": DAY_1.isoformat(), "is_trading_day": True},
                    {"trade_date": DAY_2.isoformat(), "is_trading_day": True},
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def catalog(tmp_path: Path, datasets, *, disabled=()) -> EODOperationCatalog:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    entries = []
    for index, selected in enumerate(datasets):
        provider = OfflineProvider(selected)
        config = EODProductionConfig(
            EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
            (tmp_path / f"data-{index}").resolve(),
            (tmp_path / f"calendar-{index}.json").resolve(),
            selected,
            (AKSHARE_EQUITY_PROVIDER,),
            EODProviderRetryPolicy(),
            EODProviderRateLimitPolicy(),
        )
        runtime = EODRuntimeStack(config, calendar, object(), (provider,), object(), object())
        entries.append(
            EODOperationCatalogEntry(
                selected,
                selected not in disabled,
                f"storage-{index}",
                runtime,
            )
        )
    return EODOperationCatalog(tuple(entries))


def request_for(
    selected_catalog: EODOperationCatalog,
    operation_type: EODOperationType,
    datasets,
    *,
    dry_run: bool = False,
    failure_policy: EODOperationFailurePolicy = EODOperationFailurePolicy.STOP_ON_FAILURE,
    execution_context: Optional[EODOperationExecutionContext] = None,
) -> EODOperationRequest:
    values = tuple(datasets)
    requested_range = EODDateRange(DAY_1, DAY_2)
    append = EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY)
    if operation_type is EODOperationType.INCREMENTAL_SINGLE:
        payload = EODIncrementalSingleOperationPayload(values[0], requested_range, append, dry_run)
    elif operation_type is EODOperationType.INCREMENTAL_BATCH:
        payload = EODIncrementalBatchOperationPayload(
            values,
            requested_range,
            append,
            dry_run,
            failure_policy,
        )
    elif operation_type is EODOperationType.FULL_REFRESH:
        payload = EODFullRefreshOperationPayload(
            values[0],
            requested_range,
            EODRevisionPolicy(EODRevisionStrategy.FULL_REFRESH_REQUIRED),
            dry_run,
        )
    else:
        payload = EODMaintenanceOperationPayload(values[0], dry_run=dry_run)
    return EODOperationRequest(
        operation_type,
        selected_catalog.execution_context if execution_context is None else execution_context,
        payload,
    )


def queued_job(request: EODOperationRequest, now: datetime = NOW) -> EODOperationJob:
    return EODOperationJob(
        generate_eod_operation_job_id(now),
        request,
        request.fingerprint,
        EODOperationJobStatus.QUEUED,
        now,
    )


def passive_factory(events):
    def factory(**kwargs):
        return PassiveThread(events, **kwargs)

    return factory


def make_worker(
    tmp_path: Path,
    repository,
    selected_catalog: EODOperationCatalog,
    *,
    response=None,
    clock: Optional[MutableClock] = None,
    thread_factory=None,
    worker_type=StubWorker,
    **kwargs,
):
    events = getattr(repository, "events", [])
    return worker_type(
        repository,
        selected_catalog,
        operations_root=(tmp_path / "operations").resolve(),
        worker_id="worker-1",
        lock_manager=InProcessEODDatasetLockManager(),
        clock=clock or MutableClock(),
        thread_factory=thread_factory or passive_factory(events),
        response=response,
        **kwargs,
    )


def batch_response(status: EODBatchStatus, request: EODOperationRequest) -> FakeBatchResult:
    payload = request.payload
    datasets = (
        payload.datasets
        if isinstance(payload, EODIncrementalBatchOperationPayload)
        else (payload.dataset,)
    )
    return FakeBatchResult(status, datasets)


def test_worker_constructor_has_no_side_effects(tmp_path: Path) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    repository = FakeJobRepository()
    worker = make_worker(tmp_path, repository, selected_catalog)
    assert isinstance(worker, EODOperationWorker)
    assert repository.events == []
    assert not (tmp_path / "operations").exists()
    assert selected_catalog.entries[0].runtime.providers[0].fetch_calls == 0


def test_absent_repository_returns_no_work_and_remains_absent(tmp_path: Path) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    operations = (tmp_path / "operations").resolve()
    repository = LocalEODOperationJobRepository(operations)
    result = make_worker(tmp_path, repository, selected_catalog).run_one()
    assert result.status is EODOperationWorkerStatus.NO_WORK
    assert not operations.exists()


def test_healthy_empty_and_invalid_repository_statuses(tmp_path: Path) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    healthy = make_worker(tmp_path, FakeJobRepository(), selected_catalog).run_one()
    invalid = make_worker(
        tmp_path,
        FakeJobRepository(health=EODOperationRepositoryHealthStatus.INVALID),
        selected_catalog,
    ).run_one()
    assert healthy.status is EODOperationWorkerStatus.NO_WORK
    assert invalid == EODOperationWorkerResult(
        EODOperationWorkerStatus.WORKER_FATAL,
        diagnostic="repository_invalid",
    )


def test_recovery_runs_before_every_claim_and_drains_in_bounded_chunks(tmp_path: Path) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    repository = FakeJobRepository()
    repository.expired_remaining = 300
    worker = make_worker(tmp_path, repository, selected_catalog)
    assert worker.run_one().status is EODOperationWorkerStatus.NO_WORK
    assert worker.run_one().status is EODOperationWorkerStatus.NO_WORK
    assert repository.recovery_counts == [256, 44]
    assert repository.events == ["inspect_health", "recover", "claim"] * 2


def test_expired_job_is_abandoned_with_actual_worker_time(tmp_path: Path) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    operations = (tmp_path / "operations").resolve()
    repository = LocalEODOperationJobRepository(operations)
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    submitted = repository.submit(request, now=NOW).job
    repository.claim_next(worker_id="old-worker", now=NOW, lease_seconds=30)
    clock = MutableClock(NOW + timedelta(seconds=31))
    worker = make_worker(tmp_path, repository, selected_catalog, clock=clock)
    assert worker.run_one().status is EODOperationWorkerStatus.NO_WORK
    abandoned = repository.get(submitted.job_id)
    assert abandoned.status is EODOperationJobStatus.ABANDONED
    assert abandoned.finished_at == clock.value
    assert abandoned.failure.error_code == "lease_expired"


def test_job_expiring_after_prior_loop_is_recovered_on_next_run(tmp_path: Path) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    repository = LocalEODOperationJobRepository((tmp_path / "operations").resolve())
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    submitted = repository.submit(request, now=NOW).job
    repository.claim_next(worker_id="old-worker", now=NOW, lease_seconds=30)
    clock = MutableClock(NOW + timedelta(seconds=20))
    worker = make_worker(tmp_path, repository, selected_catalog, clock=clock)
    assert worker.run_one().status is EODOperationWorkerStatus.NO_WORK
    assert repository.get(submitted.job_id).status is EODOperationJobStatus.RUNNING
    clock.value = NOW + timedelta(seconds=31)
    assert worker.run_one().status is EODOperationWorkerStatus.NO_WORK
    assert repository.get(submitted.job_id).status is EODOperationJobStatus.ABANDONED


@pytest.mark.parametrize(
    ("operation_type", "status", "result_code", "terminal_status"),
    (
        (
            EODOperationType.INCREMENTAL_SINGLE,
            EODBatchStatus.SUCCESS,
            "success",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_SINGLE,
            EODBatchStatus.DRY_RUN,
            "dry_run",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_SINGLE,
            EODBatchStatus.FULL_REFRESH_REQUIRED,
            "full_refresh_required",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_SINGLE,
            EODBatchStatus.FAILED,
            "incremental_execution_failed",
            EODOperationJobStatus.FAILED,
        ),
        (
            EODOperationType.INCREMENTAL_BATCH,
            EODBatchStatus.SUCCESS,
            "success",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_BATCH,
            EODBatchStatus.DRY_RUN,
            "dry_run",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_BATCH,
            EODBatchStatus.PARTIAL_SUCCESS,
            "partial_success",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_BATCH,
            EODBatchStatus.FULL_REFRESH_REQUIRED,
            "full_refresh_required",
            EODOperationJobStatus.COMPLETED,
        ),
        (
            EODOperationType.INCREMENTAL_BATCH,
            EODBatchStatus.FAILED,
            "batch_execution_failed",
            EODOperationJobStatus.FAILED,
        ),
    ),
)
def test_incremental_terminal_matrix(
    tmp_path: Path,
    monkeypatch,
    operation_type: EODOperationType,
    status: EODBatchStatus,
    result_code: str,
    terminal_status: EODOperationJobStatus,
) -> None:
    first = dataset()
    second = dataset("600001.SH")
    values = (first,) if operation_type is EODOperationType.INCREMENTAL_SINGLE else (first, second)
    selected_catalog = catalog(tmp_path, values)
    request = request_for(selected_catalog, operation_type, values)
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=batch_response(status, request),
    )
    outcome = worker.run_one()
    persisted = repository.get(job.job_id)
    assert persisted.status is terminal_status
    assert outcome.status is (
        EODOperationWorkerStatus.JOB_COMPLETED
        if terminal_status is EODOperationJobStatus.COMPLETED
        else EODOperationWorkerStatus.JOB_FAILED
    )
    if terminal_status is EODOperationJobStatus.COMPLETED:
        assert persisted.result.result_code == result_code
        assert persisted.failure is None
    else:
        assert persisted.failure.error_code == result_code
        assert persisted.failure.stage == (
            "incremental" if operation_type is EODOperationType.INCREMENTAL_SINGLE else "batch"
        )


@pytest.mark.parametrize(
    ("status", "result_code"),
    (
        (EODFullRefreshStatus.FULL_REFRESH_PLANNED, "dry_run"),
        (EODFullRefreshStatus.FULL_REFRESH_PUBLISHED, "success"),
        (EODFullRefreshStatus.UNCHANGED_CONTENT, "success"),
        (EODFullRefreshStatus.NOT_ELIGIBLE, "full_refresh_not_eligible"),
    ),
)
def test_full_refresh_terminal_matrix(tmp_path: Path, monkeypatch, status, result_code) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.FULL_REFRESH, (selected,))
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    monkeypatch.setattr(worker_module, "EODFullRefreshResult", FakeFullRefreshResult)
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=FakeFullRefreshResult(status, selected),
    )
    assert worker.run_one().status is EODOperationWorkerStatus.JOB_COMPLETED
    assert repository.get(job.job_id).result.result_code == result_code


@pytest.mark.parametrize(
    ("status", "result_code"),
    (
        (EODRepositoryMaintenanceStatus.EMPTY, "maintenance_empty"),
        (EODRepositoryMaintenanceStatus.INSPECTED, "maintenance_inspected"),
        (EODRepositoryMaintenanceStatus.CLEANED, "maintenance_cleaned"),
        (EODRepositoryMaintenanceStatus.BLOCKED, "maintenance_blocked"),
    ),
)
def test_maintenance_terminal_matrix(tmp_path: Path, monkeypatch, status, result_code) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    monkeypatch.setattr(worker_module, "EODRepositoryMaintenanceResult", FakeMaintenanceResult)
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=FakeMaintenanceResult(status, selected),
    )
    assert worker.run_one().status is EODOperationWorkerStatus.JOB_COMPLETED
    assert repository.get(job.job_id).result.result_code == result_code


@pytest.mark.parametrize(
    ("operation_type", "error_code", "stage"),
    (
        (EODOperationType.INCREMENTAL_SINGLE, "incremental_execution_failed", "incremental"),
        (EODOperationType.INCREMENTAL_BATCH, "batch_execution_failed", "batch"),
        (EODOperationType.FULL_REFRESH, "full_refresh_execution_failed", "full_refresh"),
        (EODOperationType.MAINTENANCE, "maintenance_execution_failed", "maintenance"),
    ),
)
def test_unexpected_domain_exception_is_persisted_safely(
    tmp_path: Path,
    operation_type: EODOperationType,
    error_code: str,
    stage: str,
) -> None:
    first = dataset()
    second = dataset("600001.SH")
    values = (first, second) if operation_type is EODOperationType.INCREMENTAL_BATCH else (first,)
    selected_catalog = catalog(tmp_path, values)
    request = request_for(selected_catalog, operation_type, values)
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=RuntimeError(r"C:\private token=secret provider payload"),
    )
    assert worker.run_one().status is EODOperationWorkerStatus.JOB_FAILED
    failure = repository.get(job.job_id).failure
    assert failure.error_code == error_code
    assert failure.stage == stage
    assert "private" not in failure.to_json()
    assert "secret" not in failure.to_json()


def test_result_mapping_failure_is_distinct_and_safe(tmp_path: Path) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    worker = make_worker(tmp_path, repository, selected_catalog, response=object())
    assert worker.run_one().status is EODOperationWorkerStatus.JOB_FAILED
    failure = repository.get(job.job_id).failure
    assert failure.error_code == "result_mapping_failed"
    assert failure.stage == "result_mapping"


def test_catalog_preflight_unknown_disabled_and_context_mismatch(
    tmp_path: Path, monkeypatch
) -> None:
    enabled = dataset()
    disabled = dataset("600001.SH")
    unknown = dataset("600002.SH")
    selected_catalog = catalog(tmp_path, (enabled, disabled), disabled=(disabled,))
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)
    mismatched_context = EODOperationExecutionContext(
        selected_catalog.execution_context.calendar_identity,
        "sha256:" + "f" * 64,
    )
    cases = (
        (unknown, None, "dataset_not_in_catalog"),
        (disabled, None, "dataset_disabled"),
        (enabled, mismatched_context, "execution_context_mismatch"),
    )
    for selected, context, expected in cases:
        request = request_for(
            selected_catalog,
            EODOperationType.INCREMENTAL_SINGLE,
            (selected,),
            execution_context=context,
        )
        job = queued_job(request)
        repository = FakeJobRepository((job,))
        worker = make_worker(
            tmp_path,
            repository,
            selected_catalog,
            response=FakeBatchResult(EODBatchStatus.SUCCESS, (selected,)),
        )
        assert worker.run_one().status is EODOperationWorkerStatus.JOB_FAILED
        assert repository.get(job.job_id).failure.error_code == expected
        assert repository.get(job.job_id).failure.stage == "catalog"
        assert worker.execution_count == 0


def test_batch_policy_generation_ids_and_started_at_flow_to_domain_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    first = dataset()
    second = dataset("600001.SH")
    selected_catalog = catalog(tmp_path, (first, second))
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)
    for policy, expected in (
        (EODOperationFailurePolicy.STOP_ON_FAILURE, EODBatchFailurePolicy.STOP_ON_FAILURE),
        (EODOperationFailurePolicy.CONTINUE_ON_FAILURE, EODBatchFailurePolicy.CONTINUE_ON_FAILURE),
    ):
        request = request_for(
            selected_catalog,
            EODOperationType.INCREMENTAL_BATCH,
            (first, second),
            failure_policy=policy,
        )
        job = queued_job(request)
        repository = FakeJobRepository((job,))
        capture = CaptureBatch(EODBatchStatus.SUCCESS)
        worker = make_worker(
            tmp_path,
            repository,
            selected_catalog,
            batch=capture,
            worker_type=CaptureBatchWorker,
        )
        assert worker.run_one().status is EODOperationWorkerStatus.JOB_COMPLETED
        domain_request, checkpoint = capture.requests[0]
        claimed = repository.get(job.job_id)
        assert domain_request.failure_policy is expected
        assert tuple(item.created_at for item in domain_request.datasets) == (
            claimed.started_at,
            claimed.started_at,
        )
        assert len({item.generation_id for item in domain_request.datasets}) == 2
        assert checkpoint is not None


def test_worker_config_defaults_and_boundaries() -> None:
    config = EODOperationWorkerConfig()
    assert config.lease_duration_seconds == 300
    assert config.heartbeat_interval_seconds == 60
    assert config.poll_interval_seconds == 5
    invalid = (
        {"lease_duration_seconds": 29},
        {"lease_duration_seconds": 3601},
        {"heartbeat_interval_seconds": 29},
        {"heartbeat_interval_seconds": 3601, "lease_duration_seconds": 3600},
        {"lease_duration_seconds": 120, "heartbeat_interval_seconds": 60},
        {"lease_duration_seconds": True},
        {"heartbeat_interval_seconds": True},
        {"poll_interval_seconds": True},
    )
    for values in invalid:
        with pytest.raises(ValueError):
            EODOperationWorkerConfig(**values)


def test_renew_uses_heartbeat_interval_and_repository_returned_expiry(tmp_path: Path) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    claimed = repository.claim_next(worker_id="worker-1", now=NOW, lease_seconds=300)
    control = EODLeaseController(claimed)
    worker = make_worker(tmp_path, repository, selected_catalog)
    old_expiry = claimed.lease_expires_at
    assert worker._renew(control) is True
    assert repository.renew_seconds == [60]
    assert control.job.lease_expires_at == old_expiry + timedelta(seconds=60)
    assert control.state is EODLeaseControlState.ACTIVE


@pytest.mark.parametrize(
    ("error", "diagnostic"),
    (
        (EODOperationJobRepositoryErrorCode.LEASE_CONFLICT, "lease_conflict"),
        (EODOperationJobRepositoryErrorCode.PERSISTENCE_BUSY, "lease_persistence_busy"),
        (EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE, "lease_persistence_failure"),
        (RuntimeError("unexpected"), "lease_control_failure"),
    ),
)
def test_final_renew_failure_enters_unsafe_without_terminal_write(
    tmp_path: Path,
    monkeypatch,
    error,
    diagnostic: str,
) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (selected,))
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    repository.renew_error = error
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=FakeBatchResult(EODBatchStatus.SUCCESS, (selected,)),
    )
    outcome = worker.run_one()
    assert outcome.status is EODOperationWorkerStatus.WORKER_UNSAFE
    assert outcome.diagnostic == diagnostic
    assert repository.get(job.job_id).status is EODOperationJobStatus.RUNNING
    assert "complete" not in repository.events
    assert "fail" not in repository.events


def test_heartbeat_start_failure_prevents_domain_side_effect(tmp_path: Path) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.MAINTENANCE, (selected,), dry_run=True)
    job = queued_job(request)
    repository = FakeJobRepository((job,))

    def failing_thread_factory(**kwargs):
        raise RuntimeError("thread unavailable")

    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=object(),
        thread_factory=failing_thread_factory,
    )
    result = worker.run_one()
    assert result.status is EODOperationWorkerStatus.WORKER_UNSAFE
    assert result.diagnostic == "heartbeat_start_failed"
    assert worker.execution_count == 0
    assert repository.get(job.job_id).status is EODOperationJobStatus.RUNNING


def test_unsafe_after_domain_return_blocks_terminal_transition(tmp_path: Path, monkeypatch) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (selected,))
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)

    def response(job, generation_ids, checkpoint):
        checkpoint.mark_unsafe("lease_conflict")
        return FakeBatchResult(EODBatchStatus.SUCCESS, (selected,))

    outcome = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=response,
    ).run_one()
    assert outcome.status is EODOperationWorkerStatus.WORKER_UNSAFE
    assert repository.get(job.job_id).status is EODOperationJobStatus.RUNNING
    assert "renew" not in repository.events
    assert "complete" not in repository.events
    assert "fail" not in repository.events


def test_heartbeat_join_final_renew_checkpoint_and_complete_order(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (selected,))
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)
    checkpoints = []
    original = worker_module.run_eod_checkpoint

    def recording_checkpoint(checkpoint, stage, selected=None):
        checkpoints.append(stage)
        return original(checkpoint, stage, selected)

    monkeypatch.setattr(worker_module, "run_eod_checkpoint", recording_checkpoint)
    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=FakeBatchResult(EODBatchStatus.SUCCESS, (selected,)),
    )
    assert worker.run_one().status is EODOperationWorkerStatus.JOB_COMPLETED
    assert repository.events.index("heartbeat_join") < repository.events.index("renew")
    assert repository.events.index("renew") < repository.events.index("complete")
    assert checkpoints == [EODCheckpointStage.BEFORE_TERMINAL_TRANSITION]


def test_run_forever_stops_after_unsafe_result(tmp_path: Path) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    worker = make_worker(tmp_path, FakeJobRepository(), selected_catalog)
    calls = []

    def unsafe_once():
        calls.append("run")
        return EODOperationWorkerResult(EODOperationWorkerStatus.WORKER_UNSAFE)

    worker.run_one = unsafe_once
    worker.run_forever(threading.Event())
    assert calls == ["run"]


def test_generation_identity_is_deterministic_unique_bounded_and_retry_specific(
    tmp_path: Path,
) -> None:
    first = dataset()
    second = dataset("600001.SH")
    selected_catalog = catalog(tmp_path, (first, second))
    request = request_for(selected_catalog, EODOperationType.INCREMENTAL_BATCH, (first, second))
    repository = FakeJobRepository(
        (queued_job(request), queued_job(request, NOW + timedelta(seconds=1)))
    )
    first_job = repository.claim_next(worker_id="worker-1", now=NOW, lease_seconds=300)
    second_job = repository.claim_next(
        worker_id="worker-2",
        now=NOW + timedelta(seconds=1),
        lease_seconds=300,
    )
    first_id = eod_generation_id(first_job, first)
    assert first_id == eod_generation_id(first_job, first)
    assert first_id != eod_generation_id(first_job, second)
    assert first_id != eod_generation_id(second_job, first)
    assert len(first_id) <= 128
    assert validate_generation_id(first_id) == first_id


def test_crash_window_keeps_domain_publication_and_running_job_until_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    selected = dataset()
    selected_catalog = catalog(tmp_path, (selected,))
    request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (selected,))
    job = queued_job(request)
    repository = FakeJobRepository((job,))
    repository.complete_error = RuntimeError("simulated crash before terminal commit")
    published = []
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)

    def response(job, generation_ids, checkpoint):
        published.append(generation_ids[selected])
        return FakeBatchResult(EODBatchStatus.SUCCESS, (selected,))

    clock = MutableClock(NOW)
    outcome = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=response,
        clock=clock,
    ).run_one()
    assert outcome.status is EODOperationWorkerStatus.WORKER_UNSAFE
    assert published and repository.get(job.job_id).status is EODOperationJobStatus.RUNNING
    clock.value = NOW + timedelta(seconds=361)
    repository.mark_expired_running_abandoned(now=clock.value, limit=256)
    assert repository.get(job.job_id).status is EODOperationJobStatus.ABANDONED
    assert published
    assert len(repository.jobs) == 1


def test_fifo_claim_integration_with_local_repository(tmp_path: Path, monkeypatch) -> None:
    first = dataset()
    second = dataset("600001.SH")
    selected_catalog = catalog(tmp_path, (first, second))
    repository = LocalEODOperationJobRepository((tmp_path / "operations").resolve())
    first_request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (first,))
    second_request = request_for(selected_catalog, EODOperationType.INCREMENTAL_SINGLE, (second,))
    first_job = repository.submit(first_request, now=NOW).job
    second_job = repository.submit(second_request, now=NOW + timedelta(seconds=1)).job
    monkeypatch.setattr(worker_module, "EODBatchResult", FakeBatchResult)

    def response(job, generation_ids, checkpoint):
        return FakeBatchResult(EODBatchStatus.SUCCESS, (job.request.payload.dataset,))

    worker = make_worker(
        tmp_path,
        repository,
        selected_catalog,
        response=response,
        clock=MutableClock(NOW + timedelta(seconds=2)),
    )
    assert worker.run_one().job_id == first_job.job_id
    assert worker.run_one().job_id == second_job.job_id
    assert repository.get(first_job.job_id).status is EODOperationJobStatus.COMPLETED
    assert repository.get(second_job.job_id).status is EODOperationJobStatus.COMPLETED


def test_imports_are_offline_and_side_effect_free(tmp_path: Path) -> None:
    script = """
import pathlib
import sys

root = pathlib.Path.cwd()
before = sorted(path.relative_to(root).as_posix() for path in root.rglob('*'))

def audit(event, args):
    if event in {'socket.bind', 'socket.connect', 'socket.getaddrinfo'}:
        raise AssertionError('network access is forbidden during import')

sys.addaudithook(audit)
import autowealth.market_data.operation_control
import autowealth.market_data.operation_catalog
import autowealth.market_data.operation_worker
after = sorted(path.relative_to(root).as_posix() for path in root.rglob('*'))
assert before == after
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={
            "PYTHONPATH": str(ROOT),
            "SystemRoot": os.environ["SystemRoot"],
            "WINDIR": os.environ["WINDIR"],
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_worker_rejects_same_nested_relative_and_parent_repository_roots(
    tmp_path: Path,
) -> None:
    selected_catalog = catalog(tmp_path, (dataset(),))
    repository = FakeJobRepository()
    generation_root = selected_catalog.entries[0].runtime.config.repository_root
    invalid_roots = (
        generation_root,
        generation_root.parent,
        generation_root / "operations",
        tmp_path / "isolated" / ".." / "operations",
        Path("operations"),
    )

    for operations_root in invalid_roots:
        with pytest.raises(ValueError, match="absolute Path|relative path|separate"):
            EODOperationWorker(
                repository,
                selected_catalog,
                operations_root=operations_root,
                worker_id="worker-1",
                lock_manager=InProcessEODDatasetLockManager(),
                clock=MutableClock(),
                thread_factory=passive_factory(repository.events),
            )

    assert repository.events == []
