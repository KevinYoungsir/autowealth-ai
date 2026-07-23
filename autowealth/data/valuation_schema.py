"""Point-in-time contracts for historical A-share valuation observations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Iterable, Optional, Tuple, Union

import pandas as pd

ValuationRevision = Union[str, int]


class ValuationMetric(str, Enum):
    """Stable metric catalog for future historical valuation providers."""

    PE_TTM = "pe_ttm"
    PB = "pb"
    PS_TTM = "ps_ttm"
    DIVIDEND_YIELD = "dividend_yield"
    MARKET_CAP = "market_cap"


VALUATION_AVAILABILITY_STATUSES: Tuple[str, ...] = (
    "available",
    "partial",
    "unavailable",
    "invalid",
)

VALUATION_REASON_CODES: Tuple[str, ...] = (
    "success",
    "provider_not_configured",
    "unsupported_metric",
    "provider_exception",
    "empty_response",
    "invalid_schema",
    "missing_available_date",
    "future_available_date",
    "non_finite_value",
    "insufficient_coverage",
    "historical_valuation_unavailable",
)

VALUATION_STATUS_REASON_CODES: dict[str, Tuple[str, ...]] = {
    "available": ("success",),
    "partial": (
        "unsupported_metric",
        "provider_exception",
        "empty_response",
        "future_available_date",
        "insufficient_coverage",
        "historical_valuation_unavailable",
    ),
    "unavailable": (
        "provider_not_configured",
        "unsupported_metric",
        "provider_exception",
        "empty_response",
        "future_available_date",
        "insufficient_coverage",
        "historical_valuation_unavailable",
    ),
    "invalid": (
        "invalid_schema",
        "missing_available_date",
        "non_finite_value",
    ),
}

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SYMBOL_PATTERN = re.compile(r"^\d{6}$")
_SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _date_only(value: object, field_name: str) -> str:
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None or value.time() != datetime.min.time():
            raise ValueError(f"{field_name} must be timezone-free and date-only")
        return value.date().isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is not None or value.time() != datetime.min.time():
            raise ValueError(f"{field_name} must be timezone-free and date-only")
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must use ISO YYYY-MM-DD")
    return date.fromisoformat(value).isoformat()


def _canonical_symbol(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("symbol must be text")
    if _SYMBOL_PATTERN.fullmatch(value) is None:
        raise ValueError("symbol must be a canonical six-digit A-share symbol")
    return value


def _metric(value: object) -> ValuationMetric:
    if isinstance(value, ValuationMetric):
        return value
    try:
        return ValuationMetric(str(value))
    except ValueError as exc:
        raise ValueError(f"unsupported valuation metric: {value}") from exc


def _source(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("source must be a machine identifier")
    candidate = value.strip()
    if not _SOURCE_PATTERN.fullmatch(candidate):
        raise ValueError("source must be a safe non-empty machine identifier")
    return candidate


def _unit(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("unit must be non-empty text")
    return value.strip()


def _revision(value: object) -> Optional[ValuationRevision]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("revision must be a stable string or integer")
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ValueError("revision cannot be empty")
        return candidate
    return value


def _sorted_metrics(values: Iterable[object]) -> Tuple[ValuationMetric, ...]:
    return tuple(sorted({_metric(value) for value in values}, key=lambda item: item.value))


@dataclass(frozen=True)
class ValuationRecord:
    """One historical metric value and the date it became knowable."""

    symbol: str
    metric: ValuationMetric
    observation_date: str
    available_date: str
    value: float
    source: str
    unit: str
    revision: Optional[ValuationRevision] = None

    def __post_init__(self) -> None:
        canonical_symbol = _canonical_symbol(self.symbol)
        metric = _metric(self.metric)
        observation_date = _date_only(self.observation_date, "observation_date")
        if self.available_date is None:
            raise ValueError("available_date is required")
        available_date = _date_only(self.available_date, "available_date")
        if available_date < observation_date:
            raise ValueError("available_date cannot be before observation_date")
        if isinstance(self.value, bool):
            raise ValueError("value must be a finite number")
        try:
            value = float(self.value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("value must be a finite number") from exc
        if not math.isfinite(value):
            raise ValueError("value must be a finite number")

        object.__setattr__(self, "symbol", canonical_symbol)
        object.__setattr__(self, "metric", metric)
        object.__setattr__(self, "observation_date", observation_date)
        object.__setattr__(self, "available_date", available_date)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "source", _source(self.source))
        object.__setattr__(self, "unit", _unit(self.unit))
        object.__setattr__(self, "revision", _revision(self.revision))

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "metric": self.metric.value,
            "observation_date": self.observation_date,
            "available_date": self.available_date,
            "value": self.value,
            "source": self.source,
            "unit": self.unit,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class ValuationAvailability:
    """Deterministic availability summary for requested valuation metrics."""

    status: str
    reason_code: str
    requested_metrics: Tuple[ValuationMetric, ...]
    available_metrics: Tuple[ValuationMetric, ...]
    missing_metrics: Tuple[ValuationMetric, ...]
    as_of_date: str
    source: str

    def __post_init__(self) -> None:
        if self.status not in VALUATION_AVAILABILITY_STATUSES:
            raise ValueError(f"unsupported valuation availability status: {self.status}")
        if self.reason_code not in VALUATION_REASON_CODES:
            raise ValueError(f"unsupported valuation reason code: {self.reason_code}")
        allowed_reasons = VALUATION_STATUS_REASON_CODES[self.status]
        if self.reason_code not in allowed_reasons:
            raise ValueError(
                f"reason code {self.reason_code} is invalid for valuation status {self.status}"
            )
        requested = _sorted_metrics(self.requested_metrics)
        available = _sorted_metrics(self.available_metrics)
        missing = _sorted_metrics(self.missing_metrics)
        if not requested:
            raise ValueError("requested_metrics cannot be empty")
        if set(available) - set(requested) or set(missing) - set(requested):
            raise ValueError("availability metrics must be subsets of requested_metrics")
        if set(available) & set(missing):
            raise ValueError("available_metrics and missing_metrics cannot overlap")
        if set(available) | set(missing) != set(requested):
            raise ValueError("availability metrics must partition requested_metrics")
        if self.status == "available" and (missing or set(available) != set(requested)):
            raise ValueError("available status requires all requested metrics and success")
        if self.status == "partial" and (not available or not missing):
            raise ValueError("partial status requires both available and missing metrics")
        if self.status in {"unavailable", "invalid"} and (
            available or set(missing) != set(requested)
        ):
            raise ValueError(f"{self.status} status requires every requested metric to be missing")

        object.__setattr__(self, "requested_metrics", requested)
        object.__setattr__(self, "available_metrics", available)
        object.__setattr__(self, "missing_metrics", missing)
        object.__setattr__(self, "as_of_date", _date_only(self.as_of_date, "as_of_date"))
        object.__setattr__(self, "source", _source(self.source))

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason_code": self.reason_code,
            "requested_metrics": [item.value for item in self.requested_metrics],
            "available_metrics": [item.value for item in self.available_metrics],
            "missing_metrics": [item.value for item in self.missing_metrics],
            "as_of_date": self.as_of_date,
            "source": self.source,
        }
