"""Side-effect-free control contracts for durable EOD operation execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import threading
from typing import Callable, Optional, Protocol

from .local_calendar import LocalTradingCalendarIdentity
from .operations import EODOperationJob, EODOperationJobStatus
from .schemas import EODDatasetKey
from .versioning import validate_generation_id

DEFAULT_EOD_WORKER_LEASE_SECONDS = 300
DEFAULT_EOD_WORKER_HEARTBEAT_SECONDS = 60
DEFAULT_EOD_WORKER_POLL_SECONDS = 5


class EODCheckpointStage(str, Enum):
    BEFORE_PROVIDER_INVOCATION = "before_provider_invocation"
    AFTER_PROVIDER_INVOCATION = "after_provider_invocation"
    AFTER_PROVIDER_STAGE = "after_provider_stage"
    BEFORE_PUBLICATION = "before_publication"
    BEFORE_NEXT_DATASET = "before_next_dataset"
    BEFORE_MAINTENANCE_DELETE = "before_maintenance_delete"
    BEFORE_TERMINAL_TRANSITION = "before_terminal_transition"


class EODLeaseControlState(str, Enum):
    ACTIVE = "active"
    UNSAFE = "unsafe"
    TERMINAL = "terminal"


class EODOperationControlError(RuntimeError):
    """Safe control-plane stop that domain layers must propagate unchanged."""

    def __init__(self, reason_code: str = "lease_control_failure") -> None:
        if type(reason_code) is not str or not reason_code or len(reason_code) > 128:
            raise ValueError("reason_code must be bounded non-empty text")
        self.reason_code = reason_code
        super().__init__("The EOD operation cannot safely begin another side effect.")


class EODExecutionCheckpoint(Protocol):
    def __call__(
        self,
        stage: EODCheckpointStage,
        dataset: Optional[EODDatasetKey] = None,
    ) -> None: ...


class EODUTCClock(Protocol):
    def now(self) -> datetime: ...


class SystemEODUTCClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class EODOperationWorkerConfig:
    lease_duration_seconds: int = DEFAULT_EOD_WORKER_LEASE_SECONDS
    heartbeat_interval_seconds: int = DEFAULT_EOD_WORKER_HEARTBEAT_SECONDS
    poll_interval_seconds: int = DEFAULT_EOD_WORKER_POLL_SECONDS

    def __post_init__(self) -> None:
        _bounded_int(self.lease_duration_seconds, 30, 3600, "lease_duration_seconds")
        _bounded_int(self.heartbeat_interval_seconds, 30, 3600, "heartbeat_interval_seconds")
        _bounded_int(self.poll_interval_seconds, 1, 3600, "poll_interval_seconds")
        if self.lease_duration_seconds < 3 * self.heartbeat_interval_seconds:
            raise ValueError("lease_duration_seconds must be at least three heartbeat intervals")


class EODLeaseController:
    """Thread-safe local ownership snapshot; it is not a fencing token."""

    def __init__(self, claimed_job: EODOperationJob) -> None:
        _validate_claimed_job(claimed_job)
        self._job = claimed_job
        self._state = EODLeaseControlState.ACTIVE
        self._reason_code: Optional[str] = None
        self._guard = threading.Lock()

    @property
    def state(self) -> EODLeaseControlState:
        with self._guard:
            return self._state

    @property
    def job(self) -> EODOperationJob:
        with self._guard:
            return self._job

    @property
    def reason_code(self) -> Optional[str]:
        with self._guard:
            return self._reason_code

    def update_ownership(self, renewed_job: EODOperationJob) -> None:
        _validate_claimed_job(renewed_job)
        with self._guard:
            if self._state is not EODLeaseControlState.ACTIVE:
                raise EODOperationControlError(self._reason_code or "lease_control_failure")
            if (
                renewed_job.job_id != self._job.job_id
                or renewed_job.worker_id != self._job.worker_id
                or renewed_job.claim_version != self._job.claim_version
                or renewed_job.lease_expires_at is None
                or self._job.lease_expires_at is None
                or renewed_job.lease_expires_at <= self._job.lease_expires_at
            ):
                self._state = EODLeaseControlState.UNSAFE
                self._reason_code = "lease_control_failure"
                raise EODOperationControlError(self._reason_code)
            self._job = renewed_job

    def mark_unsafe(self, reason_code: str) -> None:
        error = EODOperationControlError(reason_code)
        with self._guard:
            if self._state is not EODLeaseControlState.TERMINAL:
                self._state = EODLeaseControlState.UNSAFE
                self._reason_code = error.reason_code

    def mark_terminal(self) -> None:
        with self._guard:
            if self._state is not EODLeaseControlState.ACTIVE:
                raise EODOperationControlError(self._reason_code or "lease_control_failure")
            self._state = EODLeaseControlState.TERMINAL

    def __call__(
        self,
        stage: EODCheckpointStage,
        dataset: Optional[EODDatasetKey] = None,
    ) -> None:
        if type(stage) is not EODCheckpointStage:
            raise TypeError("stage must be an exact EODCheckpointStage")
        if dataset is not None and type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey or None")
        with self._guard:
            if self._state is not EODLeaseControlState.ACTIVE:
                raise EODOperationControlError(self._reason_code or "lease_control_failure")


def run_eod_checkpoint(
    checkpoint: Optional[EODExecutionCheckpoint],
    stage: EODCheckpointStage,
    dataset: Optional[EODDatasetKey] = None,
) -> None:
    if checkpoint is None:
        return
    if not callable(checkpoint):
        raise TypeError("checkpoint must be callable or None")
    checkpoint(stage, dataset)


def eod_generation_id(job: EODOperationJob, dataset: EODDatasetKey) -> str:
    if type(job) is not EODOperationJob:
        raise TypeError("job must be an exact EODOperationJob")
    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    digest = hashlib.sha256(_canonical_json(dataset.to_dict()).encode("utf-8")).hexdigest()
    return validate_generation_id(f"{job.job_id}-{digest}")


def eod_calendar_identity(identity: LocalTradingCalendarIdentity) -> str:
    if type(identity) is not LocalTradingCalendarIdentity:
        raise TypeError("identity must be an exact LocalTradingCalendarIdentity")
    digest = hashlib.sha256(_canonical_json(identity.to_dict()).encode("utf-8")).hexdigest()
    value = f"{identity.calendar_id}@{digest}"
    if len(value) > 256:
        raise ValueError("calendar identity exceeds the bounded identifier limit")
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _bounded_int(value: object, minimum: int, maximum: int, field_name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{field_name} must be an exact integer between {minimum} and {maximum}")
    return value


def _validate_claimed_job(job: object) -> EODOperationJob:
    if type(job) is not EODOperationJob or job.status is not EODOperationJobStatus.RUNNING:
        raise TypeError("claimed_job must be an exact running EODOperationJob")
    if job.worker_id is None or job.claim_version is None or job.lease_expires_at is None:
        raise ValueError("claimed_job must contain complete ownership fields")
    return job


__all__ = [
    "DEFAULT_EOD_WORKER_HEARTBEAT_SECONDS",
    "DEFAULT_EOD_WORKER_LEASE_SECONDS",
    "DEFAULT_EOD_WORKER_POLL_SECONDS",
    "EODCheckpointStage",
    "EODExecutionCheckpoint",
    "EODLeaseControlState",
    "EODLeaseController",
    "EODOperationControlError",
    "EODOperationWorkerConfig",
    "EODUTCClock",
    "SystemEODUTCClock",
    "eod_calendar_identity",
    "eod_generation_id",
    "run_eod_checkpoint",
]
