from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from typing import Dict, Optional, Sequence, Tuple

from .calendar import (
    TradingCalendar,
    TradingCalendarContractError,
    validate_trading_days,
)
from .schemas import (
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODWarningSeverity,
)

EODBarIdentity = Tuple[str, str, str, str, str, str, str]


def eod_bar_identity(bar: EODBar) -> EODBarIdentity:
    """Return the stable dataset and trading-date identity of one EOD bar."""

    if type(bar) is not EODBar:
        raise TypeError("bar must be an exact EODBar")
    return (*bar.dataset.identity, bar.trade_date.isoformat())


def _non_negative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class EODValidationReport:
    """Deterministic result of validating one homogeneous EOD batch."""

    is_valid: bool
    errors: Tuple[EODStructuredWarning, ...]
    warnings: Tuple[EODStructuredWarning, ...]
    received_row_count: int
    unique_identity_count: int
    duplicate_identical_count: int
    duplicate_conflicting_count: int
    missing_trading_dates: Tuple[date, ...]

    def __post_init__(self) -> None:
        if type(self.is_valid) is not bool:
            raise ValueError("is_valid must be a strict boolean")
        for field_name in ("errors", "warnings"):
            values = getattr(self, field_name)
            if type(values) not in (list, tuple):
                raise TypeError(f"{field_name} must be an exact list or exact tuple")
            normalized = tuple(values)
            if any(type(item) is not EODStructuredWarning for item in normalized):
                raise TypeError(f"{field_name} must contain EODStructuredWarning values")
            object.__setattr__(self, field_name, normalized)
        for field_name in (
            "received_row_count",
            "unique_identity_count",
            "duplicate_identical_count",
            "duplicate_conflicting_count",
        ):
            object.__setattr__(
                self,
                field_name,
                _non_negative_integer(getattr(self, field_name), field_name),
            )
        if type(self.missing_trading_dates) not in (list, tuple):
            raise TypeError("missing_trading_dates must be an exact list or exact tuple")
        missing_dates = tuple(self.missing_trading_dates)
        if any(type(value) is not date for value in missing_dates):
            raise TypeError("missing_trading_dates must contain exact date values")
        if tuple(sorted(set(missing_dates))) != missing_dates:
            raise ValueError("missing_trading_dates must be sorted and unique")
        object.__setattr__(self, "missing_trading_dates", missing_dates)

    def to_dict(self) -> dict[str, object]:
        return {
            "is_valid": self.is_valid,
            "errors": [issue.to_dict() for issue in self.errors],
            "warnings": [issue.to_dict() for issue in self.warnings],
            "received_row_count": self.received_row_count,
            "unique_identity_count": self.unique_identity_count,
            "duplicate_identical_count": self.duplicate_identical_count,
            "duplicate_conflicting_count": self.duplicate_conflicting_count,
            "missing_trading_dates": [value.isoformat() for value in self.missing_trading_dates],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def _issue(
    code: str,
    severity: EODWarningSeverity,
    message: str,
    details: Optional[dict[str, object]] = None,
) -> EODStructuredWarning:
    return EODStructuredWarning(
        code=code,
        severity=severity,
        message=message,
        details={} if details is None else details,
    )


def _numeric_issue_fields(bar: EODBar) -> Tuple[str, ...]:
    invalid_fields = []
    for field_name in ("open", "high", "low", "close", "volume"):
        value = getattr(bar, field_name, None)
        if type(value) is not Decimal or not value.is_finite():
            invalid_fields.append(field_name)
    amount = getattr(bar, "amount", None)
    if amount is not None and (type(amount) is not Decimal or not amount.is_finite()):
        invalid_fields.append("amount")
    return tuple(invalid_fields)


def _has_invalid_ohlc(bar: EODBar) -> bool:
    prices = (bar.open, bar.high, bar.low, bar.close)
    if any(value <= 0 for value in prices):
        return True
    if bar.volume < 0 or (bar.amount is not None and bar.amount < 0):
        return True
    return bar.high < max(bar.open, bar.low, bar.close) or bar.low > min(
        bar.open,
        bar.high,
        bar.close,
    )


def validate_eod_batch(
    dataset: EODDatasetKey,
    bars: Sequence[EODBar],
    calendar: TradingCalendar,
    expected_range: Optional[EODDateRange] = None,
) -> EODValidationReport:
    """Validate EOD rows without mutating, deduplicating, logging, or performing I/O."""

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if type(bars) not in (list, tuple):
        raise TypeError("bars must be an exact list or exact tuple")
    if expected_range is not None and type(expected_range) is not EODDateRange:
        raise TypeError("expected_range must be EODDateRange or None")

    batch = tuple(bars)
    errors = []
    warnings = []
    seen: Dict[EODBarIdentity, EODBar] = {}
    observed_dates = set()
    previous_date = None
    identical_count = 0
    conflicting_count = 0
    input_not_sorted = False

    if not batch:
        errors.append(
            _issue(
                "empty_batch",
                EODWarningSeverity.ERROR,
                "The EOD batch is empty.",
            )
        )

    for index, bar in enumerate(batch):
        if type(bar) is not EODBar:
            errors.append(
                _issue(
                    "invalid_numeric_value",
                    EODWarningSeverity.ERROR,
                    "The EOD batch contains a value that is not an EODBar.",
                    {"row_index": index},
                )
            )
            continue

        trade_date = getattr(bar, "trade_date", None)
        if type(trade_date) is not date:
            errors.append(
                _issue(
                    "invalid_trade_date",
                    EODWarningSeverity.ERROR,
                    "An EOD bar contains an invalid trading date.",
                    {"row_index": index},
                )
            )
            continue

        if previous_date is not None and trade_date < previous_date:
            input_not_sorted = True
        previous_date = trade_date

        bar_dataset = getattr(bar, "dataset", None)
        if type(bar_dataset) is not EODDatasetKey or bar_dataset != dataset:
            errors.append(
                _issue(
                    "dataset_mismatch",
                    EODWarningSeverity.ERROR,
                    "An EOD bar does not match the batch dataset.",
                    {
                        "row_index": index,
                        "trade_date": trade_date.isoformat(),
                    },
                )
            )
        else:
            observed_dates.add(trade_date)

        if expected_range is not None and not expected_range.contains(trade_date):
            errors.append(
                _issue(
                    "date_out_of_range",
                    EODWarningSeverity.ERROR,
                    "An EOD bar falls outside the expected closed date range.",
                    {
                        "row_index": index,
                        "trade_date": trade_date.isoformat(),
                    },
                )
            )

        try:
            trading_day_status = calendar.is_trading_day(trade_date)
        except Exception:
            errors.append(
                _issue(
                    "invalid_calendar",
                    EODWarningSeverity.ERROR,
                    "The trading calendar could not classify an EOD date.",
                    {
                        "row_index": index,
                        "trade_date": trade_date.isoformat(),
                    },
                )
            )
        else:
            if type(trading_day_status) is not bool:
                errors.append(
                    _issue(
                        "invalid_calendar",
                        EODWarningSeverity.ERROR,
                        "The trading calendar returned a non-boolean classification.",
                        {
                            "row_index": index,
                            "trade_date": trade_date.isoformat(),
                        },
                    )
                )
            elif not trading_day_status:
                errors.append(
                    _issue(
                        "non_trading_date",
                        EODWarningSeverity.ERROR,
                        "An EOD bar is dated on a non-trading day.",
                        {
                            "row_index": index,
                            "trade_date": trade_date.isoformat(),
                        },
                    )
                )

        invalid_numeric_fields = _numeric_issue_fields(bar)
        if invalid_numeric_fields:
            errors.append(
                _issue(
                    "invalid_numeric_value",
                    EODWarningSeverity.ERROR,
                    "An EOD bar contains a non-finite or unsupported numeric value.",
                    {
                        "row_index": index,
                        "fields": list(invalid_numeric_fields),
                    },
                )
            )
        elif _has_invalid_ohlc(bar):
            errors.append(
                _issue(
                    "invalid_ohlc",
                    EODWarningSeverity.ERROR,
                    "An EOD bar violates price or non-negative volume constraints.",
                    {"row_index": index, "trade_date": trade_date.isoformat()},
                )
            )

        identity = eod_bar_identity(bar)
        first_bar = seen.get(identity)
        if first_bar is None:
            seen[identity] = bar
        elif bar == first_bar:
            identical_count += 1
            warnings.append(
                _issue(
                    "duplicate_identical_bar",
                    EODWarningSeverity.WARNING,
                    "An identical EOD bar appears more than once.",
                    {"row_index": index, "trade_date": trade_date.isoformat()},
                )
            )
        else:
            conflicting_count += 1
            errors.append(
                _issue(
                    "duplicate_conflicting_bar",
                    EODWarningSeverity.ERROR,
                    "EOD bars with the same identity contain conflicting values.",
                    {"row_index": index, "trade_date": trade_date.isoformat()},
                )
            )

    if input_not_sorted:
        warnings.insert(
            0,
            _issue(
                "input_not_sorted",
                EODWarningSeverity.WARNING,
                "EOD bars are not ordered by ascending trading date.",
            ),
        )

    missing_dates: Tuple[date, ...] = ()
    if expected_range is not None:
        try:
            expected_dates = validate_trading_days(calendar, expected_range)
        except TradingCalendarContractError as exc:
            errors.append(
                _issue(
                    "invalid_calendar",
                    EODWarningSeverity.ERROR,
                    "The trading calendar returned an invalid date sequence.",
                    {"reason": str(exc)},
                )
            )
        except Exception:
            errors.append(
                _issue(
                    "invalid_calendar",
                    EODWarningSeverity.ERROR,
                    "The trading calendar could not produce the expected date sequence.",
                )
            )
        else:
            missing_dates = tuple(value for value in expected_dates if value not in observed_dates)
            if missing_dates:
                warnings.append(
                    _issue(
                        "missing_trading_days",
                        EODWarningSeverity.WARNING,
                        "Expected trading dates are missing from the EOD batch.",
                        {
                            "dates": [value.isoformat() for value in missing_dates],
                            "missing_count": len(missing_dates),
                        },
                    )
                )

    return EODValidationReport(
        is_valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
        received_row_count=len(batch),
        unique_identity_count=len(seen),
        duplicate_identical_count=identical_count,
        duplicate_conflicting_count=conflicting_count,
        missing_trading_dates=missing_dates,
    )
