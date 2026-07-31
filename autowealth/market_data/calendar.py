from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, Sequence, Tuple, runtime_checkable

from .schemas import EODDateRange

MARKET_TIMEZONE = "Asia/Shanghai"


class TradingCalendarContractError(ValueError):
    """Raised when a calendar implementation violates the protocol contract."""


@runtime_checkable
class TradingCalendar(Protocol):
    def is_trading_day(self, value: date) -> bool: ...

    def next_trading_day(self, value: date) -> date: ...

    def previous_trading_day(self, value: date) -> date: ...

    def trading_days(self, start_date: date, end_date: date) -> Sequence[date]: ...


def validate_trading_days(
    calendar: TradingCalendar,
    requested_range: EODDateRange,
) -> Tuple[date, ...]:
    """Return a validated, ordered trading-day sequence for a closed range."""

    if not isinstance(requested_range, EODDateRange):
        raise TypeError("requested_range must be EODDateRange")

    returned_days = calendar.trading_days(
        requested_range.start_date,
        requested_range.end_date,
    )
    if type(returned_days) not in (list, tuple):
        raise TradingCalendarContractError("trading_days must return an exact list or exact tuple")

    normalized_days = tuple(returned_days)
    previous_day = None
    for value in normalized_days:
        if type(value) is not date or isinstance(value, datetime):
            raise TradingCalendarContractError("trading_days must contain exact date values")
        if not requested_range.contains(value):
            raise TradingCalendarContractError(
                "trading_days returned a date outside the requested range"
            )
        if previous_day is not None and value <= previous_day:
            raise TradingCalendarContractError(
                "trading_days must be strictly increasing without duplicates"
            )
        if calendar.is_trading_day(value) is not True:
            raise TradingCalendarContractError(
                "trading_days returned a date not recognized as a trading day"
            )
        previous_day = value

    return normalized_days
