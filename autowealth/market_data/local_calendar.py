"""Validated, versioned local trading calendar for production composition."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
import importlib
import json
import re
from typing import FrozenSet, Tuple

from .calendar import MARKET_TIMEZONE

EOD_CALENDAR_SCHEMA_VERSION = 1
MAX_CALENDAR_DAYS = 366 * 100
MAX_CALENDAR_FILE_BYTES = 8 * 1024 * 1024

Path = importlib.import_module("pathlib").Path

_ARTIFACT_FIELDS = frozenset(
    {
        "schema_version",
        "calendar_id",
        "calendar_version",
        "timezone",
        "coverage_start",
        "coverage_end",
        "days",
    }
)
_DAY_FIELDS = frozenset({"trade_date", "is_trading_day"})
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")


class LocalTradingCalendarErrorCode(str, Enum):
    """Stable failure codes for local calendar loading and lookup."""

    SOURCE_MISSING = "source_missing"
    SOURCE_UNREADABLE = "source_unreadable"
    INVALID_JSON = "invalid_json"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    INVALID_IDENTITY = "invalid_identity"
    INVALID_TIMEZONE = "invalid_timezone"
    INVALID_COVERAGE = "invalid_coverage"
    EMPTY_CALENDAR = "empty_calendar"
    MALFORMED_DAY = "malformed_day"
    DUPLICATE_DATE = "duplicate_date"
    UNORDERED_DATES = "unordered_dates"
    INCOMPLETE_COVERAGE = "incomplete_coverage"
    OUTSIDE_COVERAGE = "outside_coverage"


_ERROR_MESSAGES = {
    LocalTradingCalendarErrorCode.SOURCE_MISSING: "The local trading calendar source is missing.",
    LocalTradingCalendarErrorCode.SOURCE_UNREADABLE: (
        "The local trading calendar source is unreadable."
    ),
    LocalTradingCalendarErrorCode.INVALID_JSON: (
        "The local trading calendar source is not valid JSON."
    ),
    LocalTradingCalendarErrorCode.UNSUPPORTED_SCHEMA: (
        "The local trading calendar schema is unsupported."
    ),
    LocalTradingCalendarErrorCode.INVALID_IDENTITY: (
        "The local trading calendar identity or version is invalid."
    ),
    LocalTradingCalendarErrorCode.INVALID_TIMEZONE: (
        "The local trading calendar timezone is unsupported."
    ),
    LocalTradingCalendarErrorCode.INVALID_COVERAGE: (
        "The local trading calendar coverage is invalid."
    ),
    LocalTradingCalendarErrorCode.EMPTY_CALENDAR: ("The local trading calendar cannot be empty."),
    LocalTradingCalendarErrorCode.MALFORMED_DAY: (
        "The local trading calendar contains a malformed day."
    ),
    LocalTradingCalendarErrorCode.DUPLICATE_DATE: (
        "The local trading calendar contains a duplicate date."
    ),
    LocalTradingCalendarErrorCode.UNORDERED_DATES: (
        "The local trading calendar dates must be strictly increasing."
    ),
    LocalTradingCalendarErrorCode.INCOMPLETE_COVERAGE: (
        "The local trading calendar must explicitly cover every calendar date."
    ),
    LocalTradingCalendarErrorCode.OUTSIDE_COVERAGE: (
        "The requested date is outside the local trading calendar coverage."
    ),
}


class LocalTradingCalendarError(ValueError):
    """Safe calendar error that never includes the configured source path."""

    def __init__(self, code: LocalTradingCalendarErrorCode) -> None:
        if not isinstance(code, LocalTradingCalendarErrorCode):
            raise TypeError("code must be LocalTradingCalendarErrorCode")
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class LocalTradingCalendarIdentity:
    """Public identity of one validated local calendar artifact."""

    schema_version: int
    calendar_id: str
    calendar_version: str
    timezone: str
    coverage_start: date
    coverage_end: date

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or (
            self.schema_version != EOD_CALENDAR_SCHEMA_VERSION
        ):
            raise ValueError("schema_version is unsupported")
        if (
            type(self.calendar_id) is not str
            or _IDENTIFIER_PATTERN.fullmatch(self.calendar_id) is None
            or type(self.calendar_version) is not str
            or _VERSION_PATTERN.fullmatch(self.calendar_version) is None
        ):
            raise ValueError("calendar identity must use stable identifiers")
        if self.timezone != MARKET_TIMEZONE:
            raise ValueError("timezone is unsupported")
        if type(self.coverage_start) is not date or type(self.coverage_end) is not date:
            raise ValueError("coverage values must be exact dates")
        if self.coverage_start > self.coverage_end:
            raise ValueError("coverage_start cannot be after coverage_end")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "calendar_id": self.calendar_id,
            "calendar_version": self.calendar_version,
            "timezone": self.timezone,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
        }


@dataclass(frozen=True)
class VersionedLocalTradingCalendar:
    """Immutable A-share session calendar loaded from a validated JSON artifact."""

    identity: LocalTradingCalendarIdentity
    _calendar_dates: Tuple[date, ...] = field(repr=False)
    _trading_dates: Tuple[date, ...] = field(repr=False)
    _trading_date_set: FrozenSet[date] = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.identity) is not LocalTradingCalendarIdentity:
            raise TypeError("identity must be LocalTradingCalendarIdentity")
        if type(self._calendar_dates) is not tuple or type(self._trading_dates) is not tuple:
            raise TypeError("calendar dates must be exact tuples")
        if type(self._trading_date_set) is not frozenset:
            raise TypeError("trading date membership must be a frozenset")
        if not self._calendar_dates or not self._trading_dates:
            raise ValueError("calendar and trading dates cannot be empty")
        if self._calendar_dates != _date_sequence(
            self.identity.coverage_start,
            self.identity.coverage_end,
        ):
            raise ValueError("calendar dates must match the declared coverage")
        if tuple(sorted(self._trading_date_set)) != self._trading_dates:
            raise ValueError("trading dates must be unique and strictly increasing")
        if not self._trading_date_set.issubset(frozenset(self._calendar_dates)):
            raise ValueError("trading dates must be inside calendar coverage")

    @classmethod
    def from_file(cls, source_path: Path) -> "VersionedLocalTradingCalendar":
        """Load one local artifact without network access or source mutation."""

        if not isinstance(source_path, Path):
            raise TypeError("source_path must be a pathlib Path")
        try:
            if not source_path.is_file():
                raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.SOURCE_MISSING)
            raw_text = source_path.read_text(encoding="utf-8")
        except LocalTradingCalendarError:
            raise
        except OSError as exc:
            error = LocalTradingCalendarError(LocalTradingCalendarErrorCode.SOURCE_UNREADABLE)
            raise error from exc
        except UnicodeError as exc:
            error = LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_JSON)
            raise error from exc

        if len(raw_text.encode("utf-8")) > MAX_CALENDAR_FILE_BYTES:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_COVERAGE)

        try:
            payload = json.loads(raw_text)
        except (json.JSONDecodeError, UnicodeError) as exc:
            error = LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_JSON)
            raise error from exc
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: object) -> "VersionedLocalTradingCalendar":
        """Validate and normalize one exact calendar artifact mapping."""

        if type(payload) is not dict or set(payload) != _ARTIFACT_FIELDS:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.UNSUPPORTED_SCHEMA)
        schema_version = payload["schema_version"]
        if type(schema_version) is not int or schema_version != EOD_CALENDAR_SCHEMA_VERSION:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.UNSUPPORTED_SCHEMA)

        calendar_id = payload["calendar_id"]
        calendar_version = payload["calendar_version"]
        if (
            type(calendar_id) is not str
            or _IDENTIFIER_PATTERN.fullmatch(calendar_id) is None
            or type(calendar_version) is not str
            or _VERSION_PATTERN.fullmatch(calendar_version) is None
        ):
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_IDENTITY)
        timezone = payload["timezone"]
        if timezone != MARKET_TIMEZONE:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_TIMEZONE)

        coverage_start = _parse_iso_date(
            payload["coverage_start"],
            LocalTradingCalendarErrorCode.INVALID_COVERAGE,
        )
        coverage_end = _parse_iso_date(
            payload["coverage_end"],
            LocalTradingCalendarErrorCode.INVALID_COVERAGE,
        )
        if coverage_start > coverage_end:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_COVERAGE)
        coverage_days = (coverage_end - coverage_start).days + 1
        if coverage_days > MAX_CALENDAR_DAYS:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INVALID_COVERAGE)

        raw_days = payload["days"]
        if type(raw_days) is not list:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.MALFORMED_DAY)
        if not raw_days:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.EMPTY_CALENDAR)
        if len(raw_days) != coverage_days:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INCOMPLETE_COVERAGE)

        calendar_dates = []
        trading_dates = []
        seen_dates = set()
        previous_date = None
        for raw_day in raw_days:
            if type(raw_day) is not dict or set(raw_day) != _DAY_FIELDS:
                raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.MALFORMED_DAY)
            trade_date = _parse_iso_date(
                raw_day["trade_date"],
                LocalTradingCalendarErrorCode.MALFORMED_DAY,
            )
            is_trading_day = raw_day["is_trading_day"]
            if type(is_trading_day) is not bool:
                raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.MALFORMED_DAY)
            if trade_date in seen_dates:
                raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.DUPLICATE_DATE)
            if previous_date is not None:
                if trade_date < previous_date:
                    raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.UNORDERED_DATES)
            calendar_dates.append(trade_date)
            seen_dates.add(trade_date)
            if is_trading_day:
                trading_dates.append(trade_date)
            previous_date = trade_date

        normalized_calendar_dates = tuple(calendar_dates)
        expected_dates = _date_sequence(coverage_start, coverage_end)
        if normalized_calendar_dates != expected_dates:
            if len(set(normalized_calendar_dates)) != len(normalized_calendar_dates):
                raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.DUPLICATE_DATE)
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.INCOMPLETE_COVERAGE)
        if not trading_dates:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.EMPTY_CALENDAR)

        identity = LocalTradingCalendarIdentity(
            schema_version=schema_version,
            calendar_id=calendar_id,
            calendar_version=calendar_version,
            timezone=timezone,
            coverage_start=coverage_start,
            coverage_end=coverage_end,
        )
        normalized_trading_dates = tuple(trading_dates)
        return cls(
            identity=identity,
            _calendar_dates=normalized_calendar_dates,
            _trading_dates=normalized_trading_dates,
            _trading_date_set=frozenset(normalized_trading_dates),
        )

    def is_trading_day(self, value: date) -> bool:
        candidate = _require_date(value)
        self._require_covered(candidate)
        return candidate in self._trading_date_set

    def next_trading_day(self, value: date) -> date:
        candidate = _require_date(value)
        self._require_covered(candidate)
        position = bisect_right(self._trading_dates, candidate)
        if position >= len(self._trading_dates):
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.OUTSIDE_COVERAGE)
        return self._trading_dates[position]

    def previous_trading_day(self, value: date) -> date:
        candidate = _require_date(value)
        self._require_covered(candidate)
        position = bisect_left(self._trading_dates, candidate) - 1
        if position < 0:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.OUTSIDE_COVERAGE)
        return self._trading_dates[position]

    def trading_days(self, start_date: date, end_date: date) -> Tuple[date, ...]:
        start = _require_date(start_date)
        end = _require_date(end_date)
        if start > end:
            raise ValueError("start_date cannot be after end_date")
        self._require_covered(start)
        self._require_covered(end)
        left = bisect_left(self._trading_dates, start)
        right = bisect_right(self._trading_dates, end)
        return self._trading_dates[left:right]

    def _require_covered(self, value: date) -> None:
        if not self.identity.coverage_start <= value <= self.identity.coverage_end:
            raise LocalTradingCalendarError(LocalTradingCalendarErrorCode.OUTSIDE_COVERAGE)


def _parse_iso_date(value: object, error_code: LocalTradingCalendarErrorCode) -> date:
    if type(value) is not str:
        raise LocalTradingCalendarError(error_code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        error = LocalTradingCalendarError(error_code)
        raise error from exc
    if parsed.isoformat() != value:
        raise LocalTradingCalendarError(error_code)
    return parsed


def _require_date(value: object) -> date:
    if type(value) is not date or isinstance(value, datetime):
        raise TypeError("calendar values must be exact date values")
    return value


def _date_sequence(start_date: date, end_date: date) -> Tuple[date, ...]:
    days = (end_date - start_date).days + 1
    return tuple(start_date + timedelta(days=offset) for offset in range(days))
