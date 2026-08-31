from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from datetime import date
from decimal import Decimal
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import Optional

import pandas as pd
import pytest

import autowealth.market_data as market_data
import autowealth.market_data.akshare_adapters as adapter_module
import autowealth.market_data.provider_chain as chain_module
from autowealth.market_data.akshare_adapters import (
    AKShareEODIndexDailyProvider,
    akshare_index_daily_symbol,
)
from autowealth.market_data.operation_control import (
    EODCheckpointStage,
    EODOperationControlError,
)
from autowealth.market_data.provider_resilience import EODProviderRetryPolicy
from autowealth.market_data.provider_chain import (
    EODProviderAttempt,
    EODProviderChain,
    EODProviderChainError,
    EODProviderChainResult,
)
from autowealth.market_data.providers import (
    EODProvider,
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRevisionStrategy,
)
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODWarningSeverity,
    Market,
    Venue,
)

DAY_0 = date(2024, 1, 1)
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
DAY_4 = date(2024, 1, 5)
DAY_5 = date(2024, 1, 8)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

INDEX_CAPABILITIES = (
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.INDEX,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SZSE,
        AssetType.INDEX,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
)
EQUITY_CAPABILITIES = (
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
)
_MISSING = object()


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


class FakeProvider:
    def __init__(
        self,
        provider_name: str,
        response: object,
        *,
        provider_version: str = "1",
        capabilities: object = INDEX_CAPABILITIES,
        endpoint_name: object = "fake_endpoint",
    ) -> None:
        self.provider_name = provider_name
        self.provider_version = provider_version
        self._capabilities = capabilities
        self.response = response
        self.calls: list[EODProviderRequest] = []
        if endpoint_name is not _MISSING:
            self.endpoint_name = endpoint_name

    @property
    def capabilities(self) -> object:
        if isinstance(self._capabilities, BaseException):
            raise self._capabilities
        return self._capabilities

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.calls.append(request)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response  # type: ignore[return-value]


def make_dataset(
    *,
    symbol: str = "000300.SH",
    venue: Venue = Venue.SSE,
    asset_type: AssetType = AssetType.INDEX,
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
    end: date = DAY_4,
) -> EODProviderRequest:
    return EODProviderRequest(
        dataset=dataset or make_dataset(),
        requested_range=EODDateRange(start, end),
    )


def make_bar(dataset: EODDatasetKey, trade_date: date, offset: int = 0) -> EODBar:
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=Decimal(10 + offset),
        high=Decimal(11 + offset),
        low=Decimal(9 + offset),
        close=Decimal("10.5") + offset,
        volume=Decimal(1000 + offset),
        amount=Decimal(10000 + offset),
    )


def missing_warning(*days: date) -> EODStructuredWarning:
    return EODStructuredWarning(
        code="missing_trading_days",
        severity=EODWarningSeverity.WARNING,
        message="Expected trading dates are missing from the EOD batch.",
        details={
            "dates": [day.isoformat() for day in days],
            "missing_count": len(days),
        },
    )


def make_result(
    request: EODProviderRequest,
    provider_name: str,
    status: EODProviderResultStatus,
    days: tuple[date, ...] = (DAY_1, DAY_2, DAY_3, DAY_4),
    *,
    provider_version: str = "1",
    warnings: tuple[EODStructuredWarning, ...] = (),
) -> EODProviderResult:
    bars = (
        ()
        if status is EODProviderResultStatus.EMPTY
        else tuple(make_bar(request.dataset, day, offset) for offset, day in enumerate(days))
    )
    return EODProviderResult(
        request=request,
        provider_name=provider_name,
        provider_version=provider_version,
        status=status,
        bars=bars,
        warnings=warnings,
    )


def provider_with_result(
    provider_name: str,
    request: EODProviderRequest,
    status: EODProviderResultStatus = EODProviderResultStatus.SUCCESS,
    days: tuple[date, ...] = (DAY_1, DAY_2, DAY_3, DAY_4),
    *,
    warnings: tuple[EODStructuredWarning, ...] = (),
) -> FakeProvider:
    return FakeProvider(
        provider_name,
        make_result(request, provider_name, status, days, warnings=warnings),
    )


def english_frame(
    days: tuple[object, ...] = (DAY_1, DAY_2, DAY_3, DAY_4),
    *,
    include_amount: bool = True,
) -> pd.DataFrame:
    rows = []
    for offset, trade_date in enumerate(days):
        row = {
            "date": trade_date.isoformat() if type(trade_date) is date else trade_date,
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


def run_isolated(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def success_attempt(**changes: object) -> EODProviderAttempt:
    values = {
        "position": 0,
        "provider_name": "provider_one",
        "provider_version": "1",
        "endpoint_name": "endpoint_one",
        "result_status": EODProviderResultStatus.SUCCESS,
        "error_code": None,
        "row_count": 2,
        "effective_range": EODDateRange(DAY_1, DAY_2),
        "warning_codes": (),
        "selected": True,
        "safe_message": "The EOD provider returned a complete validated result.",
    }
    values.update(changes)
    return EODProviderAttempt(**values)  # type: ignore[arg-type]


def test_chain_accepts_exact_tuple_and_list_without_mutating_input() -> None:
    request = make_request()
    first = provider_with_result("first", request)
    supplied = [first]
    from_list = EODProviderChain(supplied).fetch(request)
    from_tuple = EODProviderChain((first,)).fetch(request)
    assert supplied == [first]
    assert from_list.to_json() == from_tuple.to_json()


@pytest.mark.parametrize("providers", [(), [], iter(())])
def test_chain_rejects_empty_or_non_exact_provider_sequences(providers: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EODProviderChain(providers)  # type: ignore[arg-type]


def test_chain_rejects_more_than_32_providers() -> None:
    request = make_request()
    providers = [provider_with_result(f"provider_{position}", request) for position in range(33)]
    with pytest.raises(ValueError, match="more than 32"):
        EODProviderChain(providers)


def test_chain_accepts_exactly_32_unique_providers() -> None:
    request = make_request()
    providers = [
        error_provider(
            f"provider_{position}",
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        )
        for position in range(32)
    ]
    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain(providers).fetch(request)
    assert len(captured.value.attempts) == 32


def test_chain_rejects_non_provider_duplicate_object_identity_and_nested_chain() -> None:
    request = make_request()
    provider = provider_with_result("provider_one", request)
    with pytest.raises(TypeError, match="EODProvider"):
        EODProviderChain([object()])
    with pytest.raises(ValueError, match="same object"):
        EODProviderChain([provider, provider])
    with pytest.raises(TypeError, match="EODProvider"):
        EODProviderChain([EODProviderChain([provider])])


def test_chain_rejects_duplicate_provider_name_and_version() -> None:
    request = make_request()
    providers = [
        provider_with_result("duplicate", request),
        provider_with_result("duplicate", request),
    ]
    with pytest.raises(ValueError, match="duplicate provider identities"):
        EODProviderChain(providers)


def test_chain_preserves_provider_order_and_is_not_an_eod_provider() -> None:
    request = make_request()
    unavailable = EODProviderError(
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        "The provider is unavailable.",
    )
    first = FakeProvider("first", unavailable)
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert [attempt.provider_name for attempt in result.attempts] == ["first", "second"]
    assert not isinstance(EODProviderChain([second]), EODProvider)


def test_attempt_normalizes_warning_codes_and_serializes_deterministically() -> None:
    attempt = success_attempt(warning_codes=["z_warning", "a_warning", "z_warning"])
    assert attempt.warning_codes == ("a_warning", "z_warning")
    assert attempt.role == "primary"
    assert attempt.status == "success"
    assert attempt.reason_code == "success"
    assert attempt.retryable is False
    assert attempt.to_json() == attempt.to_json()
    assert json.loads(attempt.to_json()) == attempt.to_dict()


def test_attempt_is_frozen_and_fallback_role_is_derived() -> None:
    attempt = success_attempt(position=2)
    assert attempt.role == "fallback"
    with pytest.raises(FrozenInstanceError):
        attempt.selected = False  # type: ignore[misc]


@pytest.mark.parametrize("position", [-1, True, 1.0])
def test_attempt_rejects_invalid_positions(position: object) -> None:
    with pytest.raises(ValueError, match="position"):
        success_attempt(position=position)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("provider_name", ""),
        ("provider_name", "C:\\private\\provider"),
        ("provider_version", "apiKey=secret"),
        ("endpoint_name", "https://example.com/path"),
        ("endpoint_name", "endpoint?token=secret"),
    ],
)
def test_attempt_rejects_unsafe_identifiers(field_name: str, value: str) -> None:
    with pytest.raises(ValueError):
        success_attempt(**{field_name: value})


@pytest.mark.parametrize(
    "message",
    [
        "",
        "C:\\private\\provider.log",
        "Authorization: Bearer secret",
        "Traceback (most recent call last): hidden",
        "x" * 513,
    ],
)
def test_attempt_rejects_unsafe_messages(message: str) -> None:
    with pytest.raises(ValueError, match="safe_message"):
        success_attempt(safe_message=message)


def test_attempt_enforces_result_error_shape_and_selected_rules() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        success_attempt(error_code=EODProviderErrorCode.PROVIDER_UNAVAILABLE)
    with pytest.raises(ValueError, match="exactly one"):
        success_attempt(result_status=None)
    with pytest.raises(ValueError, match="empty attempt"):
        success_attempt(
            result_status=EODProviderResultStatus.EMPTY,
            row_count=0,
            effective_range=None,
        )
    with pytest.raises(ValueError, match="error attempt"):
        success_attempt(
            result_status=None,
            error_code=EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            row_count=1,
        )


@pytest.mark.parametrize(
    ("error_code", "expected_status", "retryable"),
    [
        (EODProviderErrorCode.UNSUPPORTED_REQUEST, "unsupported", False),
        (EODProviderErrorCode.PROVIDER_UNAVAILABLE, "unavailable", False),
        (EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE, "temporary_failure", True),
        (EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE, "permanent_failure", False),
        (EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, "malformed", False),
    ],
)
def test_attempt_error_status_and_retryable_mapping(
    error_code: EODProviderErrorCode,
    expected_status: str,
    retryable: bool,
) -> None:
    attempt = success_attempt(
        result_status=None,
        error_code=error_code,
        row_count=0,
        effective_range=None,
        warning_codes=(),
        selected=False,
    )
    assert attempt.status == expected_status
    assert attempt.reason_code == error_code.value
    assert attempt.retryable is retryable


def test_attempt_json_excludes_bars_request_time_uuid_traceback_and_metadata() -> None:
    payload = success_attempt().to_dict()
    forbidden = {
        "bars",
        "request",
        "started_at",
        "completed_at",
        "duration",
        "uuid",
        "traceback",
        "exception_type",
        "source_metadata",
    }
    assert forbidden.isdisjoint(payload)


def test_first_success_stops_fallback_and_preserves_request() -> None:
    request = make_request()
    before = request.to_json()
    first = provider_with_result("first", request)
    second = FakeProvider("second", AssertionError("fallback must not run"))
    result = EODProviderChain([first, second]).fetch(request)
    assert result.selected_provider_name == "first"
    assert result.selected_provider_version == "1"
    assert result.selected_position == 0
    assert result.result_status is EODProviderResultStatus.SUCCESS
    assert result.is_complete is True
    assert len(first.calls) == 1
    assert second.calls == []
    assert request.to_json() == before


@pytest.mark.parametrize(
    "error_code",
    [
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
    ],
)
def test_provider_error_falls_back_to_success(error_code: EODProviderErrorCode) -> None:
    request = make_request()
    first = FakeProvider(
        "first",
        EODProviderError(error_code, "The provider failed safely."),
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert result.selected_position == 1
    assert result.attempts[0].error_code is error_code
    assert result.attempts[1].selected is True
    assert len(first.calls) == len(second.calls) == 1


def test_unsupported_capability_skips_fetch_and_continues() -> None:
    request = make_request()
    first = FakeProvider(
        "first",
        AssertionError("unsupported provider fetch must not run"),
        capabilities=EQUITY_CAPABILITIES,
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert first.calls == []
    assert result.attempts[0].status == "unsupported"
    assert result.selected_position == 1


@pytest.mark.parametrize(
    "capabilities",
    [
        ValueError("apiKey=hidden C:\\private\\capabilities"),
        object(),
        (object(),),
        (INDEX_CAPABILITIES[0], INDEX_CAPABILITIES[0]),
        (
            INDEX_CAPABILITIES[0],
            EODProviderCapability(
                Market.CN,
                Venue.SSE,
                AssetType.INDEX,
                BarFrequency.DAILY,
                AdjustmentType.NONE,
                EODRevisionStrategy.FULL_REFRESH_REQUIRED,
            ),
        ),
    ],
)
def test_malformed_or_exceptional_capabilities_fail_closed_without_fetch(
    capabilities: object,
) -> None:
    request = make_request()
    first = FakeProvider(
        "first",
        AssertionError("malformed provider fetch must not run"),
        capabilities=capabilities,
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    attempt = result.attempts[0]
    assert first.calls == []
    assert attempt.error_code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD
    assert "hidden" not in attempt.to_json()
    assert "private" not in attempt.to_json()


def test_missing_endpoint_name_is_allowed() -> None:
    request = make_request()
    provider = FakeProvider(
        "provider_one",
        make_result(request, "provider_one", EODProviderResultStatus.SUCCESS),
        endpoint_name=_MISSING,
    )
    result = EODProviderChain([provider]).fetch(request)
    assert result.attempts[0].endpoint_name is None


@pytest.mark.parametrize(
    "endpoint_name",
    [
        "https://example.com/endpoint",
        "C:\\private\\endpoint",
        "endpoint?apiKey=hidden",
    ],
)
def test_unsafe_endpoint_name_is_malformed_and_not_called(endpoint_name: str) -> None:
    request = make_request()
    first = FakeProvider(
        "first",
        AssertionError("unsafe endpoint provider must not run"),
        endpoint_name=endpoint_name,
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert first.calls == []
    assert result.attempts[0].status == "malformed"
    assert endpoint_name not in result.to_json()


def test_capability_precheck_occurs_before_endpoint_name_read() -> None:
    request = make_request()
    provider = RaisingEndpointNameProvider(
        "unsupported",
        AssertionError("provider must not run"),
        capabilities=EQUITY_CAPABILITIES,
    )
    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain([provider]).fetch(request)
    assert captured.value.final_code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert captured.value.attempts[0].endpoint_name is None
    assert provider.calls == []


class RaisingEndpointNameProvider(FakeProvider):
    @property
    def endpoint_name(self) -> str:
        raise ValueError("Authorization: Bearer hidden C:\\private\\endpoint")

    @endpoint_name.setter
    def endpoint_name(self, value: object) -> None:
        pass


def test_endpoint_name_property_exception_is_safely_classified() -> None:
    request = make_request()
    first = RaisingEndpointNameProvider(
        "first",
        AssertionError("provider must not run"),
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert first.calls == []
    assert result.attempts[0].status == "malformed"
    assert "hidden" not in result.to_json()
    assert "private" not in result.to_json()


def test_empty_result_continues_to_success_and_preserves_empty_warning() -> None:
    request = make_request()
    first = provider_with_result("first", request, EODProviderResultStatus.EMPTY, ())
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert result.attempts[0].status == "empty"
    assert result.attempts[0].warning_codes == ("empty_response",)
    assert result.selected_position == 1


def test_partial_result_continues_to_complete_success() -> None:
    request = make_request()
    first = provider_with_result(
        "first",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
        warnings=(missing_warning(DAY_3, DAY_4),),
    )
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert result.selected_position == 1
    assert result.attempts[0].status == "partial"
    assert result.attempts[0].selected is False
    assert result.attempts[0].warning_codes == ("missing_trading_days",)


@pytest.mark.parametrize(
    ("mutation", "expected_field"),
    [
        ("not_result", "result"),
        ("request", "request"),
        ("provider_name", "provider_name"),
        ("provider_version", "provider_version"),
    ],
)
def test_result_identity_mismatch_is_malformed_and_falls_back(
    mutation: str,
    expected_field: str,
) -> None:
    request = make_request()
    if mutation == "not_result":
        response: object = object()
    elif mutation == "request":
        other_request = make_request(start=DAY_2, end=DAY_4)
        response = make_result(
            other_request,
            "first",
            EODProviderResultStatus.SUCCESS,
            (DAY_2, DAY_3, DAY_4),
        )
    elif mutation == "provider_name":
        response = make_result(request, "different", EODProviderResultStatus.SUCCESS)
    else:
        response = make_result(
            request,
            "first",
            EODProviderResultStatus.SUCCESS,
            provider_version="2",
        )
    first = FakeProvider("first", response)
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    assert result.attempts[0].status == "malformed"
    assert result.attempts[0].selected is False
    assert result.selected_position == 1
    assert expected_field


def test_ordinary_exception_is_safely_wrapped_and_falls_back() -> None:
    request = make_request()
    secret = "apiKey=hidden Authorization: Bearer private C:\\private\\response"
    first = FakeProvider("first", RuntimeError(secret))
    second = provider_with_result("second", request)
    result = EODProviderChain([first, second]).fetch(request)
    attempt = result.attempts[0]
    assert attempt.error_code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert secret not in attempt.to_json()
    assert "hidden" not in result.to_json()
    assert "private" not in result.to_json()


@pytest.mark.parametrize("raised", [KeyboardInterrupt(), SystemExit(), GeneratorExit()])
def test_base_exceptions_are_not_caught(raised: BaseException) -> None:
    request = make_request()
    first = FakeProvider("first", raised)
    second = provider_with_result("second", request)
    with pytest.raises(type(raised)):
        EODProviderChain([first, second]).fetch(request)
    assert len(first.calls) == 1
    assert second.calls == []


def test_single_partial_is_returned_after_later_failure() -> None:
    request = make_request()
    warning = missing_warning(DAY_3, DAY_4)
    partial = provider_with_result(
        "partial",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
        warnings=(warning,),
    )
    unavailable = FakeProvider(
        "unavailable",
        EODProviderError(
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            "The provider is unavailable.",
        ),
    )
    result = EODProviderChain([partial, unavailable]).fetch(request)
    assert result.selected_result is partial.response
    assert result.selected_position == 0
    assert result.is_complete is False
    assert result.attempts[0].selected is True
    assert result.attempts[1].selected is False
    assert result.selected_result.warnings == (warning,)


def test_best_partial_prefers_more_rows() -> None:
    request = make_request()
    shorter = provider_with_result(
        "shorter",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
    )
    longer = provider_with_result(
        "longer",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2, DAY_3),
    )
    result = EODProviderChain([shorter, longer]).fetch(request)
    assert result.selected_position == 1
    assert [attempt.selected for attempt in result.attempts] == [False, True]


def test_best_partial_prefers_earlier_start_then_later_end_then_position() -> None:
    request = make_request()
    later_start = provider_with_result(
        "later_start",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_2, DAY_3),
    )
    earlier_start = provider_with_result(
        "earlier_start",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
    )
    assert EODProviderChain([later_start, earlier_start]).fetch(request).selected_position == 1

    earlier_end = provider_with_result(
        "earlier_end",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
    )
    later_end = provider_with_result(
        "later_end",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_3),
    )
    assert EODProviderChain([earlier_end, later_end]).fetch(request).selected_position == 1

    first = provider_with_result(
        "first",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
    )
    second = provider_with_result(
        "second",
        request,
        EODProviderResultStatus.PARTIAL_SUCCESS,
        (DAY_1, DAY_2),
    )
    assert EODProviderChain([first, second]).fetch(request).selected_position == 0


def test_chain_result_is_frozen_validates_selected_attempt_and_keeps_bars_once() -> None:
    request = make_request()
    provider = provider_with_result("provider_one", request)
    result = EODProviderChain([provider]).fetch(request)
    assert type(result.attempts) is tuple
    assert result.attempts[0].row_count == len(result.selected_result.bars)
    assert "bars" in result.to_dict()["selected_result"]
    assert "bars" not in result.to_dict()["attempts"][0]
    assert result.to_json() == result.to_json()
    with pytest.raises(FrozenInstanceError):
        result.selected_position = 1  # type: ignore[misc]
    with pytest.raises(ValueError, match="exactly one"):
        EODProviderChainResult(
            request,
            result.selected_result,
            0,
            [replace_attempt(result.attempts[0], selected=False)],
        )


def replace_attempt(
    attempt: EODProviderAttempt,
    *,
    selected: bool,
) -> EODProviderAttempt:
    values = attempt.to_dict()
    return EODProviderAttempt(
        position=attempt.position,
        provider_name=attempt.provider_name,
        provider_version=attempt.provider_version,
        endpoint_name=attempt.endpoint_name,
        result_status=attempt.result_status,
        error_code=attempt.error_code,
        row_count=attempt.row_count,
        effective_range=attempt.effective_range,
        warning_codes=attempt.warning_codes,
        selected=selected,
        safe_message=str(values["safe_message"]),
    )


def error_provider(name: str, code: EODProviderErrorCode) -> FakeProvider:
    return FakeProvider(name, EODProviderError(code, "The provider failed safely."))


def capture_chain_error(providers: list[FakeProvider]) -> EODProviderChainError:
    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain(providers).fetch(make_request())
    return captured.value


def test_all_unavailable_raises_deterministic_chain_error() -> None:
    error = capture_chain_error(
        [
            error_provider("first", EODProviderErrorCode.PROVIDER_UNAVAILABLE),
            error_provider("second", EODProviderErrorCode.PROVIDER_UNAVAILABLE),
        ]
    )
    assert error.final_code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert error.retryable is False
    assert type(error.attempts) is tuple
    assert [attempt.position for attempt in error.attempts] == [0, 1]
    assert error.to_json() == error.to_json()
    assert "__cause__" not in error.to_json()
    assert "traceback" not in error.to_json().lower()


def test_all_unsupported_returns_unsupported_without_calling_fetch() -> None:
    request = make_request()
    providers = [
        FakeProvider("first", AssertionError("must not run"), capabilities=EQUITY_CAPABILITIES),
        FakeProvider("second", AssertionError("must not run"), capabilities=EQUITY_CAPABILITIES),
    ]
    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain(providers).fetch(request)
    assert captured.value.final_code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert [provider.calls for provider in providers] == [[], []]


def test_all_empty_and_empty_unavailable_aggregate_as_unavailable() -> None:
    request = make_request()
    empty = provider_with_result("empty", request, EODProviderResultStatus.EMPTY, ())
    with pytest.raises(EODProviderChainError) as all_empty:
        EODProviderChain([empty]).fetch(request)
    assert all_empty.value.final_code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert all_empty.value.attempts[0].warning_codes == ("empty_response",)

    second_empty = provider_with_result("second_empty", request, EODProviderResultStatus.EMPTY, ())
    unavailable = error_provider("unavailable", EODProviderErrorCode.PROVIDER_UNAVAILABLE)
    with pytest.raises(EODProviderChainError) as mixed:
        EODProviderChain([second_empty, unavailable]).fetch(request)
    assert mixed.value.final_code is EODProviderErrorCode.PROVIDER_UNAVAILABLE


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        (
            [
                EODProviderErrorCode.UNSUPPORTED_REQUEST,
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            ],
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        ),
        (
            [
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            ],
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
        ),
        (
            [
                EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            ],
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        ),
        (
            [
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            ],
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        ),
        (
            [
                EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
                EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            ],
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
        ),
        (
            [
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
            ],
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        ),
    ],
)
def test_all_failed_uses_fixed_priority(
    codes: list[EODProviderErrorCode],
    expected: EODProviderErrorCode,
) -> None:
    error = capture_chain_error(
        [error_provider(f"provider_{index}", code) for index, code in enumerate(codes)]
    )
    assert error.final_code is expected
    assert error.retryable is (expected is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE)


def test_chain_error_preserves_runtime_cause_but_never_serializes_it() -> None:
    secret = "apiKey=hidden C:\\private\\response"
    provider = FakeProvider("provider_one", RuntimeError(secret))
    error = capture_chain_error([provider])
    assert type(error.__cause__) is RuntimeError
    serialized = error.to_json()
    assert secret not in serialized
    assert "hidden" not in serialized
    assert "private" not in serialized
    assert "cause" not in serialized


def test_chain_error_rejects_empty_or_selected_attempts() -> None:
    request = make_request()
    with pytest.raises(ValueError, match="cannot be empty"):
        EODProviderChainError(
            request,
            (),
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            "No EOD provider returned usable data for the request.",
        )
    with pytest.raises(ValueError, match="cannot be selected"):
        EODProviderChainError(
            request,
            (success_attempt(),),
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            "No EOD provider returned usable data for the request.",
        )


def test_provider_fetch_is_called_at_most_once_per_chain_run() -> None:
    request = make_request()
    providers = [
        error_provider("first", EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE),
        error_provider("second", EODProviderErrorCode.PROVIDER_UNAVAILABLE),
    ]
    with pytest.raises(EODProviderChainError):
        EODProviderChain(providers).fetch(request)
    assert [len(provider.calls) for provider in providers] == [1, 1]


def test_fallback_provider_identity_protocol_and_capabilities() -> None:
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=lambda **kwargs: pd.DataFrame(),
    )
    assert isinstance(provider, EODProvider)
    assert provider.provider_name == "akshare_eod_index_daily"
    assert provider.provider_version == "1"
    assert provider.endpoint_name == "stock_zh_index_daily"
    assert type(provider.capabilities) is tuple
    assert len(provider.capabilities) == 2
    assert {capability.venue for capability in provider.capabilities} == {
        Venue.SSE,
        Venue.SZSE,
    }
    assert all(capability.asset_type is AssetType.INDEX for capability in provider.capabilities)
    assert all(
        capability.adjustment_type is AdjustmentType.NONE for capability in provider.capabilities
    )
    assert all(
        capability.revision_strategy is EODRevisionStrategy.APPEND_ONLY
        for capability in provider.capabilities
    )


@pytest.mark.parametrize(
    ("symbol", "venue", "expected"),
    [
        ("000001.SH", Venue.SSE, "sh000001"),
        ("000300.SH", Venue.SSE, "sh000300"),
        ("000905.SH", Venue.SSE, "sh000905"),
        ("000852.SH", Venue.SSE, "sh000852"),
        ("399001.SZ", Venue.SZSE, "sz399001"),
        ("399006.SZ", Venue.SZSE, "sz399006"),
    ],
)
def test_fallback_symbol_mapping(symbol: str, venue: Venue, expected: str) -> None:
    dataset = make_dataset(symbol=symbol, venue=venue)
    assert akshare_index_daily_symbol(dataset) == expected


def test_fallback_symbol_rejects_raw_equity_adjusted_and_unknown_values() -> None:
    with pytest.raises(TypeError, match="exact EODDatasetKey"):
        akshare_index_daily_symbol("000300.SH")  # type: ignore[arg-type]
    with pytest.raises(EODProviderError) as equity:
        akshare_index_daily_symbol(
            make_dataset(
                symbol="600000.SH",
                asset_type=AssetType.EQUITY,
            )
        )
    assert equity.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    for adjustment in (AdjustmentType.QFQ, AdjustmentType.HFQ):
        with pytest.raises(EODProviderError):
            akshare_index_daily_symbol(make_dataset(adjustment=adjustment))
    with pytest.raises(EODProviderError):
        akshare_index_daily_symbol(make_dataset(symbol="000002.SH"))


def test_fallback_endpoint_receives_only_exchange_prefixed_symbol_once() -> None:
    endpoint = RecordingEndpoint(english_frame((DAY_1, DAY_2)))
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    result = provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert result.status is EODProviderResultStatus.SUCCESS
    assert endpoint.calls == [{"symbol": "sh000300"}]
    assert {"start_date", "end_date", "period", "adjust", "timeout", "retry"}.isdisjoint(
        endpoint.calls[0]
    )


def test_fallback_full_history_is_filtered_to_closed_range_without_mutation() -> None:
    frame = english_frame((DAY_0, DAY_1, DAY_2, DAY_3, DAY_4, DAY_5))
    snapshot = frame.copy(deep=True)
    endpoint = RecordingEndpoint(frame)
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
        endpoint=endpoint,
    )
    result = provider.fetch(make_request())
    assert tuple(bar.trade_date for bar in result.bars) == (DAY_1, DAY_2, DAY_3, DAY_4)
    pd.testing.assert_frame_equal(frame, snapshot)


@pytest.mark.parametrize("date_column", ["date", "日期"])
def test_fallback_accepts_one_english_or_chinese_date_column(date_column: str) -> None:
    frame = english_frame((DAY_0, DAY_1, DAY_2, DAY_5))
    if date_column == "日期":
        frame = frame.rename(
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
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    result = provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert result.status is EODProviderResultStatus.SUCCESS


def test_fallback_rejects_date_alias_conflict_and_duplicate_physical_columns() -> None:
    aliases = english_frame((DAY_1, DAY_2))
    aliases["日期"] = aliases["date"]
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(aliases),
    )
    with pytest.raises(EODProviderError, match="ambiguous"):
        provider.fetch(make_request(start=DAY_1, end=DAY_2))

    duplicate = pd.DataFrame(
        [["2024-01-02", 10, 11, 9, 10.5, 1000, 10000, 1000]],
        columns=["date", "open", "high", "low", "close", "volume", "amount", "volume"],
    )
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1,)),
        endpoint=RecordingEndpoint(duplicate),
    )
    with pytest.raises(EODProviderError, match="duplicate column"):
        provider.fetch(make_request(start=DAY_1, end=DAY_1))


def test_fallback_rejects_invalid_date_even_when_other_rows_are_outside_range() -> None:
    frame = english_frame(("not-a-date", DAY_1, DAY_2))
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_fallback_filters_valid_out_of_range_row_before_numeric_validation() -> None:
    frame = english_frame((DAY_0, DAY_1, DAY_2))
    frame["open"] = frame["open"].astype("object")
    frame.loc[0, "open"] = "malformed outside requested range"
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    result = provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert result.status is EODProviderResultStatus.SUCCESS


def test_fallback_rejects_malformed_in_range_row() -> None:
    frame = english_frame((DAY_0, DAY_1, DAY_2))
    frame.loc[1, "close"] = "malformed inside requested range"
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD


def test_fallback_allows_missing_amount_column() -> None:
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(english_frame((DAY_1, DAY_2), include_amount=False)),
    )
    result = provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert result.status is EODProviderResultStatus.SUCCESS
    assert all(bar.amount is None for bar in result.bars)


def test_fallback_rejects_duplicate_dates_inside_requested_range() -> None:
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(english_frame((DAY_1, DAY_1, DAY_2))),
    )
    with pytest.raises(EODProviderError, match="duplicate trading"):
        provider.fetch(make_request(start=DAY_1, end=DAY_2))


@pytest.mark.parametrize(
    ("frame", "expected_status", "warning_codes"),
    [
        (
            english_frame((DAY_1, DAY_2)),
            EODProviderResultStatus.SUCCESS,
            (),
        ),
        (
            english_frame((DAY_1,)),
            EODProviderResultStatus.PARTIAL_SUCCESS,
            ("missing_trading_days",),
        ),
        (
            pd.DataFrame(),
            EODProviderResultStatus.EMPTY,
            ("empty_response",),
        ),
    ],
)
def test_fallback_returns_validated_success_partial_and_empty_results(
    frame: pd.DataFrame,
    expected_status: EODProviderResultStatus,
    warning_codes: tuple[str, ...],
) -> None:
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=RecordingEndpoint(frame),
    )
    result = provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert result.status is expected_status
    assert tuple(warning.code for warning in result.warnings) == warning_codes


def test_fallback_rejects_non_dataframe_and_safely_wraps_endpoint_exception() -> None:
    calendar = StaticTradingCalendar((DAY_1, DAY_2))
    non_frame = AKShareEODIndexDailyProvider(
        calendar,
        endpoint=RecordingEndpoint([]),
    )
    with pytest.raises(EODProviderError) as malformed:
        non_frame.fetch(make_request(start=DAY_1, end=DAY_2))
    assert malformed.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD

    secret = "apiKey=hidden C:\\private\\response"
    unavailable = AKShareEODIndexDailyProvider(
        calendar,
        endpoint=RecordingEndpoint(RuntimeError(secret)),
    )
    with pytest.raises(EODProviderError) as captured:
        unavailable.fetch(make_request(start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert secret not in captured.value.to_json()
    assert "hidden" not in captured.value.to_json()


@pytest.mark.parametrize("module_value", [RuntimeError("apiKey=hidden"), object()])
def test_fallback_default_endpoint_resolution_fails_safely_without_network(
    monkeypatch: pytest.MonkeyPatch,
    module_value: object,
) -> None:
    def resolve_module(name: str) -> object:
        assert name == "akshare"
        if isinstance(module_value, BaseException):
            raise module_value
        return module_value

    monkeypatch.setattr(adapter_module, "import_module", resolve_module)
    provider = AKShareEODIndexDailyProvider(StaticTradingCalendar((DAY_1, DAY_2)))
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "hidden" not in captured.value.to_json()


def test_fallback_rejects_request_without_trading_days_before_endpoint() -> None:
    endpoint = RecordingEndpoint(AssertionError("endpoint must not run"))
    provider = AKShareEODIndexDailyProvider(StaticTradingCalendar(()), endpoint=endpoint)
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert endpoint.calls == []


@pytest.mark.parametrize(
    "dataset",
    [
        make_dataset(symbol="600000.SH", asset_type=AssetType.EQUITY),
        make_dataset(adjustment=AdjustmentType.QFQ),
        make_dataset(adjustment=AdjustmentType.HFQ),
    ],
)
def test_fallback_capability_rejects_unsupported_request_without_endpoint(
    dataset: EODDatasetKey,
) -> None:
    endpoint = RecordingEndpoint(AssertionError("endpoint must not run"))
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    with pytest.raises(EODProviderError) as captured:
        provider.fetch(make_request(dataset, start=DAY_1, end=DAY_2))
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert endpoint.calls == []


def test_fallback_requires_exact_request_and_does_not_modify_it() -> None:
    endpoint = RecordingEndpoint(english_frame((DAY_1, DAY_2)))
    provider = AKShareEODIndexDailyProvider(
        StaticTradingCalendar((DAY_1, DAY_2)),
        endpoint=endpoint,
    )
    with pytest.raises(TypeError, match="exact EODProviderRequest"):
        provider.fetch(object())  # type: ignore[arg-type]
    request = make_request(start=DAY_1, end=DAY_2)
    before = request.to_json()
    provider.fetch(request)
    assert request.to_json() == before


def test_fallback_adapter_is_independent_and_does_not_call_primary_endpoints() -> None:
    source = inspect.getsource(AKShareEODIndexDailyProvider)
    assert 'getattr(ak, "stock_zh_index_daily", None)' in source
    assert "index_zh_a_hist" not in source
    assert "stock_zh_a_hist" not in source
    assert "IndexProviderChain" not in source
    assert "default_index_providers" not in source


def test_package_root_import_keeps_chain_adapter_converter_repository_and_akshare_lazy() -> None:
    completed = run_isolated("""
import sys
import autowealth
before = set(sys.modules)
import autowealth.market_data as market_data
assert "autowealth.market_data.provider_chain" not in sys.modules
assert "autowealth.market_data.akshare_adapters" not in sys.modules
assert "autowealth.market_data.dataframe_conversion" not in sys.modules
assert "autowealth.market_data.repositories" not in sys.modules
assert "pyarrow.parquet" not in sys.modules
assert "akshare" not in set(sys.modules) - before
assert "EODProviderChain" in market_data.__all__
assert "AKShareEODIndexDailyProvider" in market_data.__all__
""")
    assert completed.returncode == 0, completed.stderr


def test_explicit_chain_import_does_not_load_adapter_pandas_repository_pyarrow_or_akshare() -> None:
    completed = run_isolated("""
import sys
import autowealth
before = set(sys.modules)
from autowealth.market_data.provider_chain import EODProviderChain
new_modules = set(sys.modules) - before
assert "autowealth.market_data.akshare_adapters" not in sys.modules
assert "autowealth.market_data.dataframe_conversion" not in sys.modules
assert "autowealth.market_data.repositories" not in sys.modules
assert "pyarrow" not in {name.split(".", 1)[0] for name in new_modules}
assert "akshare" not in new_modules
assert EODProviderChain.__name__ == "EODProviderChain"
""")
    assert completed.returncode == 0, completed.stderr


def test_package_lazy_chain_and_fallback_exports_load_once_without_akshare() -> None:
    completed = run_isolated("""
import sys
import autowealth.market_data as market_data
chain = market_data.EODProviderChain
assert "autowealth.market_data.provider_chain" in sys.modules
assert "autowealth.market_data.akshare_adapters" not in sys.modules
assert "akshare" not in sys.modules
assert chain is market_data.EODProviderChain
fallback = market_data.AKShareEODIndexDailyProvider
assert "autowealth.market_data.akshare_adapters" in sys.modules
assert "akshare" not in sys.modules
assert fallback is market_data.AKShareEODIndexDailyProvider
assert len(market_data.__all__) == len(set(market_data.__all__))
try:
    market_data.UnknownProviderChainExport
except AttributeError:
    pass
else:
    raise AssertionError("unknown package attribute did not raise AttributeError")
""")
    assert completed.returncode == 0, completed.stderr


def test_fallback_default_construction_and_injected_fetch_do_not_import_akshare() -> None:
    completed = run_isolated("""
from datetime import date
import sys
import pandas as pd
from autowealth.market_data import (
    AKShareEODIndexDailyProvider, AssetType, EODDatasetKey, EODDateRange,
    EODProviderRequest, Market, Venue,
)
day = date(2024, 1, 2)
class Calendar:
    def is_trading_day(self, value): return value == day
    def next_trading_day(self, value): return day
    def previous_trading_day(self, value): return day
    def trading_days(self, start_date, end_date): return [day]
provider = AKShareEODIndexDailyProvider(Calendar())
assert "akshare" not in sys.modules
def endpoint(**kwargs):
    return pd.DataFrame([{
        "date": "2024-01-02", "open": 10, "high": 11, "low": 9,
        "close": 10.5, "volume": 1000,
    }])
provider = AKShareEODIndexDailyProvider(Calendar(), endpoint=endpoint)
dataset = EODDatasetKey(Market.CN, Venue.SSE, AssetType.INDEX, "000300.SH")
request = EODProviderRequest(dataset, EODDateRange(day, day))
assert provider.fetch(request).status.value == "success"
assert "akshare" not in sys.modules
""")
    assert completed.returncode == 0, completed.stderr


def test_chain_source_has_no_clock_uuid_environment_repository_or_external_imports() -> None:
    source = inspect.getsource(chain_module)
    forbidden = (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "uuid",
        "os.environ",
        "repository",
        "data_version",
        "generation_id",
        "pandas",
        "pyarrow",
        "akshare_adapters",
        "dataframe_conversion",
    )
    assert all(value not in source for value in forbidden)


def test_chain_and_fallback_files_parse_with_python_39_grammar() -> None:
    paths = (
        REPOSITORY_ROOT / "autowealth" / "market_data" / "provider_chain.py",
        REPOSITORY_ROOT / "autowealth" / "market_data" / "akshare_adapters.py",
        REPOSITORY_ROOT / "autowealth" / "market_data" / "__init__.py",
        Path(__file__),
    )
    for path in paths:
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=(3, 9),
        )


def test_public_exports_are_exactly_additive_and_do_not_expose_chain_internals() -> None:
    expected = {
        "EODProviderAttempt",
        "EODProviderChainResult",
        "EODProviderChainError",
        "EODProviderChain",
        "AKShareEODIndexDailyProvider",
        "akshare_index_daily_symbol",
    }
    assert expected <= set(market_data.__all__)
    assert len(market_data.__all__) == len(set(market_data.__all__))
    assert {
        "_MAX_EOD_PROVIDER_ATTEMPTS",
        "_partial_rank",
        "_filter_index_daily_frame",
        "default_eod_provider_chain",
        "default_eod_index_providers",
    }.isdisjoint(market_data.__all__)


def test_checkpoints_cover_retry_fallback_and_success_in_order() -> None:
    request = make_request()

    class SequenceProvider(FakeProvider):
        def __init__(self, provider_name: str, responses: list[object]) -> None:
            super().__init__(provider_name, object())
            self.responses = responses

        def fetch(self, value: EODProviderRequest) -> EODProviderResult:
            self.calls.append(value)
            response = self.responses.pop(0)
            if isinstance(response, BaseException):
                raise response
            return response  # type: ignore[return-value]

    primary = SequenceProvider(
        "primary",
        [
            EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The primary provider failed temporarily.",
            ),
            EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The primary provider is unavailable.",
            ),
        ],
    )
    fallback = provider_with_result("fallback", request)
    checkpoints = []

    def checkpoint(stage: EODCheckpointStage, dataset: Optional[EODDatasetKey]) -> None:
        checkpoints.append((stage, dataset))

    result = EODProviderChain(
        [primary, fallback],
        retry_policy=EODProviderRetryPolicy(
            max_attempts=2,
            initial_backoff_seconds=0,
        ),
    ).fetch(request, checkpoint=checkpoint)

    assert result.selected_provider_name == "fallback"
    assert [len(primary.calls), len(fallback.calls)] == [2, 1]
    assert checkpoints == [
        (EODCheckpointStage.BEFORE_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.AFTER_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.BEFORE_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.AFTER_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.BEFORE_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.AFTER_PROVIDER_INVOCATION, request.dataset),
        (EODCheckpointStage.AFTER_PROVIDER_STAGE, request.dataset),
    ]


def test_checkpoint_control_error_propagates_before_provider_side_effect() -> None:
    request = make_request()
    provider = provider_with_result("provider", request)
    error = EODOperationControlError("lease_control_failure")

    def checkpoint(stage: EODCheckpointStage, dataset: Optional[EODDatasetKey]) -> None:
        assert stage is EODCheckpointStage.BEFORE_PROVIDER_INVOCATION
        assert dataset == request.dataset
        raise error

    with pytest.raises(EODOperationControlError) as captured:
        EODProviderChain([provider]).fetch(request, checkpoint=checkpoint)

    assert captured.value is error
    assert provider.calls == []
