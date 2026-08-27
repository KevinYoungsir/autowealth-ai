from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import math
import re

import pytest

from autowealth.market_data.job_repository import EODOperationJobRepositoryErrorCode
from autowealth.market_data.operations import (
    EOD_OPERATION_JOB_SCHEMA_VERSION,
    EOD_OPERATION_SCHEMA_VERSION,
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
    EODOperationResultSummary,
    EODOperationSubmission,
    EODOperationSubmissionStatus,
    EODOperationType,
    generate_eod_operation_job_id,
    validate_eod_operation_job_id,
)
from autowealth.market_data.planning import EODRevisionPolicy
from autowealth.market_data.providers import EODRevisionStrategy
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODWarningSeverity,
    Market,
    Venue,
)

NOW = datetime(2026, 8, 24, 8, tzinfo=timezone.utc)
JOB_ID = "job-20260824T080000000000Z-0123456789abcdef0123456789abcdef"
CONFIG_ID = "sha256:" + "a" * 64


def dataset(symbol: str = "600000.SH") -> EODDatasetKey:
    venue = Venue.SSE if symbol.endswith(".SH") else Venue.SZSE
    return EODDatasetKey(
        Market.CN,
        venue,
        AssetType.EQUITY,
        symbol,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


def context() -> EODOperationExecutionContext:
    return EODOperationExecutionContext("cn-calendar-v1", CONFIG_ID)


def date_range() -> EODDateRange:
    return EODDateRange(date(2026, 8, 20), date(2026, 8, 21))


def append_policy() -> EODRevisionPolicy:
    return EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY)


def single_request(symbol: str = "600000.SH") -> EODOperationRequest:
    return EODOperationRequest(
        EODOperationType.INCREMENTAL_SINGLE,
        context(),
        EODIncrementalSingleOperationPayload(dataset(symbol), date_range(), append_policy(), False),
    )


def queued_job(request: EODOperationRequest | None = None) -> EODOperationJob:
    request = request or single_request()
    return EODOperationJob(
        JOB_ID,
        request,
        request.fingerprint,
        EODOperationJobStatus.QUEUED,
        NOW,
    )


@pytest.mark.parametrize(
    ("operation_type", "payload_type"),
    [
        (EODOperationType.INCREMENTAL_SINGLE, EODIncrementalSingleOperationPayload),
        (EODOperationType.INCREMENTAL_BATCH, EODIncrementalBatchOperationPayload),
        (EODOperationType.FULL_REFRESH, EODFullRefreshOperationPayload),
        (EODOperationType.MAINTENANCE, EODMaintenanceOperationPayload),
    ],
)
def test_all_four_operation_types_roundtrip(operation_type, payload_type):
    if operation_type is EODOperationType.INCREMENTAL_BATCH:
        payload = payload_type(
            (dataset("000001.SZ"), dataset()),
            date_range(),
            append_policy(),
            False,
            EODOperationFailurePolicy.CONTINUE_ON_FAILURE,
        )
    elif operation_type is EODOperationType.FULL_REFRESH:
        payload = payload_type(
            dataset(),
            date_range(),
            EODRevisionPolicy(EODRevisionStrategy.FULL_REFRESH_REQUIRED),
            False,
        )
    elif operation_type is EODOperationType.MAINTENANCE:
        payload = payload_type(dataset())
    else:
        payload = payload_type(dataset(), date_range(), append_policy(), False)
    request = EODOperationRequest(operation_type, context(), payload)
    restored = EODOperationRequest.from_json(request.to_json())
    assert restored == request
    assert restored.schema_version == EOD_OPERATION_SCHEMA_VERSION
    assert "generation_id" not in request.to_json()


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_payload_booleans_are_strict(value):
    with pytest.raises((TypeError, ValueError)):
        EODIncrementalSingleOperationPayload(dataset(), date_range(), append_policy(), value)
    with pytest.raises((TypeError, ValueError)):
        EODMaintenanceOperationPayload(dataset(), dry_run=value)


def test_full_refresh_requires_full_refresh_policy():
    with pytest.raises(ValueError, match="full_refresh_required"):
        EODFullRefreshOperationPayload(dataset(), date_range(), append_policy())


def test_batch_order_is_canonical_and_fingerprint_is_order_independent():
    first, second = dataset(), dataset("000001.SZ")
    left = EODOperationRequest(
        EODOperationType.INCREMENTAL_BATCH,
        context(),
        EODIncrementalBatchOperationPayload((first, second), date_range(), append_policy()),
    )
    right = EODOperationRequest(
        EODOperationType.INCREMENTAL_BATCH,
        context(),
        EODIncrementalBatchOperationPayload((second, first), date_range(), append_policy()),
    )
    assert left.payload.datasets == tuple(sorted((first, second), key=lambda item: item.identity))
    assert left.to_json() == right.to_json()
    assert left.fingerprint == right.fingerprint


def test_batch_rejects_duplicate_or_excess_datasets():
    with pytest.raises(ValueError, match="duplicate"):
        EODIncrementalBatchOperationPayload((dataset(), dataset()), date_range(), append_policy())
    repeated = tuple(dataset(f"{index:06d}.SZ") for index in range(1, 258))
    with pytest.raises(ValueError, match="256"):
        EODIncrementalBatchOperationPayload(repeated, date_range(), append_policy())


def test_execution_context_is_path_free_and_uses_opaque_sha_identity():
    assert context().to_dict() == {
        "calendar_identity": "cn-calendar-v1",
        "execution_config_fingerprint": CONFIG_ID,
    }
    for identity in (r"D:\private\calendar.csv", "/home/user/calendar.csv", "apiKey=secret"):
        with pytest.raises(ValueError):
            EODOperationExecutionContext(identity, CONFIG_ID)
    with pytest.raises(ValueError, match="sha256"):
        EODOperationExecutionContext("calendar-v1", "a" * 64)


def test_request_json_is_canonical_and_rejects_noncanonical_input():
    request = single_request()
    text = request.to_json()
    assert text.startswith('{"execution_context":')
    assert " " not in text
    with pytest.raises(ValueError, match="canonical"):
        EODOperationRequest.from_json(text.replace(",", ", ", 1))
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", request.fingerprint)


def test_fingerprint_excludes_job_lifecycle_fields():
    request = single_request()
    first = queued_job(request)
    second = replace(
        first,
        job_id="job-20260824T080001000000Z-fedcba9876543210fedcba9876543210",
        created_at=NOW + timedelta(seconds=1),
        record_sha256=None,
    )
    assert first.operation_fingerprint == second.operation_fingerprint == request.fingerprint
    assert first.record_sha256 != second.record_sha256


def test_job_id_is_utc_sortable_unique_and_strict():
    first = generate_eod_operation_job_id(NOW)
    second = generate_eod_operation_job_id(NOW + timedelta(microseconds=1))
    assert first < second
    assert first != generate_eod_operation_job_id(NOW)
    assert validate_eod_operation_job_id(first) == first
    assert re.fullmatch(r"job-\d{8}T\d{12}Z-[0-9a-f]{32}", first)
    for value in ("job-20260824-local", "../job", JOB_ID.upper()):
        with pytest.raises(ValueError):
            validate_eod_operation_job_id(value)


def test_job_timestamps_normalize_to_utc_and_reject_naive_values():
    offset = timezone(timedelta(hours=8))
    request = single_request()
    job = EODOperationJob(
        JOB_ID,
        request,
        request.fingerprint,
        EODOperationJobStatus.QUEUED,
        NOW.astimezone(offset),
    )
    assert job.created_at.tzinfo is timezone.utc
    assert job.to_dict()["created_at"].endswith("+00:00")
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(job, created_at=NOW.replace(tzinfo=None), record_sha256=None)


def running_job() -> EODOperationJob:
    return replace(
        queued_job(),
        status=EODOperationJobStatus.RUNNING,
        started_at=NOW,
        worker_id="worker-1",
        claim_version=1,
        lease_expires_at=NOW + timedelta(minutes=1),
        record_sha256=None,
    )


def test_exact_job_lifecycle_states_and_invariants():
    running = running_job()
    result = EODOperationResultSummary("completed")
    failure = EODOperationFailureSummary(
        "provider_unavailable", "provider", "Provider data was unavailable.", True
    )
    completed = replace(
        running,
        status=EODOperationJobStatus.COMPLETED,
        finished_at=NOW + timedelta(seconds=1),
        lease_expires_at=None,
        result=result,
        record_sha256=None,
    )
    failed = replace(
        running,
        status=EODOperationJobStatus.FAILED,
        finished_at=NOW + timedelta(seconds=1),
        lease_expires_at=None,
        failure=failure,
        record_sha256=None,
    )
    abandoned = replace(failed, status=EODOperationJobStatus.ABANDONED, record_sha256=None)
    assert {completed.status, failed.status, abandoned.status} == {
        EODOperationJobStatus.COMPLETED,
        EODOperationJobStatus.FAILED,
        EODOperationJobStatus.ABANDONED,
    }
    with pytest.raises(ValueError, match="queued"):
        replace(queued_job(), started_at=NOW, record_sha256=None)
    with pytest.raises(ValueError, match="running"):
        replace(running, lease_expires_at=NOW, record_sha256=None)
    with pytest.raises(ValueError, match="completed"):
        replace(completed, result=None, record_sha256=None)
    assert completed.schema_version == EOD_OPERATION_JOB_SCHEMA_VERSION


def test_result_and_failure_summaries_are_bounded_and_safe():
    warning = EODStructuredWarning(
        "partial_provider_response",
        EODWarningSeverity.WARNING,
        "The provider returned a partial response.",
        {"received_rows": 2},
    )
    result = EODOperationResultSummary(
        "completed_with_warnings", ({"symbol": "600000.SH"},), (warning,), {"dry_run": True}
    )
    assert result.to_dict()["warnings"][0]["code"] == "partial_provider_response"
    failure = EODOperationFailureSummary(
        "provider_failure", "provider", r"D:\private\trace.log", True, (dataset(),)
    )
    assert failure.safe_message == "The EOD operation failed safely."
    with pytest.raises(ValueError):
        EODOperationResultSummary("completed", metadata={"value": math.nan})
    with pytest.raises((TypeError, ValueError)):
        EODOperationResultSummary("completed", metadata={"a": {"b": {"c": {"d": {"e": 1}}}}})
    with pytest.raises(ValueError, match="256"):
        EODOperationResultSummary("completed", dataset_summaries=tuple({} for _ in range(257)))


def test_submission_and_repository_error_enums_are_stable():
    submission = EODOperationSubmission(EODOperationSubmissionStatus.CREATED, queued_job())
    assert submission.to_dict()["status"] == "created"
    assert {item.value for item in EODOperationJobRepositoryErrorCode} >= {
        "idempotency_conflict",
        "invalid_retry_link",
        "lease_conflict",
        "persistence_busy",
        "corrupt_record",
        "unsafe_path",
    }
