from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from typing import Optional

import pytest

import autowealth.market_data.coordinator as coordinator_module
from autowealth.market_data.calendar import TradingCalendar
from autowealth.market_data.coordinator import (
    EODIncrementalCoordinator,
    EODIncrementalCoordinatorError,
    EODIncrementalCoordinatorErrorCode,
    EODIncrementalUpdateResult,
    EODIncrementalUpdateStatus,
)
from autowealth.market_data.operation_control import (
    EODCheckpointStage,
    EODOperationControlError,
)
from autowealth.market_data.planning import (
    EODRequestPlan,
    EODRequestPlanStatus,
    EODRevisionPolicy,
)
from autowealth.market_data.provider_chain import (
    EODProviderAttempt,
    EODProviderChain,
    EODProviderChainError,
    EODProviderChainResult,
)
from autowealth.market_data.provider_resilience import EODProviderRetryPolicy
from autowealth.market_data.providers import (
    EODProviderCapability,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRevisionStrategy,
)
from autowealth.market_data.schemas import (
    EOD_SCHEMA_VERSION,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODUpdateRequest,
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_eod_content_sha256,
)

DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
DAY_4 = date(2024, 1, 5)
DAY_5 = date(2024, 1, 8)
DAY_6 = date(2024, 1, 9)
UTC_TIME = datetime(2024, 1, 10, 1, 2, 3, tzinfo=timezone.utc)
ALL_DAYS = (DAY_1, DAY_2, DAY_3, DAY_4, DAY_5, DAY_6)
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class StaticCalendar:
    days: tuple[date, ...] = ALL_DAYS

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return next(day for day in self.days if day > value)

    def previous_trading_day(self, value: date) -> date:
        return next(day for day in reversed(self.days) if day < value)

    def trading_days(self, start_date: date, end_date: date) -> list[date]:
        return [day for day in self.days if start_date <= day <= end_date]


class FakeRepository:
    def __init__(
        self,
        current: Optional[EODStoredGeneration] = None,
        *,
        load_error: Optional[BaseException] = None,
        publish_error: Optional[BaseException] = None,
        publish_result: object = None,
        events: Optional[list[str]] = None,
    ) -> None:
        self.current = current
        self.load_error = load_error
        self.publish_error = publish_error
        self.publish_result = publish_result
        self.events = [] if events is None else events
        self.load_count = 0
        self.publish_count = 0
        self.publish_arguments: Optional[dict[str, object]] = None
        self.forbidden_calls: list[str] = []

    def load_current(self, dataset: EODDatasetKey) -> Optional[EODStoredGeneration]:
        self.load_count += 1
        self.events.append("load_current")
        if self.load_error is not None:
            raise self.load_error
        return self.current

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: tuple[EODBar, ...],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> object:
        self.publish_count += 1
        self.events.append("publish")
        self.publish_arguments = {
            "dataset": dataset,
            "bars": tuple(bars),
            "generation_id": generation_id,
            "created_at": created_at,
        }
        if self.publish_error is not None:
            raise self.publish_error
        if self.publish_result is not None:
            return self.publish_result
        return make_manifest(
            tuple(bars),
            generation_id=generation_id,
            created_at=created_at,
            previous_generation_id=(
                None if self.current is None else self.current.manifest.generation_id
            ),
        )

    def load_current_manifest(self, dataset: EODDatasetKey) -> None:
        self.forbidden_calls.append("load_current_manifest")
        raise AssertionError("coordinator must not call load_current_manifest")

    def load_generation(self, dataset: EODDatasetKey, generation_id: str) -> None:
        self.forbidden_calls.append("load_generation")
        raise AssertionError("coordinator must not call load_generation")

    def list_generation_ids(self, dataset: EODDatasetKey) -> None:
        self.forbidden_calls.append("list_generation_ids")
        raise AssertionError("coordinator must not call list_generation_ids")


class FakeChain:
    def __init__(
        self,
        response: object,
        *,
        events: Optional[list[str]] = None,
    ) -> None:
        self.response = response
        self.events = [] if events is None else events
        self.fetch_count = 0
        self.requests: list[EODProviderRequest] = []

    def fetch(
        self,
        request: EODProviderRequest,
        *,
        checkpoint: object = None,
    ) -> object:
        self.fetch_count += 1
        self.requests.append(request)
        self.events.append("fetch")
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class FakeProvider:
    provider_name = "fake_provider"
    provider_version = "1"
    endpoint_name = "fake_endpoint"

    def __init__(self, result: EODProviderResult, dataset: EODDatasetKey) -> None:
        self.result = result
        self.calls = 0
        self.capabilities = (
            EODProviderCapability(
                market=dataset.market,
                venue=dataset.venue,
                asset_type=dataset.asset_type,
                frequency=dataset.frequency,
                adjustment_type=dataset.adjustment_type,
                revision_strategy=EODRevisionStrategy.APPEND_ONLY,
            ),
        )

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.calls += 1
        return self.result


def make_dataset(
    *,
    adjustment: AdjustmentType = AdjustmentType.NONE,
    symbol: str = "600000.SH",
) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=adjustment,
    )


def make_bar(
    dataset: EODDatasetKey,
    trade_date: date,
    value: int = 10,
    *,
    amount: Optional[int] = 100,
) -> EODBar:
    base = Decimal(value)
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=base,
        high=base + Decimal("1"),
        low=base - Decimal("1"),
        close=base + Decimal("0.5"),
        volume=Decimal("1000"),
        amount=None if amount is None else Decimal(amount),
    )


def make_bars(
    dataset: EODDatasetKey,
    days: tuple[date, ...],
    *,
    offset: int = 0,
) -> tuple[EODBar, ...]:
    return tuple(make_bar(dataset, day, 10 + offset + index) for index, day in enumerate(days))


def make_manifest(
    bars: tuple[EODBar, ...],
    *,
    generation_id: str = "generation-1",
    created_at: datetime = UTC_TIME,
    previous_generation_id: Optional[str] = None,
) -> EODGenerationManifest:
    digest = calculate_eod_content_sha256(bars)
    return EODGenerationManifest(
        manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
        eod_schema_version=EOD_SCHEMA_VERSION,
        generation_id=generation_id,
        dataset=bars[0].dataset,
        created_at=created_at,
        row_count=len(bars),
        first_trade_date=bars[0].trade_date,
        last_trade_date=bars[-1].trade_date,
        data_version=f"sha256:{digest}",
        content_sha256=digest,
        parquet_sha256="b" * 64,
        previous_generation_id=previous_generation_id,
    )


def make_stored(
    dataset: EODDatasetKey,
    days: tuple[date, ...],
    *,
    generation_id: str = "generation-1",
) -> EODStoredGeneration:
    bars = make_bars(dataset, days)
    return EODStoredGeneration(
        manifest=make_manifest(bars, generation_id=generation_id),
        bars=bars,
    )


def make_chain_result(
    request: EODProviderRequest,
    days: tuple[date, ...],
    *,
    status: EODProviderResultStatus = EODProviderResultStatus.SUCCESS,
    offset: int = 0,
) -> EODProviderChainResult:
    bars = make_bars(request.dataset, days, offset=offset)
    result = EODProviderResult(
        request=request,
        provider_name="fake_provider",
        provider_version="1",
        status=status,
        bars=bars,
    )
    attempt = EODProviderAttempt(
        position=0,
        provider_name="fake_provider",
        provider_version="1",
        endpoint_name="fake_endpoint",
        result_status=status,
        error_code=None,
        row_count=len(bars),
        effective_range=result.effective_range,
        warning_codes=(),
        selected=True,
        safe_message="The fake provider returned validated EOD data.",
    )
    return EODProviderChainResult(
        request=request,
        selected_result=result,
        selected_position=0,
        attempts=(attempt,),
    )


def initial_setup(
    dataset: Optional[EODDatasetKey] = None,
    *,
    days: tuple[date, ...] = (DAY_1, DAY_2, DAY_3, DAY_4),
    events: Optional[list[str]] = None,
) -> tuple[EODDatasetKey, EODDateRange, FakeRepository, FakeChain, StaticCalendar]:
    selected_dataset = dataset or make_dataset()
    requested_range = EODDateRange(days[0], days[-1])
    request = EODProviderRequest(selected_dataset, requested_range)
    repository = FakeRepository(events=events)
    chain = FakeChain(make_chain_result(request, days), events=events)
    return selected_dataset, requested_range, repository, chain, StaticCalendar()


def run_update(
    coordinator: EODIncrementalCoordinator,
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
    **kwargs: object,
) -> EODIncrementalUpdateResult:
    values = {"generation_id": "generation-2", "created_at": UTC_TIME}
    values.update(kwargs)
    return coordinator.update(dataset, requested_range, **values)


def test_constructor_accepts_fake_dependencies_without_side_effects() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    assert isinstance(calendar, TradingCalendar)
    assert repository.load_count == 0
    assert repository.publish_count == 0
    assert chain.fetch_count == 0
    assert coordinator._repository is repository
    assert coordinator._provider_chain is chain
    assert coordinator._calendar is calendar
    assert requested_range.start_date == DAY_1
    assert dataset.canonical_symbol == "600000.SH"


@pytest.mark.parametrize(
    ("repository", "chain", "calendar", "message"),
    [
        (object(), object(), StaticCalendar(), "repository"),
        (FakeRepository(), object(), StaticCalendar(), "provider_chain"),
        (FakeRepository(), FakeChain(object()), object(), "calendar"),
    ],
)
def test_constructor_rejects_invalid_dependencies(
    repository: object,
    chain: object,
    calendar: object,
    message: str,
) -> None:
    with pytest.raises(TypeError, match=message):
        EODIncrementalCoordinator(repository, chain, calendar)  # type: ignore[arg-type]


def test_constructor_rejects_nested_coordinator() -> None:
    first = EODIncrementalCoordinator(FakeRepository(), FakeChain(object()), StaticCalendar())
    with pytest.raises(TypeError, match="cannot be a coordinator"):
        EODIncrementalCoordinator(FakeRepository(), first, StaticCalendar())


def test_update_rejects_non_exact_base_inputs_before_repository_access() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    with pytest.raises(TypeError, match="dataset"):
        coordinator.update(object(), requested_range)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="requested_range"):
        coordinator.update(dataset, object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="revision_policy"):
        coordinator.update(dataset, requested_range, revision_policy=object())  # type: ignore[arg-type]
    assert repository.load_count == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"generation_id": 7}, "generation_id"),
        ({"generation_id": "../unsafe"}, "generation_id"),
        ({"created_at": date(2024, 1, 10)}, "created_at"),
        ({"created_at": datetime(2024, 1, 10)}, "created_at"),
    ],
)
def test_explicit_invalid_publication_context_fails_before_load(
    kwargs: dict[str, object],
    message: str,
) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        coordinator.update(dataset, requested_range, **kwargs)
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID
    assert captured.value.stage == "publication_context"
    assert message in captured.value.message
    assert repository.load_count == 0


def test_initial_import_publishes_complete_candidate_once() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    result = run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
    )
    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED
    assert result.published is True
    assert result.unchanged is False
    assert result.requires_full_refresh is False
    assert result.retryable is False
    assert result.previous_manifest is None
    assert result.published_manifest is not None
    assert result.row_count == 4
    assert result.added_row_count == 4
    assert result.replaced_row_count == 0
    assert result.attempts == chain.response.attempts
    assert repository.load_count == 1
    assert repository.publish_count == 1
    assert chain.fetch_count == 1
    assert repository.forbidden_calls == []


def test_initial_publish_arguments_are_exact_and_non_utc_time_is_normalized() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    source_time = datetime(2024, 1, 10, 9, 2, 3, tzinfo=timezone(timedelta(hours=8)))
    result = EODIncrementalCoordinator(repository, chain, calendar).update(
        dataset,
        requested_range,
        generation_id="generation-2",
        created_at=source_time,
    )
    assert repository.publish_arguments is not None
    assert repository.publish_arguments["dataset"] is dataset
    assert repository.publish_arguments["generation_id"] == "generation-2"
    assert repository.publish_arguments["created_at"] == UTC_TIME
    assert repository.publish_arguments["bars"] == chain.response.selected_result.bars
    assert result.published_manifest is not None
    assert result.published_manifest.created_at == UTC_TIME


@pytest.mark.parametrize("missing_field", ["generation_id", "created_at"])
def test_publish_path_requires_complete_publication_context(missing_field: str) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    kwargs: dict[str, object] = {"generation_id": "generation-2", "created_at": UTC_TIME}
    kwargs[missing_field] = None
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
            **kwargs,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID
    assert captured.value.stage == "publication_context"
    assert repository.publish_count == 0
    assert chain.fetch_count == 1


def test_already_current_is_noop_without_publication_context() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3, DAY_4))
    repository = FakeRepository(current)
    chain = FakeChain(object())
    result = EODIncrementalCoordinator(repository, chain, StaticCalendar()).update(
        dataset,
        EODDateRange(DAY_1, DAY_4),
    )
    assert result.status is EODIncrementalUpdateStatus.ALREADY_CURRENT
    assert result.unchanged is True
    assert result.published is False
    assert result.previous_manifest == current.manifest
    assert result.published_manifest is None
    assert result.attempts == ()
    assert result.row_count == 4
    assert chain.fetch_count == 0
    assert repository.publish_count == 0


def test_no_trading_days_is_noop_without_current_or_context() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(date(2024, 1, 6), date(2024, 1, 7))
    repository = FakeRepository()
    chain = FakeChain(object())
    result = EODIncrementalCoordinator(repository, chain, StaticCalendar()).update(
        dataset,
        requested_range,
    )
    assert result.status is EODIncrementalUpdateStatus.NO_TRADING_DAYS
    assert result.unchanged is True
    assert result.row_count == 0
    assert chain.fetch_count == 0
    assert repository.publish_count == 0


def test_full_refresh_required_is_normal_non_retryable_result() -> None:
    dataset = make_dataset(adjustment=AdjustmentType.QFQ)
    current = make_stored(dataset, (DAY_1, DAY_2))
    repository = FakeRepository(current)
    chain = FakeChain(object())
    result = EODIncrementalCoordinator(repository, chain, StaticCalendar()).update(
        dataset,
        EODDateRange(DAY_1, DAY_4),
    )
    assert result.status is EODIncrementalUpdateStatus.FULL_REFRESH_REQUIRED
    assert result.requires_full_refresh is True
    assert result.unchanged is False
    assert result.retryable is False
    assert chain.fetch_count == 0
    assert repository.publish_count == 0


def test_execute_rejects_non_exact_request_before_repository_access() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    with pytest.raises(TypeError, match="request"):
        coordinator.execute(object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dry_run"):
        coordinator.update(dataset, requested_range, dry_run=1)  # type: ignore[arg-type]
    assert repository.load_count == 0


def test_initial_import_dry_run_stops_before_fetch_and_publication() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    result = EODIncrementalCoordinator(repository, chain, calendar).execute(
        EODUpdateRequest(dataset, requested_range, dry_run=True)
    )
    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PLANNED
    assert result.plan.status is EODRequestPlanStatus.INITIAL_IMPORT
    assert result.plan.provider_request is not None
    assert result.plan.provider_request.requested_range == requested_range
    assert result.dry_run is True
    assert result.planned is True
    assert result.published is False
    assert result.attempts == ()
    assert repository.load_count == 1
    assert repository.publish_count == 0
    assert chain.fetch_count == 0


def test_dry_run_never_calls_provider_rate_limiter_or_retry_sleeper() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    provider_request = EODProviderRequest(dataset, requested_range)
    provider_result = EODProviderResult(
        request=provider_request,
        provider_name="fake_provider",
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4)),
    )
    provider = FakeProvider(provider_result, dataset)

    class ForbiddenRateLimiter:
        calls = 0

        def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
            self.calls += 1
            raise AssertionError("dry-run must not acquire provider rate limits")

    class ForbiddenSleeper:
        calls = 0

        def sleep(self, seconds: float) -> None:
            self.calls += 1
            raise AssertionError("dry-run must not sleep")

    limiter = ForbiddenRateLimiter()
    sleeper = ForbiddenSleeper()
    chain = EODProviderChain(
        [provider],
        retry_policy=EODProviderRetryPolicy(max_attempts=5),
        rate_limiter=limiter,
        retry_sleeper=sleeper,
    )
    repository = FakeRepository()

    result = EODIncrementalCoordinator(repository, chain, StaticCalendar()).execute(
        EODUpdateRequest(dataset, requested_range, dry_run=True)
    )

    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PLANNED
    assert provider.calls == 0
    assert limiter.calls == 0
    assert sleeper.calls == 0
    assert repository.publish_count == 0


def test_incremental_and_overlap_dry_runs_return_exact_plans_without_fetch() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2))
    requested_range = EODDateRange(DAY_1, DAY_4)

    append_repository = FakeRepository(current)
    append_chain = FakeChain(object())
    append_result = EODIncrementalCoordinator(
        append_repository,
        append_chain,
        StaticCalendar(),
    ).execute(EODUpdateRequest(dataset, requested_range, dry_run=True))
    assert append_result.status is EODIncrementalUpdateStatus.INCREMENTAL_PLANNED
    assert append_result.plan.status is EODRequestPlanStatus.INCREMENTAL
    assert append_result.plan.provider_request is not None
    assert append_result.plan.provider_request.requested_range == EODDateRange(DAY_3, DAY_4)

    overlap_repository = FakeRepository(current)
    overlap_chain = FakeChain(object())
    overlap_result = EODIncrementalCoordinator(
        overlap_repository,
        overlap_chain,
        StaticCalendar(),
    ).execute(
        EODUpdateRequest(dataset, requested_range, dry_run=True),
        revision_policy=EODRevisionPolicy(
            EODRevisionStrategy.OVERLAP_WINDOW,
            overlap_trading_days=2,
        ),
    )
    assert overlap_result.status is EODIncrementalUpdateStatus.OVERLAP_REFRESH_PLANNED
    assert overlap_result.plan.status is EODRequestPlanStatus.OVERLAP_REFRESH
    assert overlap_result.plan.provider_request is not None
    assert overlap_result.plan.provider_request.requested_range == requested_range

    assert append_chain.fetch_count == overlap_chain.fetch_count == 0
    assert append_repository.publish_count == overlap_repository.publish_count == 0


def test_dry_run_plan_matches_real_execution_from_the_same_repository_state() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2))
    requested_range = EODDateRange(DAY_1, DAY_4)
    provider_range = EODDateRange(DAY_3, DAY_4)
    provider_request = EODProviderRequest(dataset, provider_range)
    dry_repository = FakeRepository(current)
    real_repository = FakeRepository(current)
    dry_chain = FakeChain(AssertionError("dry-run fetched"))
    real_chain = FakeChain(make_chain_result(provider_request, (DAY_3, DAY_4)))

    dry_result = EODIncrementalCoordinator(
        dry_repository,
        dry_chain,
        StaticCalendar(),
    ).execute(EODUpdateRequest(dataset, requested_range, dry_run=True))
    real_result = EODIncrementalCoordinator(
        real_repository,
        real_chain,
        StaticCalendar(),
    ).execute(
        EODUpdateRequest(dataset, requested_range, dry_run=False),
        generation_id="generation-2",
        created_at=UTC_TIME,
    )

    assert dry_result.plan == real_result.plan
    assert dry_result.plan.provider_request is not None
    assert dry_result.plan.provider_request.requested_range == provider_range
    assert dry_result.dataset == real_result.dataset == dataset
    assert dry_result.requested_range == real_result.requested_range == requested_range
    assert dry_chain.fetch_count == 0
    assert dry_repository.publish_count == 0
    assert real_chain.fetch_count == 1
    assert real_repository.publish_count == 1


def test_dry_run_preserves_no_fetch_terminal_statuses() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2))
    already_repository = FakeRepository(current)
    already_chain = FakeChain(object())
    already = EODIncrementalCoordinator(
        already_repository,
        already_chain,
        StaticCalendar(),
    ).execute(EODUpdateRequest(dataset, EODDateRange(DAY_1, DAY_2), dry_run=True))
    assert already.status is EODIncrementalUpdateStatus.ALREADY_CURRENT
    assert already.dry_run is True

    adjusted = make_dataset(adjustment=AdjustmentType.QFQ)
    adjusted_current = make_stored(adjusted, (DAY_1, DAY_2))
    refresh_repository = FakeRepository(adjusted_current)
    refresh_chain = FakeChain(object())
    refresh = EODIncrementalCoordinator(
        refresh_repository,
        refresh_chain,
        StaticCalendar(),
    ).execute(
        EODUpdateRequest(
            adjusted,
            EODDateRange(DAY_1, DAY_4),
            dry_run=True,
        )
    )
    assert refresh.status is EODIncrementalUpdateStatus.FULL_REFRESH_REQUIRED
    assert refresh.dry_run is True
    assert refresh.requires_full_refresh is True
    assert already_chain.fetch_count == refresh_chain.fetch_count == 0
    assert already_repository.publish_count == refresh_repository.publish_count == 0


def test_execute_non_dry_run_preserves_existing_publication_behavior() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    result = EODIncrementalCoordinator(repository, chain, calendar).execute(
        EODUpdateRequest(dataset, requested_range, dry_run=False),
        generation_id="generation-2",
        created_at=UTC_TIME,
    )
    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED
    assert result.dry_run is False
    assert result.planned is False
    assert chain.fetch_count == 1
    assert repository.publish_count == 1


def test_noop_accepts_valid_unused_publication_context() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2))
    repository = FakeRepository(current)
    result = EODIncrementalCoordinator(
        repository,
        FakeChain(object()),
        StaticCalendar(),
    ).update(
        dataset,
        EODDateRange(DAY_1, DAY_2),
        generation_id="unused-generation",
        created_at=UTC_TIME,
    )
    assert result.status is EODIncrementalUpdateStatus.ALREADY_CURRENT
    assert repository.publish_count == 0


def test_load_current_error_is_wrapped_without_exception_text() -> None:
    dataset, requested_range, _, chain, calendar = initial_setup()
    repository = FakeRepository(load_error=RuntimeError("C:\\private\\token.txt"))
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    error = captured.value
    assert error.code is EODIncrementalCoordinatorErrorCode.CURRENT_GENERATION_INVALID
    assert error.stage == "load_current"
    assert isinstance(error.__cause__, RuntimeError)
    assert "private" not in error.to_json()
    assert repository.load_count == 1
    assert chain.fetch_count == 0


def test_base_exception_from_repository_is_not_wrapped() -> None:
    dataset, requested_range, _, chain, calendar = initial_setup()
    repository = FakeRepository(load_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )


def test_wrong_repository_return_type_is_contract_violation() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    repository.current = object()  # type: ignore[assignment]
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.REPOSITORY_CONTRACT_VIOLATION
    assert captured.value.stage == "load_current"
    assert chain.fetch_count == 0


@pytest.mark.parametrize(
    "mutation",
    ["unsorted", "bad_first", "bad_hash", "empty"],
)
def test_malformed_current_generation_fails_closed(mutation: str) -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    if mutation == "unsorted":
        object.__setattr__(current, "bars", tuple(reversed(current.bars)))
    elif mutation == "bad_first":
        object.__setattr__(current.manifest, "first_trade_date", DAY_2)
    elif mutation == "bad_hash":
        object.__setattr__(current.manifest, "content_sha256", "f" * 64)
    else:
        object.__setattr__(current, "bars", ())
    repository = FakeRepository(current)
    chain = FakeChain(object())
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, StaticCalendar()).update(
            dataset,
            EODDateRange(DAY_1, DAY_4),
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.CURRENT_GENERATION_INVALID
    assert repository.load_count == 1
    assert chain.fetch_count == 0


def test_planning_exception_is_wrapped_and_stops_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()

    def fail(*args: object, **kwargs: object) -> object:
        raise RuntimeError("planner detail")

    monkeypatch.setattr(coordinator_module, "plan_eod_request_window", fail)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PLANNING_FAILED
    assert captured.value.stage == "planning"
    assert isinstance(captured.value.__cause__, RuntimeError)
    assert repository.load_count == 1
    assert chain.fetch_count == 0


def test_mismatched_planner_result_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    other = make_dataset(symbol="600001.SH")
    other_range = EODDateRange(DAY_1, DAY_4)
    mismatched = EODRequestPlan(
        dataset=other,
        requested_range=other_range,
        effective_range=other_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY),
        status=EODRequestPlanStatus.INITIAL_IMPORT,
        provider_request=EODProviderRequest(other, other_range),
    )
    monkeypatch.setattr(
        coordinator_module,
        "plan_eod_request_window",
        lambda *args, **kwargs: mismatched,
    )
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PLANNING_FAILED
    assert chain.fetch_count == 0


def make_chain_error(
    request: EODProviderRequest,
    code: EODProviderErrorCode,
) -> EODProviderChainError:
    attempt = EODProviderAttempt(
        position=0,
        provider_name="fake_provider",
        provider_version="1",
        endpoint_name="fake_endpoint",
        result_status=None,
        error_code=code,
        row_count=0,
        effective_range=None,
        warning_codes=(),
        selected=False,
        safe_message="The fake provider failed safely.",
    )
    return EODProviderChainError(
        request=request,
        attempts=(attempt,),
        final_code=code,
        message="The provider chain failed safely.",
    )


@pytest.mark.parametrize(
    ("provider_code", "retryable"),
    [
        (EODProviderErrorCode.UNSUPPORTED_REQUEST, False),
        (EODProviderErrorCode.PROVIDER_UNAVAILABLE, False),
        (EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE, True),
        (EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE, False),
        (EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, False),
    ],
)
def test_chain_errors_are_wrapped_with_attempts_and_retryability(
    provider_code: EODProviderErrorCode,
    retryable: bool,
) -> None:
    dataset, requested_range, repository, _, calendar = initial_setup()
    request = EODProviderRequest(dataset, requested_range)
    chain_error = make_chain_error(request, provider_code)
    chain = FakeChain(chain_error)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    error = captured.value
    assert error.code is EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED
    assert error.stage == "provider_chain"
    assert error.provider_error_code is provider_code
    assert error.attempts == chain_error.attempts
    assert error.retryable is retryable
    assert error.__cause__ is chain_error
    assert repository.publish_count == 0


def test_ordinary_chain_exception_is_non_retryable_and_safe() -> None:
    dataset, requested_range, repository, _, calendar = initial_setup()
    chain = FakeChain(RuntimeError("Authorization: Bearer secret-value"))
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    error = captured.value
    assert error.code is EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED
    assert error.provider_error_code is None
    assert error.retryable is False
    assert "secret-value" not in error.to_json()


def test_partial_result_is_retryable_and_never_published() -> None:
    dataset, requested_range, repository, _, calendar = initial_setup()
    request = EODProviderRequest(dataset, requested_range)
    partial = make_chain_result(
        request,
        (DAY_1, DAY_2, DAY_3),
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
    )
    chain = FakeChain(partial)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
            generation_id="generation-2",
            created_at=UTC_TIME,
        )
    error = captured.value
    assert error.code is EODIncrementalCoordinatorErrorCode.PARTIAL_RESULT_NOT_PUBLISHABLE
    assert error.retryable is True
    assert error.attempts == partial.attempts
    assert repository.publish_count == 0


def test_malformed_chain_return_is_provider_result_mismatch() -> None:
    dataset, requested_range, repository, _, calendar = initial_setup()
    chain = FakeChain(object())
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH
    assert repository.publish_count == 0


def test_chain_request_mismatch_is_rejected_with_attempts() -> None:
    dataset, requested_range, repository, _, calendar = initial_setup()
    other_range = EODDateRange(DAY_2, DAY_4)
    other_request = EODProviderRequest(dataset, other_range)
    mismatched = make_chain_result(other_request, (DAY_2, DAY_3, DAY_4))
    chain = FakeChain(mismatched)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        EODIncrementalCoordinator(repository, chain, calendar).update(
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH
    assert captured.value.attempts == mismatched.attempts


def test_real_chain_with_fake_provider_remains_fully_offline() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    request = EODProviderRequest(dataset, requested_range)
    provider_result = EODProviderResult(
        request=request,
        provider_name="fake_provider",
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4)),
    )
    provider = FakeProvider(provider_result, dataset)
    repository = FakeRepository()
    result = run_update(
        EODIncrementalCoordinator(
            repository,
            EODProviderChain((provider,)),
            StaticCalendar(),
        ),
        dataset,
        requested_range,
    )
    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED
    assert provider.calls == 1
    assert repository.publish_count == 1


def incremental_setup(
    *,
    events: Optional[list[str]] = None,
) -> tuple[EODDatasetKey, EODDateRange, FakeRepository, FakeChain, StaticCalendar]:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2))
    requested_range = EODDateRange(DAY_1, DAY_4)
    request = EODProviderRequest(dataset, EODDateRange(DAY_3, DAY_4))
    repository = FakeRepository(current, events=events)
    chain = FakeChain(make_chain_result(request, (DAY_3, DAY_4), offset=2), events=events)
    return dataset, requested_range, repository, chain, StaticCalendar()


def test_incremental_append_preserves_history_and_publishes_once() -> None:
    dataset, requested_range, repository, chain, calendar = incremental_setup()
    result = run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
    )
    published_bars = repository.publish_arguments["bars"]  # type: ignore[index]
    assert result.status is EODIncrementalUpdateStatus.INCREMENTAL_PUBLISHED
    assert result.previous_manifest == repository.current.manifest  # type: ignore[union-attr]
    assert [bar.trade_date for bar in published_bars] == [DAY_1, DAY_2, DAY_3, DAY_4]
    assert tuple(published_bars[:2]) == repository.current.bars  # type: ignore[union-attr,index]
    assert result.row_count == 4
    assert result.added_row_count == 2
    assert result.replaced_row_count == 0
    assert repository.publish_count == 1
    assert chain.fetch_count == 1


def test_incremental_retains_history_before_requested_start() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_2, DAY_5)
    request = EODProviderRequest(dataset, EODDateRange(DAY_4, DAY_5))
    repository = FakeRepository(current)
    chain = FakeChain(make_chain_result(request, (DAY_4, DAY_5), offset=3))
    run_update(
        EODIncrementalCoordinator(repository, chain, StaticCalendar()),
        dataset,
        requested_range,
    )
    published_bars = repository.publish_arguments["bars"]  # type: ignore[index]
    assert published_bars[0].trade_date == DAY_1
    assert len(published_bars) == 5


def test_append_overlap_is_merge_conflict_even_when_bar_is_identical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_1, DAY_4)
    request = EODProviderRequest(dataset, EODDateRange(DAY_3, DAY_4))
    plan = EODRequestPlan(
        dataset=dataset,
        requested_range=requested_range,
        effective_range=requested_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.APPEND_ONLY),
        status=EODRequestPlanStatus.INCREMENTAL,
        provider_request=request,
    )
    bars = (current.bars[-1], make_bar(dataset, DAY_4, 13))
    selected = EODProviderResult(
        request=request,
        provider_name="fake_provider",
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=bars,
    )
    attempt = EODProviderAttempt(
        position=0,
        provider_name="fake_provider",
        provider_version="1",
        endpoint_name="fake_endpoint",
        result_status=EODProviderResultStatus.SUCCESS,
        error_code=None,
        row_count=2,
        effective_range=request.requested_range,
        warning_codes=(),
        selected=True,
        safe_message="The fake provider returned validated EOD data.",
    )
    chain_result = EODProviderChainResult(request, selected, 0, (attempt,))
    monkeypatch.setattr(coordinator_module, "plan_eod_request_window", lambda *args: plan)
    repository = FakeRepository(current)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, FakeChain(chain_result), StaticCalendar()),
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.MERGE_CONFLICT
    assert captured.value.stage == "merge"
    assert repository.publish_count == 0


def overlap_setup(
    *,
    changed: bool = True,
) -> tuple[EODDatasetKey, EODDateRange, FakeRepository, FakeChain, StaticCalendar]:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_1, DAY_5)
    request = EODProviderRequest(dataset, EODDateRange(DAY_3, DAY_5))
    offset = 20 if changed else 2
    repository = FakeRepository(current)
    chain = FakeChain(make_chain_result(request, (DAY_3, DAY_4, DAY_5), offset=offset))
    return dataset, requested_range, repository, chain, StaticCalendar()


def test_overlap_refresh_replaces_whole_bars_and_preserves_outside_range() -> None:
    dataset, requested_range, repository, chain, calendar = overlap_setup()
    result = run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 1),
    )
    published_bars = repository.publish_arguments["bars"]  # type: ignore[index]
    fetched_bars = chain.response.selected_result.bars
    assert result.status is EODIncrementalUpdateStatus.OVERLAP_REFRESH_PUBLISHED
    assert tuple(published_bars[:2]) == repository.current.bars[:2]  # type: ignore[union-attr,index]
    assert tuple(published_bars[2:]) == fetched_bars
    assert result.added_row_count == 2
    assert result.replaced_row_count == 1


def test_overlap_refresh_replaces_amount_with_none() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_1, DAY_4)
    request = EODProviderRequest(dataset, EODDateRange(DAY_3, DAY_4))
    replacement = (
        make_bar(dataset, DAY_3, 30, amount=None),
        make_bar(dataset, DAY_4, 31, amount=None),
    )
    result = EODProviderResult(
        request=request,
        provider_name="fake_provider",
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=replacement,
    )
    attempt = EODProviderAttempt(
        position=0,
        provider_name="fake_provider",
        provider_version="1",
        endpoint_name="fake_endpoint",
        result_status=EODProviderResultStatus.SUCCESS,
        error_code=None,
        row_count=2,
        effective_range=request.requested_range,
        warning_codes=(),
        selected=True,
        safe_message="The fake provider returned validated EOD data.",
    )
    repository = FakeRepository(current)
    run_update(
        EODIncrementalCoordinator(
            repository,
            FakeChain(EODProviderChainResult(request, result, 0, (attempt,))),
            StaticCalendar(),
        ),
        dataset,
        requested_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 1),
    )
    published = repository.publish_arguments["bars"]  # type: ignore[index]
    assert published[2].amount is None
    assert published[2] == replacement[0]


def test_overlap_missing_date_does_not_reuse_old_bar() -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_1, DAY_5)
    request = EODProviderRequest(dataset, EODDateRange(DAY_3, DAY_5))
    incomplete = make_chain_result(request, (DAY_3, DAY_5), offset=20)
    repository = FakeRepository(current)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, FakeChain(incomplete), StaticCalendar()),
            dataset,
            requested_range,
            revision_policy=EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 1),
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED
    assert "missing_trading_days" in captured.value.validation_codes
    assert repository.publish_count == 0


def test_initial_missing_trading_date_is_rejected_even_when_report_is_valid() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    request = EODProviderRequest(dataset, requested_range)
    incomplete = make_chain_result(request, (DAY_1, DAY_2, DAY_4))
    repository = FakeRepository()
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, FakeChain(incomplete), StaticCalendar()),
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED
    assert captured.value.validation_codes == ("missing_trading_days",)
    assert repository.publish_count == 0


def test_non_trading_bar_is_rejected_before_hash_and_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_dataset()
    weekend = date(2024, 1, 6)
    requested_range = EODDateRange(DAY_1, weekend)
    request = EODProviderRequest(dataset, EODDateRange(DAY_1, DAY_4))
    chain_result = make_chain_result(request, (DAY_1, DAY_2, DAY_3, DAY_4))
    repository = FakeRepository()
    coordinator = EODIncrementalCoordinator(repository, FakeChain(chain_result), StaticCalendar())
    original_merge = coordinator._merge

    def inject_non_trading(*args: object, **kwargs: object) -> object:
        candidate, added, replaced = original_merge(*args, **kwargs)
        return candidate + (make_bar(dataset, weekend, 20),), added + 1, replaced

    hash_calls = 0

    def forbidden_hash(value: object) -> str:
        nonlocal hash_calls
        hash_calls += 1
        return "a" * 64

    monkeypatch.setattr(coordinator, "_merge", inject_non_trading)
    monkeypatch.setattr(coordinator_module, "calculate_eod_content_sha256", forbidden_hash)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(coordinator, dataset, requested_range)
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED
    assert hash_calls == 0
    assert repository.publish_count == 0


def test_bar_after_effective_end_is_rejected_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    original_merge = coordinator._merge

    def inject_future(*args: object, **kwargs: object) -> object:
        candidate, added, replaced = original_merge(*args, **kwargs)
        return candidate + (make_bar(dataset, DAY_5, 20),), added + 1, replaced

    monkeypatch.setattr(coordinator, "_merge", inject_future)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(coordinator, dataset, requested_range)
    assert captured.value.validation_codes == ("date_after_effective_end",)
    assert repository.publish_count == 0


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicate_candidate_is_never_silently_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
    conflicting: bool,
) -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    coordinator = EODIncrementalCoordinator(repository, chain, calendar)
    original_merge = coordinator._merge

    def duplicate(*args: object, **kwargs: object) -> object:
        candidate, added, replaced = original_merge(*args, **kwargs)
        extra = make_bar(dataset, DAY_2, 99) if conflicting else candidate[1]
        return candidate + (extra,), added + 1, replaced

    monkeypatch.setattr(coordinator, "_merge", duplicate)
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(coordinator, dataset, requested_range)
    expected = "duplicate_conflicting_bar" if conflicting else "duplicate_identical_bar"
    assert expected in captured.value.validation_codes
    assert repository.publish_count == 0


def test_unchanged_content_is_defensive_noop_after_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_dataset()
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3))
    requested_range = EODDateRange(DAY_1, DAY_3)
    request = EODProviderRequest(dataset, requested_range)
    plan = EODRequestPlan(
        dataset=dataset,
        requested_range=requested_range,
        effective_range=requested_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.OVERLAP_WINDOW, 3),
        status=EODRequestPlanStatus.OVERLAP_REFRESH,
        provider_request=request,
    )
    chain_result = make_chain_result(request, (DAY_1, DAY_2, DAY_3))
    monkeypatch.setattr(coordinator_module, "plan_eod_request_window", lambda *args: plan)
    repository = FakeRepository(current)
    result = EODIncrementalCoordinator(
        repository,
        FakeChain(chain_result),
        StaticCalendar(),
    ).update(dataset, requested_range)
    assert result.status is EODIncrementalUpdateStatus.UNCHANGED_CONTENT
    assert result.unchanged is True
    assert result.published is False
    assert result.row_count == 3
    assert result.added_row_count == 0
    assert result.replaced_row_count == 0
    assert result.attempts == chain_result.attempts
    assert repository.publish_count == 0


def test_publish_exception_is_non_retryable_and_not_repeated() -> None:
    dataset, requested_range, _, chain, calendar = initial_setup()
    repository = FakeRepository(publish_error=RuntimeError("C:\\private\\artifact"))
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, chain, calendar),
            dataset,
            requested_range,
        )
    error = captured.value
    assert error.code is EODIncrementalCoordinatorErrorCode.PUBLICATION_FAILED
    assert error.stage == "publish"
    assert error.retryable is False
    assert isinstance(error.__cause__, RuntimeError)
    assert "private" not in error.to_json()
    assert repository.publish_count == 1


@pytest.mark.parametrize(
    "field",
    [
        "dataset",
        "generation_id",
        "created_at",
        "row_count",
        "first_trade_date",
        "last_trade_date",
        "content_sha256",
        "data_version",
        "previous_generation_id",
    ],
)
def test_publish_manifest_mismatch_is_repository_contract_violation(field: str) -> None:
    dataset, requested_range, repository, chain, calendar = incremental_setup()
    candidate = repository.current.bars + chain.response.selected_result.bars  # type: ignore[union-attr]
    valid = make_manifest(
        candidate,
        generation_id="generation-2",
        previous_generation_id=repository.current.manifest.generation_id,  # type: ignore[union-attr]
    )
    if field == "dataset":
        object.__setattr__(valid, field, make_dataset(symbol="600001.SH"))
    elif field == "generation_id":
        object.__setattr__(valid, field, "other-generation")
    elif field == "created_at":
        object.__setattr__(valid, field, UTC_TIME + timedelta(seconds=1))
    elif field == "row_count":
        object.__setattr__(valid, field, len(candidate) + 1)
    elif field == "first_trade_date":
        object.__setattr__(valid, field, DAY_2)
    elif field == "last_trade_date":
        object.__setattr__(valid, field, DAY_3)
    elif field == "content_sha256":
        object.__setattr__(valid, field, "f" * 64)
    elif field == "data_version":
        object.__setattr__(valid, field, "sha256:" + "f" * 64)
    else:
        object.__setattr__(valid, field, "wrong-previous")
    repository.publish_result = valid
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, chain, calendar),
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.REPOSITORY_CONTRACT_VIOLATION
    assert captured.value.stage == "publish_response"
    assert captured.value.retryable is False
    assert repository.publish_count == 1
    assert repository.load_count == 1


def test_non_manifest_publish_return_is_contract_violation() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    repository.publish_result = object()
    with pytest.raises(EODIncrementalCoordinatorError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, chain, calendar),
            dataset,
            requested_range,
        )
    assert captured.value.code is EODIncrementalCoordinatorErrorCode.REPOSITORY_CONTRACT_VIOLATION
    assert repository.publish_count == 1


def test_dependency_call_order_is_load_plan_fetch_validate_hash_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    dataset, requested_range, repository, chain, calendar = initial_setup(events=events)
    original_plan = coordinator_module.plan_eod_request_window
    original_validate = coordinator_module.validate_eod_batch
    original_hash = coordinator_module.calculate_eod_content_sha256

    def plan(*args: object, **kwargs: object) -> EODRequestPlan:
        events.append("plan")
        return original_plan(*args, **kwargs)

    def validate(*args: object, **kwargs: object) -> object:
        events.append("validate")
        return original_validate(*args, **kwargs)

    def content_hash(*args: object, **kwargs: object) -> str:
        events.append("hash")
        return original_hash(*args, **kwargs)

    monkeypatch.setattr(coordinator_module, "plan_eod_request_window", plan)
    monkeypatch.setattr(coordinator_module, "validate_eod_batch", validate)
    monkeypatch.setattr(coordinator_module, "calculate_eod_content_sha256", content_hash)
    run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
    )
    assert events == ["load_current", "plan", "fetch", "validate", "validate", "hash", "publish"]


def test_result_is_frozen_strict_and_deterministic() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    result = run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
    )
    assert result.to_dict() == json.loads(result.to_json())
    assert result.to_json() == result.to_json()
    assert "bars" not in result.to_dict()
    with pytest.raises(FrozenInstanceError):
        result.row_count = 99  # type: ignore[misc]


@pytest.mark.parametrize("field", ["row_count", "added_row_count", "replaced_row_count"])
@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_result_rejects_invalid_counts(field: str, value: object) -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_2)
    plan = coordinator_module.plan_eod_request_window(
        dataset,
        requested_range,
        StaticCalendar(),
    )
    values: dict[str, object] = {
        "dataset": dataset,
        "requested_range": requested_range,
        "status": EODIncrementalUpdateStatus.NO_TRADING_DAYS,
        "plan": plan,
        "previous_manifest": None,
        "published_manifest": None,
        "attempts": (),
        "row_count": 0,
        "added_row_count": 0,
        "replaced_row_count": 0,
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError)):
        EODIncrementalUpdateResult(**values)  # type: ignore[arg-type]


def test_error_serialization_is_safe_stable_and_excludes_cause() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_2)
    error = EODIncrementalCoordinatorError(
        EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED,
        "validation",
        "C:\\private\\token.txt apiKey=secret",
        dataset,
        requested_range,
        validation_codes=("missing_trading_days", "missing_trading_days"),
        retryable=False,
    )
    error.__cause__ = RuntimeError("Authorization: Bearer hidden")
    payload = error.to_dict()
    serialized = error.to_json()
    assert payload["validation_codes"] == ["missing_trading_days"]
    assert "private" not in serialized
    assert "secret" not in serialized
    assert "hidden" not in serialized
    assert "cause" not in payload
    assert "traceback" not in serialized.lower()


def test_error_rejects_retryable_value_that_conflicts_with_code() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_2)
    with pytest.raises(ValueError, match="retryable"):
        EODIncrementalCoordinatorError(
            EODIncrementalCoordinatorErrorCode.PUBLICATION_FAILED,
            "publish",
            "Publication failed safely.",
            dataset,
            requested_range,
            retryable=True,
        )


def test_root_import_defers_coordinator_repository_pyarrow_and_akshare() -> None:
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
assert "autowealth.market_data.provider_chain" not in sys.modules
assert "autowealth.market_data.repositories" not in sys.modules
assert "autowealth.market_data.akshare_adapters" not in sys.modules
assert "pyarrow" not in set(sys.modules) - before_modules
assert "akshare" not in set(sys.modules) - before_modules
assert "EODIncrementalCoordinator" in market_data.__all__
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_explicit_coordinator_import_defers_repository_and_external_packages() -> None:
    script = r"""
import sys

import autowealth

before = set(sys.modules)
import autowealth.market_data.coordinator

assert "autowealth.market_data.repositories" not in sys.modules
new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before}
assert {"akshare", "pandas", "pyarrow"}.isdisjoint(new_roots)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_coordinator_source_has_no_clock_uuid_environment_or_forbidden_imports() -> None:
    source = (ROOT / "autowealth/market_data/coordinator.py").read_text(encoding="utf-8")
    forbidden = (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "uuid",
        "secrets",
        "os.environ",
        "os.getenv",
        "import pandas",
        "import pyarrow",
        "import akshare",
        "from .repositories import LocalEODFileRepository",
    )
    assert all(fragment not in source for fragment in forbidden)


@pytest.mark.parametrize(
    "relative_path",
    [
        "autowealth/market_data/__init__.py",
        "autowealth/market_data/coordinator.py",
        "tests/test_eod_incremental_coordinator.py",
        "tests/test_eod_provider_contracts.py",
    ],
)
def test_pr6_python_files_parse_with_python_39_grammar(relative_path: str) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    ast.parse(source, filename=relative_path, feature_version=(3, 9))


def test_checkpoint_runs_immediately_before_incremental_publication() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    checkpoints = []

    def checkpoint(stage: EODCheckpointStage, value: Optional[EODDatasetKey]) -> None:
        checkpoints.append((stage, value, repository.publish_count))

    result = run_update(
        EODIncrementalCoordinator(repository, chain, calendar),
        dataset,
        requested_range,
        checkpoint=checkpoint,
    )

    assert result.status is EODIncrementalUpdateStatus.INITIAL_IMPORT_PUBLISHED
    assert checkpoints == [(EODCheckpointStage.BEFORE_PUBLICATION, dataset, 0)]
    assert repository.publish_count == 1


def test_incremental_publication_checkpoint_error_propagates_unchanged() -> None:
    dataset, requested_range, repository, chain, calendar = initial_setup()
    error = EODOperationControlError("lease_control_failure")

    def checkpoint(stage: EODCheckpointStage, value: Optional[EODDatasetKey]) -> None:
        assert stage is EODCheckpointStage.BEFORE_PUBLICATION
        assert value == dataset
        raise error

    with pytest.raises(EODOperationControlError) as captured:
        run_update(
            EODIncrementalCoordinator(repository, chain, calendar),
            dataset,
            requested_range,
            checkpoint=checkpoint,
        )

    assert captured.value is error
    assert chain.fetch_count == 1
    assert repository.publish_count == 0
