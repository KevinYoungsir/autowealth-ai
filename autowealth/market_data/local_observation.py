"""Strict, versioned local evidence for legitimate missing EOD observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
import importlib
import json
import re
from typing import FrozenSet, Optional, Tuple

from autowealth.security import contains_absolute_path, contains_sensitive_value

from .calendar import TradingCalendar
from .schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)

EOD_OBSERVATION_SCHEMA_VERSION = 1
MAX_OBSERVATION_ABSENT_DATES = 366 * 100
MAX_OBSERVATION_FILE_BYTES = 8 * 1024 * 1024

Path = importlib.import_module("pathlib").Path

_ARTIFACT_FIELDS = frozenset(
    {"schema_version", "source", "version", "dataset", "confirmed_absent_dates"}
)
_DATASET_FIELDS = frozenset(
    {
        "market",
        "venue",
        "asset_type",
        "canonical_symbol",
        "frequency",
        "adjustment_type",
    }
)
_SOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")


class LocalObservationErrorCode(str, Enum):
    SOURCE_MISSING = "source_missing"
    SOURCE_UNREADABLE = "source_unreadable"
    INVALID_JSON = "invalid_json"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    INVALID_IDENTITY = "invalid_identity"
    DATASET_MISMATCH = "dataset_mismatch"
    MALFORMED_ABSENCE = "malformed_absence"
    DUPLICATE_ABSENCE = "duplicate_absence"
    UNORDERED_ABSENCES = "unordered_absences"
    NON_TRADING_ABSENCE = "non_trading_absence"


_ERROR_MESSAGES = {
    LocalObservationErrorCode.SOURCE_MISSING: "The local observation source is missing.",
    LocalObservationErrorCode.SOURCE_UNREADABLE: "The local observation source is unreadable.",
    LocalObservationErrorCode.INVALID_JSON: "The local observation source is not valid JSON.",
    LocalObservationErrorCode.UNSUPPORTED_SCHEMA: "The local observation schema is unsupported.",
    LocalObservationErrorCode.INVALID_IDENTITY: "The local observation identity is invalid.",
    LocalObservationErrorCode.DATASET_MISMATCH: "The local observation dataset is invalid.",
    LocalObservationErrorCode.MALFORMED_ABSENCE: "The local observation absence is malformed.",
    LocalObservationErrorCode.DUPLICATE_ABSENCE: "The local observation contains a duplicate absence.",
    LocalObservationErrorCode.UNORDERED_ABSENCES: "The local observation absences must be sorted.",
    LocalObservationErrorCode.NON_TRADING_ABSENCE: (
        "The local observation marks a non-trading date as absent."
    ),
}


class LocalObservationError(ValueError):
    """Safe error that never exposes the configured artifact path or payload."""

    def __init__(self, code: LocalObservationErrorCode) -> None:
        if type(code) is not LocalObservationErrorCode:
            raise TypeError("code must be an exact LocalObservationErrorCode")
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class LocalObservationIdentity:
    schema_version: int
    source: str
    version: str
    dataset: EODDatasetKey
    confirmed_absent_dates: Tuple[date, ...]

    def __post_init__(self) -> None:
        if self.schema_version != EOD_OBSERVATION_SCHEMA_VERSION:
            raise ValueError("schema_version is unsupported")
        if (
            type(self.source) is not str
            or _SOURCE_PATTERN.fullmatch(self.source) is None
            or type(self.version) is not str
            or _VERSION_PATTERN.fullmatch(self.version) is None
            or contains_absolute_path(self.source)
            or contains_absolute_path(self.version)
            or contains_sensitive_value(self.source)
            or contains_sensitive_value(self.version)
        ):
            raise ValueError("source and version must be safe stable identifiers")
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.confirmed_absent_dates) is not tuple:
            raise TypeError("confirmed_absent_dates must be an exact tuple")
        if tuple(sorted(set(self.confirmed_absent_dates))) != self.confirmed_absent_dates:
            raise ValueError("confirmed_absent_dates must be sorted and unique")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "version": self.version,
            "dataset": self.dataset.to_dict(),
            "confirmed_absent_dates": [value.isoformat() for value in self.confirmed_absent_dates],
        }


@dataclass(frozen=True)
class VersionedLocalObservationExpectation:
    """Immutable trusted absence evidence for one exact EOD dataset."""

    identity: LocalObservationIdentity
    _confirmed_absent_date_set: FrozenSet[date] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.identity) is not LocalObservationIdentity:
            raise TypeError("identity must be an exact LocalObservationIdentity")
        if type(self._confirmed_absent_date_set) is not frozenset:
            raise TypeError("absence membership must be a frozenset")
        if self._confirmed_absent_date_set != frozenset(self.identity.confirmed_absent_dates):
            raise ValueError("absence membership must match identity")

    @classmethod
    def from_file(
        cls,
        source_path: Path,
        calendar: TradingCalendar,
        *,
        expected_dataset: Optional[EODDatasetKey] = None,
    ) -> "VersionedLocalObservationExpectation":
        if not isinstance(source_path, Path):
            raise TypeError("source_path must be a pathlib Path")
        try:
            if not source_path.is_file():
                raise LocalObservationError(LocalObservationErrorCode.SOURCE_MISSING)
            raw_text = source_path.read_text(encoding="utf-8")
        except LocalObservationError:
            raise
        except OSError as exc:
            raise LocalObservationError(LocalObservationErrorCode.SOURCE_UNREADABLE) from exc
        except UnicodeError as exc:
            raise LocalObservationError(LocalObservationErrorCode.INVALID_JSON) from exc
        if len(raw_text.encode("utf-8")) > MAX_OBSERVATION_FILE_BYTES:
            raise LocalObservationError(LocalObservationErrorCode.MALFORMED_ABSENCE)
        try:
            payload = json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise LocalObservationError(LocalObservationErrorCode.INVALID_JSON) from exc
        return cls.from_dict(payload, calendar, expected_dataset=expected_dataset)

    @classmethod
    def from_dict(
        cls,
        payload: object,
        calendar: TradingCalendar,
        *,
        expected_dataset: Optional[EODDatasetKey] = None,
    ) -> "VersionedLocalObservationExpectation":
        if type(payload) is not dict or set(payload) != _ARTIFACT_FIELDS:
            raise LocalObservationError(LocalObservationErrorCode.UNSUPPORTED_SCHEMA)
        if payload["schema_version"] != EOD_OBSERVATION_SCHEMA_VERSION:
            raise LocalObservationError(LocalObservationErrorCode.UNSUPPORTED_SCHEMA)
        source = payload["source"]
        version = payload["version"]
        if (
            type(source) is not str
            or _SOURCE_PATTERN.fullmatch(source) is None
            or type(version) is not str
            or _VERSION_PATTERN.fullmatch(version) is None
            or contains_absolute_path(source)
            or contains_absolute_path(version)
            or contains_sensitive_value(source)
            or contains_sensitive_value(version)
        ):
            raise LocalObservationError(LocalObservationErrorCode.INVALID_IDENTITY)
        raw_dataset = payload["dataset"]
        try:
            if type(raw_dataset) is not dict or set(raw_dataset) != _DATASET_FIELDS:
                raise ValueError("invalid dataset fields")
            dataset = EODDatasetKey(
                market=Market(raw_dataset["market"]),
                venue=Venue(raw_dataset["venue"]),
                asset_type=AssetType(raw_dataset["asset_type"]),
                canonical_symbol=raw_dataset["canonical_symbol"],
                frequency=BarFrequency(raw_dataset["frequency"]),
                adjustment_type=AdjustmentType(raw_dataset["adjustment_type"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LocalObservationError(LocalObservationErrorCode.DATASET_MISMATCH) from exc
        if expected_dataset is not None and dataset != expected_dataset:
            raise LocalObservationError(LocalObservationErrorCode.DATASET_MISMATCH)

        raw_absences = payload["confirmed_absent_dates"]
        if type(raw_absences) is not list or len(raw_absences) > MAX_OBSERVATION_ABSENT_DATES:
            raise LocalObservationError(LocalObservationErrorCode.MALFORMED_ABSENCE)
        absences = []
        for raw_value in raw_absences:
            if type(raw_value) is not str:
                raise LocalObservationError(LocalObservationErrorCode.MALFORMED_ABSENCE)
            try:
                value = date.fromisoformat(raw_value)
            except ValueError as exc:
                raise LocalObservationError(LocalObservationErrorCode.MALFORMED_ABSENCE) from exc
            if value.isoformat() != raw_value:
                raise LocalObservationError(LocalObservationErrorCode.MALFORMED_ABSENCE)
            absences.append(value)
        normalized = tuple(absences)
        if len(set(normalized)) != len(normalized):
            raise LocalObservationError(LocalObservationErrorCode.DUPLICATE_ABSENCE)
        if tuple(sorted(normalized)) != normalized:
            raise LocalObservationError(LocalObservationErrorCode.UNORDERED_ABSENCES)
        for value in normalized:
            try:
                is_trading = calendar.is_trading_day(value)
            except Exception as exc:
                raise LocalObservationError(LocalObservationErrorCode.NON_TRADING_ABSENCE) from exc
            if is_trading is not True:
                raise LocalObservationError(LocalObservationErrorCode.NON_TRADING_ABSENCE)

        identity = LocalObservationIdentity(
            schema_version=EOD_OBSERVATION_SCHEMA_VERSION,
            source=source,
            version=version,
            dataset=dataset,
            confirmed_absent_dates=normalized,
        )
        return cls(identity, frozenset(normalized))

    def expected_observation_dates(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        calendar: TradingCalendar,
    ) -> Tuple[date, ...]:
        if dataset != self.identity.dataset:
            raise LocalObservationError(LocalObservationErrorCode.DATASET_MISMATCH)
        trading_dates = calendar.trading_days(
            requested_range.start_date,
            requested_range.end_date,
        )
        return tuple(
            value for value in trading_dates if value not in self._confirmed_absent_date_set
        )

    def identity_dict(self) -> dict[str, object]:
        return self.identity.to_dict()


__all__ = [
    "EOD_OBSERVATION_SCHEMA_VERSION",
    "LocalObservationError",
    "LocalObservationErrorCode",
    "LocalObservationIdentity",
    "VersionedLocalObservationExpectation",
]
