"""Pure configured-dataset readiness contracts for EOD provider observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum
import re
from typing import Mapping, Optional, Protocol, Tuple, runtime_checkable

from autowealth.security import contains_absolute_path, contains_sensitive_value

from .calendar import TradingCalendar
from .schemas import BarFrequency, EODDatasetKey

MAX_EOD_READINESS_DATASETS = 256
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_DIAGNOSTIC_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class EODProviderReadinessStatus(str, Enum):
    READY = "ready"
    NOT_READY = "not_ready"
    PARTIAL = "partial"
    STALE = "stale"
    NOT_EXPECTED = "not_expected"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


def _identifier(value: object, field_name: str) -> str:
    if type(value) is not str or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe stable identifier")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        raise ValueError(f"{field_name} must not contain paths or credentials")
    return value


@dataclass(frozen=True)
class EODReadinessScope:
    """One deterministic set of configured enabled datasets for one expected date."""

    datasets: Tuple[EODDatasetKey, ...]
    expected_trade_date: date

    def __post_init__(self) -> None:
        if type(self.datasets) not in (list, tuple):
            raise TypeError("datasets must be an exact list or exact tuple")
        datasets = tuple(self.datasets)
        if not datasets or len(datasets) > MAX_EOD_READINESS_DATASETS:
            raise ValueError("datasets must contain a bounded non-empty configured scope")
        if any(type(dataset) is not EODDatasetKey for dataset in datasets):
            raise TypeError("datasets must contain exact EODDatasetKey values")
        if any(dataset.frequency is not BarFrequency.DAILY for dataset in datasets):
            raise ValueError("readiness only supports daily EOD datasets")
        if len(set(datasets)) != len(datasets):
            raise ValueError("readiness datasets cannot contain duplicates")
        if type(self.expected_trade_date) is not date:
            raise TypeError("expected_trade_date must be an exact date")
        object.__setattr__(
            self, "datasets", tuple(sorted(datasets, key=lambda item: item.identity))
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "expected_trade_date": self.expected_trade_date.isoformat(),
            "coverage_basis": "configured_datasets",
        }


@dataclass(frozen=True)
class EODProviderReadiness:
    """Side-effect-free readiness evidence; it is not an ingestion authorization.

    The publication watermark is the least-recent configured dataset observation
    only when every configured dataset has an observation; otherwise it is None.
    """

    provider_name: str
    provider_version: str
    endpoint_name: str
    scope: EODReadinessScope
    status: EODProviderReadinessStatus
    observed_at: datetime
    publication_watermark: Optional[date]
    observed_count: int
    expected_count: int
    diagnostic_code: str

    def __post_init__(self) -> None:
        provider_name = _identifier(self.provider_name, "provider_name")
        provider_version = _identifier(self.provider_version, "provider_version")
        endpoint_name = _identifier(self.endpoint_name, "endpoint_name")
        if type(self.scope) is not EODReadinessScope:
            raise TypeError("scope must be an exact EODReadinessScope")
        if not isinstance(self.status, EODProviderReadinessStatus):
            raise TypeError("status must be an EODProviderReadinessStatus")
        if type(self.observed_at) is not datetime or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be a timezone-aware datetime")
        observed_at = self.observed_at.astimezone(timezone.utc)
        if self.publication_watermark is not None and type(self.publication_watermark) is not date:
            raise TypeError("publication_watermark must be an exact date or None")
        if type(self.observed_count) is not int or type(self.expected_count) is not int:
            raise TypeError("readiness counts must be exact integers")
        if self.expected_count != len(self.scope.datasets):
            raise ValueError("expected_count must equal the configured dataset count")
        if not 0 <= self.observed_count <= self.expected_count:
            raise ValueError("observed_count must be within the configured dataset count")
        if (
            type(self.diagnostic_code) is not str
            or _DIAGNOSTIC_PATTERN.fullmatch(self.diagnostic_code) is None
        ):
            raise ValueError("diagnostic_code must be a stable lowercase identifier")
        object.__setattr__(self, "provider_name", provider_name)
        object.__setattr__(self, "provider_version", provider_version)
        object.__setattr__(self, "endpoint_name", endpoint_name)
        object.__setattr__(self, "observed_at", observed_at)

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "endpoint_name": self.endpoint_name,
            "scope": self.scope.to_dict(),
            "status": self.status.value,
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "publication_watermark": (
                None
                if self.publication_watermark is None
                else self.publication_watermark.isoformat()
            ),
            "observed_count": self.observed_count,
            "expected_count": self.expected_count,
            "diagnostic_code": self.diagnostic_code,
        }


@runtime_checkable
class EODProviderReadinessProbe(Protocol):
    """Read-only provider observation protocol, separate from ingestion fetch."""

    @property
    def provider_name(self) -> str: ...

    @property
    def provider_version(self) -> str: ...

    @property
    def endpoint_name(self) -> str: ...

    def probe_readiness(
        self,
        scope: EODReadinessScope,
        *,
        observed_at: datetime,
    ) -> EODProviderReadiness: ...


def evaluate_eod_provider_readiness(
    *,
    provider_name: str,
    provider_version: str,
    endpoint_name: str,
    scope: EODReadinessScope,
    calendar: TradingCalendar,
    observed_dates: Optional[Mapping[EODDatasetKey, Optional[date]]],
    observed_at: datetime,
    terminal_status: Optional[EODProviderReadinessStatus] = None,
) -> EODProviderReadiness:
    """Classify supplied observations without network, persistence or wall-clock guessing."""

    if type(scope) is not EODReadinessScope:
        raise TypeError("scope must be an exact EODReadinessScope")
    if not isinstance(calendar, TradingCalendar):
        raise TypeError("calendar must implement TradingCalendar")
    expected_count = len(scope.datasets)
    expected_date = scope.expected_trade_date

    if calendar.is_trading_day(expected_date) is not True:
        return EODProviderReadiness(
            provider_name,
            provider_version,
            endpoint_name,
            scope,
            EODProviderReadinessStatus.NOT_EXPECTED,
            observed_at,
            None,
            0,
            expected_count,
            "non_trading_date",
        )

    if terminal_status is not None:
        if terminal_status not in (
            EODProviderReadinessStatus.UNAVAILABLE,
            EODProviderReadinessStatus.UNSUPPORTED,
        ):
            raise ValueError("terminal_status must be unavailable or unsupported")
        if observed_dates not in (None, {}):
            raise ValueError("terminal readiness cannot include observations")
        diagnostic = (
            "provider_unavailable"
            if terminal_status is EODProviderReadinessStatus.UNAVAILABLE
            else "readiness_unsupported"
        )
        return EODProviderReadiness(
            provider_name,
            provider_version,
            endpoint_name,
            scope,
            terminal_status,
            observed_at,
            None,
            0,
            expected_count,
            diagnostic,
        )

    if type(observed_dates) is not dict or set(observed_dates) != set(scope.datasets):
        raise ValueError("observed_dates must exactly cover the configured scope")
    normalized_dates = []
    for dataset in scope.datasets:
        observed = observed_dates[dataset]
        if observed is not None and type(observed) is not date:
            raise TypeError("observed dates must be exact dates or None")
        if observed is not None and observed > expected_date:
            raise ValueError("observed date cannot be after expected_trade_date")
        normalized_dates.append(observed)

    observed_count = sum(value == expected_date for value in normalized_dates)
    dated = tuple(value for value in normalized_dates if value is not None)
    watermark = min(dated) if len(dated) == expected_count else None
    if observed_count == expected_count:
        status = EODProviderReadinessStatus.READY
        diagnostic = "configured_scope_ready"
    else:
        previous_date = calendar.previous_trading_day(expected_date)
        if any(value < previous_date for value in dated):
            status = EODProviderReadinessStatus.STALE
            diagnostic = "publication_stale"
        elif observed_count:
            status = EODProviderReadinessStatus.PARTIAL
            diagnostic = "configured_scope_partial"
        else:
            status = EODProviderReadinessStatus.NOT_READY
            diagnostic = "publication_pending"

    return EODProviderReadiness(
        provider_name,
        provider_version,
        endpoint_name,
        scope,
        status,
        observed_at,
        watermark,
        observed_count,
        expected_count,
        diagnostic,
    )


__all__ = [
    "EODProviderReadiness",
    "EODProviderReadinessProbe",
    "EODProviderReadinessStatus",
    "EODReadinessScope",
    "MAX_EOD_READINESS_DATASETS",
    "evaluate_eod_provider_readiness",
]
