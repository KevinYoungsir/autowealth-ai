from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys

import pytest

import autowealth.market_data as market_data
from autowealth.market_data import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EOD_SCHEMA_VERSION,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODGenerationManifest,
    EODProvider,
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRequestPlan,
    EODRequestPlanningError,
    EODRequestPlanningErrorCode,
    EODRequestPlanStatus,
    EODRevisionPolicy,
    EODRevisionStrategy,
    EODStructuredWarning,
    EODWarningSeverity,
    Market,
    Venue,
    default_eod_revision_policy,
    plan_eod_request_window,
    validate_eod_provider_request,
    validate_eod_provider_result,
)

DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
DAY_4 = date(2024, 1, 5)
WEEKEND = date(2024, 1, 7)
DAY_5 = date(2024, 1, 8)
CREATED_AT = datetime(2024, 1, 9, tzinfo=timezone.utc)


@dataclass(frozen=True)
class StaticTradingCalendar:
    days: tuple[date, ...]
    returned_days: object = None

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return next(day for day in self.days if day > value)

    def previous_trading_day(self, value: date) -> date:
        return next(day for day in reversed(self.days) if day < value)

    def trading_days(self, start_date: date, end_date: date) -> object:
        if self.returned_days is not None:
            return self.returned_days
        return [day for day in self.days if start_date <= day <= end_date]


class RaisingTradingCalendar(StaticTradingCalendar):
    def trading_days(self, start_date: date, end_date: date) -> object:
        raise RuntimeError("C:\\private\\calendar apiKey=calendar-secret")


@dataclass(frozen=True)
class FakeEODProvider:
    result: EODProviderResult
    provider_name: str = "fake_eod"
    provider_version: str = "1.0"
    capabilities: tuple[EODProviderCapability, ...] = ()

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        if request != self.result.request:
            raise AssertionError("unexpected request")
        return self.result


@pytest.fixture
def equity_none() -> EODDatasetKey:
    return make_dataset()


def make_dataset(
    *,
    venue: Venue = Venue.SSE,
    asset_type: AssetType = AssetType.EQUITY,
    adjustment_type: AdjustmentType = AdjustmentType.NONE,
    symbol: str = "600000.SH",
) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=venue,
        asset_type=asset_type,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=adjustment_type,
    )


def make_capability(
    dataset: EODDatasetKey,
    *,
    strategy: EODRevisionStrategy = EODRevisionStrategy.APPEND_ONLY,
    maximum_overlap_trading_days: object = None,
) -> EODProviderCapability:
    return EODProviderCapability(
        market=dataset.market,
        venue=dataset.venue,
        asset_type=dataset.asset_type,
        frequency=dataset.frequency,
        adjustment_type=dataset.adjustment_type,
        revision_strategy=strategy,
        maximum_overlap_trading_days=maximum_overlap_trading_days,
    )


def make_bar(
    dataset: EODDatasetKey,
    trade_date: date,
    *,
    close: object = "10.5",
) -> EODBar:
    close_value = Decimal(str(close))
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=Decimal("10"),
        high=max(Decimal("11"), close_value),
        low=min(Decimal("9"), close_value),
        close=close_value,
        volume=Decimal("1000"),
        amount=Decimal("10500"),
    )


def make_request(
    dataset: EODDatasetKey,
    start: date = DAY_1,
    end: date = DAY_3,
) -> EODProviderRequest:
    return EODProviderRequest(dataset, EODDateRange(start, end))


def make_result(
    dataset: EODDatasetKey,
    *,
    status: EODProviderResultStatus = EODProviderResultStatus.SUCCESS,
    bars: object = None,
    warnings: object = (),
    start: date = DAY_1,
    end: date = DAY_3,
) -> EODProviderResult:
    selected_bars = (
        [make_bar(dataset, DAY_1), make_bar(dataset, DAY_2), make_bar(dataset, DAY_3)]
        if bars is None
        else bars
    )
    return EODProviderResult(
        request=make_request(dataset, start, end),
        provider_name="fake_eod",
        provider_version="1.0.0",
        status=status,
        bars=selected_bars,
        warnings=warnings,
    )


def make_manifest(
    dataset: EODDatasetKey,
    first_date: date,
    last_date: date,
) -> EODGenerationManifest:
    digest = "a" * 64
    return EODGenerationManifest(
        manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
        eod_schema_version=EOD_SCHEMA_VERSION,
        generation_id=f"generation_{first_date:%Y%m%d}_{last_date:%Y%m%d}",
        dataset=dataset,
        created_at=CREATED_AT,
        row_count=1,
        first_trade_date=first_date,
        last_trade_date=last_date,
        data_version=f"sha256:{digest}",
        content_sha256=digest,
        parquet_sha256="b" * 64,
    )


def forge_invalid_bar(dataset: EODDatasetKey, trade_date: date) -> EODBar:
    bar = object.__new__(EODBar)
    object.__setattr__(bar, "dataset", dataset)
    object.__setattr__(bar, "trade_date", trade_date)
    object.__setattr__(bar, "open", Decimal("10"))
    object.__setattr__(bar, "high", Decimal("11"))
    object.__setattr__(bar, "low", Decimal("9"))
    object.__setattr__(bar, "close", Decimal("0"))
    object.__setattr__(bar, "volume", Decimal("1000"))
    object.__setattr__(bar, "amount", Decimal("10000"))
    return bar


def test_capability_is_one_exact_combination_and_matches_dataset(
    equity_none: EODDatasetKey,
) -> None:
    capability = make_capability(equity_none)
    assert capability.matches(equity_none)
    assert capability.to_dict() == {
        "market": "CN",
        "venue": "SSE",
        "asset_type": "equity",
        "frequency": "1d",
        "adjustment_type": "none",
        "revision_strategy": "append_only",
        "maximum_overlap_trading_days": None,
    }


@pytest.mark.parametrize(
    "dataset",
    [
        make_dataset(venue=Venue.SZSE, symbol="000001.SZ"),
        make_dataset(asset_type=AssetType.INDEX),
        make_dataset(adjustment_type=AdjustmentType.QFQ),
    ],
)
def test_capability_rejects_nonmatching_dataset_dimensions(dataset: EODDatasetKey) -> None:
    assert not make_capability(make_dataset()).matches(dataset)


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0, None])
def test_overlap_capability_requires_positive_exact_integer(value: object) -> None:
    with pytest.raises(ValueError, match="positive exact integer"):
        make_capability(
            make_dataset(),
            strategy=EODRevisionStrategy.OVERLAP_WINDOW,
            maximum_overlap_trading_days=value,
        )


@pytest.mark.parametrize(
    "strategy",
    [
        EODRevisionStrategy.APPEND_ONLY,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ],
)
def test_non_overlap_capability_rejects_overlap_count(
    strategy: EODRevisionStrategy,
) -> None:
    with pytest.raises(ValueError, match="must be None"):
        make_capability(
            make_dataset(),
            strategy=strategy,
            maximum_overlap_trading_days=1,
        )


def test_capability_json_is_deterministic(equity_none: EODDatasetKey) -> None:
    capability = make_capability(
        equity_none,
        strategy=EODRevisionStrategy.OVERLAP_WINDOW,
        maximum_overlap_trading_days=3,
    )
    assert capability.to_json() == capability.to_json()
    assert json.loads(capability.to_json()) == capability.to_dict()


def test_provider_request_requires_exact_models_and_is_frozen(
    equity_none: EODDatasetKey,
) -> None:
    request = make_request(equity_none)
    assert request.dataset is equity_none
    assert request.requested_range == EODDateRange(DAY_1, DAY_3)
    with pytest.raises(FrozenInstanceError):
        request.dataset = make_dataset(adjustment_type=AdjustmentType.QFQ)
    with pytest.raises(TypeError, match="exact EODDatasetKey"):
        EODProviderRequest(object(), EODDateRange(DAY_1, DAY_3))
    with pytest.raises(TypeError, match="exact EODDateRange"):
        EODProviderRequest(equity_none, object())


def test_provider_request_has_no_independent_symbol_or_adjustment(
    equity_none: EODDatasetKey,
) -> None:
    with pytest.raises(TypeError, match="unexpected keyword"):
        EODProviderRequest(
            dataset=equity_none,
            requested_range=EODDateRange(DAY_1, DAY_3),
            symbol="600000.SH",
        )
    assert set(make_request(equity_none).to_dict()) == {"dataset", "requested_range"}


def test_provider_request_date_range_rejects_datetime() -> None:
    with pytest.raises(ValueError, match="must be a date"):
        EODDateRange(datetime(2024, 1, 2, tzinfo=timezone.utc), DAY_3)


def test_provider_request_json_is_deterministic(equity_none: EODDatasetKey) -> None:
    request = make_request(equity_none)
    assert request.to_json() == request.to_json()
    assert json.loads(request.to_json()) == request.to_dict()


def test_request_capability_validation_returns_unique_match(
    equity_none: EODDatasetKey,
) -> None:
    matching = make_capability(equity_none)
    other = make_capability(make_dataset(venue=Venue.SZSE, symbol="000001.SZ"))
    supplied = (other, matching)
    snapshot = tuple(supplied)
    assert validate_eod_provider_request(make_request(equity_none), supplied) is matching
    assert supplied == snapshot


@pytest.mark.parametrize(
    "requested",
    [
        make_dataset(adjustment_type=AdjustmentType.QFQ),
        make_dataset(asset_type=AssetType.INDEX, adjustment_type=AdjustmentType.QFQ),
        make_dataset(venue=Venue.SZSE, symbol="000001.SZ"),
    ],
)
def test_request_capability_validation_rejects_unsupported_combinations(
    requested: EODDatasetKey,
) -> None:
    with pytest.raises(EODProviderError) as captured:
        validate_eod_provider_request(
            make_request(requested),
            (make_capability(make_dataset()),),
        )
    assert captured.value.code is EODProviderErrorCode.UNSUPPORTED_REQUEST
    assert captured.value.retryable is False


def test_request_capability_validation_rejects_duplicate_and_ambiguous_matches(
    equity_none: EODDatasetKey,
) -> None:
    capability = make_capability(equity_none)
    with pytest.raises(EODProviderError, match="duplicate"):
        validate_eod_provider_request(make_request(equity_none), (capability, capability))
    overlapping = make_capability(
        equity_none,
        strategy=EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    )
    with pytest.raises(EODProviderError, match="ambiguous"):
        validate_eod_provider_request(
            make_request(equity_none),
            (capability, overlapping),
        )


@pytest.mark.parametrize("container", [{}, set(), iter(())])
def test_request_capability_validation_requires_exact_sequence(
    equity_none: EODDatasetKey,
    container: object,
) -> None:
    with pytest.raises(TypeError, match="exact list or exact tuple"):
        validate_eod_provider_request(make_request(equity_none), container)


def test_provider_error_message_is_sanitized(tmp_path: Path) -> None:
    secret = "unit-test-provider-secret"
    error = EODProviderError(
        EODProviderErrorCode.UNSUPPORTED_REQUEST,
        f"failed at {tmp_path}\\private Authorization: Bearer {secret}",
    )
    assert str(tmp_path) not in str(error)
    assert secret not in str(error)
    assert "Authorization" not in error.to_json()


@pytest.mark.parametrize(
    ("status", "bars"),
    [
        (EODProviderResultStatus.SUCCESS, [make_bar(make_dataset(), DAY_1)]),
        (
            EODProviderResultStatus.PARTIAL_SUCCESS,
            [make_bar(make_dataset(), DAY_1)],
        ),
        (EODProviderResultStatus.EMPTY, []),
    ],
)
def test_provider_result_accepts_the_three_consistent_shapes(
    status: EODProviderResultStatus,
    bars: list[EODBar],
) -> None:
    result = make_result(
        make_dataset(),
        status=status,
        bars=bars,
        start=DAY_1,
        end=DAY_2,
    )
    assert result.status is status
    assert type(result.bars) is tuple


def test_provider_result_rejects_status_and_bar_inconsistency(
    equity_none: EODDatasetKey,
) -> None:
    with pytest.raises(EODProviderError, match="requires at least one"):
        make_result(equity_none, bars=[])
    with pytest.raises(EODProviderError, match="cannot contain"):
        make_result(
            equity_none,
            status=EODProviderResultStatus.EMPTY,
            bars=[make_bar(equity_none, DAY_1)],
        )


def test_provider_result_rejects_mixed_dataset_and_out_of_range_bar(
    equity_none: EODDatasetKey,
) -> None:
    other = make_dataset(venue=Venue.SZSE, symbol="000001.SZ")
    with pytest.raises(EODProviderError, match="mixes or changes"):
        make_result(equity_none, bars=[make_bar(other, DAY_1)])
    with pytest.raises(EODProviderError, match="outside"):
        make_result(equity_none, bars=[make_bar(equity_none, DAY_4)])


def test_provider_result_rejects_identical_and_conflicting_duplicates(
    equity_none: EODDatasetKey,
) -> None:
    first = make_bar(equity_none, DAY_1)
    with pytest.raises(EODProviderError, match="duplicate"):
        make_result(equity_none, bars=[first, first])
    with pytest.raises(EODProviderError, match="duplicate"):
        make_result(
            equity_none,
            bars=[first, make_bar(equity_none, DAY_1, close="10.75")],
        )


def test_provider_result_sorts_without_mutating_and_derives_effective_range(
    equity_none: EODDatasetKey,
) -> None:
    supplied = [
        make_bar(equity_none, DAY_3),
        make_bar(equity_none, DAY_1),
        make_bar(equity_none, DAY_2),
    ]
    snapshot = list(supplied)
    result = make_result(equity_none, bars=supplied)
    assert supplied == snapshot
    assert tuple(bar.trade_date for bar in result.bars) == (DAY_1, DAY_2, DAY_3)
    assert result.effective_range == EODDateRange(DAY_1, DAY_3)
    with pytest.raises(FrozenInstanceError):
        result.status = EODProviderResultStatus.EMPTY  # type: ignore[misc]


def test_empty_provider_result_has_warning_and_no_effective_range(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        status=EODProviderResultStatus.EMPTY,
        bars=[],
    )
    assert result.effective_range is None
    assert [warning.code for warning in result.warnings] == ["empty_response"]


def test_provider_result_warnings_are_immutable_deduplicated_and_sorted(
    equity_none: EODDatasetKey,
) -> None:
    first = EODStructuredWarning(
        code="z_warning",
        severity=EODWarningSeverity.WARNING,
        message="Z warning.",
    )
    second = EODStructuredWarning(
        code="a_warning",
        severity=EODWarningSeverity.INFO,
        message="A warning.",
    )
    supplied = [first, second, first]
    result = make_result(equity_none, warnings=supplied)
    assert supplied == [first, second, first]
    assert type(result.warnings) is tuple
    assert len(result.warnings) == 2
    assert tuple(warning.to_json() for warning in result.warnings) == tuple(
        sorted(warning.to_json() for warning in result.warnings)
    )


def test_provider_result_rejects_error_severity_warning(
    equity_none: EODDatasetKey,
) -> None:
    warning = EODStructuredWarning(
        code="provider_error",
        severity=EODWarningSeverity.ERROR,
        message="Provider error.",
    )
    with pytest.raises(EODProviderError, match="error-severity"):
        make_result(equity_none, warnings=[warning])


def test_provider_result_json_is_deterministic_and_has_no_publication_metadata(
    equity_none: EODDatasetKey,
) -> None:
    forward = make_result(equity_none)
    reverse = make_result(equity_none, bars=list(reversed(forward.bars)))
    assert forward.to_json() == reverse.to_json()
    payload = forward.to_dict()
    serialized = forward.to_json()
    assert "data_version" not in payload
    assert "generation_id" not in payload
    assert "fetched_at" not in serialized
    assert "created_at" not in serialized


def test_provider_result_decimal_equivalent_inputs_have_same_json(
    equity_none: EODDatasetKey,
) -> None:
    first = make_result(
        equity_none,
        bars=[make_bar(equity_none, DAY_1, close=Decimal("10.50"))],
        start=DAY_1,
        end=DAY_1,
    )
    second = make_result(
        equity_none,
        bars=[make_bar(equity_none, DAY_1, close=Decimal("10.5000"))],
        start=DAY_1,
        end=DAY_1,
    )
    assert first.to_json() == second.to_json()


def test_provider_result_validator_accepts_complete_success(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(equity_none)
    validated = validate_eod_provider_result(
        result,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
    )
    assert validated.status is EODProviderResultStatus.SUCCESS
    assert validated.bars == result.bars
    assert type(validated.bars) is tuple


def test_provider_result_validator_rejects_success_with_missing_day(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        bars=[make_bar(equity_none, DAY_1), make_bar(equity_none, DAY_3)],
    )
    with pytest.raises(EODProviderError, match="cannot omit"):
        validate_eod_provider_result(
            result,
            StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
        )


def test_provider_result_validator_preserves_partial_and_adds_missing_warning(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
        bars=[make_bar(equity_none, DAY_1), make_bar(equity_none, DAY_3)],
    )
    validated = validate_eod_provider_result(
        result,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
    )
    assert validated.status is EODProviderResultStatus.PARTIAL_SUCCESS
    missing = [warning for warning in validated.warnings if warning.code == "missing_trading_days"]
    assert len(missing) == 1
    assert missing[0].details["dates"] == (DAY_2.isoformat(),)


def test_provider_result_validator_rejects_partial_without_missing_day(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
    )
    with pytest.raises(EODProviderError, match="must omit"):
        validate_eod_provider_result(
            result,
            StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
        )


def test_provider_result_validator_accepts_empty_only_for_trading_date_request(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        status=EODProviderResultStatus.EMPTY,
        bars=[],
    )
    validated = validate_eod_provider_result(
        result,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
    )
    assert validated.status is EODProviderResultStatus.EMPTY
    assert [warning.code for warning in validated.warnings] == ["empty_response"]
    with pytest.raises(EODProviderError, match="without trading days"):
        validate_eod_provider_result(result, StaticTradingCalendar(()))


def test_provider_result_validator_rejects_non_trading_bar(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        bars=[make_bar(equity_none, DAY_1), make_bar(equity_none, DAY_2)],
        start=DAY_1,
        end=DAY_2,
    )
    with pytest.raises(EODProviderError, match="integrity validation"):
        validate_eod_provider_result(result, StaticTradingCalendar((DAY_1,)))


def test_provider_result_validator_rejects_forged_invalid_ohlcv(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        bars=[forge_invalid_bar(equity_none, DAY_1)],
        start=DAY_1,
        end=DAY_1,
    )
    with pytest.raises(EODProviderError, match="integrity validation"):
        validate_eod_provider_result(result, StaticTradingCalendar((DAY_1,)))


@pytest.mark.parametrize(
    "returned_days",
    [
        {DAY_1},
        [DAY_2, DAY_1],
        [datetime(2024, 1, 2, tzinfo=timezone.utc)],
        [date(2023, 12, 31)],
    ],
)
def test_provider_result_validator_wraps_calendar_contract_errors(
    equity_none: EODDatasetKey,
    returned_days: object,
) -> None:
    result = make_result(
        equity_none,
        bars=[make_bar(equity_none, DAY_1)],
        start=DAY_1,
        end=DAY_1,
    )
    calendar = StaticTradingCalendar((DAY_1, DAY_2), returned_days=returned_days)
    with pytest.raises(EODProviderError) as captured:
        validate_eod_provider_result(result, calendar)
    assert captured.value.code is EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD
    assert captured.value.__cause__ is not None


def test_provider_result_validator_does_not_mutate_input(
    equity_none: EODDatasetKey,
) -> None:
    result = make_result(
        equity_none,
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
        bars=[make_bar(equity_none, DAY_3), make_bar(equity_none, DAY_1)],
    )
    original_json = result.to_json()
    validated = validate_eod_provider_result(
        result,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
    )
    assert result.to_json() == original_json
    assert validated is not result
    assert type(validated.bars) is tuple


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        (EODProviderErrorCode.UNSUPPORTED_REQUEST, False),
        (EODProviderErrorCode.PROVIDER_UNAVAILABLE, False),
        (EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE, True),
        (EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE, False),
        (EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, False),
    ],
)
def test_provider_error_retryable_mapping(
    code: EODProviderErrorCode,
    retryable: bool,
) -> None:
    assert EODProviderError(code, "Safe provider failure.").retryable is retryable


def test_provider_error_cause_is_private_and_not_serialized(tmp_path: Path) -> None:
    secret = "provider-api-key-value"
    private_cause = None
    try:
        raise RuntimeError(f"{tmp_path}\\response Cookie: session={secret}")
    except RuntimeError as cause:
        private_cause = cause
        error = EODProviderError(
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
            f"{tmp_path}\\response apiKey={secret}",
        )
        error.__cause__ = cause
    payload = error.to_json()
    assert error.__cause__ is private_cause
    assert secret not in payload
    assert str(tmp_path) not in payload
    assert "Cookie" not in payload
    assert "__cause__" not in payload


@pytest.mark.parametrize(
    ("adjustment", "strategy"),
    [
        (AdjustmentType.NONE, EODRevisionStrategy.APPEND_ONLY),
        (AdjustmentType.QFQ, EODRevisionStrategy.FULL_REFRESH_REQUIRED),
        (AdjustmentType.HFQ, EODRevisionStrategy.FULL_REFRESH_REQUIRED),
    ],
)
def test_default_revision_policy_is_conservative(
    adjustment: AdjustmentType,
    strategy: EODRevisionStrategy,
) -> None:
    policy = default_eod_revision_policy(
        make_dataset(adjustment_type=adjustment),
    )
    assert policy.strategy is strategy
    assert policy.overlap_trading_days == 0


@pytest.mark.parametrize("value", [0, -1, True, False, 1.0])
def test_overlap_revision_policy_requires_positive_exact_integer(value: object) -> None:
    with pytest.raises(ValueError):
        EODRevisionPolicy(
            strategy=EODRevisionStrategy.OVERLAP_WINDOW,
            overlap_trading_days=value,
        )


def test_revision_policy_is_frozen_and_deterministic() -> None:
    policy = EODRevisionPolicy(
        strategy=EODRevisionStrategy.OVERLAP_WINDOW,
        overlap_trading_days=2,
    )
    assert json.loads(policy.to_json()) == policy.to_dict()
    assert policy.to_json() == policy.to_json()
    with pytest.raises(FrozenInstanceError):
        policy.overlap_trading_days = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    "adjustment",
    [AdjustmentType.NONE, AdjustmentType.QFQ, AdjustmentType.HFQ],
)
def test_first_import_requests_full_effective_range(
    adjustment: AdjustmentType,
) -> None:
    dataset = make_dataset(adjustment_type=adjustment)
    requested = EODDateRange(DAY_1, WEEKEND)
    plan = plan_eod_request_window(
        dataset,
        requested,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
    )
    assert plan.status is EODRequestPlanStatus.INITIAL_IMPORT
    assert plan.effective_range == EODDateRange(DAY_1, DAY_4)
    assert plan.provider_request == EODProviderRequest(
        dataset,
        EODDateRange(DAY_1, DAY_4),
    )


def test_planner_closes_weekend_and_holiday_end_to_last_trading_day(
    equity_none: EODDatasetKey,
) -> None:
    weekend_plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, WEEKEND),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
    )
    holiday_plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_5),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
    )
    assert weekend_plan.effective_range.end_date == DAY_4
    assert holiday_plan.effective_range.end_date == DAY_4


def test_planner_returns_no_trading_days_without_request(
    equity_none: EODDatasetKey,
) -> None:
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(WEEKEND, WEEKEND),
        StaticTradingCalendar(()),
    )
    assert plan.status is EODRequestPlanStatus.NO_TRADING_DAYS
    assert plan.effective_range is None
    assert plan.provider_request is None


def test_planner_rejects_current_dataset_mismatch(
    equity_none: EODDatasetKey,
) -> None:
    other = make_dataset(venue=Venue.SZSE, symbol="000001.SZ")
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            equity_none,
            EODDateRange(DAY_1, DAY_3),
            StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
            make_manifest(other, DAY_1, DAY_2),
        )
    assert captured.value.code is EODRequestPlanningErrorCode.CURRENT_DATASET_MISMATCH


@pytest.mark.parametrize(
    ("first_date", "last_date"),
    [
        (date(2024, 1, 1), DAY_2),
        (DAY_1, date(2024, 1, 6)),
    ],
)
def test_planner_rejects_non_trading_manifest_dates(
    equity_none: EODDatasetKey,
    first_date: date,
    last_date: date,
) -> None:
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            equity_none,
            EODDateRange(DAY_1, DAY_3),
            StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
            make_manifest(equity_none, first_date, last_date),
        )
    assert captured.value.code is EODRequestPlanningErrorCode.CURRENT_DATE_NOT_TRADING_DAY


def test_planner_rejects_current_after_effective_end(
    equity_none: EODDatasetKey,
) -> None:
    calendar = StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4))
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            equity_none,
            EODDateRange(DAY_1, DAY_3),
            calendar,
            make_manifest(equity_none, DAY_1, DAY_4),
        )
    assert captured.value.code is EODRequestPlanningErrorCode.CURRENT_AFTER_EFFECTIVE_END


def test_planner_returns_already_current_without_request(
    equity_none: EODDatasetKey,
) -> None:
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_3),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
        make_manifest(equity_none, DAY_1, DAY_3),
    )
    assert plan.status is EODRequestPlanStatus.ALREADY_CURRENT
    assert plan.provider_request is None


def test_append_only_starts_at_next_actual_trading_day_not_calendar_day(
    equity_none: EODDatasetKey,
) -> None:
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_5),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4, DAY_5)),
        make_manifest(equity_none, DAY_1, DAY_4),
    )
    assert plan.status is EODRequestPlanStatus.INCREMENTAL
    assert plan.provider_request.requested_range == EODDateRange(DAY_5, DAY_5)
    assert DAY_5 != date(2024, 1, 6)


def test_append_only_current_before_effective_range_starts_at_effective_start(
    equity_none: EODDatasetKey,
) -> None:
    prior = date(2023, 12, 29)
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_3),
        StaticTradingCalendar((prior, DAY_1, DAY_2, DAY_3)),
        make_manifest(equity_none, prior, prior),
    )
    assert plan.status is EODRequestPlanStatus.INCREMENTAL
    assert plan.provider_request.requested_range == EODDateRange(DAY_1, DAY_3)


def test_left_history_gap_requires_full_refresh_without_request(
    equity_none: EODDatasetKey,
) -> None:
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_4),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
        make_manifest(equity_none, DAY_2, DAY_3),
    )
    assert plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
    assert plan.provider_request is None


@pytest.mark.parametrize(
    ("overlap", "expected_start"),
    [
        (1, DAY_3),
        (2, DAY_2),
        (9, DAY_1),
    ],
)
def test_overlap_window_uses_bounded_existing_trading_days(
    equity_none: EODDatasetKey,
    overlap: int,
    expected_start: date,
) -> None:
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_4),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
        make_manifest(equity_none, DAY_1, DAY_3),
        EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, overlap),
    )
    assert plan.status is EODRequestPlanStatus.OVERLAP_REFRESH
    assert plan.provider_request.requested_range == EODDateRange(expected_start, DAY_4)


def test_overlap_current_before_range_starts_at_effective_start(
    equity_none: EODDatasetKey,
) -> None:
    prior = date(2023, 12, 29)
    plan = plan_eod_request_window(
        equity_none,
        EODDateRange(DAY_1, DAY_3),
        StaticTradingCalendar((prior, DAY_1, DAY_2, DAY_3)),
        make_manifest(equity_none, prior, prior),
        EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 3),
    )
    assert plan.status is EODRequestPlanStatus.OVERLAP_REFRESH
    assert plan.provider_request.requested_range == EODDateRange(DAY_1, DAY_3)


@pytest.mark.parametrize("adjustment", [AdjustmentType.QFQ, AdjustmentType.HFQ])
def test_adjusted_append_only_is_rejected(adjustment: AdjustmentType) -> None:
    dataset = make_dataset(adjustment_type=adjustment)
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            dataset,
            EODDateRange(DAY_1, DAY_3),
            StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
            make_manifest(dataset, DAY_1, DAY_2),
            EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY),
        )
    assert captured.value.code is EODRequestPlanningErrorCode.INVALID_REVISION_POLICY


@pytest.mark.parametrize("adjustment", [AdjustmentType.QFQ, AdjustmentType.HFQ])
def test_adjusted_existing_dataset_requires_explicit_full_refresh(
    adjustment: AdjustmentType,
) -> None:
    dataset = make_dataset(adjustment_type=adjustment)
    plan = plan_eod_request_window(
        dataset,
        EODDateRange(DAY_1, DAY_3),
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3)),
        make_manifest(dataset, DAY_1, DAY_2),
    )
    assert plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
    assert plan.provider_request is None


def test_planner_rejects_calendar_that_omits_current_manifest_date(
    equity_none: EODDatasetKey,
) -> None:
    calendar = StaticTradingCalendar(
        (DAY_1, DAY_2, DAY_3),
        returned_days=[DAY_1, DAY_3],
    )
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            equity_none,
            EODDateRange(DAY_1, DAY_3),
            calendar,
            make_manifest(equity_none, DAY_1, DAY_2),
        )
    assert captured.value.code is EODRequestPlanningErrorCode.INVALID_CALENDAR


def test_planning_error_is_sanitized_and_preserves_private_cause(
    equity_none: EODDatasetKey,
    tmp_path: Path,
) -> None:
    with pytest.raises(EODRequestPlanningError) as captured:
        plan_eod_request_window(
            equity_none,
            EODDateRange(DAY_1, DAY_3),
            RaisingTradingCalendar((DAY_1, DAY_2, DAY_3)),
        )
    error = captured.value
    assert error.code is EODRequestPlanningErrorCode.INVALID_CALENDAR
    assert error.__cause__ is not None
    assert "calendar-secret" not in error.to_json()
    assert str(tmp_path) not in error.to_json()
    assert "__cause__" not in error.to_json()


def test_request_plan_enforces_status_and_request_consistency(
    equity_none: EODDatasetKey,
) -> None:
    requested = EODDateRange(DAY_1, DAY_3)
    policy = EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY)
    request = EODProviderRequest(equity_none, requested)
    with pytest.raises(ValueError, match="must not contain"):
        EODRequestPlan(
            equity_none,
            requested,
            requested,
            policy,
            EODRequestPlanStatus.ALREADY_CURRENT,
            request,
        )
    with pytest.raises(ValueError, match="requires"):
        EODRequestPlan(
            equity_none,
            requested,
            requested,
            policy,
            EODRequestPlanStatus.INCREMENTAL,
            None,
        )
    with pytest.raises(ValueError, match="append_only"):
        EODRequestPlan(
            equity_none,
            requested,
            requested,
            EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 1),
            EODRequestPlanStatus.INCREMENTAL,
            request,
        )


def test_planner_is_deterministic_frozen_and_does_not_mutate_inputs(
    equity_none: EODDatasetKey,
) -> None:
    requested = EODDateRange(DAY_1, DAY_4)
    manifest = make_manifest(equity_none, DAY_1, DAY_3)
    policy = EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY)
    snapshot = (
        equity_none.to_json(),
        requested.to_json(),
        manifest.to_json(),
        policy.to_json(),
    )
    first = plan_eod_request_window(
        equity_none,
        requested,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
        manifest,
        policy,
    )
    second = plan_eod_request_window(
        equity_none,
        requested,
        StaticTradingCalendar((DAY_1, DAY_2, DAY_3, DAY_4)),
        manifest,
        policy,
    )
    assert first.to_json() == second.to_json()
    assert snapshot == (
        equity_none.to_json(),
        requested.to_json(),
        manifest.to_json(),
        policy.to_json(),
    )
    with pytest.raises(FrozenInstanceError):
        first.status = EODRequestPlanStatus.ALREADY_CURRENT  # type: ignore[misc]


def test_offline_fake_provider_satisfies_protocol(
    equity_none: EODDatasetKey,
) -> None:
    request = make_request(equity_none)
    result = make_result(equity_none)
    provider = FakeEODProvider(
        result=result,
        capabilities=(make_capability(equity_none),),
    )
    assert isinstance(provider, EODProvider)
    assert provider.fetch(request) is result
    assert provider.provider_name == "fake_eod"
    assert provider.capabilities[0].matches(equity_none)


def test_market_data_exports_are_unique_and_exclude_unimplemented_runtime_components() -> None:
    required = {
        "EODIncrementalCoordinator",
        "EODIncrementalCoordinatorError",
        "EODIncrementalCoordinatorErrorCode",
        "EODIncrementalUpdateResult",
        "EODIncrementalUpdateStatus",
        "EODProvider",
        "EODProviderAttempt",
        "EODProviderCapability",
        "EODProviderChain",
        "EODProviderChainError",
        "EODProviderChainResult",
        "EODProviderError",
        "EODProviderErrorCode",
        "EODProviderRequest",
        "EODProviderResult",
        "EODProviderResultStatus",
        "EODRevisionStrategy",
        "EODRevisionPolicy",
        "EODRequestPlan",
        "EODRequestPlanStatus",
        "EODRequestPlanningError",
        "EODRequestPlanningErrorCode",
        "default_eod_revision_policy",
        "plan_eod_request_window",
        "validate_eod_provider_request",
        "validate_eod_provider_result",
    }
    assert required <= set(market_data.__all__)
    assert len(market_data.__all__) == len(set(market_data.__all__))
    forbidden = {
        "AKShareEODProvider",
        "EODUpdateCoordinator",
        "EODRetryExecutor",
    }
    assert forbidden.isdisjoint(market_data.__all__)


def test_fresh_package_import_has_no_external_runtime_or_repository_side_effects() -> None:
    script = r"""
import builtins
import os
from pathlib import Path
import socket
import sys

import autowealth

before = dict(os.environ)
before_modules = set(sys.modules)
original_open = builtins.open

def blocked(*args, **kwargs):
    raise AssertionError("forbidden import-time side effect")

def guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        blocked()
    return original_open(file, mode, *args, **kwargs)

builtins.open = guarded_open
Path.write_text = blocked
Path.write_bytes = blocked
Path.touch = blocked
socket.create_connection = blocked
socket.socket.connect = blocked

import autowealth.market_data as market_data

assert dict(os.environ) == before
assert "autowealth.market_data.coordinator" not in sys.modules
assert "autowealth.market_data.repositories" not in sys.modules
assert "pyarrow.parquet" not in sys.modules
new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before_modules}
assert {"akshare", "requests", "yfinance", "pyarrow"}.isdisjoint(new_roots)
assert market_data.EODProviderRequest.__module__ == "autowealth.market_data.providers"
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_provider_and_planner_sources_have_no_io_clock_or_runtime_provider_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    provider_source = (root / "autowealth/market_data/providers.py").read_text(encoding="utf-8")
    planner_source = (root / "autowealth/market_data/planning.py").read_text(encoding="utf-8")
    combined = provider_source + planner_source
    forbidden_fragments = (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "time.time",
        "time.monotonic",
        "os.environ",
        "os.getenv",
        "open(",
        "pathlib",
        "requests",
        "yfinance",
        "akshare",
        "pyarrow",
        ".repositories",
        "autowealth.data",
    )
    assert all(fragment not in combined for fragment in forbidden_fragments)


def test_planner_public_signature_has_no_provider_or_repository_dependency() -> None:
    annotations = plan_eod_request_window.__annotations__
    assert set(annotations) == {
        "dataset",
        "requested_range",
        "calendar",
        "current_manifest",
        "revision_policy",
        "return",
    }
    assert "provider" not in annotations
    assert "repository" not in annotations


@pytest.mark.parametrize(
    "relative_path",
    [
        "autowealth/market_data/__init__.py",
        "autowealth/market_data/providers.py",
        "autowealth/market_data/planning.py",
        "tests/test_eod_provider_contracts.py",
    ],
)
def test_changed_python_files_parse_with_python_39_grammar(relative_path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / relative_path).read_text(encoding="utf-8")
    ast.parse(source, filename=relative_path, feature_version=(3, 9))


def test_public_contract_json_contains_no_secret_or_absolute_path(tmp_path: Path) -> None:
    secret = "provider-secret-value"
    provider_error = EODProviderError(
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        f"provider failed at {tmp_path}\\cache Cookie: session={secret}",
    )
    planning_error = EODRequestPlanningError(
        EODRequestPlanningErrorCode.INVALID_CALENDAR,
        f"calendar failed at {tmp_path}\\cache Authorization: Bearer {secret}",
    )
    for payload in (provider_error.to_json(), planning_error.to_json()):
        assert secret not in payload
        assert str(tmp_path) not in payload
        assert "Authorization" not in payload
        assert "Cookie" not in payload
        assert "traceback" not in payload.lower()
