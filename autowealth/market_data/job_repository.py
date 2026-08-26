"""Durable local SQLite repository for EOD operation jobs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import importlib
import json
import re
import sqlite3
from typing import Callable, Optional, Protocol, Tuple, Type, TypeVar

from .operations import (
    EOD_OPERATION_JOB_SCHEMA_VERSION,
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
    validate_worker_id,
)
from .schemas import EODDatasetKey, EODStructuredWarning

Path = importlib.import_module("pathlib").Path
EOD_OPERATION_DATABASE_NAME = "eod_operation_jobs.sqlite3"
EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION = 1
EOD_OPERATION_BUSY_TIMEOUT_MILLISECONDS = 5_000
MAX_EOD_JOB_ALIASES = 32
MAX_EOD_JOB_LIST_LIMIT = 256

_IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_IDEMPOTENCY_DOMAIN = b"autowealth:eod-operation-idempotency:v1:"
_JOB_COLUMNS = (
    "job_id,schema_version,operation_type,canonical_request_json,"
    "operation_fingerprint,retry_of_job_id,status,created_at,started_at,"
    "finished_at,worker_id,claim_version,lease_expires_at,result_summary_json,"
    "failure_summary_json,record_sha256"
)
_CRITICAL_INDEX_SQL = "CREATE UNIQUE INDEX one_active_operation_fingerprint ON jobs(operation_fingerprint) WHERE status IN ('queued','running')"
_EnumType = TypeVar("_EnumType", bound=Enum)


def _schema_signature(connection: sqlite3.Connection) -> tuple:
    def rows(statement: str) -> tuple:
        return tuple(tuple(row) for row in connection.execute(statement))

    critical = "one_active_operation_fingerprint"
    objects = tuple(
        (*row[:3], "".join(row[3].split()) if isinstance(row[3], str) and row[3].strip() else None)
        for row in rows(
            "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name IN "
            "('metadata','jobs','idempotency_bindings','one_active_operation_fingerprint',"
            "'jobs_recent','idempotency_bindings_job') ORDER BY type,name"
        )
    )
    tables = tuple(
        (
            table,
            tuple(row[1:6] for row in rows(f"PRAGMA table_info({table})")),
            tuple((row[3], row[2], *row[4:8]) for row in rows(f"PRAGMA foreign_key_list({table})")),
        )
        for table in ("metadata", "jobs", "idempotency_bindings")
    )
    index = tuple(
        (row[1], row[2], row[4]) for row in rows("PRAGMA index_list('jobs')") if row[1] == critical
    )
    index_columns = tuple(row[2] for row in rows(f"PRAGMA index_info({critical})"))
    return objects, tables, index, index_columns


class EODOperationJobRepositoryErrorCode(str, Enum):
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDEMPOTENCY_ALIAS_LIMIT = "idempotency_alias_limit"
    INVALID_RETRY_LINK = "invalid_retry_link"
    JOB_NOT_FOUND = "job_not_found"
    INVALID_TRANSITION = "invalid_transition"
    LEASE_CONFLICT = "lease_conflict"
    PERSISTENCE_ABSENT = "persistence_absent"
    PERSISTENCE_BUSY = "persistence_busy"
    PERSISTENCE_FAILURE = "persistence_failure"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    CORRUPT_RECORD = "corrupt_record"
    UNSAFE_PATH = "unsafe_path"


class EODOperationJobRepositoryError(RuntimeError):
    def __init__(self, code: EODOperationJobRepositoryErrorCode) -> None:
        if type(code) is not EODOperationJobRepositoryErrorCode:
            raise TypeError("code must be an exact repository error code")
        self.code = code
        self.message = f"The EOD operation repository rejected the request ({code.value})."
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


class EODOperationRepositoryHealthStatus(str, Enum):
    ABSENT = "absent"
    HEALTHY = "healthy"
    INVALID = "invalid"


@dataclass(frozen=True)
class EODOperationRepositoryHealth:
    status: EODOperationRepositoryHealthStatus
    schema_version: Optional[int] = None
    reason_code: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.status) is not EODOperationRepositoryHealthStatus:
            raise TypeError("status must be an exact health status")
        if self.status is EODOperationRepositoryHealthStatus.ABSENT:
            if self.schema_version is not None or self.reason_code is not None:
                raise ValueError("absent health cannot contain schema or reason")
        elif self.status is EODOperationRepositoryHealthStatus.HEALTHY:
            if (
                self.schema_version != EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION
                or self.reason_code is not None
            ):
                raise ValueError("healthy repository requires the recognized schema")
        elif type(self.reason_code) is not str or not self.reason_code:
            raise ValueError("invalid repository health requires a reason_code")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "schema_version": self.schema_version,
            "reason_code": self.reason_code,
        }


class EODOperationJobRepository(Protocol):
    def submit(self, request, *, now, idempotency_key=None, retry_of_job_id=None): ...
    def get(self, job_id) -> Optional[EODOperationJob]: ...
    def list_recent(self, *, limit=50, statuses=None, operation_types=None): ...
    def claim_next(self, *, worker_id, now, lease_seconds): ...
    def renew_lease(self, job_id, *, worker_id, claim_version, now, lease_seconds): ...
    def complete(self, job_id, *, worker_id, claim_version, result, now): ...
    def fail(self, job_id, *, worker_id, claim_version, failure, now): ...
    def mark_expired_running_abandoned(self, *, now, limit=256): ...
    def inspect_health(self) -> EODOperationRepositoryHealth: ...


class LocalEODOperationJobRepository:
    def __init__(self, operations_root: Path) -> None:
        if not isinstance(operations_root, Path):
            raise TypeError("operations_root must be a pathlib Path")
        if not operations_root.is_absolute() or len(str(operations_root)) > 4096:
            raise ValueError("operations_root must be a bounded absolute path")
        self._root = operations_root
        self._database = operations_root / EOD_OPERATION_DATABASE_NAME

    def submit(
        self,
        request: EODOperationRequest,
        *,
        now: datetime,
        idempotency_key: Optional[str] = None,
        retry_of_job_id: Optional[str] = None,
    ) -> EODOperationSubmission:
        if type(request) is not EODOperationRequest:
            raise TypeError("request must be an exact EODOperationRequest")
        timestamp = self._utc(now, "now")
        key_hash = self._idempotency_hash(idempotency_key)
        retry_of = None
        if retry_of_job_id is not None:
            retry_of = validate_eod_operation_job_id(retry_of_job_id, "retry_of_job_id")

        def action(connection: sqlite3.Connection) -> EODOperationSubmission:
            if key_hash is not None:
                binding = self._execute(
                    connection,
                    "SELECT job_id,operation_fingerprint,retry_of_job_id "
                    "FROM idempotency_bindings WHERE key_sha256=?",
                    (key_hash,),
                ).fetchone()
                if binding is not None:
                    if (
                        binding["operation_fingerprint"] != request.fingerprint
                        or binding["retry_of_job_id"] != retry_of
                    ):
                        self._raise(EODOperationJobRepositoryErrorCode.IDEMPOTENCY_CONFLICT)
                    return EODOperationSubmission(
                        EODOperationSubmissionStatus.IDEMPOTENT_REPLAY,
                        self._required_job(connection, binding["job_id"]),
                    )
            self._validate_retry(connection, retry_of, request.fingerprint)
            active = self._execute(
                connection,
                f"SELECT {_JOB_COLUMNS} FROM jobs "
                "WHERE operation_fingerprint=? AND status IN ('queued','running')",
                (request.fingerprint,),
            ).fetchone()
            if active is not None:
                job = self._row_to_job(connection, active)
                if key_hash is not None:
                    self._bind_alias(
                        connection, key_hash, job.job_id, request.fingerprint, retry_of
                    )
                return EODOperationSubmission(EODOperationSubmissionStatus.EXISTING_ACTIVE, job)
            job = EODOperationJob(
                job_id=generate_eod_operation_job_id(timestamp),
                request=request,
                operation_fingerprint=request.fingerprint,
                retry_of_job_id=retry_of,
                status=EODOperationJobStatus.QUEUED,
                created_at=timestamp,
            )
            existing = self._insert_job(connection, job)
            submission_status = EODOperationSubmissionStatus.CREATED
            if existing is not None:
                job = existing
                submission_status = EODOperationSubmissionStatus.EXISTING_ACTIVE
            if key_hash is not None:
                self._bind_alias(connection, key_hash, job.job_id, request.fingerprint, retry_of)
            return EODOperationSubmission(submission_status, job)

        return self._mutate(action, initialize=True)

    def get(self, job_id: str) -> Optional[EODOperationJob]:
        safe_id = validate_eod_operation_job_id(job_id)
        connection = self._open_read()
        if connection is None:
            return None
        try:
            self._ensure_schema(connection, initialize=False)
            row = self._execute(
                connection, f"SELECT {_JOB_COLUMNS} FROM jobs WHERE job_id=?", (safe_id,)
            ).fetchone()
            return None if row is None else self._row_to_job(connection, row)
        finally:
            connection.close()

    def list_recent(
        self,
        *,
        limit: int = 50,
        statuses: Optional[Tuple[EODOperationJobStatus, ...]] = None,
        operation_types: Optional[Tuple[EODOperationType, ...]] = None,
    ) -> Tuple[EODOperationJob, ...]:
        safe_limit = self._bounded_int(limit, 1, MAX_EOD_JOB_LIST_LIMIT, "limit")
        status_values = self._enum_filter(statuses, EODOperationJobStatus, "statuses")
        type_values = self._enum_filter(operation_types, EODOperationType, "operation_types")
        connection = self._open_read()
        if connection is None:
            return ()
        try:
            self._ensure_schema(connection, initialize=False)
            clauses, parameters = [], []
            for column, values in (("status", status_values), ("operation_type", type_values)):
                if values:
                    clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
                    parameters.extend(item.value for item in values)
            where = "" if not clauses else " WHERE " + " AND ".join(clauses)
            rows = self._execute(
                connection,
                f"SELECT {_JOB_COLUMNS} FROM jobs{where} "
                "ORDER BY created_at DESC,job_id DESC LIMIT ?",
                (*parameters, safe_limit),
            ).fetchall()
            return tuple(self._row_to_job(connection, row) for row in rows)
        finally:
            connection.close()

    def claim_next(
        self, *, worker_id: str, now: datetime, lease_seconds: int
    ) -> Optional[EODOperationJob]:
        worker = validate_worker_id(worker_id)
        timestamp = self._utc(now, "now")
        seconds = self._bounded_int(lease_seconds, 30, 3600, "lease_seconds")

        def action(connection: sqlite3.Connection) -> Optional[EODOperationJob]:
            row = self._execute(
                connection,
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE status='queued' "
                "ORDER BY created_at ASC,job_id ASC LIMIT 1",
            ).fetchone()
            if row is None:
                return None
            job = self._row_to_job(connection, row)
            claimed = replace(
                job,
                status=EODOperationJobStatus.RUNNING,
                started_at=timestamp,
                worker_id=worker,
                claim_version=1,
                lease_expires_at=timestamp + timedelta(seconds=seconds),
                record_sha256=None,
            )
            self._update_job(connection, claimed)
            return claimed

        return self._mutate(action)

    def renew_lease(
        self,
        job_id: str,
        *,
        worker_id: str,
        claim_version: int,
        now: datetime,
        lease_seconds: int,
    ) -> EODOperationJob:
        timestamp = self._utc(now, "now")
        seconds = self._bounded_int(lease_seconds, 30, 3600, "lease_seconds")

        def action(connection: sqlite3.Connection) -> EODOperationJob:
            job = self._owned_running(connection, job_id, worker_id, claim_version, timestamp)
            renewed = replace(
                job,
                lease_expires_at=job.lease_expires_at + timedelta(seconds=seconds),
                record_sha256=None,
            )
            self._update_job(connection, renewed)
            return renewed

        return self._mutate(action)

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str,
        claim_version: int,
        result: EODOperationResultSummary,
        now: datetime,
    ) -> EODOperationJob:
        if type(result) is not EODOperationResultSummary:
            raise TypeError("result must be exact EODOperationResultSummary")
        return self._finish(job_id, worker_id, claim_version, now, result=result)

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        claim_version: int,
        failure: EODOperationFailureSummary,
        now: datetime,
    ) -> EODOperationJob:
        if type(failure) is not EODOperationFailureSummary:
            raise TypeError("failure must be exact EODOperationFailureSummary")
        return self._finish(job_id, worker_id, claim_version, now, failure=failure)

    def mark_expired_running_abandoned(
        self, *, now: datetime, limit: int = 256
    ) -> Tuple[EODOperationJob, ...]:
        timestamp = self._utc(now, "now")
        safe_limit = self._bounded_int(limit, 1, 256, "limit")

        def action(connection: sqlite3.Connection) -> Tuple[EODOperationJob, ...]:
            rows = self._execute(
                connection,
                f"SELECT {_JOB_COLUMNS} FROM jobs "
                "WHERE status='running' AND lease_expires_at<=? "
                "ORDER BY lease_expires_at ASC,created_at ASC,job_id ASC LIMIT ?",
                (timestamp.isoformat(timespec="microseconds"), safe_limit),
            ).fetchall()
            abandoned = []
            failure = EODOperationFailureSummary(
                error_code="lease_expired",
                stage="lease",
                safe_message="The EOD operation lease expired before completion.",
                retryable=True,
            )
            for row in rows:
                job = self._row_to_job(connection, row)
                terminal = replace(
                    job,
                    status=EODOperationJobStatus.ABANDONED,
                    finished_at=timestamp,
                    lease_expires_at=None,
                    failure=failure,
                    record_sha256=None,
                )
                self._update_job(connection, terminal)
                abandoned.append(terminal)
            return tuple(abandoned)

        return self._mutate(action)

    def inspect_health(self) -> EODOperationRepositoryHealth:
        try:
            connection = self._open_read()
            if connection is None:
                return EODOperationRepositoryHealth(EODOperationRepositoryHealthStatus.ABSENT)
            try:
                self._ensure_schema(connection, initialize=False)
                result = self._execute(connection, "PRAGMA quick_check").fetchone()
                if result is None or result[0] != "ok":
                    self._raise(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD)
            finally:
                connection.close()
            return EODOperationRepositoryHealth(
                EODOperationRepositoryHealthStatus.HEALTHY,
                schema_version=EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION,
            )
        except EODOperationJobRepositoryError as exc:
            reason = exc.code.value
        except sqlite3.Error:
            reason = EODOperationJobRepositoryErrorCode.CORRUPT_RECORD.value
        return EODOperationRepositoryHealth(
            EODOperationRepositoryHealthStatus.INVALID, reason_code=reason
        )

    def _finish(
        self, job_id, worker_id, claim_version, now, *, result=None, failure=None
    ) -> EODOperationJob:
        timestamp = self._utc(now, "now")

        def action(connection: sqlite3.Connection) -> EODOperationJob:
            job = self._owned_running(connection, job_id, worker_id, claim_version, timestamp)
            terminal = replace(
                job,
                status=(
                    EODOperationJobStatus.COMPLETED
                    if result is not None
                    else EODOperationJobStatus.FAILED
                ),
                finished_at=timestamp,
                lease_expires_at=None,
                result=result,
                failure=failure,
                record_sha256=None,
            )
            self._update_job(connection, terminal)
            return terminal

        return self._mutate(action)

    def _owned_running(self, connection, job_id, worker_id, claim_version, now) -> EODOperationJob:
        job = self._required_job(connection, validate_eod_operation_job_id(job_id))
        worker = validate_worker_id(worker_id)
        if isinstance(claim_version, bool) or type(claim_version) is not int or claim_version < 1:
            raise ValueError("claim_version must be a positive exact integer")
        if (
            job.status is not EODOperationJobStatus.RUNNING
            or job.worker_id != worker
            or job.claim_version != claim_version
            or job.lease_expires_at is None
            or job.lease_expires_at <= now
        ):
            self._raise(EODOperationJobRepositoryErrorCode.LEASE_CONFLICT)
        return job

    def _mutate(self, action: Callable[[sqlite3.Connection], object], initialize: bool = False):
        connection = self._open_write(create=initialize)
        try:
            self._begin(connection)
            self._ensure_schema(connection, initialize=initialize)
            result = action(connection)
            self._commit(connection)
            return result
        except EODOperationJobRepositoryError:
            self._rollback(connection)
            raise
        except Exception as exc:
            self._rollback(connection)
            raise self._persistence_error(exc) from None
        finally:
            connection.close()

    def _open_write(self, *, create: bool) -> sqlite3.Connection:
        self._assert_path_safety()
        if not self._database.exists():
            if not create:
                self._raise(EODOperationJobRepositoryErrorCode.PERSISTENCE_ABSENT)
            try:
                self._root.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._raise(EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE)
            self._assert_path_safety()
        try:
            connection = sqlite3.connect(
                self._database,
                timeout=EOD_OPERATION_BUSY_TIMEOUT_MILLISECONDS / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(f"PRAGMA busy_timeout={EOD_OPERATION_BUSY_TIMEOUT_MILLISECONDS}")
            return connection
        except sqlite3.Error as exc:
            raise self._persistence_error(exc) from None

    def _open_read(self) -> Optional[sqlite3.Connection]:
        self._assert_path_safety()
        if not self._root.exists() or not self._database.exists():
            return None
        uri = self._database.resolve(strict=True).as_uri() + "?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute(f"PRAGMA busy_timeout={EOD_OPERATION_BUSY_TIMEOUT_MILLISECONDS}")
            connection.execute("PRAGMA query_only=ON")
            return connection
        except (OSError, sqlite3.Error) as exc:
            raise self._persistence_error(exc) from None

    def _ensure_schema(self, connection: sqlite3.Connection, *, initialize: bool) -> None:
        metadata = self._execute(
            connection,
            "SELECT name FROM sqlite_master WHERE type='table' AND name='metadata'",
        ).fetchone()
        if metadata is None:
            tables = self._execute(
                connection,
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'",
            ).fetchall()
            if not initialize or tables:
                self._raise(EODOperationJobRepositoryErrorCode.UNSUPPORTED_SCHEMA)
            self._initialize_schema(connection)
        row = self._execute(
            connection, "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        if row is None or row["value"] != str(EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION):
            self._raise(EODOperationJobRepositoryErrorCode.UNSUPPORTED_SCHEMA)
        self._validate_schema_v1(connection)

    def _validate_schema_v1(self, connection: sqlite3.Connection) -> None:
        reference = sqlite3.connect(":memory:")
        try:
            self._initialize_schema(reference)
            valid = _schema_signature(connection) == _schema_signature(reference)
        except sqlite3.Error:
            valid = False
        finally:
            reference.close()
        if not valid:
            self._raise(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD)

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        statements = (
            "CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL)",
            "INSERT INTO metadata(key,value) VALUES ('schema_version','1')",
            "CREATE TABLE jobs (job_id TEXT PRIMARY KEY,schema_version INTEGER NOT NULL,operation_type TEXT NOT NULL,canonical_request_json TEXT NOT NULL,"
            "operation_fingerprint TEXT NOT NULL,retry_of_job_id TEXT,status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed','abandoned')),"
            "created_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,worker_id TEXT,claim_version INTEGER,lease_expires_at TEXT,result_summary_json TEXT,"
            "failure_summary_json TEXT,record_sha256 TEXT NOT NULL,FOREIGN KEY(retry_of_job_id) REFERENCES jobs(job_id))",
            _CRITICAL_INDEX_SQL,
            "CREATE INDEX jobs_recent ON jobs(created_at DESC,job_id DESC)",
            "CREATE TABLE idempotency_bindings (key_sha256 TEXT PRIMARY KEY,job_id TEXT NOT NULL,"
            "operation_fingerprint TEXT NOT NULL,retry_of_job_id TEXT,FOREIGN KEY(job_id) REFERENCES jobs(job_id))",
            "CREATE INDEX idempotency_bindings_job ON idempotency_bindings(job_id)",
        )
        for statement in statements:
            self._execute(connection, statement)

    def _job_values(self, job: EODOperationJob) -> tuple:
        values = job.to_dict()
        values.update(
            operation_type=job.request.operation_type.value,
            canonical_request_json=job.request.to_json(),
            result_summary_json=None if job.result is None else job.result.to_json(),
            failure_summary_json=None if job.failure is None else job.failure.to_json(),
        )
        return tuple(values.get(name) for name in _JOB_COLUMNS.split(","))

    def _insert_job(
        self, connection: sqlite3.Connection, job: EODOperationJob
    ) -> Optional[EODOperationJob]:
        placeholders = ",".join("?" for _ in _JOB_COLUMNS.split(","))
        try:
            self._execute(
                connection,
                f"INSERT INTO jobs ({_JOB_COLUMNS}) VALUES ({placeholders})",
                self._job_values(job),
            )
        except sqlite3.IntegrityError:
            row = self._execute(
                connection,
                f"SELECT {_JOB_COLUMNS} FROM jobs WHERE operation_fingerprint=? "
                "AND status IN ('queued','running')",
                (job.operation_fingerprint,),
            ).fetchone()
            if row is None:
                raise
            return self._row_to_job(connection, row)
        return None

    def _update_job(self, connection: sqlite3.Connection, job: EODOperationJob) -> None:
        columns = _JOB_COLUMNS.split(",")[6:]
        values = self._job_values(job)[6:]
        cursor = self._execute(
            connection,
            f"UPDATE jobs SET {','.join(f'{name}=?' for name in columns)} WHERE job_id=?",
            (*values, job.job_id),
        )
        if cursor.rowcount != 1:
            self._raise(EODOperationJobRepositoryErrorCode.JOB_NOT_FOUND)

    def _row_to_job(self, connection, row, validate_retry=True) -> EODOperationJob:
        try:
            values = dict(row)
            request = EODOperationRequest.from_json(values.pop("canonical_request_json"))
            if values.pop("operation_type") != request.operation_type.value:
                raise ValueError("operation_type does not match request")
            values["request"] = request
            values["result"] = self._summary(
                values.pop("result_summary_json"), EODOperationResultSummary
            )
            values["failure"] = self._summary(
                values.pop("failure_summary_json"), EODOperationFailureSummary
            )
            for field_name in ("created_at", "started_at", "finished_at", "lease_expires_at"):
                values[field_name] = self._time_or_none(values[field_name], field_name)
            job = EODOperationJob(**values)
            if validate_retry:
                self._validate_retry(
                    connection, job.retry_of_job_id, job.operation_fingerprint, job.job_id
                )
            return job
        except EODOperationJobRepositoryError as exc:
            if exc.code is EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK:
                self._raise(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD)
            raise
        except (KeyError, TypeError, ValueError):
            self._raise(EODOperationJobRepositoryErrorCode.CORRUPT_RECORD)

    def _summary(self, value: object, summary_type: type):
        if value is None:
            return None
        if type(value) is not str:
            raise ValueError("summary JSON must be text")
        payload = json.loads(value)
        if type(payload) is not dict:
            raise ValueError("summary JSON must contain an object")

        def exact(item: object, value_type: type):
            if type(item) is not dict:
                raise TypeError("persisted value must be an exact dict")
            restored = value_type(**item)
            if restored.to_dict() != item:
                raise ValueError("persisted value is not canonical")
            return restored

        if summary_type is EODOperationResultSummary:
            if set(payload) != {"result_code", "dataset_summaries", "warnings", "metadata"}:
                raise ValueError("result summary fields are invalid")
            payload["warnings"] = tuple(
                exact(item, EODStructuredWarning) for item in payload["warnings"]
            )
            payload["dataset_summaries"] = tuple(payload["dataset_summaries"])
        else:
            if set(payload) != {
                "error_code",
                "stage",
                "safe_message",
                "retryable",
                "datasets",
                "details",
            }:
                raise ValueError("failure summary fields are invalid")
            payload["datasets"] = tuple(exact(item, EODDatasetKey) for item in payload["datasets"])
        summary = summary_type(**payload)
        if summary.to_json() != value:
            raise ValueError("summary JSON is not canonical")
        return summary

    def _time_or_none(self, value: object, field_name: str) -> Optional[datetime]:
        if value is None:
            return None
        if type(value) is not str:
            raise ValueError(f"{field_name} must be canonical UTC text")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        normalized = parsed.astimezone(timezone.utc)
        if normalized.isoformat(timespec="microseconds") != value:
            raise ValueError(f"{field_name} must use canonical UTC serialization")
        return normalized

    def _required_job(self, connection: sqlite3.Connection, job_id: str) -> EODOperationJob:
        row = self._execute(
            connection, f"SELECT {_JOB_COLUMNS} FROM jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            self._raise(EODOperationJobRepositoryErrorCode.JOB_NOT_FOUND)
        return self._row_to_job(connection, row)

    def _validate_retry(self, connection, retry_of, fingerprint, root_job_id=None) -> None:
        visited = set() if root_job_id is None else {root_job_id}
        while retry_of is not None:
            if retry_of in visited:
                self._raise(EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK)
            visited.add(retry_of)
            row = self._execute(
                connection, f"SELECT {_JOB_COLUMNS} FROM jobs WHERE job_id=?", (retry_of,)
            ).fetchone()
            if row is None:
                self._raise(EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK)
            try:
                target = self._row_to_job(connection, row, False)
            except EODOperationJobRepositoryError:
                self._raise(EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK)
            if target.operation_fingerprint != fingerprint or target.status.value not in (
                "failed",
                "abandoned",
            ):
                self._raise(EODOperationJobRepositoryErrorCode.INVALID_RETRY_LINK)
            retry_of = target.retry_of_job_id

    def _bind_alias(self, connection, key_hash, job_id, fingerprint, retry_of) -> None:
        count = self._execute(
            connection, "SELECT COUNT(*) FROM idempotency_bindings WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        if count >= MAX_EOD_JOB_ALIASES:
            self._raise(EODOperationJobRepositoryErrorCode.IDEMPOTENCY_ALIAS_LIMIT)
        self._execute(
            connection,
            "INSERT INTO idempotency_bindings "
            "(key_sha256,job_id,operation_fingerprint,retry_of_job_id) VALUES (?,?,?,?)",
            (key_hash, job_id, fingerprint, retry_of),
        )

    def _idempotency_hash(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if type(value) is not str or _IDEMPOTENCY_PATTERN.fullmatch(value) is None:
            raise ValueError("idempotency_key must use 1..128 safe ASCII characters")
        return "sha256:" + hashlib.sha256(_IDEMPOTENCY_DOMAIN + value.encode("ascii")).hexdigest()

    def _utc(self, value: object, field_name: str) -> datetime:
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be an exact timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _bounded_int(self, value: object, minimum: int, maximum: int, field_name: str) -> int:
        if isinstance(value, bool) or type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f"{field_name} must be an exact integer from {minimum} to {maximum}")
        return value

    def _enum_filter(self, values, enum_type: Type[_EnumType], field_name: str) -> tuple:
        if values is None:
            return ()
        if type(values) not in (list, tuple) or len(values) > MAX_EOD_JOB_LIST_LIMIT:
            raise ValueError(f"{field_name} must be a bounded exact list or tuple")
        if any(type(item) is not enum_type for item in values) or len(set(values)) != len(values):
            raise ValueError(f"{field_name} contains invalid or duplicate values")
        return tuple(values)

    def _assert_path_safety(self) -> None:
        try:
            if self._root.is_symlink() or (self._root.exists() and not self._root.is_dir()):
                self._raise(EODOperationJobRepositoryErrorCode.UNSAFE_PATH)
            paths = (self._database,) + tuple(
                Path(str(self._database) + suffix) for suffix in ("-journal", "-wal", "-shm")
            )
            if any(path.is_symlink() or (path.exists() and not path.is_file()) for path in paths):
                self._raise(EODOperationJobRepositoryErrorCode.UNSAFE_PATH)
        except OSError:
            self._raise(EODOperationJobRepositoryErrorCode.UNSAFE_PATH)

    def _execute(self, connection, statement, parameters=()):
        try:
            return connection.execute(statement, parameters)
        except sqlite3.IntegrityError:
            raise
        except sqlite3.Error as exc:
            raise self._persistence_error(exc) from None

    def _begin(self, connection):
        connection.execute("BEGIN IMMEDIATE")

    def _commit(self, connection):
        connection.commit()

    def _rollback(self, connection):
        try:
            connection.rollback()
        except sqlite3.Error:
            pass

    def _persistence_error(self, exc: Exception) -> EODOperationJobRepositoryError:
        text = str(exc).lower()
        code = EODOperationJobRepositoryErrorCode.PERSISTENCE_FAILURE
        if "locked" in text or "busy" in text:
            code = EODOperationJobRepositoryErrorCode.PERSISTENCE_BUSY
        return EODOperationJobRepositoryError(code)

    def _raise(self, code: EODOperationJobRepositoryErrorCode) -> None:
        raise EODOperationJobRepositoryError(code)
