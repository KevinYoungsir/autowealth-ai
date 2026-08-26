from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from multiprocessing import get_context
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from threading import Barrier, Thread

import pytest

from autowealth.market_data.job_repository import (
    EOD_OPERATION_DATABASE_NAME,
    EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION,
    EODOperationJobRepositoryError,
    EODOperationJobRepositoryErrorCode,
    EODOperationRepositoryHealthStatus,
    LocalEODOperationJobRepository,
    MAX_EOD_JOB_ALIASES,
)
from autowealth.market_data.operations import (
    EODIncrementalSingleOperationPayload,
    EODOperationExecutionContext,
    EODOperationFailureSummary,
    EODOperationJobStatus,
    EODOperationRequest,
    EODOperationResultSummary,
    EODOperationSubmissionStatus,
    EODOperationType,
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

NOW = datetime(2026, 8, 24, 8, tzinfo=timezone.utc)
CONFIG_ID = "sha256:" + "b" * 64
MISSING_JOB_ID = "job-20260824T000000000000Z-ffffffffffffffffffffffffffffffff"


def make_dataset(symbol: str = "600000.SH") -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        Venue.SSE if symbol.endswith(".SH") else Venue.SZSE,
        AssetType.EQUITY,
        symbol,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


def make_request(symbol: str = "600000.SH") -> EODOperationRequest:
    return EODOperationRequest(
        EODOperationType.INCREMENTAL_SINGLE,
        EODOperationExecutionContext("cn-calendar-v1", CONFIG_ID),
        EODIncrementalSingleOperationPayload(
            make_dataset(symbol),
            EODDateRange(date(2026, 8, 20), date(2026, 8, 21)),
            EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY),
            False,
        ),
    )


def failure() -> EODOperationFailureSummary:
    return EODOperationFailureSummary(
        "provider_unavailable", "provider", "Provider data was unavailable.", True
    )


def assert_error(code: EODOperationJobRepositoryErrorCode, call, *args, **kwargs):
    with pytest.raises(EODOperationJobRepositoryError) as captured:
        call(*args, **kwargs)
    assert captured.value.code is code
    assert captured.value.to_dict()["code"] == code.value


def submit_and_claim(repository, request=None, *, now=NOW, key=None, lease_seconds=60):
    submitted = repository.submit(request or make_request(), now=now, idempotency_key=key)
    claimed = repository.claim_next(worker_id="worker-1", now=now, lease_seconds=lease_seconds)
    assert claimed is not None
    return submitted, claimed


def fail_terminal(repository, request=None, *, key=None):
    submitted, claimed = submit_and_claim(repository, request, key=key)
    terminal = repository.fail(
        claimed.job_id,
        worker_id="worker-1",
        claim_version=claimed.claim_version,
        failure=failure(),
        now=NOW + timedelta(seconds=1),
    )
    return submitted, terminal


def _failed_retry_chain(repository, length):
    chain = []
    for index in range(length):
        timestamp = NOW + timedelta(seconds=index * 3)
        retry_of = None if not chain else chain[-1].job_id
        submitted = repository.submit(make_request(), now=timestamp, retry_of_job_id=retry_of)
        claimed = repository.claim_next(
            worker_id=f"worker-{index}", now=timestamp, lease_seconds=60
        )
        assert claimed is not None and claimed.job_id == submitted.job.job_id
        chain.append(
            repository.fail(
                claimed.job_id,
                worker_id=f"worker-{index}",
                claim_version=claimed.claim_version,
                failure=failure(),
                now=timestamp + timedelta(seconds=1),
            )
        )
    return tuple(chain)


def _record_sha_with_retry(job, retry_of_job_id):
    payload = job.logical_record_dict()
    payload["retry_of_job_id"] = retry_of_job_id
    serialized = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _rewrite_retry_link(root: Path, job, retry_of_job_id) -> None:
    database = root / EOD_OPERATION_DATABASE_NAME
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE jobs SET retry_of_job_id=?,record_sha256=? WHERE job_id=?",
            (retry_of_job_id, _record_sha_with_retry(job, retry_of_job_id), job.job_id),
        )


def _persistence_snapshot(root: Path) -> tuple:
    database = root / EOD_OPERATION_DATABASE_NAME
    with sqlite3.connect(database) as connection:
        jobs = tuple(connection.execute("SELECT * FROM jobs ORDER BY job_id"))
        bindings = tuple(
            connection.execute("SELECT * FROM idempotency_bindings ORDER BY key_sha256")
        )
    return jobs, bindings, _schema_snapshot(root)


def test_constructor_and_missing_reads_have_no_side_effects(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    assert not root.exists()
    assert repository.get(MISSING_JOB_ID) is None
    assert repository.list_recent() == ()
    health = repository.inspect_health()
    assert health.status is EODOperationRepositoryHealthStatus.ABSENT
    assert not root.exists()


def test_only_submit_initializes_schema_v1(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_ABSENT,
        repository.claim_next,
        worker_id="worker-1",
        now=NOW,
        lease_seconds=60,
    )
    assert not root.exists()
    submission = repository.submit(make_request(), now=NOW)
    database = root / EOD_OPERATION_DATABASE_NAME
    assert submission.status is EODOperationSubmissionStatus.CREATED
    assert database.is_file()
    connection = sqlite3.connect(database)
    try:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()[0] == str(EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION)
        index_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='one_active_operation_fingerprint'"
        ).fetchone()[0]
        index = next(
            row
            for row in connection.execute("PRAGMA index_list('jobs')")
            if row[1] == "one_active_operation_fingerprint"
        )
        assert "WHERE status IN ('queued','running')" in index_sql
        assert (index[2], index[4]) == (1, 1)
        assert tuple(
            row[2]
            for row in connection.execute("PRAGMA index_info(one_active_operation_fingerprint)")
        ) == ("operation_fingerprint",)
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        connection.close()
    assert repository.inspect_health().status is EODOperationRepositoryHealthStatus.HEALTHY


def _schema_snapshot(root: Path) -> tuple:
    connection = sqlite3.connect(root / EOD_OPERATION_DATABASE_NAME)
    try:
        return tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT type,name,tbl_name,sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        )
    finally:
        connection.close()


class _SchemaSqlOverrideConnection:
    def __init__(self, connection: sqlite3.Connection, sql_value: object) -> None:
        self._connection = connection
        self._sql_value = sql_value

    def execute(self, statement: str, parameters=()):
        result = self._connection.execute(statement, parameters)
        if statement.startswith("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name IN "):
            rows = []
            for row in result:
                values = list(row)
                if values[1] == "one_active_operation_fingerprint":
                    values[3] = self._sql_value
                rows.append(tuple(values))
            return rows
        return result

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def _edit_schema(root: Path, edit) -> None:
    connection = sqlite3.connect(root / EOD_OPERATION_DATABASE_NAME)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        edit(connection)
        connection.commit()
    finally:
        connection.close()


def _assert_corrupt_schema_rejected(root: Path, job_id: str, repository=None) -> None:
    expected_schema = _schema_snapshot(root)
    repository = repository or LocalEODOperationJobRepository(root)
    health = repository.inspect_health()
    assert health.status is EODOperationRepositoryHealthStatus.INVALID
    assert health.reason_code == EODOperationJobRepositoryErrorCode.CORRUPT_RECORD.value
    assert_error(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD, repository.get, job_id)
    assert_error(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD, repository.list_recent)
    mutations = (
        lambda: repository.submit(make_request("000001.SZ"), now=NOW),
        lambda: repository.claim_next(worker_id="worker-1", now=NOW, lease_seconds=60),
        lambda: repository.renew_lease(
            job_id, worker_id="worker-1", claim_version=1, now=NOW, lease_seconds=60
        ),
        lambda: repository.complete(
            job_id,
            worker_id="worker-1",
            claim_version=1,
            result=EODOperationResultSummary("completed"),
            now=NOW,
        ),
        lambda: repository.fail(
            job_id,
            worker_id="worker-1",
            claim_version=1,
            failure=failure(),
            now=NOW,
        ),
        lambda: repository.mark_expired_running_abandoned(now=NOW),
    )
    for mutation in mutations:
        assert_error(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD, mutation)
    assert _schema_snapshot(root) == expected_schema


def test_dropped_critical_index_is_invalid_and_all_mutations_fail_closed(tmp_path):
    root = tmp_path / "operations"
    job = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job
    _edit_schema(
        root, lambda connection: connection.execute("DROP INDEX one_active_operation_fingerprint")
    )
    _assert_corrupt_schema_rejected(root, job.job_id)


def test_same_name_index_with_wrong_predicate_is_invalid(tmp_path):
    root = tmp_path / "operations"
    job = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job

    def replace_index(connection):
        connection.execute("DROP INDEX one_active_operation_fingerprint")
        connection.execute(
            "CREATE UNIQUE INDEX one_active_operation_fingerprint "
            "ON jobs(operation_fingerprint) WHERE status = 'queued'"
        )

    _edit_schema(root, replace_index)
    _assert_corrupt_schema_rejected(root, job.job_id)


def test_missing_required_table_is_invalid_and_not_repaired(tmp_path):
    root = tmp_path / "operations"
    job = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job
    _edit_schema(root, lambda connection: connection.execute("DROP TABLE idempotency_bindings"))
    _assert_corrupt_schema_rejected(root, job.job_id)


def test_missing_required_column_is_invalid(tmp_path):
    root = tmp_path / "operations"
    job = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job

    def remove_column(connection):
        definitions = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name IN "
                "('jobs','one_active_operation_fingerprint','jobs_recent',"
                "'idempotency_bindings','idempotency_bindings_job')"
            )
        )
        connection.execute("DROP TABLE idempotency_bindings")
        connection.execute("DROP INDEX one_active_operation_fingerprint")
        connection.execute("DROP INDEX jobs_recent")
        connection.execute("ALTER TABLE jobs RENAME TO jobs_original")
        malformed = definitions["jobs"].replace("result_summary_json TEXT,", "")
        assert malformed != definitions["jobs"]
        connection.execute(malformed)
        for name in (
            "one_active_operation_fingerprint",
            "jobs_recent",
            "idempotency_bindings",
            "idempotency_bindings_job",
        ):
            connection.execute(definitions[name])
        connection.execute("DROP TABLE jobs_original")

    _edit_schema(root, remove_column)
    _assert_corrupt_schema_rejected(root, job.job_id)


def test_missing_foreign_key_is_invalid(tmp_path):
    root = tmp_path / "operations"
    job = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job

    def remove_foreign_key(connection):
        definitions = dict(
            connection.execute(
                "SELECT name,sql FROM sqlite_master "
                "WHERE name IN ('idempotency_bindings','idempotency_bindings_job')"
            )
        )
        connection.execute("DROP TABLE idempotency_bindings")
        malformed = definitions["idempotency_bindings"].replace(
            ",FOREIGN KEY(job_id) REFERENCES jobs(job_id)", ""
        )
        assert malformed != definitions["idempotency_bindings"]
        connection.execute(malformed)
        connection.execute(definitions["idempotency_bindings_job"])

    _edit_schema(root, remove_foreign_key)
    _assert_corrupt_schema_rejected(root, job.job_id)


@pytest.mark.parametrize(
    "malformed_sql",
    [None, 7, "", "   "],
    ids=("null", "non-text", "empty", "whitespace-only"),
)
def test_non_text_or_empty_schema_sql_is_corrupt_and_fail_closed(
    tmp_path, monkeypatch, malformed_sql
):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    job = repository.submit(make_request(), now=NOW).job
    open_read = repository._open_read
    open_write = repository._open_write

    def overridden_read():
        connection = open_read()
        assert connection is not None
        return _SchemaSqlOverrideConnection(connection, malformed_sql)

    def overridden_write(*, create):
        return _SchemaSqlOverrideConnection(open_write(create=create), malformed_sql)

    monkeypatch.setattr(repository, "_open_read", overridden_read)
    monkeypatch.setattr(repository, "_open_write", overridden_write)
    _assert_corrupt_schema_rejected(root, job.job_id, repository)


def test_submit_get_roundtrip_and_list_filters(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    first = repository.submit(make_request(), now=NOW).job
    second = repository.submit(make_request("000001.SZ"), now=NOW + timedelta(seconds=1)).job
    first_running = repository.claim_next(
        worker_id="worker-1", now=NOW + timedelta(seconds=1), lease_seconds=60
    )
    assert first_running.job_id == first.job_id
    assert repository.get(first.job_id) == first_running
    assert [job.job_id for job in repository.list_recent()] == [second.job_id, first.job_id]
    assert repository.list_recent(statuses=(EODOperationJobStatus.QUEUED,)) == (second,)
    assert repository.list_recent(operation_types=(EODOperationType.INCREMENTAL_SINGLE,)) == (
        second,
        first_running,
    )
    for value in (0, 257, True):
        with pytest.raises(ValueError):
            repository.list_recent(limit=value)
    with pytest.raises(ValueError):
        repository.list_recent(statuses=("queued",))


def test_idempotency_truth_table_active_and_terminal(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    request = make_request()
    created = repository.submit(request, now=NOW, idempotency_key="key-1")
    replay = repository.submit(request, now=NOW + timedelta(seconds=1), idempotency_key="key-1")
    no_key = repository.submit(request, now=NOW + timedelta(seconds=2))
    alias = repository.submit(request, now=NOW + timedelta(seconds=3), idempotency_key="key-2")
    assert created.status is EODOperationSubmissionStatus.CREATED
    assert replay.status is EODOperationSubmissionStatus.IDEMPOTENT_REPLAY
    assert no_key.status is alias.status is EODOperationSubmissionStatus.EXISTING_ACTIVE
    assert {created.job.job_id, replay.job.job_id, no_key.job.job_id, alias.job.job_id} == {
        created.job.job_id
    }
    assert_error(
        EODOperationJobRepositoryErrorCode.IDEMPOTENCY_CONFLICT,
        repository.submit,
        make_request("000001.SZ"),
        now=NOW,
        idempotency_key="key-1",
    )
    claimed = repository.claim_next(worker_id="worker-1", now=NOW, lease_seconds=60)
    repository.fail(
        claimed.job_id,
        worker_id="worker-1",
        claim_version=1,
        failure=failure(),
        now=NOW + timedelta(seconds=1),
    )
    old = repository.submit(request, now=NOW + timedelta(seconds=2), idempotency_key="key-1")
    fresh = repository.submit(request, now=NOW + timedelta(seconds=2))
    assert old.status is EODOperationSubmissionStatus.IDEMPOTENT_REPLAY
    assert old.job.job_id == created.job.job_id
    assert fresh.status is EODOperationSubmissionStatus.CREATED
    assert fresh.job.job_id != created.job.job_id


def test_idempotency_alias_limit_is_atomic(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    request = make_request()
    canonical = repository.submit(request, now=NOW, idempotency_key="alias-0").job
    for index in range(1, MAX_EOD_JOB_ALIASES):
        submission = repository.submit(request, now=NOW, idempotency_key=f"alias-{index}")
        assert submission.job.job_id == canonical.job_id
    assert_error(
        EODOperationJobRepositoryErrorCode.IDEMPOTENCY_ALIAS_LIMIT,
        repository.submit,
        request,
        now=NOW,
        idempotency_key="alias-over-limit",
    )
    assert repository.list_recent() == (canonical,)


def test_same_key_with_different_retry_intent_conflicts(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    original, terminal = fail_terminal(repository)
    retry = repository.submit(
        make_request(),
        now=NOW + timedelta(seconds=2),
        idempotency_key="retry-key",
        retry_of_job_id=terminal.job_id,
    )
    assert retry.job.retry_of_job_id == original.job.job_id
    assert_error(
        EODOperationJobRepositoryErrorCode.IDEMPOTENCY_CONFLICT,
        repository.submit,
        make_request(),
        now=NOW + timedelta(seconds=3),
        idempotency_key="retry-key",
    )


def test_retry_links_accept_only_same_failed_or_abandoned_job(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    _, failed = fail_terminal(repository)
    retry = repository.submit(
        make_request(), now=NOW + timedelta(seconds=2), retry_of_job_id=failed.job_id
    )
    assert retry.job.retry_of_job_id == failed.job_id

    other = LocalEODOperationJobRepository(tmp_path / "other")
    completed_submission, claimed = submit_and_claim(other)
    completed = other.complete(
        claimed.job_id,
        worker_id="worker-1",
        claim_version=1,
        result=EODOperationResultSummary("completed"),
        now=NOW + timedelta(seconds=1),
    )
    for retry_id, request in (
        (MISSING_JOB_ID, make_request()),
        (completed.job_id, make_request()),
        (completed_submission.job.job_id, make_request("000001.SZ")),
    ):
        assert_error(
            EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK,
            other.submit,
            request,
            now=NOW + timedelta(seconds=2),
            retry_of_job_id=retry_id,
        )


def test_queued_and_running_retry_targets_are_rejected(tmp_path):
    queued_repo = LocalEODOperationJobRepository(tmp_path / "queued")
    queued = queued_repo.submit(make_request(), now=NOW).job
    assert_error(
        EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK,
        queued_repo.submit,
        make_request(),
        now=NOW,
        retry_of_job_id=queued.job_id,
    )
    running_repo = LocalEODOperationJobRepository(tmp_path / "running")
    _, running = submit_and_claim(running_repo)
    assert_error(
        EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK,
        running_repo.submit,
        make_request(),
        now=NOW,
        retry_of_job_id=running.job_id,
    )


def test_self_retry_cycle_fails_closed_and_preserves_database(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    (job,) = _failed_retry_chain(repository, 1)
    _rewrite_retry_link(root, job, job.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.CORRUPT_RECORD,
        repository.get,
        job.job_id,
    )
    assert _persistence_snapshot(root) == expected


def test_two_node_retry_cycle_fails_closed_and_preserves_database(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    first, second = _failed_retry_chain(repository, 2)
    _rewrite_retry_link(root, first, second.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.CORRUPT_RECORD,
        repository.get,
        first.job_id,
    )
    assert _persistence_snapshot(root) == expected


def test_non_root_retry_cycle_fails_closed_and_preserves_database(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    first, second, root_job = _failed_retry_chain(repository, 3)
    _rewrite_retry_link(root, first, second.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.CORRUPT_RECORD,
        repository.get,
        root_job.job_id,
    )
    assert _persistence_snapshot(root) == expected


def test_valid_multi_hop_retry_chain_remains_readable(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    chain = _failed_retry_chain(repository, 3)
    assert tuple(repository.get(job.job_id) for job in chain) == chain
    assert repository.list_recent() == tuple(reversed(chain))


def test_list_retry_cycle_fails_closed_and_preserves_database(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    first, second = _failed_retry_chain(repository, 2)
    _rewrite_retry_link(root, first, second.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.CORRUPT_RECORD,
        repository.list_recent,
    )
    assert _persistence_snapshot(root) == expected


def test_claim_retry_cycle_fails_closed_before_transition(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    first, second = _failed_retry_chain(repository, 2)
    queued = repository.submit(
        make_request(),
        now=NOW + timedelta(seconds=6),
        retry_of_job_id=second.job_id,
    ).job
    _rewrite_retry_link(root, first, second.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.CORRUPT_RECORD,
        repository.claim_next,
        worker_id="worker-claim",
        now=NOW + timedelta(seconds=6),
        lease_seconds=60,
    )
    assert _persistence_snapshot(root) == expected
    with sqlite3.connect(root / EOD_OPERATION_DATABASE_NAME) as connection:
        status = connection.execute(
            "SELECT status FROM jobs WHERE job_id=?", (queued.job_id,)
        ).fetchone()[0]
    assert status == "queued"


def test_submit_retry_cycle_is_invalid_and_preserves_database(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    first, second = _failed_retry_chain(repository, 2)
    _rewrite_retry_link(root, first, second.job_id)
    expected = _persistence_snapshot(root)
    assert_error(
        EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK,
        repository.submit,
        make_request(),
        now=NOW + timedelta(seconds=6),
        retry_of_job_id=first.job_id,
        idempotency_key="cycle-submit",
    )
    assert _persistence_snapshot(root) == expected


def test_claim_renew_complete_and_fail_lease_rules(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    submitted, running = submit_and_claim(repository)
    assert running.status is EODOperationJobStatus.RUNNING
    assert running.claim_version == 1
    renewed = repository.renew_lease(
        running.job_id,
        worker_id="worker-1",
        claim_version=1,
        now=NOW + timedelta(seconds=1),
        lease_seconds=60,
    )
    assert renewed.lease_expires_at > running.lease_expires_at
    for worker, version in (("worker-2", 1), ("worker-1", 2)):
        assert_error(
            EODOperationJobRepositoryErrorCode.LEASE_CONFLICT,
            repository.complete,
            running.job_id,
            worker_id=worker,
            claim_version=version,
            result=EODOperationResultSummary("completed"),
            now=NOW + timedelta(seconds=2),
        )
    completed = repository.complete(
        running.job_id,
        worker_id="worker-1",
        claim_version=1,
        result=EODOperationResultSummary("completed"),
        now=NOW + timedelta(seconds=2),
    )
    assert completed.status is EODOperationJobStatus.COMPLETED
    assert completed.result.result_code == "completed"
    assert_error(
        EODOperationJobRepositoryErrorCode.LEASE_CONFLICT,
        repository.fail,
        submitted.job.job_id,
        worker_id="worker-1",
        claim_version=1,
        failure=failure(),
        now=NOW + timedelta(seconds=3),
    )


def test_expired_claim_cannot_complete_and_explicit_abandonment_is_bounded(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    _, running = submit_and_claim(repository, lease_seconds=30)
    expired = NOW + timedelta(seconds=30)
    assert_error(
        EODOperationJobRepositoryErrorCode.LEASE_CONFLICT,
        repository.complete,
        running.job_id,
        worker_id="worker-1",
        claim_version=1,
        result=EODOperationResultSummary("completed"),
        now=expired,
    )
    abandoned = repository.mark_expired_running_abandoned(now=expired, limit=1)
    assert len(abandoned) == 1
    assert abandoned[0].status is EODOperationJobStatus.ABANDONED
    assert abandoned[0].failure.error_code == "lease_expired"
    assert repository.mark_expired_running_abandoned(now=expired, limit=1) == ()


def _process_submit(root: str, gate, output) -> None:
    gate.wait()
    try:
        result = LocalEODOperationJobRepository(Path(root)).submit(make_request(), now=NOW)
        output.put(("ok", result.status.value, result.job.job_id))
    except Exception as exc:
        output.put(("error", type(exc).__name__, ""))


def _process_claim(root: str, worker_id: str, gate, output) -> None:
    gate.wait()
    try:
        result = LocalEODOperationJobRepository(Path(root)).claim_next(
            worker_id=worker_id, now=NOW, lease_seconds=60
        )
        output.put(("ok", None if result is None else result.job_id))
    except Exception as exc:
        output.put(("error", type(exc).__name__))


def _run_spawn_pair(target, args_one, args_two):
    context = get_context("spawn")
    gate = context.Event()
    output = context.Queue()
    processes = (
        context.Process(target=target, args=(*args_one, gate, output)),
        context.Process(target=target, args=(*args_two, gate, output)),
    )
    for process in processes:
        process.start()
    gate.set()
    results = tuple(output.get(timeout=20) for _ in processes)
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    return results


def test_threaded_submit_creates_exactly_one_active_job(tmp_path):
    root = tmp_path / "operations"
    barrier = Barrier(3)
    results = []

    def submit() -> None:
        barrier.wait()
        results.append(LocalEODOperationJobRepository(root).submit(make_request(), now=NOW))

    threads = (Thread(target=submit), Thread(target=submit))
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert sorted(result.status.value for result in results) == ["created", "existing_active"]
    assert len({result.job.job_id for result in results}) == 1


def test_threaded_claim_returns_job_to_exactly_one_worker(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    queued = repository.submit(make_request(), now=NOW).job
    barrier = Barrier(3)
    results = []

    def claim(worker: str) -> None:
        barrier.wait()
        results.append(repository.claim_next(worker_id=worker, now=NOW, lease_seconds=60))

    threads = (Thread(target=claim, args=("worker-1",)), Thread(target=claim, args=("worker-2",)))
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0].job_id == queued.job_id


def test_spawn_processes_submit_one_active_job(tmp_path):
    root_path = tmp_path / "operations"
    assert not root_path.exists()
    root = str(root_path)
    results = _run_spawn_pair(_process_submit, (root,), (root,))
    assert {item[0] for item in results} == {"ok"}
    assert sorted(item[1] for item in results) == ["created", "existing_active"]
    assert len({item[2] for item in results}) == 1
    repository = LocalEODOperationJobRepository(root_path)
    assert repository.inspect_health().status is EODOperationRepositoryHealthStatus.HEALTHY
    connection = sqlite3.connect(root_path / EOD_OPERATION_DATABASE_NAME)
    try:
        index = next(
            row
            for row in connection.execute("PRAGMA index_list('jobs')")
            if row[1] == "one_active_operation_fingerprint"
        )
        columns = tuple(
            row[2]
            for row in connection.execute("PRAGMA index_info(one_active_operation_fingerprint)")
        )
    finally:
        connection.close()
    assert (index[2], index[4], columns) == (1, 1, ("operation_fingerprint",))


def test_concurrent_idempotency_aliases_enforce_the_cap_atomically(tmp_path):
    root = tmp_path / "operations"
    request = make_request()
    repository = LocalEODOperationJobRepository(root)
    for index in range(MAX_EOD_JOB_ALIASES - 1):
        repository.submit(request, now=NOW, idempotency_key=f"alias-{index}")
    barrier = Barrier(3)
    outcomes = []

    def submit_alias(key: str) -> None:
        barrier.wait()
        try:
            submission = LocalEODOperationJobRepository(root).submit(
                request, now=NOW, idempotency_key=key
            )
            outcomes.append(("ok", submission.status.value))
        except EODOperationJobRepositoryError as exc:
            outcomes.append(("error", exc.code.value))

    threads = tuple(
        Thread(target=submit_alias, args=(f"concurrent-{index}",)) for index in range(2)
    )
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert sorted(outcomes) == [
        ("error", EODOperationJobRepositoryErrorCode.IDEMPOTENCY_ALIAS_LIMIT.value),
        ("ok", EODOperationSubmissionStatus.EXISTING_ACTIVE.value),
    ]
    connection = sqlite3.connect(root / EOD_OPERATION_DATABASE_NAME)
    try:
        count = connection.execute("SELECT COUNT(*) FROM idempotency_bindings").fetchone()[0]
    finally:
        connection.close()
    assert count == MAX_EOD_JOB_ALIASES


def test_complete_and_abandon_race_has_exactly_one_terminal_transition(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    _, running = submit_and_claim(repository, lease_seconds=30)
    barrier = Barrier(3)
    outcomes = []

    def complete() -> None:
        barrier.wait()
        try:
            terminal = LocalEODOperationJobRepository(root).complete(
                running.job_id,
                worker_id="worker-1",
                claim_version=1,
                result=EODOperationResultSummary("completed"),
                now=NOW + timedelta(seconds=30, microseconds=-1),
            )
            outcomes.append(("complete", terminal.status.value))
        except EODOperationJobRepositoryError as exc:
            outcomes.append(("complete_error", exc.code.value))

    def abandon() -> None:
        barrier.wait()
        terminal = LocalEODOperationJobRepository(root).mark_expired_running_abandoned(
            now=NOW + timedelta(seconds=30)
        )
        outcomes.append(("abandon", tuple(job.status.value for job in terminal)))

    threads = (Thread(target=complete), Thread(target=abandon))
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    final = repository.get(running.job_id)
    assert final.status in (
        EODOperationJobStatus.COMPLETED,
        EODOperationJobStatus.ABANDONED,
    )
    if final.status is EODOperationJobStatus.COMPLETED:
        assert ("complete", "completed") in outcomes
        assert ("abandon", ()) in outcomes
    else:
        assert ("abandon", ("abandoned",)) in outcomes
        assert (
            "complete_error",
            EODOperationJobRepositoryErrorCode.LEASE_CONFLICT.value,
        ) in outcomes


def test_spawn_processes_claim_one_queued_job(tmp_path):
    root = tmp_path / "operations"
    queued = LocalEODOperationJobRepository(root).submit(make_request(), now=NOW).job
    results = _run_spawn_pair(
        _process_claim,
        (str(root), "worker-1"),
        (str(root), "worker-2"),
    )
    assert {item[0] for item in results} == {"ok"}
    assert sorted(item[1] is None for item in results) == [False, True]
    assert queued.job_id in {item[1] for item in results}


def test_begin_insert_and_commit_failures_leave_no_ghost_jobs(tmp_path, monkeypatch):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    original = repository.submit(make_request(), now=NOW).job

    def rejected(*_args, **_kwargs):
        raise EODOperationJobRepositoryError(EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(repository, "_begin", rejected)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.submit,
        make_request("000001.SZ"),
        now=NOW,
    )
    monkeypatch.undo()
    assert repository.list_recent() == (original,)

    execute = repository._execute

    def fail_insert(connection, statement, parameters=()):
        if statement.startswith("INSERT INTO jobs"):
            raise sqlite3.OperationalError("synthetic insert failure")
        return execute(connection, statement, parameters)

    monkeypatch.setattr(repository, "_execute", fail_insert)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.submit,
        make_request("000001.SZ"),
        now=NOW,
    )
    monkeypatch.undo()
    assert repository.list_recent() == (original,)

    monkeypatch.setattr(repository, "_commit", rejected)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.submit,
        make_request("000001.SZ"),
        now=NOW,
    )
    monkeypatch.undo()
    assert repository.list_recent() == (original,)


def test_state_transition_commit_failure_rolls_back_for_new_repository(tmp_path, monkeypatch):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    queued = repository.submit(make_request(), now=NOW).job

    def rejected(_connection):
        raise EODOperationJobRepositoryError(EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(repository, "_commit", rejected)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.claim_next,
        worker_id="worker-1",
        now=NOW,
        lease_seconds=60,
    )
    monkeypatch.undo()
    reopened = LocalEODOperationJobRepository(root)
    assert reopened.get(queued.job_id).status is EODOperationJobStatus.QUEUED


def test_update_serialization_and_hash_failures_roll_back(tmp_path, monkeypatch):
    import autowealth.market_data.operations as operations_module

    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    queued = repository.submit(make_request(), now=NOW).job

    def rejected(*_args, **_kwargs):
        raise EODOperationJobRepositoryError(EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE)

    monkeypatch.setattr(repository, "_update_job", rejected)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.claim_next,
        worker_id="worker-1",
        now=NOW,
        lease_seconds=60,
    )
    monkeypatch.undo()
    assert repository.get(queued.job_id).status is EODOperationJobStatus.QUEUED

    def serialization_failure(_self):
        raise ValueError("synthetic serialization failure")

    monkeypatch.setattr(EODOperationRequest, "to_json", serialization_failure)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.submit,
        make_request("000001.SZ"),
        now=NOW,
    )
    monkeypatch.undo()

    original_fingerprint = operations_module._fingerprint
    fingerprint_calls = 0

    def hash_failure(payload):
        nonlocal fingerprint_calls
        fingerprint_calls += 1
        if fingerprint_calls >= 3:
            raise ValueError("synthetic hash failure")
        return original_fingerprint(payload)

    monkeypatch.setattr(operations_module, "_fingerprint", hash_failure)
    assert_error(
        EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE,
        repository.claim_next,
        worker_id="worker-1",
        now=NOW,
        lease_seconds=60,
    )
    monkeypatch.undo()
    assert repository.get(queued.job_id).status is EODOperationJobStatus.QUEUED


def _corrupt_job(tmp_path, statement: str, parameters=()):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    job = repository.submit(make_request(), now=NOW).job
    with sqlite3.connect(tmp_path / "operations" / EOD_OPERATION_DATABASE_NAME) as connection:
        connection.execute("PRAGMA ignore_check_constraints=ON")
        connection.execute(statement, parameters)
        connection.commit()
    return repository, job


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        ("UPDATE jobs SET canonical_request_json='{}'", ()),
        ("UPDATE jobs SET status='unknown'", ()),
        ("UPDATE jobs SET created_at='2026-08-24T08:00:00'", ()),
        ("UPDATE jobs SET status='running'", ()),
        ("UPDATE jobs SET operation_fingerprint='sha256:' || lower(hex(randomblob(32)))", ()),
        ("UPDATE jobs SET record_sha256='sha256:' || lower(hex(randomblob(32)))", ()),
        ("UPDATE jobs SET retry_of_job_id=?", (MISSING_JOB_ID,)),
    ],
)
def test_corrupt_job_rows_fail_closed(tmp_path, statement, parameters):
    repository, job = _corrupt_job(tmp_path, statement, parameters)
    assert_error(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD, repository.get, job.job_id)


def test_unknown_schema_and_invalid_database_fail_closed(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "unknown")
    job = repository.submit(make_request(), now=NOW).job
    with sqlite3.connect(tmp_path / "unknown" / EOD_OPERATION_DATABASE_NAME) as connection:
        connection.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
        connection.commit()
    assert_error(EODOperationJobRepositoryErrorCode.UNSUPPORTED_SCHEMA, repository.get, job.job_id)

    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    (invalid_root / EOD_OPERATION_DATABASE_NAME).write_bytes(b"not-a-sqlite-database")
    health = LocalEODOperationJobRepository(invalid_root).inspect_health()
    assert health.status is EODOperationRepositoryHealthStatus.INVALID


def test_list_recent_fails_entire_selection_on_one_corrupt_row(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    first = repository.submit(make_request(), now=NOW).job
    repository.submit(make_request("000001.SZ"), now=NOW + timedelta(seconds=1))
    database = tmp_path / "operations" / EOD_OPERATION_DATABASE_NAME
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE jobs SET record_sha256='sha256:' || ? WHERE job_id=?", ("0" * 64, first.job_id)
        )
        connection.commit()
    assert_error(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD, repository.list_recent)


def _symlink_or_skip(target: Path, link: Path, *, directory: bool) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink capability is unavailable: {type(exc).__name__}")


def test_root_database_and_sidecar_symlinks_are_rejected(tmp_path):
    target_root = tmp_path / "target-root"
    target_root.mkdir()
    root_link = tmp_path / "root-link"
    _symlink_or_skip(target_root, root_link, directory=True)
    linked = LocalEODOperationJobRepository(root_link)
    assert_error(EODOperationJobRepositoryErrorCode.UNSAFE_PATH, linked.get, MISSING_JOB_ID)

    root = tmp_path / "database-link"
    root.mkdir()
    target_file = tmp_path / "target.sqlite3"
    target_file.touch()
    _symlink_or_skip(target_file, root / EOD_OPERATION_DATABASE_NAME, directory=False)
    assert_error(
        EODOperationJobRepositoryErrorCode.UNSAFE_PATH,
        LocalEODOperationJobRepository(root).submit,
        make_request(),
        now=NOW,
    )

    sidecar_root = tmp_path / "sidecar-link"
    sidecar_root.mkdir()
    sidecar_target = tmp_path / "sidecar-target"
    sidecar_target.touch()
    _symlink_or_skip(
        sidecar_target,
        Path(str(sidecar_root / EOD_OPERATION_DATABASE_NAME) + "-journal"),
        directory=False,
    )
    assert_error(
        EODOperationJobRepositoryErrorCode.UNSAFE_PATH,
        LocalEODOperationJobRepository(sidecar_root).submit,
        make_request(),
        now=NOW,
    )


def test_unsafe_root_and_database_file_types_are_rejected(tmp_path):
    root_file = tmp_path / "root-file"
    root_file.write_text("unsafe", encoding="utf-8")
    assert_error(
        EODOperationJobRepositoryErrorCode.UNSAFE_PATH,
        LocalEODOperationJobRepository(root_file).submit,
        make_request(),
        now=NOW,
    )
    root = tmp_path / "db-directory"
    root.mkdir()
    (root / EOD_OPERATION_DATABASE_NAME).mkdir()
    assert_error(
        EODOperationJobRepositoryErrorCode.UNSAFE_PATH,
        LocalEODOperationJobRepository(root).submit,
        make_request(),
        now=NOW,
    )


def test_imports_do_not_connect_sqlite_write_files_or_load_executors(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    code = """
import pathlib
import socket
import sqlite3
import sys

def blocked(*args, **kwargs):
    raise AssertionError("import attempted a forbidden side effect")

sqlite3.connect = blocked
socket.create_connection = blocked
socket.socket.connect = blocked
before = set(pathlib.Path.cwd().iterdir())
import autowealth.market_data.operations
import autowealth.market_data.job_repository
import autowealth.market_data
assert before == set(pathlib.Path.cwd().iterdir())
for name in (
    "autowealth.market_data.batch",
    "autowealth.market_data.coordinator",
    "autowealth.market_data.provider_chain",
    "autowealth.market_data.full_refresh",
    "autowealth.market_data.maintenance",
):
    assert name not in sys.modules, name
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(source_root)
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_abandoned_retry_and_different_fingerprint_retry_rules(tmp_path):
    repository = LocalEODOperationJobRepository(tmp_path / "operations")
    request = make_request()
    _, running = submit_and_claim(repository, request, lease_seconds=30)
    abandoned = repository.mark_expired_running_abandoned(now=NOW + timedelta(seconds=30))[0]
    retry = repository.submit(
        request,
        now=NOW + timedelta(seconds=31),
        retry_of_job_id=abandoned.job_id,
    )
    assert retry.job.retry_of_job_id == abandoned.job_id

    other = LocalEODOperationJobRepository(tmp_path / "different")
    _, failed = fail_terminal(other, request)
    assert_error(
        EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK,
        other.submit,
        make_request("000001.SZ"),
        now=NOW + timedelta(seconds=2),
        retry_of_job_id=failed.job_id,
    )


def test_plaintext_idempotency_key_is_not_persisted(tmp_path):
    root = tmp_path / "operations"
    repository = LocalEODOperationJobRepository(root)
    plaintext = "private-idempotency-key"
    repository.submit(make_request(), now=NOW, idempotency_key=plaintext)
    database_bytes = (root / EOD_OPERATION_DATABASE_NAME).read_bytes()
    assert plaintext.encode("ascii") not in database_bytes
    with sqlite3.connect(root / EOD_OPERATION_DATABASE_NAME) as connection:
        stored = connection.execute("SELECT key_sha256 FROM idempotency_bindings").fetchone()[0]
    assert stored.startswith("sha256:")
    assert len(stored) == 71
