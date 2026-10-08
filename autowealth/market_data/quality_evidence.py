"""Deterministic, provider-neutral EOD quality evidence.

This module only evaluates evidence supplied by its caller.  It never fetches
data, reads credentials, consults a clock, or performs persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
import math
import re
from typing import Iterable, Optional, Sequence, Tuple

from .calendar import TradingCalendar
from .capability_registry import (
    DEFAULT_EOD_CAPABILITY_REGISTRY,
    EODCapabilityRegistry,
    EODCapabilityRegistryError,
)
from .observation import DatasetObservationExpectation, validate_expected_observation_dates
from .schemas import EODDatasetKey, EODDateRange

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"

_QUALITY_STATES = frozenset({PASS, PARTIAL, FAIL})
_FRESHNESS_STATES = frozenset({"fresh", "stale", "unknown"})
_UNIT_STATES = frozenset({"verified", "unverified", "mismatch", "unknown"})
_OBSERVATION_STATES = frozenset({"valid", "invalid", "unknown"})
_CAPABILITY_STATES = frozenset({"compatible", "incompatible", "unknown"})
_PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(?:SH|SZ)$")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _date(value: object, field_name: str) -> date:
    if type(value) is not date or isinstance(value, datetime):
        raise TypeError(f"{field_name} must be an exact date")
    return value


def _dates(values: Iterable[date], field_name: str) -> Tuple[date, ...]:
    if type(values) not in (list, tuple, set, frozenset):
        raise TypeError(f"{field_name} must be a date sequence")
    normalized = tuple(sorted(values))
    if any(type(value) is not date or isinstance(value, datetime) for value in normalized):
        raise TypeError(f"{field_name} must contain exact dates")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} must be unique")
    return normalized


def _non_negative_count(value: object, field_name: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _status(value: object, allowed: frozenset[str], field_name: str) -> str:
    if type(value) is not str or value not in allowed:
        raise ValueError(f"{field_name} is unsupported")
    return value


def _source_fingerprint(value: object) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("source_fingerprint must be a lowercase SHA-256 identity")
    return value


def _dataset_from_text(value: object, symbol: str) -> EODDatasetKey:
    """Accept only the existing dataset contract's canonical JSON, not free text."""
    if type(value) is not str:
        raise ValueError("dataset_id must be canonical dataset JSON")
    try:
        payload = json.loads(value)
        if type(payload) is not dict:
            raise ValueError("dataset_id must be canonical dataset JSON")
        dataset = EODDatasetKey(**payload)
    except (TypeError, ValueError) as exc:
        raise ValueError("dataset_id must be canonical dataset JSON") from exc
    if value != dataset.to_json() or dataset.canonical_symbol != symbol:
        raise ValueError("dataset_id must be canonical and match symbol")
    return dataset


def _quality_state(missing, extra, freshness, unit, observation, capability) -> str:
    return (
        PASS
        if missing == 0
        and extra == 0
        and freshness == "fresh"
        and unit == "verified"
        and observation == "valid"
        and capability == "compatible"
        else FAIL
    )


@dataclass(frozen=True)
class DataQualityEvidence:
    """Immutable quality evidence with no runtime-dependent fields."""

    schema_version: int
    provider_id: str
    dataset_id: str
    symbol: str
    observation_start: date
    observation_end: date
    expected_observations: int
    observed_observations: int
    missing_observations: int
    extra_observations: int
    coverage_ratio: float
    freshness_status: str
    unit_status: str
    observation_status: str
    capability_status: str
    quality_state: str
    source_fingerprint: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("schema_version must be 1")
        if (
            type(self.provider_id) is not str
            or _PROVIDER_PATTERN.fullmatch(self.provider_id) is None
        ):
            raise ValueError("provider_id must be a stable lowercase identifier")
        if type(self.dataset_id) is not str or not self.dataset_id:
            raise ValueError("dataset_id must be non-empty text")
        if type(self.symbol) is not str or _SYMBOL_PATTERN.fullmatch(self.symbol) is None:
            raise ValueError("symbol must be a canonical A-share identifier")
        dataset = _dataset_from_text(self.dataset_id, self.symbol)
        start = _date(self.observation_start, "observation_start")
        end = _date(self.observation_end, "observation_end")
        if start > end:
            raise ValueError("observation_start cannot be after observation_end")
        object.__setattr__(self, "observation_start", start)
        object.__setattr__(self, "observation_end", end)
        for name in (
            "expected_observations",
            "observed_observations",
            "missing_observations",
            "extra_observations",
        ):
            object.__setattr__(self, name, _non_negative_count(getattr(self, name), name))
        if (
            type(self.coverage_ratio) not in (int, float)
            or isinstance(self.coverage_ratio, bool)
            or not math.isfinite(float(self.coverage_ratio))
        ):
            raise TypeError("coverage_ratio must be a finite number")
        ratio = float(self.coverage_ratio)
        if ratio < 0.0 or ratio > 1.0:
            raise ValueError("coverage_ratio must be between 0 and 1")
        object.__setattr__(self, "coverage_ratio", ratio)
        object.__setattr__(
            self,
            "freshness_status",
            _status(self.freshness_status, _FRESHNESS_STATES, "freshness_status"),
        )
        object.__setattr__(
            self, "unit_status", _status(self.unit_status, _UNIT_STATES, "unit_status")
        )
        object.__setattr__(
            self,
            "observation_status",
            _status(self.observation_status, _OBSERVATION_STATES, "observation_status"),
        )
        object.__setattr__(
            self,
            "capability_status",
            _status(self.capability_status, _CAPABILITY_STATES, "capability_status"),
        )
        object.__setattr__(
            self, "quality_state", _status(self.quality_state, _QUALITY_STATES, "quality_state")
        )
        object.__setattr__(self, "source_fingerprint", _source_fingerprint(self.source_fingerprint))
        if (
            self.missing_observations > self.expected_observations
            or self.extra_observations > self.observed_observations
            or self.expected_observations - self.missing_observations
            != self.observed_observations - self.extra_observations
        ):
            raise ValueError("observation counts must describe consistent sets")
        expected_ratio = (
            (self.expected_observations - self.missing_observations) / self.expected_observations
            if self.expected_observations
            else 1.0
        )
        if ratio != expected_ratio:
            raise ValueError("coverage_ratio must match observation counts")
        # Registry truth may never be upgraded by a directly constructed value.
        try:
            declaration = DEFAULT_EOD_CAPABILITY_REGISTRY.lookup(self.provider_id)
        except EODCapabilityRegistryError:
            declaration = None
        if self.capability_status == "compatible" and (
            declaration is None or not declaration.supports(dataset)
        ):
            raise ValueError("compatible evidence must match registry capability")
        if self.unit_status == "verified" and (
            declaration is None or declaration.unit_verification != "verified"
        ):
            raise ValueError("verified evidence must match registry units")
        state = _quality_state(
            self.missing_observations,
            self.extra_observations,
            self.freshness_status,
            self.unit_status,
            self.observation_status,
            self.capability_status,
        )
        if self.quality_state != state:
            raise ValueError("quality_state must match evidence dimensions")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider_id": self.provider_id,
            "dataset_id": self.dataset_id,
            "symbol": self.symbol,
            "observation_start": self.observation_start.isoformat(),
            "observation_end": self.observation_end.isoformat(),
            "expected_observations": self.expected_observations,
            "observed_observations": self.observed_observations,
            "missing_observations": self.missing_observations,
            "extra_observations": self.extra_observations,
            "coverage_ratio": self.coverage_ratio,
            "freshness_status": self.freshness_status,
            "unit_status": self.unit_status,
            "observation_status": self.observation_status,
            "capability_status": self.capability_status,
            "quality_state": self.quality_state,
            "source_fingerprint": self.source_fingerprint,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def identity(self) -> str:
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @property
    def content_hash(self) -> str:
        return self.identity

    def __hash__(self) -> int:
        return int(self.identity[7:23], 16)


def generate_quality_evidence(
    *,
    provider_id: str,
    dataset_id: EODDatasetKey,
    symbol: str,
    observation_start: date,
    observation_end: date,
    expected_observations: Sequence[date],
    observed_observations: Sequence[date],
    source_fingerprint: str,
    observation_calendar: TradingCalendar,
    observation_expectation: DatasetObservationExpectation,
    freshness_status: str = "unknown",
    unit_status: Optional[str] = None,
    observation_status: str = "valid",
    capability_status: Optional[str] = None,
    capability_registry: EODCapabilityRegistry = DEFAULT_EOD_CAPABILITY_REGISTRY,
) -> DataQualityEvidence:
    """Build evidence from explicit observations and the existing contracts."""

    start = _date(observation_start, "observation_start")
    end = _date(observation_end, "observation_end")
    provider = provider_id
    if type(provider) is not str or _PROVIDER_PATTERN.fullmatch(provider) is None:
        raise TypeError("provider_id must be a stable lowercase identifier")
    if type(dataset_id) is not EODDatasetKey:
        raise TypeError("dataset_id must be an exact EODDatasetKey")
    if type(symbol) is not str or symbol != dataset_id.canonical_symbol:
        raise ValueError("symbol must match dataset_id")
    if not isinstance(observation_calendar, TradingCalendar):
        raise TypeError("observation_calendar must implement TradingCalendar")
    if not isinstance(observation_expectation, DatasetObservationExpectation):
        raise TypeError("observation_expectation must implement DatasetObservationExpectation")
    _source_fingerprint(source_fingerprint)
    expected = _dates(expected_observations, "expected_observations")
    observed = _dates(observed_observations, "observed_observations")
    contract_expected = validate_expected_observation_dates(
        observation_expectation,
        dataset_id,
        EODDateRange(start, end),
        observation_calendar,
    )
    if expected != contract_expected:
        raise ValueError("expected_observations must match the observation expectation contract")
    expected_set = frozenset(expected)
    observed_set = frozenset(observed)
    missing = tuple(sorted(expected_set - observed_set))
    extra = tuple(sorted(observed_set - expected_set))

    if any(value < start or value > end for value in observed):
        raise ValueError("observation dates must be inside the evidence range")

    _status(freshness_status, _FRESHNESS_STATES, "freshness_status")
    _status(observation_status, _OBSERVATION_STATES, "observation_status")

    if type(capability_registry) is not EODCapabilityRegistry:
        raise TypeError("capability_registry must be an exact EODCapabilityRegistry")
    try:
        declaration = capability_registry.lookup(provider)
    except EODCapabilityRegistryError:
        declaration = None
        capability = "incompatible"
    else:
        capability = "compatible" if declaration.supports(dataset_id) else "incompatible"
    if capability_status is not None:
        supplied = _status(capability_status, _CAPABILITY_STATES, "capability_status")
        if capability == "compatible":
            capability = supplied
    if unit_status is None:
        unit = declaration.unit_verification if declaration is not None else "unknown"
    else:
        unit = _status(unit_status, _UNIT_STATES, "unit_status")
        if declaration is None and unit == "verified":
            unit = "unknown"
        elif (
            declaration is not None
            and declaration.unit_verification != "verified"
            and unit == "verified"
        ):
            unit = "unverified"
    state = _quality_state(
        len(missing), len(extra), freshness_status, unit, observation_status, capability
    )
    ratio = 1.0 if not expected else len(observed_set.intersection(expected_set)) / len(expected)
    return DataQualityEvidence(
        schema_version=1,
        provider_id=provider,
        dataset_id=dataset_id.to_json(),
        symbol=symbol,
        observation_start=start,
        observation_end=end,
        expected_observations=len(expected),
        observed_observations=len(observed),
        missing_observations=len(missing),
        extra_observations=len(extra),
        coverage_ratio=ratio,
        freshness_status=freshness_status,
        unit_status=unit,
        observation_status=observation_status,
        capability_status=capability,
        quality_state=state,
        source_fingerprint=source_fingerprint,
    )


build_quality_evidence = generate_quality_evidence

__all__ = [
    "FAIL",
    "PARTIAL",
    "PASS",
    "DataQualityEvidence",
    "build_quality_evidence",
    "generate_quality_evidence",
]
