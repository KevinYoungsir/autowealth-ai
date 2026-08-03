from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import inspect
from pathlib import Path
import subprocess
import sys
from typing import Optional

import numpy as np
import pandas as pd
import pytest

import autowealth.market_data as market_data
import autowealth.market_data.akshare_adapters as adapter_module
from autowealth.market_data.akshare_adapters import (
    AKShareEODEquityProvider,
    AKShareEODIndexProvider,
    akshare_equity_symbol,
    akshare_index_symbol,
)
from autowealth.market_data.dataframe_conversion import convert_eod_dataframe_to_bars
from autowealth.market_data.providers import (
    EODProvider,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResultStatus,
    EODRevisionStrategy,
)
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)

DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


class RecordingEndpoint:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        if type(self.response) is pd.DataFrame:
            return self.response.copy(deep=True)
        return self.response


def make_dataset(
    *,
    symbol: str = "600000.SH",
    venue: Venue = Venue.SSE,
    asset_type: AssetType = AssetType.EQUITY,
    adjustment: AdjustmentType = AdjustmentType.NONE,
) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=venue,
        asset_type=asset_type,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=adjustment,
    )


def make_request(
    dataset: Optional[EODDatasetKey] = None,
    *,
    start: date = DAY_1,
    end: date = DAY_2,
) -> EODProviderRequest:
    return EODProviderRequest(
        dataset=dataset or make_dataset(),
        requested_range=EODDateRange(start, end),
    )


def english_frame(
    days: tuple[date, ...] = (DAY_1, DAY_2),
    *,
    include_amount: bool = True,
) -> pd.DataFrame:
    rows = []
    for offset, trade_date in enumerate(days):
        row = {
            "date": trade_date.isoformat(),
            "open": 10 + offset,
            "high": 11 + offset,
            "low": 9 + offset,
            "close": Decimal("10.5") + offset,
            "volume": 1000 + offset,
        }
        if include_amount:
            row["amount"] = 10000 + offset
        rows.append(row)
    return pd.DataFrame(rows)


def chinese_frame(days: tuple[date, ...] = (DAY_1, DAY_2)) -> pd.DataFrame:
    return english_frame(days).rename(
        columns={
            "date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
        }
    )


def convert(frame: pd.DataFrame, dataset: Optional[EODDatasetKey] = None) -> tuple:
    return convert_eod_dataframe_to_bars(
        frame,
        dataset or make_dataset(),
        EODDateRange(DAY_1, DAY_3),
    )


def run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("dataset", "expected"),
    [
        (make_dataset(), "600000"),
        (
            make_dataset(symbol="000001.SZ", venue=Venue.SZSE),
            "000001",
        ),
    ],
)
def test_equity_symbol_mapping(dataset: EODDatasetKey, expected: str) -> None:
    assert akshare_equity_symbol(dataset) == expected


def test_equity_symbol_rejects_index_and_non_daily_dataset() -> None:
    index_dataset = make_dataset(asset_type=AssetType.INDEX)
    with pytest.raises(EODProviderError) as index_error:
        akshare_equity_symbol(index_dataset)
    assert index_error.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST

    non_daily = make_dataset()
    object.__setattr__(non_daily, "frequency", "weekly")
    with pytest.raises(EODProviderError) as frequency_error:
        akshare_equity_symbol(non_daily)
    assert frequency_error.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST


@pytest.mark.parametrize(
    ("symbol", "venue", "expected"),
    [
        ("000001.SH", Venue.SSE, "000001"),
        ("000300.SH", Venue.SSE, "000300"),
        ("000905.SH", Venue.SSE, "000905"),
        ("000852.SH", Venue.SSE, "000852"),
        ("399001.SZ", Venue.SZSE, "399001"),
        ("399006.SZ", Venue.SZSE, "399006"),
    ],
)
def test_index_symbol_mapping(symbol: str, venue: Venue, expected: str) -> None:
    dataset = make_dataset(symbol=symbol, venue=venue, asset_type=AssetType.INDEX)
    assert akshare_index_symbol(dataset) == expected


def test_equity_and_index_identity_prevents_000001_ambiguity() -> None:
    equity = make_dataset(symbol="000001.SZ", venue=Venue.SZSE)
    index = make_dataset(symbol="000001.SH", asset_type=AssetType.INDEX)
    assert akshare_equity_symbol(equity) == "000001"
    assert akshare_index_symbol(index) == "000001"
    with pytest.raises(EODProviderError):
        akshare_equity_symbol(index)
    with pytest.raises(EODProviderError):
        akshare_index_symbol(equity)


@pytest.mark.parametrize("adjustment", [AdjustmentType.QFQ, AdjustmentType.HFQ])
def test_index_symbol_rejects_adjusted_dataset(adjustment: AdjustmentType) -> None:
    dataset = make_dataset(asset_type=AssetType.INDEX, adjustment=adjustment)
    with pytest.raises(EODProviderError) as captured:
        akshare_index_symbol(dataset)
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST


def test_index_symbol_rejects_unsupported_canonical_index() -> None:
    dataset = make_dataset(symbol="000002.SH", asset_type=AssetType.INDEX)
    with pytest.raises(EODProviderError) as captured:
        akshare_index_symbol(dataset)
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST


def test_symbol_resolvers_require_exact_dataset() -> None:
    with pytest.raises(TypeError, match="exact EODDatasetKey"):
        akshare_equity_symbol("600000.SH")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="exact EODDatasetKey"):
        akshare_index_symbol("000300.SH")  # type: ignore[arg-type]


def test_converter_accepts_exact_chinese_and_english_frames() -> None:
    chinese = convert(chinese_frame())
    english = convert(english_frame())
    assert chinese == english
    assert type(chinese) is tuple
    assert [bar.trade_date for bar in chinese] == [DAY_1, DAY_2]


def test_converter_rejects_dataframe_subclass_and_non_dataframe() -> None:
    class FrameSubclass(pd.DataFrame):
        pass

    with pytest.raises(EODProviderError) as subclass_error:
        convert(FrameSubclass(english_frame()))
    assert subclass_error.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD
    with pytest.raises(EODProviderError):
        convert_eod_dataframe_to_bars([], make_dataset(), EODDateRange(DAY_1, DAY_2))


def test_converter_requires_exact_dataset_and_date_range() -> None:
    class DatasetSubclass(EODDatasetKey):
        pass

    class RangeSubclass(EODDateRange):
        pass

    dataset = DatasetSubclass(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol="600000.SH",
    )
    requested_range = RangeSubclass(DAY_1, DAY_2)
    with pytest.raises(TypeError, match="exact EODDatasetKey"):
        convert_eod_dataframe_to_bars(english_frame(), dataset, EODDateRange(DAY_1, DAY_2))
    with pytest.raises(TypeError, match="exact EODDateRange"):
        convert_eod_dataframe_to_bars(english_frame(), make_dataset(), requested_range)


def test_converter_allows_missing_amount_column_and_extra_columns() -> None:
    frame = english_frame(include_amount=False)
    frame["extra"] = ["ignored", "ignored"]
    bars = convert(frame)
    assert all(bar.amount is None for bar in bars)


@pytest.mark.parametrize("missing", [None, pd.NA])
def test_converter_rejects_row_level_missing_amount(missing: object) -> None:
    frame = english_frame()
    frame["amount"] = pd.Series([missing, 10001], dtype="object")
    with pytest.raises(EODProviderError) as captured:
        convert(frame)
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_converter_rejects_alias_conflicts_and_duplicate_physical_columns() -> None:
    aliases = english_frame()
    aliases["日期"] = aliases["date"]
    with pytest.raises(EODProviderError, match="ambiguous"):
        convert(aliases)

    duplicate_columns = list(english_frame().columns) + ["volume"]
    duplicate = pd.DataFrame(
        [["2024-01-02", 10, 11, 9, 10.5, 1000, 10000, 1000]],
        columns=duplicate_columns,
    )
    with pytest.raises(EODProviderError, match="duplicate column"):
        convert(duplicate)


@pytest.mark.parametrize("column", ["date", "open", "volume"])
def test_converter_rejects_missing_required_columns(column: str) -> None:
    with pytest.raises(EODProviderError, match="required"):
        convert(english_frame().drop(columns=[column]))


def test_empty_dataframe_requires_no_columns_but_rejects_duplicate_labels() -> None:
    assert convert(pd.DataFrame()) == ()
    duplicate = pd.DataFrame(columns=["date", "date"])
    with pytest.raises(EODProviderError, match="duplicate column"):
        convert(duplicate)


def test_converter_does_not_modify_input_and_sorts_output() -> None:
    frame = english_frame((DAY_2, DAY_1))
    snapshot = frame.copy(deep=True)
    bars = convert(frame)
    pd.testing.assert_frame_equal(frame, snapshot)
    assert tuple(bar.trade_date for bar in bars) == (DAY_1, DAY_2)


@pytest.mark.parametrize("conflicting", [False, True])
def test_converter_rejects_identical_and_conflicting_duplicate_dates(conflicting: bool) -> None:
    frame = english_frame((DAY_1, DAY_1))
    if conflicting:
        frame.loc[1, "close"] = Decimal("10.75")
    with pytest.raises(EODProviderError, match="duplicate trading"):
        convert(frame)


def test_converter_rejects_out_of_range_date_without_clipping() -> None:
    frame = english_frame((date(2024, 1, 1),))
    with pytest.raises(EODProviderError, match="outside"):
        convert(frame)


@pytest.mark.parametrize(
    "value",
    [
        DAY_1,
        "2024-01-02",
        "20240102",
        datetime(2024, 1, 2),
        pd.Timestamp("2024-01-02 00:00:00"),
    ],
)
def test_converter_accepts_strict_date_forms(value: object) -> None:
    frame = english_frame((DAY_1,))
    frame["date"] = pd.Series([value], dtype="object")
    assert convert(frame)[0].trade_date == DAY_1


@pytest.mark.parametrize(
    "value",
    [
        datetime(2024, 1, 2, 0, 0, 1),
        pd.Timestamp("2024-01-02 00:00:00.000000001"),
        pd.Timestamp("2024-01-02", tz=timezone.utc),
        pd.NaT,
        pd.NA,
        np.datetime64("2024-01-02"),
        "2024-02-30",
        " 2024-01-02",
        "2024-01-02 ",
    ],
)
def test_converter_rejects_ambiguous_or_invalid_date_forms(value: object) -> None:
    frame = english_frame((DAY_1,))
    frame["date"] = pd.Series([value], dtype="object")
    with pytest.raises(EODProviderError) as captured:
        convert(frame)
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize(
    "value",
    [
        Decimal("10"),
        10,
        10.0,
        np.int64(10),
        np.float64(10.0),
        "10.000",
        "1e1",
    ],
)
def test_converter_accepts_strict_finite_numeric_forms(value: object) -> None:
    frame = english_frame((DAY_1,))
    frame["open"] = pd.Series([value], dtype="object")
    assert convert(frame)[0].open == Decimal("10")


@pytest.mark.parametrize(
    "value",
    [
        True,
        np.bool_(True),
        float("nan"),
        float("inf"),
        float("-inf"),
        Decimal("NaN"),
        pd.NA,
        pd.NaT,
        None,
        "",
        " 10",
        "10 ",
        complex(10, 0),
        object(),
    ],
)
def test_converter_rejects_invalid_numeric_forms(value: object) -> None:
    frame = english_frame((DAY_1,))
    frame["open"] = pd.Series([value], dtype="object")
    with pytest.raises(EODProviderError) as captured:
        convert(frame)
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_converter_preserves_decimal_equivalence_across_supported_scalars() -> None:
    values = [Decimal("10.125"), 10.125, np.float64(10.125), "10.125"]
    converted = []
    for value in values:
        frame = english_frame((DAY_1,))
        frame["open"] = pd.Series([value], dtype="object")
        converted.append(convert(frame)[0].open)
    assert converted == [Decimal("10.125")] * len(values)


def test_converter_delegates_ohlcv_integrity_to_eod_bar() -> None:
    malformed = english_frame((DAY_1,))
    malformed.loc[0, "high"] = 5
    with pytest.raises(EODProviderError) as captured:
        convert(malformed)
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD
    assert captured.value.__cause__ is not None

    zero_volume = english_frame((DAY_1,))
    zero_volume.loc[0, "volume"] = 0
    assert convert(zero_volume)[0].volume == Decimal("0")

    negative_volume = english_frame((DAY_1,))
    negative_volume.loc[0, "volume"] = -1
    with pytest.raises(EODProviderError):
        convert(negative_volume)


def test_converter_output_is_deterministic_and_never_repairs_bad_rows() -> None:
    frame = english_frame((DAY_2, DAY_1))
    first = convert(frame)
    second = convert(frame.copy(deep=True))
    assert first == second
    assert tuple(bar.to_json() for bar in first) == tuple(bar.to_json() for bar in second)

    missing = english_frame()
    missing.loc[0, "close"] = pd.NA
    with pytest.raises(EODProviderError):
        convert(missing)


def test_equity_provider_protocol_identity_and_capabilities() -> None:
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)), endpoint=lambda: None
    )
    assert isinstance(provider, EODProvider)
    assert provider.provider_name == "akshare_eod_equity"
    assert provider.provider_version == "1"
    assert type(provider.capabilities) is tuple
    assert len(provider.capabilities) == 6
    assert len(set(provider.capabilities)) == 6
    assert [item.venue for item in provider.capabilities] == [
        Venue.SSE,
        Venue.SSE,
        Venue.SSE,
        Venue.SZSE,
        Venue.SZSE,
        Venue.SZSE,
    ]
    assert [item.revision_strategy for item in provider.capabilities] == [
        EODRevisionStrategy.APPEND_ONLY,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
        EODRevisionStrategy.APPEND_ONLY,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ]


def test_index_provider_protocol_identity_and_capabilities() -> None:
    provider = AKShareEODIndexProvider(StaticTradingCalendar((DAY_1, DAY_2)), endpoint=lambda: None)
    assert isinstance(provider, EODProvider)
    assert provider.provider_name == "akshare_eod_index"
    assert provider.provider_version == "1"
    assert type(provider.capabilities) is tuple
    assert len(provider.capabilities) == 2
    assert len(set(provider.capabilities)) == 2
    assert {item.venue for item in provider.capabilities} == {Venue.SSE, Venue.SZSE}
    assert all(item.asset_type is AssetType.INDEX for item in provider.capabilities)
    assert all(item.adjustment_type is AdjustmentType.NONE for item in provider.capabilities)
    assert all(
        item.revision_strategy is EODRevisionStrategy.APPEND_ONLY for item in provider.capabilities
    )


@pytest.mark.parametrize(
    ("symbol", "venue", "adjustment", "provider_symbol", "adjust"),
    [
        ("600000.SH", Venue.SSE, AdjustmentType.NONE, "600000", ""),
        ("000001.SZ", Venue.SZSE, AdjustmentType.QFQ, "000001", "qfq"),
        ("000001.SZ", Venue.SZSE, AdjustmentType.HFQ, "000001", "hfq"),
    ],
)
def test_equity_provider_uses_exact_endpoint_kwargs(
    symbol: str,
    venue: Venue,
    adjustment: AdjustmentType,
    provider_symbol: str,
    adjust: str,
) -> None:
    endpoint = RecordingEndpoint(english_frame())
    dataset = make_dataset(symbol=symbol, venue=venue, adjustment=adjustment)
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    result = provider.fetch(make_request(dataset))
    assert result.status is EODProviderResultStatus.SUCCESS
    assert endpoint.calls == [
        {
            "symbol": provider_symbol,
            "period": "daily",
            "start_date": "20240102",
            "end_date": "20240103",
            "adjust": adjust,
        }
    ]


@pytest.mark.parametrize(
    ("symbol", "venue", "provider_symbol"),
    [
        ("000300.SH", Venue.SSE, "000300"),
        ("399006.SZ", Venue.SZSE, "399006"),
    ],
)
def test_index_provider_uses_exact_endpoint_kwargs(
    symbol: str,
    venue: Venue,
    provider_symbol: str,
) -> None:
    endpoint = RecordingEndpoint(english_frame())
    dataset = make_dataset(symbol=symbol, venue=venue, asset_type=AssetType.INDEX)
    provider = AKShareEODIndexProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    result = provider.fetch(make_request(dataset))
    assert result.status is EODProviderResultStatus.SUCCESS
    assert endpoint.calls == [
        {
            "symbol": provider_symbol,
            "period": "daily",
            "start_date": "20240102",
            "end_date": "20240103",
        }
    ]
    assert "adjust" not in endpoint.calls[0]


@pytest.mark.parametrize(
    ("provider_type", "dataset"),
    [
        (AKShareEODEquityProvider, make_dataset()),
        (
            AKShareEODIndexProvider,
            make_dataset(symbol="000300.SH", asset_type=AssetType.INDEX),
        ),
    ],
)
def test_adapters_generate_success_partial_and_empty_statuses(
    provider_type: type,
    dataset: EODDatasetKey,
) -> None:
    calendar = StaticTradingCalendar((DAY_1, DAY_2))
    success = provider_type(calendar, endpoint=RecordingEndpoint(english_frame())).fetch(
        make_request(dataset)
    )
    assert success.status is EODProviderResultStatus.SUCCESS
    assert not success.warnings

    partial = provider_type(
        calendar,
        endpoint=RecordingEndpoint(english_frame((DAY_1,))),
    ).fetch(make_request(dataset))
    assert partial.status is EODProviderResultStatus.PARTIAL_SUCCESS
    assert [warning.code for warning in partial.warnings] == ["missing_trading_days"]

    empty = provider_type(calendar, endpoint=RecordingEndpoint(pd.DataFrame())).fetch(
        make_request(dataset)
    )
    assert empty.status is EODProviderResultStatus.EMPTY
    assert empty.bars == ()
    assert [warning.code for warning in empty.warnings] == ["empty_response"]


def test_index_provider_accepts_payload_without_amount() -> None:
    dataset = make_dataset(symbol="000300.SH", asset_type=AssetType.INDEX)
    provider = AKShareEODIndexProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(english_frame(include_amount=False)),
    )
    assert all(bar.amount is None for bar in provider.fetch(make_request(dataset)).bars)


@pytest.mark.parametrize("response", [object(), {"date": "2024-01-02"}])
def test_adapters_reject_non_dataframe_payload(response: object) -> None:
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(response),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_adapter_keeps_malformed_payload_classification() -> None:
    frame = english_frame()
    frame.loc[0, "close"] = pd.NA
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize("provider_type", [AKShareEODEquityProvider, AKShareEODIndexProvider])
def test_endpoint_exception_maps_to_unavailable_and_preserves_cause(provider_type: type) -> None:
    secret = "Authorization: Bearer secret Cookie: session=private apiKey=hidden"
    endpoint_error = RuntimeError(secret + r" D:\private\response.json")
    endpoint = RecordingEndpoint(endpoint_error)
    dataset = (
        make_dataset()
        if provider_type is AKShareEODEquityProvider
        else make_dataset(symbol="000300.SH", asset_type=AssetType.INDEX)
    )
    provider = provider_type(StaticTradingCalendar((DAY_1, DAY_2)), endpoint=endpoint)
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(dataset))
    error = captured.value
    assert error.code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert error.__cause__ is endpoint_error
    public = error.to_json()
    assert "secret" not in public
    assert "private" not in public
    assert "Authorization" not in public
    assert "Cookie" not in public
    assert "apiKey" not in public
    assert len(endpoint.calls) == 1


def test_endpoint_base_exception_is_not_caught() -> None:
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(KeyboardInterrupt()),
    )
    with pytest.raises(KeyboardInterrupt):
        provider.fetch(make_request())


def test_no_trading_day_rejects_before_symbol_or_endpoint_resolution() -> None:
    endpoint = RecordingEndpoint(AssertionError("endpoint must not run"))
    unsupported_index = make_dataset(symbol="000002.SH", asset_type=AssetType.INDEX)
    provider = AKShareEODIndexProvider(StaticTradingCalendar(()), endpoint=endpoint)
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(unsupported_index))
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert endpoint.calls == []


def test_calendar_exception_maps_to_malformed_and_preserves_cause() -> None:
    class BrokenCalendar(StaticTradingCalendar):
        def trading_days(self, start_date: date, end_date: date) -> list[date]:
            raise RuntimeError("apiKey=calendar-secret")

    endpoint = RecordingEndpoint(AssertionError("endpoint must not run"))
    provider = AKShareEODEquityProvider(BrokenCalendar((DAY_1, DAY_2)), endpoint=endpoint)
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD
    assert captured.value.__cause__ is not None
    assert "calendar-secret" not in captured.value.to_json()
    assert endpoint.calls == []


def test_existing_validator_rejects_non_trading_bar_after_conversion() -> None:
    frame = english_frame((DAY_1, DAY_2))
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1,)),
        endpoint=RecordingEndpoint(frame),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_fetch_rejects_wrong_request_type_and_does_not_modify_request() -> None:
    endpoint = RecordingEndpoint(english_frame())
    provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    with pytest.raises(TypeError, match="exact EODProviderRequest"):
        provider.fetch(object())  # type: ignore[arg-type]
    request = make_request()
    before = request.to_json()
    provider.fetch(request)
    assert request.to_json() == before


def test_provider_request_capabilities_reject_wrong_asset_and_adjustment() -> None:
    endpoint = RecordingEndpoint(AssertionError("endpoint must not run"))
    equity_provider = AKShareEODEquityProvider(
        StaticTradingCalendar((DAY_1, DAY_2)), endpoint=endpoint
    )
    index_request = make_request(make_dataset(asset_type=AssetType.INDEX))
    with pytest.raises(EODProviderError) as equity_error:
        equity_provider.fetch(index_request)
    assert equity_error.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST

    index_provider = AKShareEODIndexProvider(
        StaticTradingCalendar((DAY_1, DAY_2)), endpoint=endpoint
    )
    with pytest.raises(EODProviderError):
        index_provider.fetch(make_request())
    for adjustment in (AdjustmentType.QFQ, AdjustmentType.HFQ):
        dataset = make_dataset(asset_type=AssetType.INDEX, adjustment=adjustment)
        with pytest.raises(EODProviderError):
            index_provider.fetch(make_request(dataset))
    assert endpoint.calls == []


def test_index_adapter_has_no_fallback_endpoint_or_chain_dependency() -> None:
    source = inspect.getsource(adapter_module)
    assert "stock_zh_index_daily" not in source
    assert "IndexProviderChain" not in source
    assert "default_index_providers" not in source


def test_package_root_import_defers_new_modules_repository_pyarrow_and_akshare() -> None:
    completed = run_isolated("""
import sys
import autowealth
before = set(sys.modules)
import autowealth.market_data as market_data
assert "autowealth.market_data.akshare_adapters" not in sys.modules
assert "autowealth.market_data.dataframe_conversion" not in sys.modules
assert "autowealth.market_data.repositories" not in sys.modules
assert "pyarrow.parquet" not in sys.modules
assert "akshare" not in set(sys.modules) - before
assert "AKShareEODEquityProvider" in market_data.__all__
assert "convert_eod_dataframe_to_bars" in market_data.__all__
""")
    assert completed.returncode == 0, completed.stderr


def test_package_lazy_exports_load_once_without_importing_akshare() -> None:
    completed = run_isolated("""
import sys
import autowealth.market_data as market_data
first = market_data.AKShareEODEquityProvider
assert "autowealth.market_data.akshare_adapters" in sys.modules
assert "autowealth.market_data.dataframe_conversion" in sys.modules
assert "akshare" not in sys.modules
from autowealth.market_data import AKShareEODEquityProvider
assert first is AKShareEODEquityProvider
assert first is market_data.AKShareEODEquityProvider
assert market_data.convert_eod_dataframe_to_bars is market_data.convert_eod_dataframe_to_bars
try:
    market_data.UnknownAdapterExport
except AttributeError as exc:
    assert "UnknownAdapterExport" in str(exc)
else:
    raise AssertionError("unknown package attribute did not raise AttributeError")
""")
    assert completed.returncode == 0, completed.stderr


def test_adapter_import_and_default_construction_do_not_import_akshare_or_access_network() -> None:
    completed = run_isolated("""
from datetime import date
import os
import socket
import sys

before_environment = dict(os.environ)
def fail_network(*args, **kwargs):
    raise AssertionError("adapter import attempted network access")
socket.create_connection = fail_network
socket.socket.connect = fail_network
from autowealth.market_data import AKShareEODEquityProvider

class Calendar:
    def is_trading_day(self, value): return True
    def next_trading_day(self, value): return value
    def previous_trading_day(self, value): return value
    def trading_days(self, start_date, end_date): return [start_date]

provider = AKShareEODEquityProvider(Calendar())
assert provider.provider_name == "akshare_eod_equity"
assert "akshare" not in sys.modules
assert dict(os.environ) == before_environment
""")
    assert completed.returncode == 0, completed.stderr


def test_injected_endpoint_fetch_does_not_import_akshare() -> None:
    completed = run_isolated("""
from datetime import date
import sys
import pandas as pd
from autowealth.market_data import (
    AKShareEODEquityProvider, AdjustmentType, AssetType, BarFrequency,
    EODDatasetKey, EODDateRange, EODProviderRequest, Market, Venue,
)
day = date(2024, 1, 2)
class Calendar:
    def is_trading_day(self, value): return value == day
    def next_trading_day(self, value): return day
    def previous_trading_day(self, value): return day
    def trading_days(self, start_date, end_date): return [day]
def endpoint(**kwargs):
    return pd.DataFrame([{
        "date": "2024-01-02", "open": 10, "high": 11, "low": 9,
        "close": 10.5, "volume": 1000,
    }])
dataset = EODDatasetKey(Market.CN, Venue.SSE, AssetType.EQUITY, "600000.SH")
request = EODProviderRequest(dataset, EODDateRange(day, day))
result = AKShareEODEquityProvider(Calendar(), endpoint=endpoint).fetch(request)
assert result.status.value == "success"
assert "akshare" not in sys.modules
""")
    assert completed.returncode == 0, completed.stderr


def test_adapter_source_has_no_clock_environment_repository_or_business_ids() -> None:
    source = inspect.getsource(adapter_module)
    assert "datetime.now" not in source
    assert "datetime.utcnow" not in source
    assert "date.today" not in source
    assert "os.environ" not in source
    assert "requests." not in source
    assert "data_version" not in source
    assert "generation_id" not in source
    assert ".publish(" not in source


def test_public_exports_are_unique_and_only_include_approved_adapter_names() -> None:
    expected = {
        "AKShareEODEquityProvider",
        "AKShareEODIndexProvider",
        "akshare_equity_symbol",
        "akshare_index_symbol",
        "convert_eod_dataframe_to_bars",
    }
    assert expected <= set(market_data.__all__)
    assert len(market_data.__all__) == len(set(market_data.__all__))
    assert {
        "ColumnMapping",
        "EODProviderChain",
        "EODUpdateCoordinator",
        "stock_zh_index_daily",
    }.isdisjoint(market_data.__all__)


def test_converter_and_adapter_public_errors_do_not_echo_raw_values(tmp_path: Path) -> None:
    secret = "apiKey=hidden Authorization: Bearer private Cookie: session=secret"
    frame = english_frame((DAY_1,))
    frame["open"] = pd.Series([secret + str(tmp_path)], dtype="object")
    with pytest.raises(EODProviderError) as converter_error:
        convert(frame)
    public = converter_error.value.to_json()
    assert secret not in public
    assert str(tmp_path) not in public
    assert "hidden" not in public
    assert "private" not in public


def test_default_endpoint_attribute_is_resolved_only_during_fetch() -> None:
    source = inspect.getsource(adapter_module)
    assert source.count('import_module("akshare")') == 2
    assert 'getattr(ak, "stock_zh_a_hist", None)' in source
    assert 'getattr(ak, "index_zh_a_hist", None)' in source
    assert source.count("frame = endpoint(") == 2
