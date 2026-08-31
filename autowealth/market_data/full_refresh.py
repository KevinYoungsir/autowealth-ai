"""Explicit, fail-closed execution of complete EOD replacement generations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
from typing import TYPE_CHECKING, Optional, Tuple, Type, TypeVar

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
)

from .batch import EODDatasetLockManager, eod_dataset_lock_key
from .calendar import TradingCalendar
from .coordinator import (
    EODIncrementalCoordinator,
    EODIncrementalCoordinatorErrorCode,
)
from .operation_control import (
    EODCheckpointStage,
    EODExecutionCheckpoint,
    run_eod_checkpoint,
)
from .normalization import normalize_eod_bars
from .planning import EODRequestPlan, EODRequestPlanStatus, EODRevisionPolicy
from .provider_chain import EODProviderAttempt
from .providers import EODProviderRequest
from .schemas import EODBar, EODDatasetKey, EODDateRange
from .versioning import EODGenerationManifest, calculate_eod_content_sha256

if TYPE_CHECKING:
    from .repositories import EODFileRepository

_EnumType = TypeVar("_EnumType", bound=Enum)
_SAFE_ERROR_FALLBACK = "The explicit EOD full refresh failed safely."


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
        return _SAFE_ERROR_FALLBACK
    if contains_absolute_path(value) or contains_sensitive_value(value):
        return _SAFE_ERROR_FALLBACK
    sanitized = sanitize_public_text(value)[:512]
    if not sanitized or contains_absolute_path(sanitized) or contains_sensitive_value(sanitized):
        return _SAFE_ERROR_FALLBACK
    return sanitized


def _non_negative_count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative exact integer")
    return value


def _attempt_tuple(value: object) -> Tuple[EODProviderAttempt, ...]:
    if type(value) not in (list, tuple):
        raise TypeError("attempts must be an exact list or exact tuple")
    attempts = tuple(value)
    if any(type(attempt) is not EODProviderAttempt for attempt in attempts):
        raise TypeError("attempts must contain exact EODProviderAttempt values")
    return attempts


class EODFullRefreshStatus(str, Enum):
    """Stable outcomes of the explicit full-refresh execution boundary."""

    FULL_REFRESH_PLANNED = "full_refresh_planned"
    FULL_REFRESH_PUBLISHED = "full_refresh_published"
    UNCHANGED_CONTENT = "unchanged_content"
    NOT_ELIGIBLE = "not_eligible"


class EODFullRefreshErrorCode(str, Enum):
    """Finite lock-boundary failures unique to explicit full refresh."""

    LOCK_ACQUISITION_FAILED = "lock_acquisition_failed"
    LOCK_CONTRACT_VIOLATION = "lock_contract_violation"
    LOCK_UNAVAILABLE = "lock_unavailable"
    LOCK_RELEASE_FAILED = "lock_release_failed"


@dataclass(frozen=True)
class EODFullRefreshRequest:
    """Explicit caller intent to evaluate or execute one complete replacement."""

    dataset: EODDatasetKey
    requested_range: EODDateRange
    dry_run: bool = False

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if type(self.dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "execution_mode": "full_refresh",
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "dry_run": self.dry_run,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


class EODFullRefreshExecutorError(RuntimeError):
    """Safe deterministic failure at the full-refresh write-lock boundary."""

    def __init__(
        self,
        code: EODFullRefreshErrorCode,
        message: str,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        *,
        lock_key: str,
    ) -> None:
        normalized_code = _enum_value(code, EODFullRefreshErrorCode, "code")
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if type(lock_key) is not str or lock_key != eod_dataset_lock_key(dataset):
            raise ValueError("lock_key must be a canonical EOD dataset lock key")
        self.code = normalized_code
        self.message = _safe_message(message)
        self.dataset = dataset
        self.requested_range = requested_range
        self.lock_key = lock_key
        super().__init__(self.message)

    @property
    def retryable(self) -> bool:
        return self.code is EODFullRefreshErrorCode.LOCK_UNAVAILABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "lock_key": self.lock_key,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODFullRefreshResult:
    """Immutable public result without raw bars or dependency payloads."""

    request: EODFullRefreshRequest
    status: EODFullRefreshStatus
    plan: EODRequestPlan
    provider_request: Optional[EODProviderRequest]
    previous_manifest: Optional[EODGenerationManifest]
    published_manifest: Optional[EODGenerationManifest]
    attempts: Tuple[EODProviderAttempt, ...]
    row_count: int
    replaced_row_count: int
    lock_key: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.request) is not EODFullRefreshRequest:
            raise TypeError("request must be an exact EODFullRefreshRequest")
        status = _enum_value(self.status, EODFullRefreshStatus, "status")
        if type(self.plan) is not EODRequestPlan:
            raise TypeError("plan must be an exact EODRequestPlan")
        if (
            self.plan.dataset != self.request.dataset
            or self.plan.requested_range != self.request.requested_range
        ):
            raise ValueError("plan must match the full-refresh request")
        if (
            self.provider_request is not None
            and type(self.provider_request) is not EODProviderRequest
        ):
            raise TypeError("provider_request must be an exact EODProviderRequest or None")
        if (
            self.previous_manifest is not None
            and type(self.previous_manifest) is not EODGenerationManifest
        ):
            raise TypeError("previous_manifest must be an exact EODGenerationManifest or None")
        if (
            self.previous_manifest is not None
            and self.previous_manifest.dataset != self.request.dataset
        ):
            raise ValueError("previous_manifest must match the full-refresh dataset")
        if (
            self.published_manifest is not None
            and type(self.published_manifest) is not EODGenerationManifest
        ):
            raise TypeError("published_manifest must be an exact EODGenerationManifest or None")
        attempts = _attempt_tuple(self.attempts)
        row_count = _non_negative_count(self.row_count, "row_count")
        replaced_row_count = _non_negative_count(
            self.replaced_row_count,
            "replaced_row_count",
        )
        expected_lock_key = eod_dataset_lock_key(self.request.dataset)
        if self.request.dry_run:
            if self.lock_key is not None:
                raise ValueError("dry_run cannot contain lock state")
        elif self.lock_key != expected_lock_key:
            raise ValueError("real execution must contain the canonical dataset lock key")

        eligible = self.plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
        if (status is EODFullRefreshStatus.NOT_ELIGIBLE) is eligible:
            raise ValueError("status must agree with planner full-refresh eligibility")
        if eligible:
            if self.plan.effective_range is None or self.previous_manifest is None:
                raise ValueError("eligible full refresh requires current and effective range")
            if self.provider_request is None:
                raise ValueError("eligible full refresh requires an explicit provider request")
            if (
                self.provider_request.dataset != self.request.dataset
                or self.provider_request.requested_range != self.plan.effective_range
            ):
                raise ValueError("provider request must equal the full effective range")
        elif self.provider_request is not None:
            raise ValueError("not-eligible result cannot contain a provider request")

        if status is EODFullRefreshStatus.FULL_REFRESH_PLANNED and not self.request.dry_run:
            raise ValueError("full_refresh_planned requires dry_run")
        if (
            self.request.dry_run
            and status is not EODFullRefreshStatus.FULL_REFRESH_PLANNED
            and eligible
        ):
            raise ValueError("eligible dry_run must remain a planned result")
        if self.request.dry_run and attempts:
            raise ValueError("dry_run cannot contain provider attempts")
        if status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED:
            if self.published_manifest is None or self.request.dry_run:
                raise ValueError("published status requires one real published manifest")
        elif self.published_manifest is not None:
            raise ValueError("non-published result cannot contain a published manifest")
        if (
            status
            in (
                EODFullRefreshStatus.FULL_REFRESH_PUBLISHED,
                EODFullRefreshStatus.UNCHANGED_CONTENT,
            )
            and not attempts
        ):
            raise ValueError("executed full refresh requires provider attempts")
        if (
            status
            in (
                EODFullRefreshStatus.FULL_REFRESH_PLANNED,
                EODFullRefreshStatus.NOT_ELIGIBLE,
            )
            and attempts
        ):
            raise ValueError("non-fetch result cannot contain provider attempts")
        if self.published_manifest is not None:
            if (
                self.published_manifest.dataset != self.request.dataset
                or self.published_manifest.row_count != row_count
                or self.previous_manifest is None
                or self.published_manifest.previous_generation_id
                != self.previous_manifest.generation_id
                or replaced_row_count != self.previous_manifest.row_count
            ):
                raise ValueError("published manifest must match the full-refresh result")
        elif replaced_row_count != 0:
            raise ValueError("non-published result cannot report replaced rows")

        expected_current_rows = (
            0 if self.previous_manifest is None else self.previous_manifest.row_count
        )
        if (
            status
            in (
                EODFullRefreshStatus.FULL_REFRESH_PLANNED,
                EODFullRefreshStatus.UNCHANGED_CONTENT,
                EODFullRefreshStatus.NOT_ELIGIBLE,
            )
            and row_count != expected_current_rows
        ):
            raise ValueError("non-published row_count must match the inspected current generation")

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "row_count", row_count)
        object.__setattr__(self, "replaced_row_count", replaced_row_count)

    @property
    def eligible(self) -> bool:
        return self.plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED

    @property
    def planned(self) -> bool:
        return self.status is EODFullRefreshStatus.FULL_REFRESH_PLANNED

    @property
    def published(self) -> bool:
        return self.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED

    @property
    def unchanged(self) -> bool:
        return self.status is EODFullRefreshStatus.UNCHANGED_CONTENT

    @property
    def would_publish(self) -> bool:
        return self.published

    @property
    def would_replace_generation_id(self) -> Optional[str]:
        if not self.eligible or self.previous_manifest is None:
            return None
        return self.previous_manifest.generation_id

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request.to_dict(),
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "provider_request": (
                None if self.provider_request is None else self.provider_request.to_dict()
            ),
            "previous_manifest": (
                None if self.previous_manifest is None else self.previous_manifest.to_dict()
            ),
            "published_manifest": (
                None if self.published_manifest is None else self.published_manifest.to_dict()
            ),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "row_count": self.row_count,
            "replaced_row_count": self.replaced_row_count,
            "lock_key": self.lock_key,
            "eligible": self.eligible,
            "planned": self.planned,
            "published": self.published,
            "unchanged": self.unchanged,
            "would_publish": self.would_publish,
            "would_replace_generation_id": self.would_replace_generation_id,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


class EODFullRefreshExecutor:
    """Execute a full replacement only when the existing planner requires it."""

    def __init__(
        self,
        repository: "EODFileRepository",
        provider_chain: object,
        calendar: TradingCalendar,
        lock_manager: EODDatasetLockManager,
    ) -> None:
        if not isinstance(lock_manager, EODDatasetLockManager):
            raise TypeError("lock_manager must implement EODDatasetLockManager")
        self._operations = EODIncrementalCoordinator(
            repository,
            provider_chain,
            calendar,
        )
        self._repository = repository
        self._lock_manager = lock_manager

    def execute(
        self,
        request: EODFullRefreshRequest,
        *,
        revision_policy: Optional[EODRevisionPolicy] = None,
        generation_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        checkpoint: Optional[EODExecutionCheckpoint] = None,
    ) -> EODFullRefreshResult:
        """Evaluate or run one explicitly authorized complete replacement."""

        if type(request) is not EODFullRefreshRequest:
            raise TypeError("request must be an exact EODFullRefreshRequest")
        if revision_policy is not None and type(revision_policy) is not EODRevisionPolicy:
            raise TypeError("revision_policy must be an exact EODRevisionPolicy or None")

        if request.dry_run:
            return self._execute_from_current_state(
                request,
                revision_policy,
                generation_id,
                created_at,
                lock_key=None,
                checkpoint=checkpoint,
            )

        lock_key = eod_dataset_lock_key(request.dataset)
        try:
            acquired = self._lock_manager.acquire(lock_key)
        except Exception as exc:
            error = self._lock_error(
                EODFullRefreshErrorCode.LOCK_ACQUISITION_FAILED,
                "The EOD dataset lock could not be acquired safely.",
                request,
                lock_key,
            )
            raise error from exc
        if type(acquired) is not bool:
            raise self._lock_error(
                EODFullRefreshErrorCode.LOCK_CONTRACT_VIOLATION,
                "The EOD dataset lock returned an invalid acquisition result.",
                request,
                lock_key,
            )
        if not acquired:
            raise self._lock_error(
                EODFullRefreshErrorCode.LOCK_UNAVAILABLE,
                "The EOD dataset is already being updated.",
                request,
                lock_key,
            )

        try:
            result = self._execute_from_current_state(
                request,
                revision_policy,
                generation_id,
                created_at,
                lock_key=lock_key,
                checkpoint=checkpoint,
            )
        except BaseException:
            self._release_after_failure(request, lock_key)
            raise
        self._release_after_success(request, lock_key)
        return result

    def _execute_from_current_state(
        self,
        request: EODFullRefreshRequest,
        revision_policy: Optional[EODRevisionPolicy],
        generation_id: Optional[str],
        created_at: Optional[datetime],
        *,
        lock_key: Optional[str],
        checkpoint: Optional[EODExecutionCheckpoint],
    ) -> EODFullRefreshResult:
        current = self._operations._load_current(
            request.dataset,
            request.requested_range,
            propagate_unknown=True,
        )
        current_manifest = None if current is None else current.manifest
        plan = self._operations._plan(
            request.dataset,
            request.requested_range,
            current_manifest,
            revision_policy,
            propagate_unknown=True,
        )
        if plan.status is not EODRequestPlanStatus.FULL_REFRESH_REQUIRED:
            return EODFullRefreshResult(
                request=request,
                status=EODFullRefreshStatus.NOT_ELIGIBLE,
                plan=plan,
                provider_request=None,
                previous_manifest=current_manifest,
                published_manifest=None,
                attempts=(),
                row_count=0 if current is None else len(current.bars),
                replaced_row_count=0,
                lock_key=lock_key,
            )
        if current is None or plan.effective_range is None:
            raise self._operations._error(
                EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
                "planning",
                "The full-refresh plan conflicts with the current generation.",
                request.dataset,
                request.requested_range,
                plan=plan,
            )

        provider_request = EODProviderRequest(
            dataset=request.dataset,
            requested_range=plan.effective_range,
        )
        if request.dry_run:
            return EODFullRefreshResult(
                request=request,
                status=EODFullRefreshStatus.FULL_REFRESH_PLANNED,
                plan=plan,
                provider_request=provider_request,
                previous_manifest=current.manifest,
                published_manifest=None,
                attempts=(),
                row_count=len(current.bars),
                replaced_row_count=0,
                lock_key=None,
            )

        chain_result = self._operations._fetch_provider_request(
            provider_request,
            plan,
            request.dataset,
            request.requested_range,
            propagate_unknown=True,
            checkpoint=checkpoint,
        )
        attempts = chain_result.attempts
        candidate = self._replacement_candidate(
            chain_result.selected_result.bars,
            provider_request,
            plan,
            attempts,
        )
        self._operations._validate_candidate(
            plan,
            candidate,
            request.dataset,
            request.requested_range,
            attempts,
            propagate_unknown=True,
        )
        candidate_sha = calculate_eod_content_sha256(candidate)

        if candidate_sha == current.manifest.content_sha256:
            return EODFullRefreshResult(
                request=request,
                status=EODFullRefreshStatus.UNCHANGED_CONTENT,
                plan=plan,
                provider_request=provider_request,
                previous_manifest=current.manifest,
                published_manifest=None,
                attempts=attempts,
                row_count=len(current.bars),
                replaced_row_count=0,
                lock_key=lock_key,
            )

        generation_id = self._operations._validate_explicit_generation_id(
            generation_id,
            request.dataset,
            request.requested_range,
        )
        created_at = self._operations._validate_explicit_created_at(
            created_at,
            request.dataset,
            request.requested_range,
        )
        if generation_id is None or created_at is None:
            missing = "generation_id" if generation_id is None else "created_at"
            raise self._operations._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID,
                "publication_context",
                f"{missing} is required before publishing an EOD generation.",
                request.dataset,
                request.requested_range,
                plan=plan,
                attempts=attempts,
            )

        run_eod_checkpoint(
            checkpoint,
            EODCheckpointStage.BEFORE_PUBLICATION,
            request.dataset,
        )
        published_manifest = self._repository.publish(
            request.dataset,
            candidate,
            generation_id=generation_id,
            created_at=created_at,
        )

        self._operations._validate_published_manifest(
            published_manifest,
            request.dataset,
            request.requested_range,
            plan,
            attempts,
            candidate,
            candidate_sha,
            generation_id,
            created_at,
            current.manifest,
        )
        return EODFullRefreshResult(
            request=request,
            status=EODFullRefreshStatus.FULL_REFRESH_PUBLISHED,
            plan=plan,
            provider_request=provider_request,
            previous_manifest=current.manifest,
            published_manifest=published_manifest,
            attempts=attempts,
            row_count=len(candidate),
            replaced_row_count=len(current.bars),
            lock_key=lock_key,
        )

    def _replacement_candidate(
        self,
        fetched_bars: Tuple[EODBar, ...],
        provider_request: EODProviderRequest,
        plan: EODRequestPlan,
        attempts: Tuple[EODProviderAttempt, ...],
    ) -> Tuple[EODBar, ...]:
        if type(fetched_bars) not in (list, tuple) or not fetched_bars:
            raise self._operations._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "replacement",
                "A successful full-refresh provider result must contain bars.",
                provider_request.dataset,
                plan.requested_range,
                plan=plan,
                attempts=attempts,
            )
        fetched = tuple(fetched_bars)
        if any(
            type(bar) is not EODBar
            or bar.dataset != provider_request.dataset
            or not provider_request.requested_range.contains(bar.trade_date)
            for bar in fetched
        ):
            raise self._operations._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "replacement",
                "The full-refresh provider bars do not match the complete request.",
                provider_request.dataset,
                plan.requested_range,
                plan=plan,
                attempts=attempts,
            )
        return normalize_eod_bars(fetched)

    def _release_after_failure(
        self,
        request: EODFullRefreshRequest,
        lock_key: str,
    ) -> None:
        try:
            self._lock_manager.release(lock_key)
        except Exception as exc:
            error = self._lock_error(
                EODFullRefreshErrorCode.LOCK_RELEASE_FAILED,
                "The EOD dataset lock could not be released safely.",
                request,
                lock_key,
            )
            raise error from exc

    def _release_after_success(
        self,
        request: EODFullRefreshRequest,
        lock_key: str,
    ) -> None:
        try:
            self._lock_manager.release(lock_key)
        except Exception as exc:
            error = self._lock_error(
                EODFullRefreshErrorCode.LOCK_RELEASE_FAILED,
                "The EOD dataset lock could not be released safely.",
                request,
                lock_key,
            )
            raise error from exc

    @staticmethod
    def _lock_error(
        code: EODFullRefreshErrorCode,
        message: str,
        request: EODFullRefreshRequest,
        lock_key: str,
    ) -> EODFullRefreshExecutorError:
        return EODFullRefreshExecutorError(
            code,
            message,
            request.dataset,
            request.requested_range,
            lock_key=lock_key,
        )


__all__ = [
    "EODFullRefreshErrorCode",
    "EODFullRefreshExecutor",
    "EODFullRefreshExecutorError",
    "EODFullRefreshRequest",
    "EODFullRefreshResult",
    "EODFullRefreshStatus",
]
