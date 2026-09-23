"""Provider-neutral expectations for per-dataset EOD observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, Sequence, Tuple, runtime_checkable

from .calendar import TradingCalendar, validate_trading_days
from .schemas import EODDatasetKey, EODDateRange


class DatasetObservationExpectationContractError(ValueError):
    """Raised when an observation expectation violates its pure contract."""


@runtime_checkable
class DatasetObservationExpectation(Protocol):
    """Decide which exchange sessions require rows for one exact dataset."""

    def expected_observation_dates(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        calendar: TradingCalendar,
    ) -> Sequence[date]: ...

    def identity_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True)
class StrictTradingDayObservationExpectation:
    """Legacy behavior: every exchange trading day requires one EOD row."""

    def expected_observation_dates(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        calendar: TradingCalendar,
    ) -> Tuple[date, ...]:
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        return validate_trading_days(calendar, requested_range)

    def identity_dict(self) -> dict[str, object]:
        return {
            "contract": "strict_trading_day_observation",
            "contract_version": 1,
        }


def validate_expected_observation_dates(
    expectation: DatasetObservationExpectation,
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
    calendar: TradingCalendar,
) -> Tuple[date, ...]:
    """Return a sorted subset of exchange sessions or fail closed."""

    if not isinstance(expectation, DatasetObservationExpectation):
        raise TypeError("expectation must implement DatasetObservationExpectation")
    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if type(requested_range) is not EODDateRange:
        raise TypeError("requested_range must be an exact EODDateRange")
    trading_dates = validate_trading_days(calendar, requested_range)
    returned = expectation.expected_observation_dates(dataset, requested_range, calendar)
    if type(returned) not in (list, tuple):
        raise DatasetObservationExpectationContractError(
            "expected_observation_dates must return an exact list or tuple"
        )
    normalized = tuple(returned)
    previous = None
    trading_set = frozenset(trading_dates)
    for value in normalized:
        if type(value) is not date or isinstance(value, datetime):
            raise DatasetObservationExpectationContractError(
                "expected observation dates must contain exact dates"
            )
        if value not in trading_set:
            raise DatasetObservationExpectationContractError(
                "expected observation dates must be exchange trading dates"
            )
        if previous is not None and value <= previous:
            raise DatasetObservationExpectationContractError(
                "expected observation dates must be strictly increasing"
            )
        previous = value
    return normalized


def is_observation_expected(
    expectation: DatasetObservationExpectation,
    dataset: EODDatasetKey,
    value: date,
    calendar: TradingCalendar,
) -> bool:
    """Classify one date without inferring absence from missing market data."""

    if type(value) is not date or isinstance(value, datetime):
        raise TypeError("value must be an exact date")
    requested_range = EODDateRange(value, value)
    return bool(
        validate_expected_observation_dates(
            expectation,
            dataset,
            requested_range,
            calendar,
        )
    )


def observation_expectation_identity(
    expectation: DatasetObservationExpectation,
) -> dict[str, object]:
    """Return a canonical, path-independent logical identity."""

    if not isinstance(expectation, DatasetObservationExpectation):
        raise TypeError("expectation must implement DatasetObservationExpectation")
    payload = expectation.identity_dict()
    if type(payload) is not dict:
        raise DatasetObservationExpectationContractError(
            "observation expectation identity must be an exact dict"
        )
    return payload


__all__ = [
    "DatasetObservationExpectation",
    "DatasetObservationExpectationContractError",
    "StrictTradingDayObservationExpectation",
    "is_observation_expected",
    "observation_expectation_identity",
    "validate_expected_observation_dates",
]
