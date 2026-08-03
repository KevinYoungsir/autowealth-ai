"""Pure request-window planning for incremental China A-share EOD updates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Optional, Type, TypeVar

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
)

from .calendar import TradingCalendar, validate_trading_days
from .providers import EODProviderRequest, EODRevisionStrategy
from .schemas import AdjustmentType, EODDatasetKey, EODDateRange
from .versioning import EODGenerationManifest

_EnumType = TypeVar("_EnumType", bound=Enum)


class EODRequestPlanStatus(str, Enum):
    """Stable outcomes of pure EOD request-window planning."""

    INITIAL_IMPORT = "initial_import"
    INCREMENTAL = "incremental"
    OVERLAP_REFRESH = "overlap_refresh"
    ALREADY_CURRENT = "already_current"
    NO_TRADING_DAYS = "no_trading_days"
    FULL_REFRESH_REQUIRED = "full_refresh_required"


class EODRequestPlanningErrorCode(str, Enum):
    """Finite planning failures that require caller intervention."""

    CURRENT_DATASET_MISMATCH = "current_dataset_mismatch"
    CURRENT_AFTER_EFFECTIVE_END = "current_after_effective_end"
    CURRENT_DATE_NOT_TRADING_DAY = "current_date_not_trading_day"
    INVALID_REVISION_POLICY = "invalid_revision_policy"
    INVALID_CALENDAR = "invalid_calendar"


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
        return "The EOD request window could not be planned safely."
    sanitized = sanitize_public_text(value)[:512]
    if not sanitized or contains_absolute_path(sanitized) or contains_sensitive_value(sanitized):
        return "The EOD request window could not be planned safely."
    return sanitized


class EODRequestPlanningError(ValueError):
    """Single safe exception type for deterministic planning failures."""

    def __init__(self, code: EODRequestPlanningErrorCode, message: str) -> None:
        normalized_code = _enum_value(code, EODRequestPlanningErrorCode, "code")
        safe_message = _safe_message(message)
        self.code = normalized_code
        self.message = safe_message
        super().__init__(safe_message)

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "message": self.message}

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODRevisionPolicy:
    """Explicit revision behavior used by the pure request planner."""

    strategy: EODRevisionStrategy
    overlap_trading_days: int = 0

    def __post_init__(self) -> None:
        strategy = _enum_value(
            self.strategy,
            EODRevisionStrategy,
            "strategy",
        )
        overlap = self.overlap_trading_days
        if isinstance(overlap, bool) or type(overlap) is not int:
            raise ValueError("overlap_trading_days must be an exact integer")
        if strategy is EODRevisionStrategy.OVERLAP_WINDOW:
            if overlap <= 0:
                raise ValueError("overlap_trading_days must be positive for overlap_window")
        elif overlap != 0:
            raise ValueError("overlap_trading_days must be zero outside overlap_window")
        object.__setattr__(self, "strategy", strategy)

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "overlap_trading_days": self.overlap_trading_days,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


def default_eod_revision_policy(dataset: EODDatasetKey) -> EODRevisionPolicy:
    """Return the conservative default revision policy for one dataset.

    Later corporate actions may recalculate historical qfq or hfq prices, so
    adjusted history cannot be assumed to be safely append-only. This function
    only selects a safe policy; it never performs a refresh.
    """

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    strategy = (
        EODRevisionStrategy.APPEND_ONLY
        if dataset.adjustment_type is AdjustmentType.NONE
        else EODRevisionStrategy.FULL_REFRESH_REQUIRED
    )
    return EODRevisionPolicy(strategy=strategy)


@dataclass(frozen=True)
class EODRequestPlan:
    """Immutable result of planning one EOD provider request window."""

    dataset: EODDatasetKey
    requested_range: EODDateRange
    effective_range: Optional[EODDateRange]
    revision_policy: EODRevisionPolicy
    status: EODRequestPlanStatus
    provider_request: Optional[EODProviderRequest]

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")
        if self.effective_range is not None and type(self.effective_range) is not EODDateRange:
            raise TypeError("effective_range must be an exact EODDateRange or None")
        if type(self.revision_policy) is not EODRevisionPolicy:
            raise TypeError("revision_policy must be an exact EODRevisionPolicy")
        status = _enum_value(self.status, EODRequestPlanStatus, "status")
        if (
            self.provider_request is not None
            and type(self.provider_request) is not EODProviderRequest
        ):
            raise TypeError("provider_request must be an exact EODProviderRequest or None")

        fetch_statuses = {
            EODRequestPlanStatus.INITIAL_IMPORT,
            EODRequestPlanStatus.INCREMENTAL,
            EODRequestPlanStatus.OVERLAP_REFRESH,
        }
        no_request_statuses = {
            EODRequestPlanStatus.ALREADY_CURRENT,
            EODRequestPlanStatus.NO_TRADING_DAYS,
            EODRequestPlanStatus.FULL_REFRESH_REQUIRED,
        }
        if status in fetch_statuses:
            if self.effective_range is None or self.provider_request is None:
                raise ValueError(f"{status.value} requires an effective range and request")
        elif status in no_request_statuses and self.provider_request is not None:
            raise ValueError(f"{status.value} must not contain a provider request")

        if status is EODRequestPlanStatus.NO_TRADING_DAYS:
            if self.effective_range is not None:
                raise ValueError("no_trading_days must not contain an effective range")
        elif self.effective_range is None:
            raise ValueError(f"{status.value} requires an effective range")

        request = self.provider_request
        effective = self.effective_range
        if request is not None and effective is not None:
            if request.dataset != self.dataset:
                raise ValueError("provider request dataset must match the plan dataset")
            if not (
                effective.contains(request.requested_range.start_date)
                and effective.contains(request.requested_range.end_date)
            ):
                raise ValueError("provider request range must be inside the effective range")
            if request.requested_range.end_date != effective.end_date:
                raise ValueError("provider request must end on the effective end date")

        if status is EODRequestPlanStatus.INITIAL_IMPORT:
            if request is None or effective is None or request.requested_range != effective:
                raise ValueError("initial_import request range must equal the effective range")
        if status is EODRequestPlanStatus.INCREMENTAL and (
            self.revision_policy.strategy is not EODRevisionStrategy.APPEND_ONLY
        ):
            raise ValueError("incremental requires append_only policy")
        if status is EODRequestPlanStatus.OVERLAP_REFRESH and (
            self.revision_policy.strategy is not EODRevisionStrategy.OVERLAP_WINDOW
        ):
            raise ValueError("overlap_refresh requires overlap_window policy")

        object.__setattr__(self, "status", status)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "effective_range": (
                None if self.effective_range is None else self.effective_range.to_dict()
            ),
            "revision_policy": self.revision_policy.to_dict(),
            "status": self.status.value,
            "provider_request": (
                None if self.provider_request is None else self.provider_request.to_dict()
            ),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


def _calendar_date_status(calendar: TradingCalendar, value: object) -> bool:
    try:
        status = calendar.is_trading_day(value)
    except Exception as exc:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_CALENDAR,
            "The trading calendar could not classify a current manifest date.",
        ) from exc
    if type(status) is not bool:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_CALENDAR,
            "The trading calendar returned a non-boolean date classification.",
        )
    return status


def _plan(
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
    effective_range: Optional[EODDateRange],
    policy: EODRevisionPolicy,
    status: EODRequestPlanStatus,
    request_range: Optional[EODDateRange] = None,
) -> EODRequestPlan:
    provider_request = (
        None
        if request_range is None
        else EODProviderRequest(dataset=dataset, requested_range=request_range)
    )
    return EODRequestPlan(
        dataset=dataset,
        requested_range=requested_range,
        effective_range=effective_range,
        revision_policy=policy,
        status=status,
        provider_request=provider_request,
    )


def plan_eod_request_window(
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
    calendar: TradingCalendar,
    current_manifest: Optional[EODGenerationManifest] = None,
    revision_policy: Optional[EODRevisionPolicy] = None,
) -> EODRequestPlan:
    """Plan a deterministic EOD request without Provider or repository access."""

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if type(requested_range) is not EODDateRange:
        raise TypeError("requested_range must be an exact EODDateRange")
    if current_manifest is not None and type(current_manifest) is not EODGenerationManifest:
        raise TypeError("current_manifest must be an exact EODGenerationManifest or None")
    if revision_policy is not None and type(revision_policy) is not EODRevisionPolicy:
        raise TypeError("revision_policy must be an exact EODRevisionPolicy or None")
    policy = revision_policy or default_eod_revision_policy(dataset)

    try:
        trading_days = validate_trading_days(calendar, requested_range)
    except Exception as exc:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_CALENDAR,
            "The trading calendar returned an invalid requested date sequence.",
        ) from exc

    if not trading_days:
        return _plan(
            dataset,
            requested_range,
            None,
            policy,
            EODRequestPlanStatus.NO_TRADING_DAYS,
        )

    effective_range = EODDateRange(trading_days[0], trading_days[-1])
    if (
        policy.strategy is EODRevisionStrategy.APPEND_ONLY
        and dataset.adjustment_type is not AdjustmentType.NONE
    ):
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_REVISION_POLICY,
            "Adjusted EOD datasets cannot use append_only revision policy.",
        )

    if current_manifest is None:
        return _plan(
            dataset,
            requested_range,
            effective_range,
            policy,
            EODRequestPlanStatus.INITIAL_IMPORT,
            effective_range,
        )
    if current_manifest.dataset != dataset:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.CURRENT_DATASET_MISMATCH,
            "The current manifest dataset does not match the requested dataset.",
        )
    if not _calendar_date_status(calendar, current_manifest.first_trade_date):
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.CURRENT_DATE_NOT_TRADING_DAY,
            "The current manifest first date is not a recognized trading day.",
        )
    if not _calendar_date_status(calendar, current_manifest.last_trade_date):
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.CURRENT_DATE_NOT_TRADING_DAY,
            "The current manifest last date is not a recognized trading day.",
        )
    if (
        effective_range.contains(current_manifest.last_trade_date)
        and current_manifest.last_trade_date not in trading_days
    ):
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_CALENDAR,
            "The trading calendar omitted the current manifest last date.",
        )
    if current_manifest.last_trade_date > effective_range.end_date:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.CURRENT_AFTER_EFFECTIVE_END,
            "The current manifest extends beyond the effective requested end date.",
        )
    if current_manifest.first_trade_date > effective_range.start_date:
        return _plan(
            dataset,
            requested_range,
            effective_range,
            policy,
            EODRequestPlanStatus.FULL_REFRESH_REQUIRED,
        )
    if current_manifest.last_trade_date == effective_range.end_date:
        return _plan(
            dataset,
            requested_range,
            effective_range,
            policy,
            EODRequestPlanStatus.ALREADY_CURRENT,
        )
    if policy.strategy is EODRevisionStrategy.FULL_REFRESH_REQUIRED:
        return _plan(
            dataset,
            requested_range,
            effective_range,
            policy,
            EODRequestPlanStatus.FULL_REFRESH_REQUIRED,
        )

    if policy.strategy is EODRevisionStrategy.APPEND_ONLY:
        request_start = next(day for day in trading_days if day > current_manifest.last_trade_date)
        return _plan(
            dataset,
            requested_range,
            effective_range,
            policy,
            EODRequestPlanStatus.INCREMENTAL,
            EODDateRange(request_start, effective_range.end_date),
        )

    existing_days = tuple(day for day in trading_days if day <= current_manifest.last_trade_date)
    if existing_days:
        overlap_count = min(policy.overlap_trading_days, len(existing_days))
        request_start = existing_days[-overlap_count]
    else:
        request_start = effective_range.start_date
    return _plan(
        dataset,
        requested_range,
        effective_range,
        policy,
        EODRequestPlanStatus.OVERLAP_REFRESH,
        EODDateRange(request_start, effective_range.end_date),
    )
