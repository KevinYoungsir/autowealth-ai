"""Strict, side-effect-free conversion from provider DataFrames to EOD bars."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from .normalization import normalize_eod_bars
from .providers import EODProviderError, EODProviderErrorCode
from .schemas import EODBar, EODDatasetKey, EODDateRange

_COLUMN_ALIASES = (
    ("date", ("日期", "date")),
    ("open", ("开盘", "open")),
    ("high", ("最高", "high")),
    ("low", ("最低", "low")),
    ("close", ("收盘", "close")),
    ("volume", ("成交量", "volume")),
    ("amount", ("成交额", "amount")),
)
_REQUIRED_COLUMNS = frozenset({"date", "open", "high", "low", "close", "volume"})
_DASHED_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_COMPACT_DATE = re.compile(r"^[0-9]{8}$")
_DECIMAL_TEXT = re.compile(r"^[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?$")


def _malformed(message: str) -> EODProviderError:
    return EODProviderError(EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, message)


def _resolve_columns(frame: pd.DataFrame) -> dict[str, Optional[object]]:
    if frame.columns.has_duplicates:
        raise _malformed("The provider payload contains duplicate column labels.")

    resolved: dict[str, Optional[object]] = {}
    for canonical_name, aliases in _COLUMN_ALIASES:
        matches = tuple(alias for alias in aliases if alias in frame.columns)
        if len(matches) > 1:
            raise _malformed("The provider payload contains ambiguous column aliases.")
        if not matches:
            if canonical_name in _REQUIRED_COLUMNS:
                raise _malformed("The provider payload is missing a required EOD column.")
            resolved[canonical_name] = None
        else:
            resolved[canonical_name] = matches[0]
    return resolved


def _parse_trade_date(value: object, requested_range: EODDateRange) -> date:
    parsed: Optional[date] = None
    if type(value) is date:
        parsed = value
    elif type(value) is datetime:
        if value.tzinfo is None and not any(
            (value.hour, value.minute, value.second, value.microsecond)
        ):
            parsed = value.date()
    elif type(value) is pd.Timestamp:
        if (
            value is not pd.NaT
            and value.tzinfo is None
            and not any(
                (
                    value.hour,
                    value.minute,
                    value.second,
                    value.microsecond,
                    value.nanosecond,
                )
            )
        ):
            parsed = value.date()
    elif type(value) is str and value == value.strip():
        try:
            if _DASHED_DATE.fullmatch(value) is not None:
                parsed = date.fromisoformat(value)
            elif _COMPACT_DATE.fullmatch(value) is not None:
                parsed = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            parsed = None

    if parsed is None:
        raise _malformed("The provider payload contains an invalid EOD date value.")
    if not requested_range.contains(parsed):
        raise _malformed("The provider payload contains a date outside the requested range.")
    return parsed


def _parse_decimal(value: object) -> Decimal:
    if type(value) is Decimal:
        normalized = value
    elif type(value) in (int, float):
        normalized = _decimal_from_text(str(value))
    elif isinstance(value, np.bool_):
        raise _malformed("The provider payload contains an invalid EOD numeric value.")
    elif isinstance(value, (np.integer, np.floating)):
        normalized = _decimal_from_text(str(value))
    elif type(value) is str and value == value.strip() and value:
        normalized = _decimal_from_text(value)
    else:
        raise _malformed("The provider payload contains an invalid EOD numeric value.")

    if not normalized.is_finite():
        raise _malformed("The provider payload contains a non-finite EOD numeric value.")
    return normalized


def _decimal_from_text(value: str) -> Decimal:
    if _DECIMAL_TEXT.fullmatch(value) is None:
        raise _malformed("The provider payload contains an invalid EOD numeric value.")
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise _malformed("The provider payload contains an invalid EOD numeric value.") from exc


def convert_eod_dataframe_to_bars(
    frame: pd.DataFrame,
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
) -> Tuple[EODBar, ...]:
    """Convert one exact provider DataFrame into validated, sorted EOD bars."""

    if type(frame) is not pd.DataFrame:
        raise _malformed("The provider payload must be an exact pandas DataFrame.")
    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if type(requested_range) is not EODDateRange:
        raise TypeError("requested_range must be an exact EODDateRange")

    isolated = frame.copy(deep=True)
    if isolated.columns.has_duplicates:
        raise _malformed("The provider payload contains duplicate column labels.")
    if isolated.empty:
        return ()

    columns = _resolve_columns(isolated)
    bars = []
    seen_dates = set()
    for row_number in range(len(isolated.index)):
        row = isolated.iloc[row_number]
        trade_date = _parse_trade_date(row[columns["date"]], requested_range)
        if trade_date in seen_dates:
            raise _malformed("The provider payload contains duplicate trading dates.")
        seen_dates.add(trade_date)

        amount_column = columns["amount"]
        amount = None if amount_column is None else _parse_decimal(row[amount_column])
        try:
            bar = EODBar(
                dataset=dataset,
                trade_date=trade_date,
                open=_parse_decimal(row[columns["open"]]),
                high=_parse_decimal(row[columns["high"]]),
                low=_parse_decimal(row[columns["low"]]),
                close=_parse_decimal(row[columns["close"]]),
                volume=_parse_decimal(row[columns["volume"]]),
                amount=amount,
            )
        except EODProviderError:
            raise
        except (TypeError, ValueError, InvalidOperation, OverflowError) as exc:
            raise _malformed("The provider payload contains an invalid EOD bar.") from exc
        bars.append(bar)

    return normalize_eod_bars(bars)


__all__ = ["convert_eod_dataframe_to_bars"]
