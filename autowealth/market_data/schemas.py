"""Stable, side-effect-free contracts for China A-share EOD market data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Type, TypeVar

from autowealth.security import (
    contains_absolute_path,
    contains_sensitive_value,
    validate_bounded_json,
)

EOD_SCHEMA_VERSION = 1


class Market(str, Enum):
    """Markets supported by the first EOD contract."""

    CN = "CN"


class Venue(str, Enum):
    """Mainland China venues supported by the first EOD contract."""

    SSE = "SSE"
    SZSE = "SZSE"


class AssetType(str, Enum):
    """Asset types whose daily bars share the initial EOD contract."""

    EQUITY = "equity"
    INDEX = "index"


class BarFrequency(str, Enum):
    """Bar frequencies supported by the first EOD contract."""

    DAILY = "1d"


class AdjustmentType(str, Enum):
    """Price adjustment identities that must never share one dataset."""

    NONE = "none"
    QFQ = "qfq"
    HFQ = "hfq"


class EODUpdateStatus(str, Enum):
    """Stable update outcomes for future coordinators."""

    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    NOOP = "noop"


class EODWarningSeverity(str, Enum):
    """Severity levels used by EOD validation and update contracts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


_EnumType = TypeVar("_EnumType", bound=Enum)
_CANONICAL_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(?:SH|SZ)$")
_MACHINE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_MACHINE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _enum_value(value: object, enum_type: Type[_EnumType], field_name: str) -> _EnumType:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ValueError(f"{field_name} must be a supported string enum value")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"unsupported {field_name}: {value}") from exc


def _date_only(value: object, field_name: str) -> date:
    if type(value) is not date:
        raise ValueError(f"{field_name} must be a date")
    return value


def _aware_datetime(value: object, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value


def _decimal_number(
    value: object,
    field_name: str,
    *,
    strictly_positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    if isinstance(value, bool) or type(value) not in (int, float, Decimal):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        normalized = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"{field_name} must be a finite number") from exc
    if not normalized.is_finite():
        raise ValueError(f"{field_name} must be a finite number")
    if strictly_positive and normalized <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    if non_negative and normalized < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return normalized


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _non_negative_count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _optional_machine_name(value: object, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if type(value) is not str or _MACHINE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe machine identifier")
    return value


def _optional_version(value: object, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if type(value) is not str or _VERSION_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a stable version identifier")
    return value


def _json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _freeze_json(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if type(value) is tuple:
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class EODDatasetKey:
    """Immutable identity of one homogeneous EOD bar dataset."""

    market: Market
    venue: Venue
    asset_type: AssetType
    canonical_symbol: str
    frequency: BarFrequency = BarFrequency.DAILY
    adjustment_type: AdjustmentType = AdjustmentType.NONE

    def __post_init__(self) -> None:
        market = _enum_value(self.market, Market, "market")
        venue = _enum_value(self.venue, Venue, "venue")
        asset_type = _enum_value(self.asset_type, AssetType, "asset_type")
        frequency = _enum_value(self.frequency, BarFrequency, "frequency")
        adjustment = _enum_value(self.adjustment_type, AdjustmentType, "adjustment_type")
        if type(self.canonical_symbol) is not str:
            raise ValueError("canonical_symbol must be text")
        if _CANONICAL_SYMBOL_PATTERN.fullmatch(self.canonical_symbol) is None:
            raise ValueError("canonical_symbol must use the exact 600000.SH or 000001.SZ form")
        expected_venue = Venue.SSE if self.canonical_symbol.endswith(".SH") else Venue.SZSE
        if venue is not expected_venue:
            raise ValueError(f"canonical_symbol suffix conflicts with venue {venue.value}")

        object.__setattr__(self, "market", market)
        object.__setattr__(self, "venue", venue)
        object.__setattr__(self, "asset_type", asset_type)
        object.__setattr__(self, "frequency", frequency)
        object.__setattr__(self, "adjustment_type", adjustment)

    @property
    def identity(self) -> Tuple[str, str, str, str, str, str]:
        """Return the stable dataset identity tuple."""
        return (
            self.market.value,
            self.venue.value,
            self.asset_type.value,
            self.canonical_symbol,
            self.frequency.value,
            self.adjustment_type.value,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market.value,
            "venue": self.venue.value,
            "asset_type": self.asset_type.value,
            "canonical_symbol": self.canonical_symbol,
            "frequency": self.frequency.value,
            "adjustment_type": self.adjustment_type.value,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODBar:
    """One validated EOD bar with stable decimal values."""

    dataset: EODDatasetKey
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    amount: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an EODDatasetKey")
        trade_date = _date_only(self.trade_date, "trade_date")
        open_value = _decimal_number(self.open, "open", strictly_positive=True)
        high_value = _decimal_number(self.high, "high", strictly_positive=True)
        low_value = _decimal_number(self.low, "low", strictly_positive=True)
        close_value = _decimal_number(self.close, "close", strictly_positive=True)
        volume = _decimal_number(self.volume, "volume", non_negative=True)
        amount = (
            None
            if self.amount is None
            else _decimal_number(self.amount, "amount", non_negative=True)
        )
        if high_value < max(open_value, low_value, close_value):
            raise ValueError("high must be greater than or equal to open, low and close")
        if low_value > min(open_value, high_value, close_value):
            raise ValueError("low must be less than or equal to open, high and close")

        object.__setattr__(self, "trade_date", trade_date)
        object.__setattr__(self, "open", open_value)
        object.__setattr__(self, "high", high_value)
        object.__setattr__(self, "low", low_value)
        object.__setattr__(self, "close", close_value)
        object.__setattr__(self, "volume", volume)
        object.__setattr__(self, "amount", amount)

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "trade_date": self.trade_date.isoformat(),
            "open": _decimal_text(self.open),
            "high": _decimal_text(self.high),
            "low": _decimal_text(self.low),
            "close": _decimal_text(self.close),
            "volume": _decimal_text(self.volume),
            "amount": None if self.amount is None else _decimal_text(self.amount),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODDateRange:
    """Inclusive date range used by EOD requests and validation."""

    start_date: date
    end_date: date

    def __post_init__(self) -> None:
        start = _date_only(self.start_date, "start_date")
        end = _date_only(self.end_date, "end_date")
        if start > end:
            raise ValueError("start_date cannot be after end_date")
        object.__setattr__(self, "start_date", start)
        object.__setattr__(self, "end_date", end)

    def contains(self, value: date) -> bool:
        """Return whether a date is inside this closed interval."""
        candidate = _date_only(value, "value")
        return self.start_date <= candidate <= self.end_date

    def to_dict(self) -> dict[str, object]:
        return {
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODUpdateRequest:
    """Serializable request contract; it performs no update work."""

    dataset: EODDatasetKey
    requested_range: EODDateRange
    dry_run: bool = False

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an EODDateRange")
        if type(self.dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "dry_run": self.dry_run,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODStructuredWarning:
    """Bounded, JSON-safe issue metadata for EOD validation and updates."""

    code: str
    severity: EODWarningSeverity
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if type(self.code) is not str or _MACHINE_CODE_PATTERN.fullmatch(self.code) is None:
            raise ValueError("code must be a stable lowercase machine identifier")
        severity = _enum_value(self.severity, EODWarningSeverity, "severity")
        if type(self.message) is not str or not self.message or len(self.message) > 512:
            raise ValueError("message must be non-empty text of at most 512 characters")
        if contains_absolute_path(self.message) or contains_sensitive_value(self.message):
            raise ValueError("message must not contain paths or credentials")
        if type(self.details) is not dict:
            raise TypeError("details must be an exact dict")
        details = validate_bounded_json(
            self.details,
            field_name="details",
            maximum_depth=3,
            maximum_mapping_keys=32,
            maximum_list_items=32,
            maximum_string_length=512,
            maximum_json_bytes=16 * 1024,
        )
        if type(details) is not dict:  # pragma: no cover - exact dict is required above.
            raise TypeError("details normalization must remain a dict")

        object.__setattr__(self, "severity", severity)
        object.__setattr__(self, "details", _freeze_json(details))

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "details": _thaw_json(self.details),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODUpdateResult:
    """Serializable outcome contract for a future EOD coordinator."""

    status: EODUpdateStatus
    dataset: EODDatasetKey
    requested_range: EODDateRange
    received_row_count: int
    inserted_row_count: int
    updated_row_count: int
    skipped_row_count: int
    started_at: datetime
    finished_at: datetime
    provider: Optional[str] = None
    latest_effective_trading_date: Optional[date] = None
    warnings: Tuple[EODStructuredWarning, ...] = ()
    before_data_version: Optional[str] = None
    after_data_version: Optional[str] = None
    generation_checksum: Optional[str] = None

    def __post_init__(self) -> None:
        status = _enum_value(self.status, EODUpdateStatus, "status")
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an EODDatasetKey")
        if type(self.requested_range) is not EODDateRange:
            raise TypeError("requested_range must be an EODDateRange")
        counts = {
            "received_row_count": _non_negative_count(
                self.received_row_count, "received_row_count"
            ),
            "inserted_row_count": _non_negative_count(
                self.inserted_row_count, "inserted_row_count"
            ),
            "updated_row_count": _non_negative_count(self.updated_row_count, "updated_row_count"),
            "skipped_row_count": _non_negative_count(self.skipped_row_count, "skipped_row_count"),
        }
        started_at = _aware_datetime(self.started_at, "started_at")
        finished_at = _aware_datetime(self.finished_at, "finished_at")
        if finished_at < started_at:
            raise ValueError("finished_at cannot be before started_at")
        latest_date = (
            None
            if self.latest_effective_trading_date is None
            else _date_only(
                self.latest_effective_trading_date,
                "latest_effective_trading_date",
            )
        )
        if type(self.warnings) not in (list, tuple):
            raise TypeError("warnings must be an exact list or tuple")
        warnings = tuple(self.warnings)
        if any(type(item) is not EODStructuredWarning for item in warnings):
            raise TypeError("warnings must contain EODStructuredWarning values")
        checksum = self.generation_checksum
        if checksum is not None and (
            type(checksum) is not str or _SHA256_PATTERN.fullmatch(checksum) is None
        ):
            raise ValueError("generation_checksum must be a lowercase SHA-256 digest")

        object.__setattr__(self, "status", status)
        for field_name, value in counts.items():
            object.__setattr__(self, field_name, value)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "finished_at", finished_at)
        object.__setattr__(
            self,
            "provider",
            _optional_machine_name(self.provider, "provider"),
        )
        object.__setattr__(self, "latest_effective_trading_date", latest_date)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(
            self,
            "before_data_version",
            _optional_version(self.before_data_version, "before_data_version"),
        )
        object.__setattr__(
            self,
            "after_data_version",
            _optional_version(self.after_data_version, "after_data_version"),
        )
        object.__setattr__(self, "generation_checksum", checksum)

    @property
    def succeeded(self) -> bool:
        """Return true only for an explicit successful update."""
        return self.status is EODUpdateStatus.SUCCESS

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "dataset": self.dataset.to_dict(),
            "requested_range": self.requested_range.to_dict(),
            "provider": self.provider,
            "received_row_count": self.received_row_count,
            "inserted_row_count": self.inserted_row_count,
            "updated_row_count": self.updated_row_count,
            "skipped_row_count": self.skipped_row_count,
            "latest_effective_trading_date": (
                None
                if self.latest_effective_trading_date is None
                else self.latest_effective_trading_date.isoformat()
            ),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "before_data_version": self.before_data_version,
            "after_data_version": self.after_data_version,
            "generation_checksum": self.generation_checksum,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())
