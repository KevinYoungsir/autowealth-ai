from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

import pytest

from autowealth.market_data import (
    EOD_SCHEMA_VERSION,
    MARKET_TIMEZONE,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODUpdateRequest,
    EODUpdateResult,
    EODUpdateStatus,
    EODWarningSeverity,
    Market,
    TradingCalendarContractError,
    Venue,
    eod_bar_identity,
    normalize_canonical_symbol,
    normalize_eod_bars,
    validate_eod_batch,
    validate_trading_days,
)


@dataclass(frozen=True)
class StaticTradingCalendar:
    days: tuple[date, ...]

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return next(day for day in self.days if day > value)

    def previous_trading_day(self, value: date) -> date:
        return next(day for day in reversed(self.days) if day < value)

    def trading_days(self, start_date: date, end_date: date) -> list[date]:
        return [day for day in self.days if start_date <= day <= end_date]


@dataclass(frozen=True)
class ReturnedDaysCalendar(StaticTradingCalendar):
    returned_days: tuple[date, ...] = ()

    def trading_days(self, start_date: date, end_date: date) -> list[date]:
        return list(self.returned_days)


@pytest.fixture
def dataset() -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol="600000.SH",
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


@pytest.fixture
def calendar() -> StaticTradingCalendar:
    return StaticTradingCalendar(
        (
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        )
    )


def make_bar(
    dataset: EODDatasetKey,
    trade_date: date,
    *,
    open_value: object = "10",
    high_value: object = "11",
    low_value: object = "9",
    close_value: object = "10.5",
    volume: object = "1000",
    amount: object = "10500",
) -> EODBar:
    def number(value: object) -> object:
        return Decimal(value) if type(value) is str else value

    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=number(open_value),
        high=number(high_value),
        low=number(low_value),
        close=number(close_value),
        volume=number(volume),
        amount=None if amount is None else number(amount),
    )


def make_update_result(
    dataset: EODDatasetKey,
    **overrides: object,
) -> EODUpdateResult:
    values = {
        "status": EODUpdateStatus.SUCCESS,
        "dataset": dataset,
        "requested_range": EODDateRange(date(2024, 1, 2), date(2024, 1, 4)),
        "provider": "fake_provider",
        "received_row_count": 3,
        "inserted_row_count": 1,
        "updated_row_count": 1,
        "skipped_row_count": 1,
        "latest_effective_trading_date": date(2024, 1, 4),
        "started_at": datetime(2024, 1, 5, 1, tzinfo=timezone.utc),
        "finished_at": datetime(2024, 1, 5, 2, tzinfo=timezone.utc),
        "before_data_version": "v1",
        "after_data_version": "v2",
        "generation_checksum": "a" * 64,
    }
    values.update(overrides)
    return EODUpdateResult(**values)


def issue_codes(issues: tuple[EODStructuredWarning, ...]) -> list[str]:
    return [issue.code for issue in issues]


def test_eod_schema_version_and_fixed_domain() -> None:
    assert EOD_SCHEMA_VERSION == 1
    assert MARKET_TIMEZONE == "Asia/Shanghai"
    assert list(Market) == [Market.CN]
    assert list(Venue) == [Venue.SSE, Venue.SZSE]
    assert list(AssetType) == [AssetType.EQUITY, AssetType.INDEX]
    assert list(BarFrequency) == [BarFrequency.DAILY]
    assert list(AdjustmentType) == [
        AdjustmentType.NONE,
        AdjustmentType.QFQ,
        AdjustmentType.HFQ,
    ]


@pytest.mark.parametrize(
    ("symbol", "venue", "expected"),
    [
        ("600000.SH", None, "600000.SH"),
        ("600000.sh", None, "600000.SH"),
        ("000001.SZ", Venue.SZSE, "000001.SZ"),
        ("000001", Venue.SZSE, "000001.SZ"),
        ("600000", "SSE", "600000.SH"),
    ],
)
def test_normalize_canonical_symbol(
    symbol: str,
    venue: object,
    expected: str,
) -> None:
    assert normalize_canonical_symbol(symbol, venue) == expected


def test_bare_symbol_requires_explicit_venue() -> None:
    with pytest.raises(ValueError, match="venue is required"):
        normalize_canonical_symbol("600000")


@pytest.mark.parametrize(
    ("canonical_symbol", "venue"),
    [
        ("600000.SH", Venue.SSE),
        ("000001.SZ", Venue.SZSE),
    ],
)
def test_dataset_accepts_matching_symbol_and_venue(
    canonical_symbol: str,
    venue: Venue,
) -> None:
    key = EODDatasetKey(
        Market.CN,
        venue,
        AssetType.EQUITY,
        canonical_symbol,
    )
    assert key.canonical_symbol == canonical_symbol
    assert key.venue is venue


def test_symbol_suffix_and_venue_conflict_is_rejected() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        normalize_canonical_symbol("600000.SH", Venue.SZSE)
    with pytest.raises(ValueError, match="conflicts"):
        EODDatasetKey(
            Market.CN,
            Venue.SZSE,
            AssetType.EQUITY,
            "600000.SH",
        )


@pytest.mark.parametrize(
    "symbol",
    [
        "",
        "60000",
        "6000000",
        "ABCDEF",
        "600000.HK",
        " 600000.SH",
        "600000.SH ",
        "600 000.SH",
    ],
)
def test_invalid_symbols_are_rejected(symbol: str) -> None:
    with pytest.raises(ValueError):
        normalize_canonical_symbol(symbol, Venue.SSE)


def test_asset_type_is_part_of_dataset_identity(dataset: EODDatasetKey) -> None:
    index_dataset = EODDatasetKey(
        dataset.market,
        dataset.venue,
        AssetType.INDEX,
        dataset.canonical_symbol,
        dataset.frequency,
        dataset.adjustment_type,
    )
    assert dataset != index_dataset
    assert dataset.identity != index_dataset.identity


def test_adjustment_types_have_isolated_dataset_identities(dataset: EODDatasetKey) -> None:
    keys = {
        EODDatasetKey(
            dataset.market,
            dataset.venue,
            dataset.asset_type,
            dataset.canonical_symbol,
            dataset.frequency,
            adjustment,
        )
        for adjustment in AdjustmentType
    }
    assert len(keys) == 3
    assert len({key.identity for key in keys}) == 3


def test_dataset_equality_and_hash_are_stable(dataset: EODDatasetKey) -> None:
    same = EODDatasetKey(
        "CN",
        "SSE",
        "equity",
        "600000.SH",
        "1d",
        "none",
    )
    assert same == dataset
    assert hash(same) == hash(dataset)
    assert same.identity == (
        "CN",
        "SSE",
        "equity",
        "600000.SH",
        "1d",
        "none",
    )


def test_schema_json_serialization_is_stable(dataset: EODDatasetKey) -> None:
    warning = EODStructuredWarning(
        code="missing_trading_days",
        severity=EODWarningSeverity.WARNING,
        message="Expected trading dates are missing.",
        details={"count": 1, "dates": ["2024-01-03"]},
    )
    request = EODUpdateRequest(
        dataset=dataset,
        requested_range=EODDateRange(date(2024, 1, 2), date(2024, 1, 4)),
        dry_run=True,
    )
    result = make_update_result(dataset, warnings=(warning,))
    bar = make_bar(dataset, date(2024, 1, 2), open_value=10.10)

    for value in (dataset, warning, request, result, bar):
        assert value.to_json() == value.to_json()
        assert json.loads(value.to_json()) == value.to_dict()
    assert json.loads(bar.to_json())["open"] == "10.1"
    assert result.succeeded is True
    assert make_update_result(dataset, status=EODUpdateStatus.FAILED).succeeded is False


def test_warning_details_reject_sensitive_or_raw_transport_data() -> None:
    with pytest.raises(ValueError, match="secret-like key"):
        EODStructuredWarning(
            code="unsafe_warning",
            severity=EODWarningSeverity.ERROR,
            message="Unsafe warning.",
            details={"api_key": "not-a-real-key"},
        )
    with pytest.raises(ValueError, match="raw transport"):
        EODStructuredWarning(
            code="unsafe_warning",
            severity=EODWarningSeverity.ERROR,
            message="Unsafe warning.",
            details={"headers": {"x": "y"}},
        )


def test_warning_to_dict_does_not_expose_internal_containers() -> None:
    warning = EODStructuredWarning(
        code="missing_trading_days",
        severity=EODWarningSeverity.WARNING,
        message="Expected trading dates are missing.",
        details={"dates": ["2024-01-03"], "metadata": {"count": 1}},
    )

    public_details = warning.to_dict()["details"]
    assert type(public_details) is dict
    public_details["dates"].append("2024-01-04")
    public_details["metadata"]["count"] = 2

    assert warning.to_dict()["details"] == {
        "dates": ["2024-01-03"],
        "metadata": {"count": 1},
    }


def test_date_range_is_closed_and_rejects_reverse_order() -> None:
    requested_range = EODDateRange(date(2024, 1, 2), date(2024, 1, 4))
    assert requested_range.contains(date(2024, 1, 2))
    assert requested_range.contains(date(2024, 1, 4))
    assert not requested_range.contains(date(2024, 1, 5))
    with pytest.raises(ValueError, match="cannot be after"):
        EODDateRange(date(2024, 1, 4), date(2024, 1, 2))


@pytest.mark.parametrize("field_name", ["start_date", "end_date"])
def test_date_range_rejects_datetime_values(field_name: str) -> None:
    values = {
        "start_date": date(2024, 1, 2),
        "end_date": date(2024, 1, 4),
    }
    values[field_name] = datetime(2024, 1, 3, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match=f"{field_name} must be a date"):
        EODDateRange(**values)


def test_eod_bar_normalizes_valid_financial_numbers(dataset: EODDatasetKey) -> None:
    bar = make_bar(dataset, date(2024, 1, 2), amount=None)
    assert bar.open == Decimal("10")
    assert bar.close == Decimal("10.5")
    assert bar.volume == Decimal("1000")
    assert bar.amount is None
    assert eod_bar_identity(bar) == (*dataset.identity, "2024-01-02")


def test_eod_bar_rejects_datetime_trade_date(dataset: EODDatasetKey) -> None:
    with pytest.raises(ValueError, match="trade_date must be a date"):
        make_bar(
            dataset,
            datetime(2024, 1, 2, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"high_value": "9.9"},
        {"low_value": "10.1"},
        {"low_value": "11.1"},
    ],
)
def test_eod_bar_rejects_high_low_invariant_violations(
    dataset: EODDatasetKey,
    overrides: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="high|low"):
        make_bar(dataset, date(2024, 1, 2), **overrides)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("open_value", 0),
        ("high_value", -1),
        ("low_value", 0),
        ("close_value", -1),
    ],
)
def test_eod_bar_rejects_non_positive_prices(
    dataset: EODDatasetKey,
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        make_bar(dataset, date(2024, 1, 2), **{field_name: value})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), Decimal("-Infinity")])
def test_eod_bar_rejects_non_finite_numbers(
    dataset: EODDatasetKey,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="finite number"):
        make_bar(dataset, date(2024, 1, 2), close_value=value)


@pytest.mark.parametrize("field_name", ["open_value", "volume", "amount"])
def test_bool_is_not_accepted_as_financial_number(
    dataset: EODDatasetKey,
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="finite number"):
        make_bar(dataset, date(2024, 1, 2), **{field_name: True})


def test_bool_is_not_accepted_as_count(dataset: EODDatasetKey) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        make_update_result(dataset, received_row_count=True)


def test_decimal_zero_has_one_stable_json_representation(dataset: EODDatasetKey) -> None:
    positive_zero = make_bar(dataset, date(2024, 1, 2), volume=Decimal("0"))
    negative_zero = make_bar(dataset, date(2024, 1, 2), volume=Decimal("-0.000"))
    assert positive_zero.to_dict()["volume"] == "0"
    assert negative_zero.to_dict()["volume"] == "0"


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("volume", -1),
        ("amount", -1),
    ],
)
def test_negative_volume_or_amount_is_rejected(
    dataset: EODDatasetKey,
    field_name: str,
    value: object,
) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        make_bar(dataset, date(2024, 1, 2), **{field_name: value})


def test_normalize_eod_bars_does_not_mutate_input(dataset: EODDatasetKey) -> None:
    later = make_bar(dataset, date(2024, 1, 3))
    earlier = make_bar(dataset, date(2024, 1, 2))
    original = [later, earlier, earlier]
    snapshot = list(original)

    normalized = normalize_eod_bars(original)

    assert original == snapshot
    assert normalized == (earlier, earlier, later)
    assert len(normalized) == len(original)


def test_normalize_eod_bars_uses_stable_dataset_and_date_order(
    dataset: EODDatasetKey,
) -> None:
    second_dataset = EODDatasetKey(
        Market.CN,
        Venue.SZSE,
        AssetType.EQUITY,
        "000001.SZ",
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )
    values = [
        make_bar(dataset, date(2024, 1, 3)),
        make_bar(second_dataset, date(2024, 1, 2)),
        make_bar(dataset, date(2024, 1, 2)),
    ]
    first = normalize_eod_bars(values)
    second = normalize_eod_bars(values)
    assert first == second
    assert [eod_bar_identity(bar) for bar in first] == sorted(
        eod_bar_identity(bar) for bar in values
    )


def test_identical_duplicate_is_a_warning_and_is_not_removed(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    bar = make_bar(dataset, date(2024, 1, 2))
    report = validate_eod_batch(dataset, [bar, bar], calendar)
    assert report.is_valid
    assert report.received_row_count == 2
    assert report.unique_identity_count == 1
    assert report.duplicate_identical_count == 1
    assert report.duplicate_conflicting_count == 0
    assert issue_codes(report.warnings) == ["duplicate_identical_bar"]
    assert report.errors == ()


def test_conflicting_duplicate_is_an_error_and_is_not_overwritten(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    first = make_bar(dataset, date(2024, 1, 2), close_value="10.5")
    conflicting = make_bar(dataset, date(2024, 1, 2), close_value="10.8")
    normalized = normalize_eod_bars([first, conflicting])
    report = validate_eod_batch(dataset, normalized, calendar)
    assert len(normalized) == 2
    assert normalized == (first, conflicting)
    assert not report.is_valid
    assert report.received_row_count == 2
    assert report.unique_identity_count == 1
    assert report.duplicate_identical_count == 0
    assert report.duplicate_conflicting_count == 1
    assert "duplicate_conflicting_bar" in issue_codes(report.errors)


def test_decimal_scale_does_not_make_equal_bars_conflicting(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    first = make_bar(dataset, date(2024, 1, 2), close_value=Decimal("10.50"))
    same_value = make_bar(dataset, date(2024, 1, 2), close_value=Decimal("10.5000"))
    report = validate_eod_batch(dataset, [first, same_value], calendar)
    assert report.is_valid
    assert report.duplicate_identical_count == 1
    assert report.duplicate_conflicting_count == 0


def test_none_and_zero_amount_are_conflicting_duplicate_values(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    missing_amount = make_bar(dataset, date(2024, 1, 2), amount=None)
    zero_amount = make_bar(dataset, date(2024, 1, 2), amount=Decimal("0"))
    report = validate_eod_batch(dataset, [missing_amount, zero_amount], calendar)
    assert not report.is_valid
    assert report.duplicate_identical_count == 0
    assert report.duplicate_conflicting_count == 1
    assert issue_codes(report.errors) == ["duplicate_conflicting_bar"]


def test_batch_dataset_mismatch_is_an_error(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    other_dataset = EODDatasetKey(
        Market.CN,
        Venue.SZSE,
        AssetType.EQUITY,
        "000001.SZ",
    )
    report = validate_eod_batch(
        dataset,
        [make_bar(other_dataset, date(2024, 1, 2))],
        calendar,
        EODDateRange(date(2024, 1, 2), date(2024, 1, 2)),
    )
    assert not report.is_valid
    assert issue_codes(report.errors) == ["dataset_mismatch"]
    assert issue_codes(report.warnings) == ["missing_trading_days"]
    assert report.missing_trading_dates == (date(2024, 1, 2),)


def test_non_trading_date_is_an_error(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    report = validate_eod_batch(
        dataset,
        [make_bar(dataset, date(2024, 1, 6))],
        calendar,
    )
    assert not report.is_valid
    assert issue_codes(report.errors) == ["non_trading_date"]


def test_missing_expected_trading_day_is_a_warning(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    report = validate_eod_batch(
        dataset,
        [
            make_bar(dataset, date(2024, 1, 2)),
            make_bar(dataset, date(2024, 1, 4)),
        ],
        calendar,
        EODDateRange(date(2024, 1, 2), date(2024, 1, 4)),
    )
    assert report.is_valid
    assert report.missing_trading_dates == (date(2024, 1, 3),)
    assert issue_codes(report.warnings) == ["missing_trading_days"]


def test_date_outside_expected_range_is_an_error(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    report = validate_eod_batch(
        dataset,
        [make_bar(dataset, date(2024, 1, 2))],
        calendar,
        EODDateRange(date(2024, 1, 3), date(2024, 1, 4)),
    )
    assert not report.is_valid
    assert "date_out_of_range" in issue_codes(report.errors)
    assert report.missing_trading_dates == (
        date(2024, 1, 3),
        date(2024, 1, 4),
    )


def test_descending_input_produces_stable_warning(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    report = validate_eod_batch(
        dataset,
        [
            make_bar(dataset, date(2024, 1, 4)),
            make_bar(dataset, date(2024, 1, 2)),
        ],
        calendar,
    )
    assert report.is_valid
    assert issue_codes(report.warnings) == ["input_not_sorted"]


def test_empty_batch_is_structured_and_invalid(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    report = validate_eod_batch(dataset, [], calendar)
    assert not report.is_valid
    assert report.received_row_count == 0
    assert report.unique_identity_count == 0
    assert issue_codes(report.errors) == ["empty_batch"]


@pytest.mark.parametrize(
    "field_name",
    [
        "received_row_count",
        "inserted_row_count",
        "updated_row_count",
        "skipped_row_count",
    ],
)
def test_update_result_rejects_negative_counts(
    dataset: EODDatasetKey,
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        make_update_result(dataset, **{field_name: -1})


@pytest.mark.parametrize("field_name", ["started_at", "finished_at"])
def test_update_result_rejects_naive_datetime(
    dataset: EODDatasetKey,
    field_name: str,
) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        make_update_result(dataset, **{field_name: datetime(2024, 1, 5, 1)})


def test_update_result_rejects_reversed_timestamps(dataset: EODDatasetKey) -> None:
    with pytest.raises(ValueError, match="cannot be before"):
        make_update_result(
            dataset,
            started_at=datetime(2024, 1, 5, 2, tzinfo=timezone.utc),
            finished_at=datetime(2024, 1, 5, 1, tzinfo=timezone.utc),
        )


def test_update_result_warning_default_is_immutable_and_safe(
    dataset: EODDatasetKey,
) -> None:
    first = make_update_result(dataset)
    second = make_update_result(dataset)
    assert first.warnings == ()
    assert second.warnings == ()
    with pytest.raises(FrozenInstanceError):
        first.warnings = (
            EODStructuredWarning(
                "test_warning",
                EODWarningSeverity.WARNING,
                "Test warning.",
            ),
        )
    assert second.warnings == ()


@pytest.mark.parametrize(
    ("recognized_days", "returned_days", "match"),
    [
        (
            (date(2024, 1, 2),),
            (date(2024, 1, 2), date(2024, 1, 2)),
            "strictly increasing",
        ),
        (
            (date(2024, 1, 2), date(2024, 1, 3)),
            (date(2024, 1, 3), date(2024, 1, 2)),
            "strictly increasing",
        ),
        (
            (date(2024, 1, 2),),
            (date(2024, 1, 2), date(2024, 1, 5)),
            "outside the requested range",
        ),
        (
            (date(2024, 1, 2),),
            (date(2024, 1, 2), date(2024, 1, 3)),
            "not recognized as a trading day",
        ),
    ],
)
def test_fake_calendar_return_contract_is_validated(
    recognized_days: tuple[date, ...],
    returned_days: tuple[date, ...],
    match: str,
) -> None:
    calendar = ReturnedDaysCalendar(recognized_days, returned_days)
    requested_range = EODDateRange(date(2024, 1, 2), date(2024, 1, 4))
    with pytest.raises(TradingCalendarContractError, match=match):
        validate_trading_days(calendar, requested_range)


def test_valid_fake_calendar_dates_are_returned_without_mutation(
    calendar: StaticTradingCalendar,
) -> None:
    requested_range = EODDateRange(date(2024, 1, 2), date(2024, 1, 4))
    assert validate_trading_days(calendar, requested_range) == calendar.days


def test_fake_calendar_rejects_datetime_as_trading_date() -> None:
    trading_datetime = datetime(2024, 1, 2, tzinfo=timezone.utc)
    calendar = ReturnedDaysCalendar(
        (date(2024, 1, 2),),
        (trading_datetime,),
    )
    requested_range = EODDateRange(date(2024, 1, 2), date(2024, 1, 4))
    with pytest.raises(TradingCalendarContractError, match="exact date"):
        validate_trading_days(calendar, requested_range)


def test_calendar_protocol_exception_becomes_structured_error(
    dataset: EODDatasetKey,
) -> None:
    class BrokenCalendar(StaticTradingCalendar):
        def is_trading_day(self, value: date) -> bool:
            raise RuntimeError("untrusted calendar detail")

    calendar = BrokenCalendar((date(2024, 1, 2),))
    report = validate_eod_batch(
        dataset,
        [make_bar(dataset, date(2024, 1, 2))],
        calendar,
    )
    assert not report.is_valid
    assert issue_codes(report.errors) == ["invalid_calendar"]
    assert "untrusted calendar detail" not in report.to_json()


def test_validation_detects_forged_invalid_numbers(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    bar = make_bar(dataset, date(2024, 1, 2))
    object.__setattr__(bar, "close", Decimal("NaN"))
    report = validate_eod_batch(dataset, [bar], calendar)
    assert not report.is_valid
    assert issue_codes(report.errors) == ["invalid_numeric_value"]


def test_validation_detects_forged_invalid_ohlc(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    bar = make_bar(dataset, date(2024, 1, 2))
    object.__setattr__(bar, "high", Decimal("9.5"))
    report = validate_eod_batch(dataset, [bar], calendar)
    assert not report.is_valid
    assert issue_codes(report.errors) == ["invalid_ohlc"]


def test_validation_issue_order_and_json_are_deterministic(
    dataset: EODDatasetKey,
    calendar: StaticTradingCalendar,
) -> None:
    later = make_bar(dataset, date(2024, 1, 4))
    earlier = make_bar(dataset, date(2024, 1, 2))
    bars = [later, earlier, earlier]
    expected_range = EODDateRange(date(2024, 1, 2), date(2024, 1, 4))

    first = validate_eod_batch(dataset, bars, calendar, expected_range)
    second = validate_eod_batch(dataset, bars, calendar, expected_range)

    assert issue_codes(first.warnings) == [
        "input_not_sorted",
        "duplicate_identical_bar",
        "missing_trading_days",
    ]
    assert first.to_dict() == second.to_dict()
    assert first.to_json() == second.to_json()


def test_market_data_import_has_no_external_side_effects() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    banned_import_roots = {
        "akshare",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "time",
        "yfinance",
    }
    for module_path in sorted((repository_root / "autowealth" / "market_data").glob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported_roots.update(
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        assert banned_import_roots.isdisjoint(imported_roots)

    script = """
import builtins
import os
from pathlib import Path
import socket
import sys
import time

import autowealth

before_environment = dict(os.environ)
before_modules = set(sys.modules)
blocked_module_roots = {"akshare", "httpx", "requests", "yfinance"}
original_open = builtins.open

def fail_external(*args, **kwargs):
    raise AssertionError("market_data import attempted an external side effect")

def guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        fail_external()
    return original_open(file, mode, *args, **kwargs)

builtins.open = guarded_open
socket.create_connection = fail_external
socket.socket.connect = fail_external
Path.write_text = fail_external
Path.write_bytes = fail_external
Path.touch = fail_external
os.getenv = fail_external
os._Environ.get = fail_external
time.time = fail_external

import autowealth.market_data

assert dict(os.environ) == before_environment
new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before_modules}
assert blocked_module_roots.isdisjoint(new_roots)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
