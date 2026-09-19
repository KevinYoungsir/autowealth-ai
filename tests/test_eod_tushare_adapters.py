from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import subprocess
import sys
import traceback

import pandas as pd
import pytest

from autowealth.market_data.provider_chain import EODProviderChain, EODProviderChainError
from autowealth.market_data.provider_resilience import (
    EODProviderRetryPolicy,
    NoOpEODProviderRateLimiter,
)
from autowealth.market_data.providers import (
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResultStatus,
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
from autowealth.market_data.tushare_adapters import TushareEODEquityProvider

ROOT = Path(__file__).resolve().parents[1]
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)


class FakeCalendar:
    def __init__(self, days: tuple[date, ...] = (DAY_1, DAY_2, DAY_3)) -> None:
        self.days = days

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) + 1]

    def previous_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) - 1]

    def trading_days(self, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(value for value in self.days if start_date <= value <= end_date)


class FakeClient:
    def __init__(self, response: object = None, error: Exception = None) -> None:
        self.response = pd.DataFrame() if response is None else response
        self.error = error
        self.calls: list[dict[str, object]] = []

    def daily(self, **kwargs: object) -> object:
        self.calls.append(dict(kwargs))
        if self.error is not None:
            raise self.error
        return self.response


class NoOpSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_dataset(
    *,
    symbol: str = "600000.SH",
    venue: Venue = Venue.SSE,
    asset_type: AssetType = AssetType.EQUITY,
    adjustment: AdjustmentType = AdjustmentType.NONE,
) -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        venue,
        asset_type,
        symbol,
        BarFrequency.DAILY,
        adjustment,
    )


def make_request(dataset: EODDatasetKey = None) -> EODProviderRequest:
    return EODProviderRequest(dataset or make_dataset(), EODDateRange(DAY_1, DAY_2))


def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "600000.SH",
                "trade_date": "20240103",
                "open": "10.20",
                "high": "10.80",
                "low": "10.10",
                "close": "10.70",
                "vol": "12.34",
                "amount": "56.789",
            },
            {
                "ts_code": "600000.sh",
                "trade_date": "20240102",
                "open": "10.00",
                "high": "10.50",
                "low": "9.90",
                "close": "10.20",
                "vol": "10.01",
                "amount": "20.345",
            },
        ]
    )


def make_provider(
    client: FakeClient, secret: str = "TEST_FIXTURE_TOKEN"
) -> TushareEODEquityProvider:
    return TushareEODEquityProvider(
        FakeCalendar(),
        token_resolver=lambda: secret,
        client_factory=lambda token: client,
    )


def test_valid_response_maps_fields_units_and_stable_order() -> None:
    client = FakeClient(valid_frame())
    result = make_provider(client).fetch(make_request())

    assert result.status is EODProviderResultStatus.SUCCESS
    assert tuple(bar.trade_date for bar in result.bars) == (DAY_1, DAY_2)
    assert result.bars[0].volume == Decimal("1001.00")
    assert result.bars[0].amount == Decimal("20345.000")
    assert result.bars[1].volume == Decimal("1234.00")
    assert result.bars[1].amount == Decimal("56789.000")
    assert result.bars[0].open == Decimal("10.00")
    assert result.bars[1].close == Decimal("10.70")
    assert client.calls == [
        {
            "ts_code": "600000.SH",
            "start_date": "20240102",
            "end_date": "20240103",
            "fields": "ts_code,trade_date,open,high,low,close,vol,amount",
        }
    ]


def test_extra_columns_are_ignored_without_expanding_eod_bar() -> None:
    frame = valid_frame()
    frame["pre_close"] = "9.90"
    frame["change"] = "0.10"
    frame["pct_chg"] = "1.01"
    result = make_provider(FakeClient(frame)).fetch(make_request())
    assert result.status is EODProviderResultStatus.SUCCESS
    assert "pre_close" not in result.bars[0].to_dict()


def test_empty_payload_is_empty_not_success() -> None:
    result = make_provider(FakeClient(pd.DataFrame())).fetch(make_request())
    assert result.status is EODProviderResultStatus.EMPTY
    assert result.bars == ()


@pytest.mark.parametrize("missing", ["ts_code", "trade_date", "open", "vol", "amount"])
def test_missing_required_columns_fail_closed(missing: str) -> None:
    frame = valid_frame().drop(columns=[missing])
    with pytest.raises(EODProviderError) as captured:
        make_provider(FakeClient(frame)).fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("open", "not-a-number"),
        ("high", "NaN"),
        ("low", "Infinity"),
        ("vol", "-1"),
        ("amount", "-1"),
    ],
)
def test_invalid_numeric_values_fail_closed(column: str, value: str) -> None:
    frame = valid_frame()
    frame.loc[0, column] = value
    with pytest.raises(EODProviderError) as captured:
        make_provider(FakeClient(frame)).fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("ts_code", "000001.SZ"),
        ("trade_date", "20240104"),
        ("trade_date", "2024-01-03"),
    ],
)
def test_wrong_identity_or_date_fails_closed(column: str, value: str) -> None:
    frame = valid_frame()
    frame.loc[0, column] = value
    with pytest.raises(EODProviderError) as captured:
        make_provider(FakeClient(frame)).fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_dates_fail_closed(conflicting: bool) -> None:
    frame = valid_frame()
    duplicate = frame.iloc[[0]].copy(deep=True)
    if conflicting:
        duplicate.loc[duplicate.index[0], "close"] = "10.60"
    frame = pd.concat([frame, duplicate], ignore_index=True)
    with pytest.raises(EODProviderError) as captured:
        make_provider(FakeClient(frame)).fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


@pytest.mark.parametrize(
    "dataset",
    [
        make_dataset(symbol="000300.SH", asset_type=AssetType.INDEX),
        make_dataset(adjustment=AdjustmentType.QFQ),
        make_dataset(adjustment=AdjustmentType.HFQ),
    ],
)
def test_unsupported_dataset_contracts_fail_before_client(dataset: EODDatasetKey) -> None:
    client = FakeClient(valid_frame())
    with pytest.raises(EODProviderError) as captured:
        make_provider(client).fetch(make_request(dataset))
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert client.calls == []


def test_unsupported_frequency_fails_before_client() -> None:
    dataset = make_dataset()
    object.__setattr__(dataset, "frequency", "weekly")
    client = FakeClient(valid_frame())
    with pytest.raises(EODProviderError) as captured:
        make_provider(client).fetch(make_request(dataset))
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert client.calls == []


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (TimeoutError("SENTINEL_TUSHARE_SECRET"), EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE),
        (
            ConnectionError("SENTINEL_TUSHARE_SECRET"),
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        ),
        (
            RuntimeError("rate limit SENTINEL_TUSHARE_SECRET"),
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        ),
        (
            RuntimeError("invalid token SENTINEL_TUSHARE_SECRET"),
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        ),
        (
            RuntimeError("permission denied SENTINEL_TUSHARE_SECRET"),
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        ),
        (
            RuntimeError("unknown SENTINEL_TUSHARE_SECRET"),
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        ),
    ],
)
def test_client_errors_use_existing_safe_taxonomy(
    error: Exception,
    expected_code: EODProviderErrorCode,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "SENTINEL_TUSHARE_SECRET"
    with pytest.raises(EODProviderError) as captured:
        make_provider(FakeClient(error=error), secret).fetch(make_request())
    assert captured.value.code is expected_code
    serialized = repr(captured.value) + captured.value.to_json()
    formatted = "".join(traceback.format_exception(captured.type, captured.value, captured.tb))
    assert "SENTINEL_TUSHARE_SECRET" not in serialized
    assert "SENTINEL_TUSHARE_SECRET" not in formatted
    assert str(error) not in formatted
    assert captured.value.__cause__ is None
    assert "SENTINEL_TUSHARE_SECRET" not in caplog.text


def test_token_resolver_exception_traceback_is_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client_calls = []

    def resolver() -> str:
        raise RuntimeError("resolver exposed SENTINEL_TUSHARE_SECRET")

    provider = TushareEODEquityProvider(
        FakeCalendar(),
        token_resolver=resolver,
        client_factory=lambda token: client_calls.append(token),  # type: ignore[arg-type]
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    formatted = "".join(traceback.format_exception(captured.type, captured.value, captured.tb))
    assert captured.value.code is EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE
    assert "The Tushare credential is unavailable." in formatted
    assert "SENTINEL_TUSHARE_SECRET" not in formatted
    assert "resolver exposed" not in formatted
    assert captured.value.__cause__ is None
    assert captured.value.__suppress_context__ is True
    assert "SENTINEL_TUSHARE_SECRET" not in caplog.text
    assert client_calls == []


@pytest.mark.parametrize(
    "code",
    [
        EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
    ],
)
def test_token_resolver_preserves_safe_provider_error(
    code: EODProviderErrorCode,
) -> None:
    safe_error = EODProviderError(code, "The resolver reported a safe provider failure.")

    def resolver() -> str:
        raise safe_error

    provider = TushareEODEquityProvider(
        FakeCalendar(),
        token_resolver=resolver,
        client_factory=lambda token: pytest.fail("client factory must not be called"),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    formatted = "".join(traceback.format_exception(captured.type, captured.value, captured.tb))
    assert captured.value is safe_error
    assert captured.value.code is code
    assert captured.value.__cause__ is None
    assert "The resolver reported a safe provider failure." in formatted


def test_missing_token_is_permanent_and_client_is_not_constructed() -> None:
    calls = []
    provider = TushareEODEquityProvider(
        FakeCalendar(),
        token_resolver=lambda: "",
        client_factory=lambda token: calls.append(token),  # type: ignore[arg-type]
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request())
    assert captured.value.code is EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE
    assert calls == []


def test_construction_does_not_resolve_token_or_construct_client() -> None:
    calls = []
    provider = TushareEODEquityProvider(
        FakeCalendar(),
        token_resolver=lambda: calls.append("token") or "secret",
        client_factory=lambda token: calls.append(token),  # type: ignore[arg-type]
    )
    assert provider.provider_name == "tushare_eod_equity"
    assert provider.endpoint_name == "daily"
    assert calls == []
    assert "secret" not in repr(provider)


def test_permanent_failure_is_not_retried_by_provider_chain() -> None:
    client = FakeClient(error=RuntimeError("invalid token"))
    provider = make_provider(client)
    sleeper = NoOpSleeper()
    chain = EODProviderChain(
        (provider,),
        retry_policy=EODProviderRetryPolicy(max_attempts=3),
        rate_limiter=NoOpEODProviderRateLimiter(),
        retry_sleeper=sleeper,
    )
    with pytest.raises(EODProviderChainError) as captured:
        chain.fetch(make_request())
    assert captured.value.final_code is EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE
    assert len(client.calls) == 1
    assert sleeper.calls == []


def test_provider_chain_owns_temporary_attempt_count() -> None:
    client = FakeClient(error=TimeoutError("temporary"))
    provider = make_provider(client)
    sleeper = NoOpSleeper()
    chain = EODProviderChain(
        (provider,),
        retry_policy=EODProviderRetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
        ),
        rate_limiter=NoOpEODProviderRateLimiter(),
        retry_sleeper=sleeper,
    )
    with pytest.raises(EODProviderChainError) as captured:
        chain.fetch(make_request())
    assert captured.value.final_code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE
    assert len(client.calls) == 3
    assert sleeper.calls == []


def test_module_import_does_not_import_sdk_or_access_network() -> None:
    script = """
import sys
import autowealth.market_data.tushare_adapters as adapter
assert "tushare" not in sys.modules
assert adapter.TushareEODEquityProvider.provider_name == "tushare_eod_equity"
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
