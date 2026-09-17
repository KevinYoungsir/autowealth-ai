from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import autowealth.market_data.operation_operator as operator_module
from autowealth.market_data.job_repository import (
    EODOperationRepositoryHealth,
    EODOperationRepositoryHealthStatus,
)
from autowealth.market_data.operation_operator import (
    EODOperationOperator,
    EODOperationOperatorError,
    EODOperationOperatorErrorCode,
)
from autowealth.market_data.operation_worker import (
    EODOperationWorkerResult,
    EODOperationWorkerStatus,
)
from autowealth.market_data.operations import (
    EODOperationExecutionContext,
    EODOperationFailurePolicy,
    EODOperationFailureSummary,
    EODOperationJob,
    EODOperationJobStatus,
    EODOperationRequest,
    EODOperationSubmission,
    EODOperationSubmissionStatus,
    EODOperationType,
    generate_eod_operation_job_id,
)
from autowealth.market_data.operator_config import (
    EODOperatorConfig,
    EODOperatorDatasetConfig,
)
from autowealth.market_data.planning import EODRevisionPolicy
from autowealth.market_data.providers import EODRevisionStrategy
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)

NOW = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
RANGE = EODDateRange(date(2024, 1, 2), date(2024, 1, 5))
APPEND = EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY)
CONTEXT = EODOperationExecutionContext("calendar-fixture", "sha256:" + "a" * 64)


def dataset(symbol: str) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


DATASET_A = dataset("600000.SH")
DATASET_B = dataset("600001.SH")
DATASET_C = dataset("600002.SH")


def config(tmp_path: Path, count: int = 1) -> EODOperatorConfig:
    return EODOperatorConfig(
        config_schema_version=1,
        operations_root=(tmp_path / "operations").resolve(),
        datasets=tuple(
            EODOperatorDatasetConfig(
                production_config=(tmp_path / f"production-{index}.yaml").resolve(),
                storage_identity=f"storage-{index}",
                enabled=index != 2,
            )
            for index in range(count)
        ),
    )


def catalog() -> SimpleNamespace:
    entries = (
        SimpleNamespace(
            dataset=DATASET_B,
            storage_identity="storage-1",
            enabled=True,
            provider_identities=(("fake-two", "fixture-v1"),),
            calendar_identity="calendar-fixture",
        ),
        SimpleNamespace(
            dataset=DATASET_A,
            storage_identity="storage-0",
            enabled=True,
            provider_identities=(("fake-one", "fixture-v1"),),
            calendar_identity="calendar-fixture",
        ),
        SimpleNamespace(
            dataset=DATASET_C,
            storage_identity="storage-2",
            enabled=False,
            provider_identities=(("fake-three", "fixture-v1"),),
            calendar_identity="calendar-fixture",
        ),
    )
    return SimpleNamespace(
        entries=entries,
        execution_context=CONTEXT,
        calendar_identity="calendar-fixture",
        execution_config_fingerprint=CONTEXT.execution_config_fingerprint,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.jobs: dict[str, EODOperationJob] = {}
        self.submissions: list[dict[str, object]] = []
        self.list_arguments = None
        self.counter = 0

    def inspect_health(self) -> EODOperationRepositoryHealth:
        return EODOperationRepositoryHealth(EODOperationRepositoryHealthStatus.ABSENT)

    def list_recent(self, *, limit=50, statuses=None, operation_types=None):
        self.list_arguments = (limit, statuses, operation_types)
        return tuple(self.jobs.values())

    def get(self, job_id: str):
        return self.jobs.get(job_id)

    def submit(
        self,
        request: EODOperationRequest,
        *,
        now: datetime,
        idempotency_key=None,
        retry_of_job_id=None,
    ) -> EODOperationSubmission:
        self.counter += 1
        job = EODOperationJob(
            generate_eod_operation_job_id(now + timedelta(microseconds=self.counter)),
            request,
            request.fingerprint,
            EODOperationJobStatus.QUEUED,
            now,
            retry_of_job_id=retry_of_job_id,
        )
        self.jobs[job.job_id] = job
        self.submissions.append(
            {
                "request": request,
                "idempotency_key": idempotency_key,
                "retry_of_job_id": retry_of_job_id,
            }
        )
        return EODOperationSubmission(EODOperationSubmissionStatus.CREATED, job)


def install_repository(monkeypatch, repository: FakeRepository) -> None:
    monkeypatch.setattr(
        operator_module,
        "LocalEODOperationJobRepository",
        lambda operations_root: repository,
    )


def selected_operator(
    tmp_path: Path,
    monkeypatch,
    repository: FakeRepository,
) -> EODOperationOperator:
    install_repository(monkeypatch, repository)
    value = EODOperationOperator(config(tmp_path, 3), clock=SimpleNamespace(now=lambda: NOW))
    value._catalog = catalog
    return value


def terminal_job(
    request: EODOperationRequest,
    status: EODOperationJobStatus,
) -> EODOperationJob:
    created = NOW
    started = NOW + timedelta(seconds=1)
    finished = NOW + timedelta(seconds=2)
    failure = EODOperationFailureSummary(
        "fixture_failure",
        "execute",
        "The fixture operation failed safely.",
        True,
    )
    return EODOperationJob(
        generate_eod_operation_job_id(created + timedelta(microseconds=7)),
        request,
        request.fingerprint,
        status,
        created,
        started_at=started,
        finished_at=finished,
        worker_id="fixture-worker",
        claim_version=1,
        failure=failure,
    )


def assert_operator_error(code: EODOperationOperatorErrorCode, call) -> None:
    with pytest.raises(EODOperationOperatorError) as captured:
        call()
    assert captured.value.code is code


def test_read_only_job_commands_do_not_load_runtime_or_create_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    value = EODOperationOperator(config(tmp_path))
    monkeypatch.setattr(
        operator_module,
        "load_eod_production_config",
        lambda path: (_ for _ in ()).throw(AssertionError("runtime must not load")),
    )
    root = value._config.operations_root
    missing_job = "job-20260901T080000000000Z-" + "a" * 32

    assert value.jobs_health()["status"] == "absent"
    assert value.jobs_list() == {"jobs": []}
    assert_operator_error(
        EODOperationOperatorErrorCode.JOB_NOT_FOUND,
        lambda: value.jobs_show(missing_job),
    )
    assert not root.exists()


def test_catalog_inspection_is_path_free_and_does_not_fetch_provider(
    tmp_path: Path,
) -> None:
    value = EODOperationOperator(config(tmp_path, 3))
    value._catalog = catalog

    result = value.catalog_inspect()

    assert result["calendar_identity"] == "calendar-fixture"
    assert [item["storage_identity"] for item in result["datasets"]] == [
        "storage-1",
        "storage-0",
        "storage-2",
    ]
    assert "path" not in repr(result).lower()
    assert str(tmp_path.resolve()) not in repr(result)


def test_incremental_single_submission_preserves_exact_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)

    result = value.submit_incremental_single(
        storage_identity="storage-0",
        requested_range=RANGE,
        revision_policy=APPEND,
        dry_run=True,
        execute=False,
        idempotency_key="plaintext-secret-alias",
    )

    request = repository.submissions[0]["request"]
    assert request.operation_type is EODOperationType.INCREMENTAL_SINGLE
    assert request.execution_context == CONTEXT
    assert request.payload.dataset == DATASET_A
    assert request.payload.requested_range == RANGE
    assert request.payload.revision_policy == APPEND
    assert request.payload.dry_run is True
    assert "plaintext-secret-alias" not in repr(result)


def test_execution_mode_requires_one_explicit_choice(tmp_path: Path, monkeypatch) -> None:
    value = selected_operator(tmp_path, monkeypatch, FakeRepository())
    for dry_run, execute in ((False, False), (True, True)):
        assert_operator_error(
            EODOperationOperatorErrorCode.INVALID_INPUT,
            lambda dry_run=dry_run, execute=execute: value.submit_incremental_single(
                storage_identity="storage-0",
                requested_range=RANGE,
                revision_policy=APPEND,
                dry_run=dry_run,
                execute=execute,
            ),
        )


def test_batch_selection_is_canonical_and_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)

    value.submit_incremental_batch(
        storage_identities=("storage-1", "storage-0"),
        all_enabled=False,
        requested_range=RANGE,
        revision_policy=APPEND,
        failure_policy=EODOperationFailurePolicy.CONTINUE_ON_FAILURE,
        dry_run=False,
        execute=True,
    )
    request = repository.submissions[-1]["request"]
    assert request.payload.datasets == (DATASET_A, DATASET_B)
    assert request.payload.failure_policy is EODOperationFailurePolicy.CONTINUE_ON_FAILURE

    value.submit_incremental_batch(
        storage_identities=(),
        all_enabled=True,
        requested_range=RANGE,
        revision_policy=APPEND,
        failure_policy=EODOperationFailurePolicy.STOP_ON_FAILURE,
        dry_run=True,
        execute=False,
    )
    assert repository.submissions[-1]["request"].payload.datasets == (DATASET_A, DATASET_B)

    for identities, all_enabled, code in (
        (("storage-0", "storage-0"), False, EODOperationOperatorErrorCode.DUPLICATE_SELECTOR),
        (("unknown",), False, EODOperationOperatorErrorCode.STORAGE_IDENTITY_NOT_FOUND),
        (("storage-2",), False, EODOperationOperatorErrorCode.DATASET_DISABLED),
        (("storage-0",), True, EODOperationOperatorErrorCode.INVALID_INPUT),
    ):
        assert_operator_error(
            code,
            lambda identities=identities, all_enabled=all_enabled: value.submit_incremental_batch(
                storage_identities=identities,
                all_enabled=all_enabled,
                requested_range=RANGE,
                revision_policy=APPEND,
                failure_policy=EODOperationFailurePolicy.STOP_ON_FAILURE,
                dry_run=True,
                execute=False,
            ),
        )


def test_full_refresh_and_maintenance_use_existing_payload_contracts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)

    value.submit_full_refresh(
        storage_identity="storage-0",
        requested_range=RANGE,
        dry_run=False,
        execute=True,
    )
    refresh = repository.submissions[-1]["request"]
    assert refresh.payload.revision_policy.strategy is EODRevisionStrategy.FULL_REFRESH_REQUIRED
    assert refresh.payload.dry_run is False

    value.submit_maintenance(
        storage_identity="storage-0",
        dry_run=True,
        execute=False,
        cleanup_staging=False,
        cleanup_pointer_temps=True,
    )
    maintenance = repository.submissions[-1]["request"]
    assert maintenance.payload.dry_run is True
    assert maintenance.payload.cleanup_staging is False
    assert maintenance.payload.cleanup_pointer_temps is True


@pytest.mark.parametrize(
    "status",
    [EODOperationJobStatus.FAILED, EODOperationJobStatus.ABANDONED],
)
def test_retry_reuses_exact_request_and_records_predecessor(
    tmp_path: Path,
    monkeypatch,
    status: EODOperationJobStatus,
) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)
    value.submit_incremental_single(
        storage_identity="storage-0",
        requested_range=RANGE,
        revision_policy=APPEND,
        dry_run=False,
        execute=True,
    )
    request = repository.submissions[-1]["request"]
    predecessor = terminal_job(request, status)
    repository.jobs = {predecessor.job_id: predecessor}

    result = value.jobs_retry(predecessor.job_id, execute=True)

    retry = repository.submissions[-1]
    assert retry["request"] is predecessor.request
    assert retry["request"].fingerprint == predecessor.request.fingerprint
    assert retry["retry_of_job_id"] == predecessor.job_id
    assert result["job"]["retry_of_job_id"] == predecessor.job_id


def test_retry_gates_status_context_and_real_confirmation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)
    value.submit_incremental_single(
        storage_identity="storage-0",
        requested_range=RANGE,
        revision_policy=APPEND,
        dry_run=False,
        execute=True,
    )
    request = repository.submissions[-1]["request"]
    failed = terminal_job(request, EODOperationJobStatus.FAILED)

    repository.jobs = {failed.job_id: failed}
    assert_operator_error(
        EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED,
        lambda: value.jobs_retry(failed.job_id, execute=False),
    )

    queued = replace(
        failed,
        status=EODOperationJobStatus.QUEUED,
        started_at=None,
        finished_at=None,
        worker_id=None,
        claim_version=None,
        failure=None,
        record_sha256=None,
    )
    repository.jobs = {queued.job_id: queued}
    assert_operator_error(
        EODOperationOperatorErrorCode.RETRY_STATUS_INVALID,
        lambda: value.jobs_retry(queued.job_id, execute=True),
    )

    stale_context = EODOperationExecutionContext("other-calendar", "sha256:" + "b" * 64)
    stale_request = replace(request, execution_context=stale_context)
    stale = terminal_job(stale_request, EODOperationJobStatus.FAILED)
    repository.jobs = {stale.job_id: stale}
    assert_operator_error(
        EODOperationOperatorErrorCode.RETRY_CONTEXT_STALE,
        lambda: value.jobs_retry(stale.job_id, execute=True),
    )


def test_dry_run_retry_cannot_become_real(tmp_path: Path, monkeypatch) -> None:
    repository = FakeRepository()
    value = selected_operator(tmp_path, monkeypatch, repository)
    value.submit_incremental_single(
        storage_identity="storage-0",
        requested_range=RANGE,
        revision_policy=APPEND,
        dry_run=True,
        execute=False,
    )
    request = repository.submissions[-1]["request"]
    failed = terminal_job(request, EODOperationJobStatus.FAILED)
    repository.jobs = {failed.job_id: failed}

    value.jobs_retry(failed.job_id, execute=True)

    assert repository.submissions[-1]["request"] is request
    assert repository.submissions[-1]["request"].payload.dry_run is True


def test_worker_requires_confirmation_and_runs_exactly_once(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = FakeRepository()
    calls = []
    response = EODOperationWorkerResult(EODOperationWorkerStatus.NO_WORK)

    class Worker:
        def run_one(self):
            calls.append("run_one")
            return response

    def factory(*args, **kwargs):
        calls.append(("factory", args, kwargs))
        return Worker()

    install_repository(monkeypatch, repository)
    value = EODOperationOperator(
        config(tmp_path, 3),
        clock=SimpleNamespace(now=lambda: NOW),
        worker_factory=factory,
    )
    value._catalog = catalog

    assert_operator_error(
        EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED,
        lambda: value.worker_run_one(worker_id="worker-1", execute=False),
    )
    assert calls == []

    assert value.worker_run_one(worker_id="worker-1", execute=True) is response
    assert [item for item in calls if item == "run_one"] == ["run_one"]
    assert not hasattr(Worker, "run_forever")


def test_invalid_worker_id_fails_before_catalog_access(tmp_path: Path) -> None:
    value = EODOperationOperator(config(tmp_path))
    value._catalog = lambda: (_ for _ in ()).throw(AssertionError("catalog must not load"))

    assert_operator_error(
        EODOperationOperatorErrorCode.INVALID_INPUT,
        lambda: value.worker_run_one(worker_id="../unsafe", execute=True),
    )


@pytest.mark.parametrize("relationship", ["same", "operations-parent", "generation-parent"])
def test_catalog_rejects_equal_or_nested_storage_roots(
    tmp_path: Path,
    monkeypatch,
    relationship: str,
) -> None:
    value = EODOperationOperator(config(tmp_path))
    operations = value._config.operations_root
    if relationship == "same":
        generation = operations
    elif relationship == "operations-parent":
        generation = operations / "generation"
    else:
        generation = operations.parent
    production = SimpleNamespace(dataset=DATASET_A, repository_root=generation)
    monkeypatch.setattr(operator_module, "load_eod_production_config", lambda path: production)
    monkeypatch.setattr(
        operator_module,
        "build_eod_operation_catalog",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("builder must not run")),
    )

    assert_operator_error(EODOperationOperatorErrorCode.ROOTS_NOT_SEPARATE, value._catalog)


def test_catalog_rejects_duplicate_dataset_before_mapping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    value = EODOperationOperator(config(tmp_path, 2))
    production = SimpleNamespace(
        dataset=DATASET_A,
        repository_root=(tmp_path / "generation").resolve(),
    )
    monkeypatch.setattr(operator_module, "load_eod_production_config", lambda path: production)

    assert_operator_error(EODOperationOperatorErrorCode.DUPLICATE_DATASET, value._catalog)
