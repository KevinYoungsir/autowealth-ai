"""Pure provider contracts for validated China A-share EOD data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
from typing import Optional, Protocol, Tuple, Type, TypeVar, runtime_checkable

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    sanitize_public_text,
)

from .calendar import TradingCalendar, validate_trading_days
from .normalization import normalize_eod_bars
from .schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODWarningSeverity,
    Market,
    Venue,
)
from .validation import validate_eod_batch

_MACHINE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_EnumType = TypeVar("_EnumType", bound=Enum)


class EODRevisionStrategy(str, Enum):
    """How a dataset may be refreshed when new EOD dates become available."""

    APPEND_ONLY = "append_only"
    OVERLAP_WINDOW = "overlap_window"
    FULL_REFRESH_REQUIRED = "full_refresh_required"


class EODProviderResultStatus(str, Enum):
    """Stable provider result states before repository publication."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    EMPTY = "empty"


class EODProviderErrorCode(str, Enum):
    """Finite provider failure classes for future fallback decisions."""

    UNSUPPORTED_REQUEST = "unsupported_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    TEMPORARY_PROVIDER_FAILURE = "temporary_provider_failure"
    PERMANENT_PROVIDER_FAILURE = "permanent_provider_failure"
    MALFORMED_PROVIDER_PAYLOAD = "malformed_provider_payload"


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


def _safe_identifier(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe stable identifier")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        raise ValueError(f"{field_name} must not contain paths or credentials")
    return value


def _safe_message(value: object, fallback: str) -> str:
    if type(value) is not str or not value:
        raise ValueError("message must be non-empty text")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        return fallback
    sanitized = sanitize_public_text(value)[:512]
    if not sanitized or contains_absolute_path(sanitized) or contains_sensitive_value(sanitized):
        return fallback
    return sanitized


def _normalized_warnings(
    warnings: object,
    additions: Tuple[EODStructuredWarning, ...] = (),
) -> Tuple[EODStructuredWarning, ...]:
    if type(warnings) not in (list, tuple):
        raise TypeError("warnings must be an exact list or exact tuple")
    values = tuple(warnings) + additions
    if any(type(item) is not EODStructuredWarning for item in values):
        raise TypeError("warnings must contain exact EODStructuredWarning values")
    by_json = {warning.to_json(): warning for warning in values}
    return tuple(by_json[key] for key in sorted(by_json))


def _empty_response_warning(request: "EODProviderRequest") -> EODStructuredWarning:
    return EODStructuredWarning(
        code="empty_response",
        severity=EODWarningSeverity.WARNING,
        message="The EOD provider returned no rows for a trading-date request.",
        details={"requested_range": request.requested_range.to_dict()},
    )


class EODProviderError(RuntimeError):
    """Single safe exception type for finite provider failures."""

    def __init__(self, code: EODProviderErrorCode, message: str) -> None:
        normalized_code = _enum_value(code, EODProviderErrorCode, "code")
        safe_message = _safe_message(message, "The EOD provider operation failed safely.")
        self.code = normalized_code
        self.message = safe_message
        super().__init__(safe_message)

    @property
    def retryable(self) -> bool:
        """Return whether a future bounded retry may repeat this provider."""

        return self.code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODProviderCapability:
    """One exact dataset combination supported by an EOD provider."""

    market: Market
    venue: Venue
    asset_type: AssetType
    frequency: BarFrequency
    adjustment_type: AdjustmentType
    revision_strategy: EODRevisionStrategy
    maximum_overlap_trading_days: Optional[int] = None

    def __post_init__(self) -> None:
        market = _enum_value(self.market, Market, "market")
        venue = _enum_value(self.venue, Venue, "venue")
        asset_type = _enum_value(self.asset_type, AssetType, "asset_type")
        frequency = _enum_value(self.frequency, BarFrequency, "frequency")
        adjustment = _enum_value(
            self.adjustment_type,
            AdjustmentType,
            "adjustment_type",
        )
        strategy = _enum_value(
            self.revision_strategy,
            EODRevisionStrategy,
            "revision_strategy",
        )
        overlap = self.maximum_overlap_trading_days
        if strategy is EODRevisionStrategy.OVERLAP_WINDOW:
            if isinstance(overlap, bool) or type(overlap) is not int or overlap <= 0:
                raise ValueError(
                    "maximum_overlap_trading_days must be a positive exact integer "
                    "for overlap_window"
                )
        elif overlap is not None:
            raise ValueError("maximum_overlap_trading_days must be None outside overlap_window")

        object.__setattr__(self, "market", market)
        object.__setattr__(self, "venue", venue)
        object.__setattr__(self, "asset_type", asset_type)
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(self, "adjustment_type", adjustment)
        object.__setattr__(self, "revision_strategy", strategy)

    def matches(self, dataset: EODDatasetKey) -> bool:
        """Return whether this exact capability supports a dataset identity."""

        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        return (
            self.market is dataset.market
            and self.venue is dataset.venue
            and self.asset_type is dataset.asset_type
            and self.frequency is dataset.frequency
            and self.adjustment_type is dataset.adjustment_type
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market.value,
            "venue": self.venue.value,
            "asset_type": self.asset_type.value,
            "frequency": self.frequency.value,
            "adjustment_type": self.adjustment_type.value,
            "revision_strategy": self.revision_strategy.value,
            "maximum_overlap_trading_days": self.maximum_overlap_trading_days,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODProviderRequest:
    """Immutable request for one canonical EOD dataset and closed date range."""

    dataset: EODDatasetKey
    requested_range: EODDateRange

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an exact EODDateRange")

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODProviderResult:
    """Deterministic provider output that is not yet publishable."""

    request: EODProviderRequest
    provider_name: str
    provider_version: str
    status: EODProviderResultStatus
    bars: Tuple[EODBar, ...]
    warnings: Tuple[EODStructuredWarning, ...] = ()

    def __post_init__(self) -> None:
        if type(self.request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        provider_name = _safe_identifier(
            self.provider_name,
            "provider_name",
            _MACHINE_NAME_PATTERN,
        )
        provider_version = _safe_identifier(
            self.provider_version,
            "provider_version",
            _VERSION_PATTERN,
        )
        status = _enum_value(self.status, EODProviderResultStatus, "status")
        if type(self.bars) not in (list, tuple):
            raise TypeError("bars must be an exact list or exact tuple")
        supplied_bars = tuple(self.bars)
        if any(type(bar) is not EODBar for bar in supplied_bars):
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "The provider payload contains a value that is not an EOD bar.",
            )
        if any(bar.dataset != self.request.dataset for bar in supplied_bars):
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "The provider payload mixes or changes the requested dataset.",
            )
        if any(not self.request.requested_range.contains(bar.trade_date) for bar in supplied_bars):
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "The provider payload contains a date outside the requested range.",
            )
        trade_dates = [bar.trade_date for bar in supplied_bars]
        if len(set(trade_dates)) != len(trade_dates):
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "The provider payload contains duplicate trading dates.",
            )
        normalized_bars = normalize_eod_bars(supplied_bars)
        if status is EODProviderResultStatus.EMPTY and normalized_bars:
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "An empty provider result cannot contain EOD bars.",
            )
        if status is not EODProviderResultStatus.EMPTY and not normalized_bars:
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "A non-empty provider status requires at least one EOD bar.",
            )

        additions = (
            (_empty_response_warning(self.request),)
            if status is EODProviderResultStatus.EMPTY
            else ()
        )
        warnings = _normalized_warnings(self.warnings, additions)
        if any(warning.severity is EODWarningSeverity.ERROR for warning in warnings):
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "A provider result cannot contain an error-severity warning.",
            )

        object.__setattr__(self, "provider_name", provider_name)
        object.__setattr__(self, "provider_version", provider_version)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "bars", normalized_bars)
        object.__setattr__(self, "warnings", warnings)

    @property
    def effective_range(self) -> Optional[EODDateRange]:
        """Return the observed bar range, or None for an empty result."""

        if not self.bars:
            return None
        return EODDateRange(self.bars[0].trade_date, self.bars[-1].trade_date)

    def to_dict(self) -> dict[str, object]:
        effective_range = self.effective_range
        return {
            "request": self.request.to_dict(),
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "status": self.status.value,
            "bars": [bar.to_dict() for bar in self.bars],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "effective_range": (None if effective_range is None else effective_range.to_dict()),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@runtime_checkable
class EODProvider(Protocol):
    """Read-only protocol implemented by future EOD provider adapters."""

    @property
    def provider_name(self) -> str: ...

    @property
    def provider_version(self) -> str: ...

    @property
    def capabilities(self) -> Tuple[EODProviderCapability, ...]: ...

    def fetch(self, request: EODProviderRequest) -> EODProviderResult: ...


def validate_eod_provider_request(
    request: EODProviderRequest,
    capabilities: Tuple[EODProviderCapability, ...],
) -> EODProviderCapability:
    """Return the unique exact capability matching an immutable request."""

    if type(request) is not EODProviderRequest:
        raise TypeError("request must be an exact EODProviderRequest")
    if type(capabilities) not in (list, tuple):
        raise TypeError("capabilities must be an exact list or exact tuple")
    normalized = tuple(capabilities)
    if any(type(item) is not EODProviderCapability for item in normalized):
        raise TypeError("capabilities must contain exact EODProviderCapability values")
    if len(set(normalized)) != len(normalized):
        raise EODProviderError(
            EODProviderErrorCode.UNSUPPORTED_REQUEST,
            "Provider capabilities contain duplicate entries.",
        )
    matches = tuple(item for item in normalized if item.matches(request.dataset))
    if len(matches) != 1:
        message = (
            "No provider capability supports the requested dataset."
            if not matches
            else "Provider capabilities contain ambiguous matches."
        )
        raise EODProviderError(EODProviderErrorCode.UNSUPPORTED_REQUEST, message)
    return matches[0]


def validate_eod_provider_result(
    result: EODProviderResult,
    calendar: TradingCalendar,
) -> EODProviderResult:
    """Validate, normalize and classify provider bars without performing I/O."""

    if type(result) is not EODProviderResult:
        raise TypeError("result must be an exact EODProviderResult")
    try:
        expected_dates = validate_trading_days(
            calendar,
            result.request.requested_range,
        )
    except Exception as exc:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The provider result could not be validated against the trading calendar.",
        ) from exc

    if result.status is EODProviderResultStatus.EMPTY:
        if not expected_dates:
            raise EODProviderError(
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                "An empty provider result cannot represent a range without trading days.",
            )
        return EODProviderResult(
            request=result.request,
            provider_name=result.provider_name,
            provider_version=result.provider_version,
            status=result.status,
            bars=(),
            warnings=result.warnings,
        )

    try:
        report = validate_eod_batch(
            result.request.dataset,
            result.bars,
            calendar,
            result.request.requested_range,
        )
    except Exception as exc:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The provider result failed deterministic EOD validation.",
        ) from exc

    if (
        not report.is_valid
        or report.duplicate_identical_count
        or report.duplicate_conflicting_count
    ):
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The provider payload failed EOD structure or integrity validation.",
        )

    has_missing_dates = bool(report.missing_trading_dates)
    if result.status is EODProviderResultStatus.SUCCESS and has_missing_dates:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "A successful provider result cannot omit expected trading dates.",
        )
    if result.status is EODProviderResultStatus.PARTIAL_SUCCESS and not has_missing_dates:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "A partial provider result must omit at least one expected trading date.",
        )
    if result.status is EODProviderResultStatus.SUCCESS and any(
        warning.code == "missing_trading_days" for warning in result.warnings
    ):
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "A successful provider result cannot carry a missing-trading-days warning.",
        )

    warnings = _normalized_warnings(result.warnings, report.warnings)
    return EODProviderResult(
        request=result.request,
        provider_name=result.provider_name,
        provider_version=result.provider_version,
        status=result.status,
        bars=result.bars,
        warnings=warnings,
    )
