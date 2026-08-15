"""Single-dataset orchestration for incremental EOD generation publication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import re
from typing import TYPE_CHECKING, Optional, Tuple, Type, TypeVar

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
)

from .calendar import TradingCalendar
from .normalization import normalize_eod_bars
from .planning import (
    EODRequestPlan,
    EODRequestPlanStatus,
    EODRevisionPolicy,
    plan_eod_request_window,
)
from .provider_chain import (
    EODProviderAttempt,
    EODProviderChainError,
    EODProviderChainResult,
)
from .providers import EODProviderErrorCode, EODProviderResultStatus
from .schemas import EODBar, EODDatasetKey, EODDateRange, EODUpdateRequest
from .validation import EODValidationReport, validate_eod_batch
from .versioning import (
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_eod_content_sha256,
    validate_generation_id,
)

if TYPE_CHECKING:
    from .repositories import EODFileRepository

_EnumType = TypeVar("_EnumType", bound=Enum)
_MACHINE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_STAGES = frozenset(
    {
        "load_current",
        "planning",
        "provider_chain",
        "merge",
        "validation",
        "publication_context",
        "publish",
        "publish_response",
    }
)
_PUBLISHED_STATUSES = frozenset(
    {
        "initial_import_published",
        "incremental_published",
        "overlap_refresh_published",
    }
)
_UNCHANGED_STATUSES = frozenset(
    {
        "already_current",
        "no_trading_days",
        "unchanged_content",
    }
)
_PLANNED_STATUSES = frozenset(
    {
        "initial_import_planned",
        "incremental_planned",
        "overlap_refresh_planned",
    }
)
_DRY_RUN_STATUSES = _PLANNED_STATUSES | frozenset(
    {
        "already_current",
        "no_trading_days",
        "full_refresh_required",
    }
)
_SAFE_ERROR_FALLBACK = "The incremental EOD update failed safely."


def _enum_value(value: object, enum_type: Type[_EnumType], field_name: str) -> _EnumType:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a supported string enum value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {field_name}: {value}") from exc


def _json_text(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_message(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("message must be non-empty text")
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


class EODIncrementalUpdateStatus(str, Enum):
    """Stable outcomes of one synchronous incremental EOD update."""

    INITIAL_IMPORT_PUBLISHED = "initial_import_published"
    INCREMENTAL_PUBLISHED = "incremental_published"
    OVERLAP_REFRESH_PUBLISHED = "overlap_refresh_published"
    ALREADY_CURRENT = "already_current"
    NO_TRADING_DAYS = "no_trading_days"
    FULL_REFRESH_REQUIRED = "full_refresh_required"
    UNCHANGED_CONTENT = "unchanged_content"
    INITIAL_IMPORT_PLANNED = "initial_import_planned"
    INCREMENTAL_PLANNED = "incremental_planned"
    OVERLAP_REFRESH_PLANNED = "overlap_refresh_planned"


@dataclass(frozen=True)
class EODIncrementalUpdateResult:
    """Immutable public result without bars or dependency payloads."""

    dataset: EODDatasetKey
    requested_range: EODDateRange
    status: EODIncrementalUpdateStatus
    plan: EODRequestPlan
    previous_manifest: Optional[EODGenerationManifest]
    published_manifest: Optional[EODGenerationManifest]
    attempts: Tuple[EODProviderAttempt, ...]
    row_count: int
    added_row_count: int
    replaced_row_count: int
    dry_run: bool = False

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        status = _enum_value(self.status, EODIncrementalUpdateStatus, "status")
        if type(self.plan) is not EODRequestPlan:
            raise TypeError("plan must be an exact EODRequestPlan")
        if self.plan.dataset != self.dataset or self.plan.requested_range != self.requested_range:
            raise ValueError("plan must match the result request")
        if self.previous_manifest is not None and (
            type(self.previous_manifest) is not EODGenerationManifest
        ):
            raise TypeError("previous_manifest must be an exact EODGenerationManifest or None")
        if self.published_manifest is not None and (
            type(self.published_manifest) is not EODGenerationManifest
        ):
            raise TypeError("published_manifest must be an exact EODGenerationManifest or None")
        attempts = _attempt_tuple(self.attempts)
        row_count = _non_negative_count(self.row_count, "row_count")
        added_count = _non_negative_count(self.added_row_count, "added_row_count")
        replaced_count = _non_negative_count(
            self.replaced_row_count,
            "replaced_row_count",
        )
        if type(self.dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")

        is_published = status.value in _PUBLISHED_STATUSES
        if is_published != (self.published_manifest is not None):
            raise ValueError("published result status and manifest must agree")
        if status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED and (
            self.previous_manifest is not None
        ):
            raise ValueError("initial import cannot contain a previous manifest")
        if status.value in _PLANNED_STATUSES and not self.dry_run:
            raise ValueError("planned result statuses require dry_run")
        if self.dry_run and status.value not in _DRY_RUN_STATUSES:
            raise ValueError("dry_run result status is incompatible with dry_run")
        if self.published_manifest is not None:
            if self.published_manifest.dataset != self.dataset:
                raise ValueError("published manifest dataset must match the result dataset")
            if self.published_manifest.row_count != row_count:
                raise ValueError("published manifest row_count must match the result")

        object.__setattr__(self, "status", status)
        object.__setattr__(self, "attempts", attempts)
        object.__setattr__(self, "row_count", row_count)
        object.__setattr__(self, "added_row_count", added_count)
        object.__setattr__(self, "replaced_row_count", replaced_count)

    @property
    def published(self) -> bool:
        return self.status.value in _PUBLISHED_STATUSES

    @property
    def unchanged(self) -> bool:
        return self.status.value in _UNCHANGED_STATUSES

    @property
    def requires_full_refresh(self) -> bool:
        return self.status is EODIncrementalUpdateStatus.FULL_REFRESH_REQUIRED

    @property
    def planned(self) -> bool:
        return self.dry_run

    @property
    def retryable(self) -> bool:
        return False

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "status": self.status.value,
            "plan": self.plan.to_dict(),
            "previous_manifest": (
                None if self.previous_manifest is None else self.previous_manifest.to_dict()
            ),
            "published_manifest": (
                None if self.published_manifest is None else self.published_manifest.to_dict()
            ),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "row_count": self.row_count,
            "added_row_count": self.added_row_count,
            "replaced_row_count": self.replaced_row_count,
            "dry_run": self.dry_run,
            "planned": self.planned,
            "published": self.published,
            "unchanged": self.unchanged,
            "requires_full_refresh": self.requires_full_refresh,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


class EODIncrementalCoordinatorErrorCode(str, Enum):
    """Finite failure codes for incremental update orchestration."""

    CURRENT_GENERATION_INVALID = "current_generation_invalid"
    PLANNING_FAILED = "planning_failed"
    PROVIDER_CHAIN_FAILED = "provider_chain_failed"
    PARTIAL_RESULT_NOT_PUBLISHABLE = "partial_result_not_publishable"
    PROVIDER_RESULT_MISMATCH = "provider_result_mismatch"
    MERGE_CONFLICT = "merge_conflict"
    VALIDATION_FAILED = "validation_failed"
    PUBLICATION_CONTEXT_INVALID = "publication_context_invalid"
    PUBLICATION_FAILED = "publication_failed"
    REPOSITORY_CONTRACT_VIOLATION = "repository_contract_violation"


class EODIncrementalCoordinatorError(RuntimeError):
    """Safe deterministic failure diagnostics for one coordinator stage."""

    def __init__(
        self,
        code: EODIncrementalCoordinatorErrorCode,
        stage: str,
        message: str,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        *,
        plan: Optional[EODRequestPlan] = None,
        attempts: Tuple[EODProviderAttempt, ...] = (),
        provider_error_code: Optional[EODProviderErrorCode] = None,
        validation_codes: Tuple[str, ...] = (),
        retryable: bool = False,
    ) -> None:
        normalized_code = _enum_value(code, EODIncrementalCoordinatorErrorCode, "code")
        if type(stage) is not str or stage not in _STAGES:
            raise ValueError("stage must be a supported coordinator stage")
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if plan is not None and type(plan) is not EODRequestPlan:
            raise TypeError("plan must be an exact EODRequestPlan or None")
        if plan is not None and (
            plan.dataset != dataset or plan.requested_range != requested_range
        ):
            raise ValueError("plan must match the coordinator error request")
        normalized_attempts = _attempt_tuple(attempts)
        if provider_error_code is not None and (
            type(provider_error_code) is not EODProviderErrorCode
        ):
            raise TypeError("provider_error_code must be an exact EODProviderErrorCode or None")
        if type(validation_codes) not in (list, tuple):
            raise TypeError("validation_codes must be an exact list or exact tuple")
        codes = tuple(validation_codes)
        if any(
            type(item) is not str or _MACHINE_CODE_PATTERN.fullmatch(item) is None for item in codes
        ):
            raise ValueError("validation_codes must contain stable machine codes")
        codes = tuple(sorted(set(codes)))
        if type(retryable) is not bool:
            raise ValueError("retryable must be a strict boolean")
        expected_retryable = normalized_code is (
            EODIncrementalCoordinatorErrorCode.PARTIAL_RESULT_NOT_PUBLISHABLE
        ) or (
            normalized_code is EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED
            and provider_error_code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE
        )
        if retryable is not expected_retryable:
            raise ValueError("retryable does not match the coordinator error code")

        self.code = normalized_code
        self.stage = stage
        self.message = _safe_message(message)
        self.dataset = dataset
        self.requested_range = requested_range
        self.plan = plan
        self.attempts = normalized_attempts
        self.provider_error_code = provider_error_code
        self.validation_codes = codes
        self.retryable = retryable
        super().__init__(self.message)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "stage": self.stage,
            "message": self.message,
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "plan": None if self.plan is None else self.plan.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "provider_error_code": (
                None if self.provider_error_code is None else self.provider_error_code.value
            ),
            "validation_codes": list(self.validation_codes),
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


class EODIncrementalCoordinator:
    """Coordinate one complete EOD fetch, merge, validation and publication."""

    def __init__(
        self,
        repository: "EODFileRepository",
        provider_chain: object,
        calendar: TradingCalendar,
    ) -> None:
        if not callable(getattr(repository, "load_current", None)) or not callable(
            getattr(repository, "publish", None)
        ):
            raise TypeError("repository must implement load_current and publish")
        if isinstance(provider_chain, EODIncrementalCoordinator) or not callable(
            getattr(provider_chain, "fetch", None)
        ):
            raise TypeError("provider_chain must implement fetch and cannot be a coordinator")
        if not isinstance(calendar, TradingCalendar):
            raise TypeError("calendar must implement TradingCalendar")
        self._repository = repository
        self._provider_chain = provider_chain
        self._calendar = calendar

    def execute(
        self,
        request: EODUpdateRequest,
        *,
        revision_policy: Optional[EODRevisionPolicy] = None,
        generation_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
    ) -> EODIncrementalUpdateResult:
        """Execute one serializable update request without changing legacy defaults."""

        if type(request) is not EODUpdateRequest:
            raise TypeError("request must be an exact EODUpdateRequest")
        return self.update(
            request.dataset,
            request.requested_range,
            revision_policy=revision_policy,
            generation_id=generation_id,
            created_at=created_at,
            dry_run=request.dry_run,
        )

    def update(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        *,
        revision_policy: Optional[EODRevisionPolicy] = None,
        generation_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        dry_run: bool = False,
    ) -> EODIncrementalUpdateResult:
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if revision_policy is not None and type(revision_policy) is not EODRevisionPolicy:
            raise TypeError("revision_policy must be an exact EODRevisionPolicy or None")
        if type(dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")

        validated_generation_id = self._validate_explicit_generation_id(
            generation_id,
            dataset,
            requested_range,
        )
        normalized_created_at = self._validate_explicit_created_at(
            created_at,
            dataset,
            requested_range,
        )
        current = self._load_current(dataset, requested_range)
        current_manifest = None if current is None else current.manifest
        plan = self._plan(
            dataset,
            requested_range,
            current_manifest,
            revision_policy,
        )

        no_fetch_status = self._no_fetch_status(plan.status)
        if no_fetch_status is not None:
            return EODIncrementalUpdateResult(
                dataset=dataset,
                requested_range=requested_range,
                status=no_fetch_status,
                plan=plan,
                previous_manifest=current_manifest,
                published_manifest=None,
                attempts=(),
                row_count=0 if current is None else len(current.bars),
                added_row_count=0,
                replaced_row_count=0,
                dry_run=dry_run,
            )

        self._validate_plan_current_state(plan, current, dataset, requested_range)
        if dry_run:
            return EODIncrementalUpdateResult(
                dataset=dataset,
                requested_range=requested_range,
                status=self._planned_status(plan.status),
                plan=plan,
                previous_manifest=current_manifest,
                published_manifest=None,
                attempts=(),
                row_count=0 if current is None else len(current.bars),
                added_row_count=0,
                replaced_row_count=0,
                dry_run=True,
            )
        chain_result = self._fetch(plan, dataset, requested_range)
        attempts = chain_result.attempts
        fetched_bars = chain_result.selected_result.bars
        candidate, added_count, replaced_count = self._merge(
            plan,
            current,
            fetched_bars,
            dataset,
            requested_range,
            attempts,
        )
        self._validate_candidate(
            plan,
            candidate,
            dataset,
            requested_range,
            attempts,
        )
        try:
            candidate_sha = calculate_eod_content_sha256(candidate)
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The validated EOD candidate could not be hashed safely.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=("content_hash_failed",),
            )
            raise error from exc

        if current is not None and candidate_sha == current.manifest.content_sha256:
            return EODIncrementalUpdateResult(
                dataset=dataset,
                requested_range=requested_range,
                status=EODIncrementalUpdateStatus.UNCHANGED_CONTENT,
                plan=plan,
                previous_manifest=current.manifest,
                published_manifest=None,
                attempts=attempts,
                row_count=len(current.bars),
                added_row_count=0,
                replaced_row_count=0,
            )

        if validated_generation_id is None or normalized_created_at is None:
            missing = "generation_id" if validated_generation_id is None else "created_at"
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID,
                "publication_context",
                f"{missing} is required before publishing an EOD generation.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )

        try:
            published_manifest = self._repository.publish(
                dataset,
                candidate,
                generation_id=validated_generation_id,
                created_at=normalized_created_at,
            )
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_FAILED,
                "publish",
                "The EOD repository could not publish the candidate generation.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )
            raise error from exc

        self._validate_published_manifest(
            published_manifest,
            dataset,
            requested_range,
            plan,
            attempts,
            candidate,
            candidate_sha,
            validated_generation_id,
            normalized_created_at,
            current_manifest,
        )
        return EODIncrementalUpdateResult(
            dataset=dataset,
            requested_range=requested_range,
            status=self._published_status(plan.status),
            plan=plan,
            previous_manifest=current_manifest,
            published_manifest=published_manifest,
            attempts=attempts,
            row_count=len(candidate),
            added_row_count=added_count,
            replaced_row_count=replaced_count,
        )

    @staticmethod
    def _error(
        code: EODIncrementalCoordinatorErrorCode,
        stage: str,
        message: str,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        *,
        plan: Optional[EODRequestPlan] = None,
        attempts: Tuple[EODProviderAttempt, ...] = (),
        provider_error_code: Optional[EODProviderErrorCode] = None,
        validation_codes: Tuple[str, ...] = (),
        retryable: bool = False,
    ) -> EODIncrementalCoordinatorError:
        return EODIncrementalCoordinatorError(
            code,
            stage,
            message,
            dataset,
            requested_range,
            plan=plan,
            attempts=attempts,
            provider_error_code=provider_error_code,
            validation_codes=validation_codes,
            retryable=retryable,
        )

    @classmethod
    def _validate_explicit_generation_id(
        cls,
        generation_id: Optional[str],
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
    ) -> Optional[str]:
        if generation_id is None:
            return None
        if type(generation_id) is not str:
            raise cls._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID,
                "publication_context",
                "generation_id must be an exact string when provided.",
                dataset,
                requested_range,
            )
        try:
            return validate_generation_id(generation_id)
        except Exception as exc:
            error = cls._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID,
                "publication_context",
                "generation_id is not a safe machine identifier.",
                dataset,
                requested_range,
            )
            raise error from exc

    @classmethod
    def _validate_explicit_created_at(
        cls,
        created_at: Optional[datetime],
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
    ) -> Optional[datetime]:
        if created_at is None:
            return None
        if (
            type(created_at) is not datetime
            or created_at.tzinfo is None
            or created_at.utcoffset() is None
        ):
            raise cls._error(
                EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID,
                "publication_context",
                "created_at must be an exact timezone-aware datetime when provided.",
                dataset,
                requested_range,
            )
        return created_at.astimezone(timezone.utc)

    def _load_current(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
    ) -> Optional[EODStoredGeneration]:
        try:
            current = self._repository.load_current(dataset)
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.CURRENT_GENERATION_INVALID,
                "load_current",
                "The current EOD generation could not be loaded safely.",
                dataset,
                requested_range,
            )
            raise error from exc
        if current is None:
            return None
        if type(current) is not EODStoredGeneration:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.REPOSITORY_CONTRACT_VIOLATION,
                "load_current",
                "The EOD repository returned an unsupported current generation value.",
                dataset,
                requested_range,
            )
        try:
            normalized = normalize_eod_bars(current.bars)
            valid = (
                current.manifest.dataset == dataset
                and bool(current.bars)
                and all(bar.dataset == dataset for bar in current.bars)
                and normalized == current.bars
                and current.bars[0].trade_date == current.manifest.first_trade_date
                and current.bars[-1].trade_date == current.manifest.last_trade_date
                and len(current.bars) == current.manifest.row_count
                and calculate_eod_content_sha256(current.bars) == current.manifest.content_sha256
            )
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.CURRENT_GENERATION_INVALID,
                "load_current",
                "The current EOD generation failed coordinator integrity checks.",
                dataset,
                requested_range,
            )
            raise error from exc
        if not valid:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.CURRENT_GENERATION_INVALID,
                "load_current",
                "The current EOD generation failed coordinator integrity checks.",
                dataset,
                requested_range,
            )
        return current

    def _plan(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        current_manifest: Optional[EODGenerationManifest],
        revision_policy: Optional[EODRevisionPolicy],
    ) -> EODRequestPlan:
        try:
            plan = plan_eod_request_window(
                dataset,
                requested_range,
                self._calendar,
                current_manifest,
                revision_policy,
            )
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
                "planning",
                "The incremental EOD request could not be planned safely.",
                dataset,
                requested_range,
            )
            raise error from exc
        if type(plan) is not EODRequestPlan or (
            plan.dataset != dataset or plan.requested_range != requested_range
        ):
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
                "planning",
                "The EOD planner returned a mismatched request plan.",
                dataset,
                requested_range,
            )
        return plan

    @staticmethod
    def _no_fetch_status(
        status: EODRequestPlanStatus,
    ) -> Optional[EODIncrementalUpdateStatus]:
        return {
            EODRequestPlanStatus.ALREADY_CURRENT: EODIncrementalUpdateStatus.ALREADY_CURRENT,
            EODRequestPlanStatus.NO_TRADING_DAYS: EODIncrementalUpdateStatus.NO_TRADING_DAYS,
            EODRequestPlanStatus.FULL_REFRESH_REQUIRED: (
                EODIncrementalUpdateStatus.FULL_REFRESH_REQUIRED
            ),
        }.get(status)

    def _validate_plan_current_state(
        self,
        plan: EODRequestPlan,
        current: Optional[EODStoredGeneration],
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
    ) -> None:
        initial_mismatch = (
            plan.status is EODRequestPlanStatus.INITIAL_IMPORT and current is not None
        )
        current_required = (
            plan.status
            in (
                EODRequestPlanStatus.INCREMENTAL,
                EODRequestPlanStatus.OVERLAP_REFRESH,
            )
            and current is None
        )
        if initial_mismatch or current_required or plan.provider_request is None:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
                "planning",
                "The EOD plan conflicts with the loaded current generation.",
                dataset,
                requested_range,
                plan=plan,
            )

    def _fetch(
        self,
        plan: EODRequestPlan,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
    ) -> EODProviderChainResult:
        request = plan.provider_request
        if request is None:  # pragma: no cover - guarded by the caller.
            raise RuntimeError("fetch plan request is unavailable")
        try:
            result = self._provider_chain.fetch(request)
        except EODProviderChainError as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED,
                "provider_chain",
                "The EOD provider chain could not return publishable data.",
                dataset,
                requested_range,
                plan=plan,
                attempts=exc.attempts,
                provider_error_code=exc.final_code,
                retryable=exc.retryable,
            )
            raise error from exc
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED,
                "provider_chain",
                "The EOD provider chain failed safely.",
                dataset,
                requested_range,
                plan=plan,
            )
            raise error from exc
        if type(result) is not EODProviderChainResult:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "provider_chain",
                "The EOD provider chain returned an unsupported result value.",
                dataset,
                requested_range,
                plan=plan,
            )
        if (
            result.request != request
            or result.selected_result.request != request
            or result.selected_result.request.dataset != dataset
        ):
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "provider_chain",
                "The EOD provider result does not match the planned request.",
                dataset,
                requested_range,
                plan=plan,
                attempts=result.attempts,
            )
        if result.selected_result.status is EODProviderResultStatus.PARTIAL_SUCCESS:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PARTIAL_RESULT_NOT_PUBLISHABLE,
                "provider_chain",
                "A partial EOD provider result cannot be published.",
                dataset,
                requested_range,
                plan=plan,
                attempts=result.attempts,
                retryable=True,
            )
        if result.selected_result.status is not EODProviderResultStatus.SUCCESS:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "provider_chain",
                "The EOD provider result is not a complete success.",
                dataset,
                requested_range,
                plan=plan,
                attempts=result.attempts,
            )
        return result

    def _merge(
        self,
        plan: EODRequestPlan,
        current: Optional[EODStoredGeneration],
        fetched_bars: Tuple[EODBar, ...],
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        attempts: Tuple[EODProviderAttempt, ...],
    ) -> Tuple[Tuple[EODBar, ...], int, int]:
        request = plan.provider_request
        if request is None:  # pragma: no cover - guarded by the caller.
            raise RuntimeError("merge request is unavailable")
        if type(fetched_bars) not in (list, tuple) or not fetched_bars:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "merge",
                "A successful EOD provider result must contain bars.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )
        fetched = tuple(fetched_bars)
        if any(
            type(bar) is not EODBar
            or bar.dataset != dataset
            or not request.requested_range.contains(bar.trade_date)
            for bar in fetched
        ):
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH,
                "merge",
                "The EOD provider bars do not match the planned dataset and range.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )

        if plan.status is EODRequestPlanStatus.INITIAL_IMPORT:
            return normalize_eod_bars(fetched), len(fetched), 0
        if current is None:  # pragma: no cover - guarded by plan/current validation.
            raise RuntimeError("current generation is unavailable")

        current_dates = {bar.trade_date for bar in current.bars}
        fetched_dates = {bar.trade_date for bar in fetched}
        if plan.status is EODRequestPlanStatus.INCREMENTAL:
            if current_dates & fetched_dates or any(
                bar.trade_date <= current.manifest.last_trade_date for bar in fetched
            ):
                raise self._error(
                    EODIncrementalCoordinatorErrorCode.MERGE_CONFLICT,
                    "merge",
                    "Append-only EOD data overlaps the current generation.",
                    dataset,
                    requested_range,
                    plan=plan,
                    attempts=attempts,
                )
            candidate = normalize_eod_bars(tuple(current.bars) + fetched)
            return candidate, len(fetched), 0

        if plan.status is EODRequestPlanStatus.OVERLAP_REFRESH:
            refresh_range = request.requested_range
            existing_refresh_dates = {
                bar.trade_date for bar in current.bars if refresh_range.contains(bar.trade_date)
            }
            preserved = tuple(
                bar for bar in current.bars if not refresh_range.contains(bar.trade_date)
            )
            candidate = normalize_eod_bars(preserved + fetched)
            return (
                candidate,
                len(fetched_dates - existing_refresh_dates),
                len(existing_refresh_dates & fetched_dates),
            )

        raise self._error(
            EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
            "merge",
            "The EOD plan status cannot be merged incrementally.",
            dataset,
            requested_range,
            plan=plan,
            attempts=attempts,
        )

    def _validate_candidate(
        self,
        plan: EODRequestPlan,
        candidate: Tuple[EODBar, ...],
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        attempts: Tuple[EODProviderAttempt, ...],
    ) -> None:
        effective_range = plan.effective_range
        if effective_range is None:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.PLANNING_FAILED,
                "validation",
                "A fetch plan must include an effective date range.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )
        if any(bar.trade_date > effective_range.end_date for bar in candidate):
            raise self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The EOD candidate extends beyond the effective end date.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=("date_after_effective_end",),
            )
        try:
            full_report = validate_eod_batch(
                dataset,
                candidate,
                self._calendar,
                expected_range=None,
            )
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The complete EOD candidate could not be validated safely.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=("validation_exception",),
            )
            raise error from exc
        self._require_valid_report(
            full_report,
            dataset,
            requested_range,
            plan,
            attempts,
        )

        coverage_bars = tuple(bar for bar in candidate if effective_range.contains(bar.trade_date))
        try:
            coverage_report = validate_eod_batch(
                dataset,
                coverage_bars,
                self._calendar,
                expected_range=effective_range,
            )
        except Exception as exc:
            error = self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The EOD effective-range coverage could not be validated safely.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=("validation_exception",),
            )
            raise error from exc
        self._require_valid_report(
            coverage_report,
            dataset,
            requested_range,
            plan,
            attempts,
            require_complete_coverage=True,
        )

    def _require_valid_report(
        self,
        report: object,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        plan: EODRequestPlan,
        attempts: Tuple[EODProviderAttempt, ...],
        *,
        require_complete_coverage: bool = False,
    ) -> None:
        if type(report) is not EODValidationReport:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The EOD validator returned an unsupported report value.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=("invalid_validation_report",),
            )
        invalid = (
            not report.is_valid
            or report.duplicate_identical_count != 0
            or report.duplicate_conflicting_count != 0
            or (require_complete_coverage and bool(report.missing_trading_dates))
        )
        if invalid:
            codes = tuple(issue.code for issue in report.errors + report.warnings)
            if require_complete_coverage and report.missing_trading_dates:
                codes += ("missing_trading_days",)
            raise self._error(
                EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
                "validation",
                "The EOD candidate failed publication validation.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
                validation_codes=codes,
            )

    def _validate_published_manifest(
        self,
        manifest: object,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        plan: EODRequestPlan,
        attempts: Tuple[EODProviderAttempt, ...],
        candidate: Tuple[EODBar, ...],
        candidate_sha: str,
        generation_id: str,
        created_at: datetime,
        current_manifest: Optional[EODGenerationManifest],
    ) -> None:
        expected_previous = None if current_manifest is None else current_manifest.generation_id
        valid = type(manifest) is EODGenerationManifest and (
            manifest.dataset == dataset
            and manifest.generation_id == generation_id
            and manifest.created_at == created_at
            and manifest.row_count == len(candidate)
            and manifest.first_trade_date == candidate[0].trade_date
            and manifest.last_trade_date == candidate[-1].trade_date
            and manifest.content_sha256 == candidate_sha
            and manifest.data_version == f"sha256:{candidate_sha}"
            and manifest.previous_generation_id == expected_previous
        )
        if not valid:
            raise self._error(
                EODIncrementalCoordinatorErrorCode.REPOSITORY_CONTRACT_VIOLATION,
                "publish_response",
                "The EOD repository returned a mismatched publication manifest.",
                dataset,
                requested_range,
                plan=plan,
                attempts=attempts,
            )

    @staticmethod
    def _published_status(status: EODRequestPlanStatus) -> EODIncrementalUpdateStatus:
        mapping = {
            EODRequestPlanStatus.INITIAL_IMPORT: (
                EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED
            ),
            EODRequestPlanStatus.INCREMENTAL: (EODIncrementalUpdateStatus.INCREMENTAL_PUBLISHED),
            EODRequestPlanStatus.OVERLAP_REFRESH: (
                EODIncrementalUpdateStatus.OVERLAP_REFRESH_PUBLISHED
            ),
        }
        try:
            return mapping[status]
        except KeyError as exc:  # pragma: no cover - guarded before publication.
            raise RuntimeError("unsupported published plan status") from exc

    @staticmethod
    def _planned_status(status: EODRequestPlanStatus) -> EODIncrementalUpdateStatus:
        mapping = {
            EODRequestPlanStatus.INITIAL_IMPORT: (
                EODIncrementalUpdateStatus.INITIAL_IMPORT_PLANNED
            ),
            EODRequestPlanStatus.INCREMENTAL: EODIncrementalUpdateStatus.INCREMENTAL_PLANNED,
            EODRequestPlanStatus.OVERLAP_REFRESH: (
                EODIncrementalUpdateStatus.OVERLAP_REFRESH_PLANNED
            ),
        }
        try:
            return mapping[status]
        except KeyError as exc:  # pragma: no cover - guarded before dry-run return.
            raise RuntimeError("unsupported planned status") from exc
