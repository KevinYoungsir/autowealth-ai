from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import ast
import json
import socket
import subprocess
import sys
from typing import Callable, Optional, Tuple

import pytest

from autowealth.market_data.batch import (
    InProcessEODDatasetLockManager,
    eod_dataset_lock_key,
)
from autowealth.market_data.coordinator import (
    EODIncrementalCoordinator,
    EODIncrementalCoordinatorError,
    EODIncrementalCoordinatorErrorCode,
    EODIncrementalUpdateStatus,
)
from autowealth.market_data.full_refresh import (
    EODFullRefreshErrorCode,
    EODFullRefreshExecutor,
    EODFullRefreshExecutorError,
    EODFullRefreshRequest,
    EODFullRefreshResult,
    EODFullRefreshStatus,
)
from autowealth.market_data.operation_control import (
    EODCheckpointStage,
    EODOperationControlError,
)
from autowealth.market_data.planning import (
    EODRequestPlan,
    EODRequestPlanningError,
    EODRequestPlanningErrorCode,
    EODRequestPlanStatus,
    EODRevisionPolicy,
)
from autowealth.market_data.provider_chain import (
    EODProviderAttempt,
    EODProviderChain,
    EODProviderChainError,
    EODProviderChainResult,
)
from autowealth.market_data.provider_resilience import (
    EODProviderRetryPolicy,
    NoOpEODProviderRateLimiter,
)
from autowealth.market_data.providers import (
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRevisionStrategy,
)
from autowealth.market_data.repositories import LocalEODFileRepository
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EOD_PARQUET_FILE,
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_eod_content_sha256,
)

DAY_0 = date(2024, 1, 1)
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
DAY_4 = date(2024, 1, 5)
DAY_5 = date(2024, 1, 8)
TRADING_DAYS = (DAY_1, DAY_2, DAY_3, DAY_4, DAY_5)
UTC_TIME = datetime(2024, 1, 9, 8, 0, tzinfo=timezone.utc)


class StaticCalendar:
    def __init__(self, days: Tuple[date, ...] = TRADING_DAYS) -> None:
        self.days = days

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return next(day for day in self.days if day > value)

    def previous_trading_day(self, value: date) -> date:
        return next(day for day in reversed(self.days) if day < value)

    def trading_days(self, start_date: date, end_date: date) -> Tuple[date, ...]:
        return tuple(day for day in self.days if start_date <= day <= end_date)


class FakeRepository:
    def __init__(
        self,
        current: Optional[EODStoredGeneration],
        *,
        publish_error: Optional[BaseException] = None,
        manifest_mutation: Optional[Callable[[EODGenerationManifest], object]] = None,
        load_error: Optional[BaseException] = None,
    ) -> None:
        self.current = current
        self.publish_error = publish_error
        self.manifest_mutation = manifest_mutation
        self.load_error = load_error
        self.load_count = 0
        self.publish_count = 0
        self.published_bars: Tuple[EODBar, ...] = ()
        self.generations = {} if current is None else {current.manifest.generation_id: current}

    def load_current(self, dataset: EODDatasetKey) -> Optional[EODStoredGeneration]:
        self.load_count += 1
        if self.load_error is not None:
            raise self.load_error
        if self.current is not None and self.current.manifest.dataset != dataset:
            raise AssertionError("unexpected dataset")
        return self.current

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: Tuple[EODBar, ...],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> object:
        self.publish_count += 1
        if self.publish_error is not None:
            raise self.publish_error
        normalized = tuple(bars)
        self.published_bars = normalized
        previous = None if self.current is None else self.current.manifest.generation_id
        content_sha = calculate_eod_content_sha256(normalized)
        manifest = EODGenerationManifest(
            manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
            eod_schema_version=1,
            generation_id=generation_id,
            dataset=dataset,
            created_at=created_at,
            row_count=len(normalized),
            first_trade_date=normalized[0].trade_date,
            last_trade_date=normalized[-1].trade_date,
            data_version=f"sha256:{content_sha}",
            content_sha256=content_sha,
            parquet_sha256="a" * 64,
            previous_generation_id=previous,
            parquet_file=EOD_PARQUET_FILE,
        )
        returned = manifest if self.manifest_mutation is None else self.manifest_mutation(manifest)
        if type(returned) is EODGenerationManifest:
            stored = EODStoredGeneration(manifest=manifest, bars=normalized)
            self.generations[generation_id] = stored
            self.current = stored
        return returned


class FakeChain:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.fetch_count = 0
        self.requests = []

    def fetch(
        self,
        request: EODProviderRequest,
        *,
        checkpoint: object = None,
    ) -> object:
        self.fetch_count += 1
        self.requests.append(request)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


class RecordingLockManager:
    def __init__(self) -> None:
        self.held = set()
        self.acquire_count = 0
        self.release_count = 0
        self.acquire_result: object = True
        self.acquire_error: Optional[Exception] = None
        self.release_error: Optional[Exception] = None

    def acquire(self, lock_key: str) -> bool:
        self.acquire_count += 1
        if self.acquire_error is not None:
            raise self.acquire_error
        if self.acquire_result is not True or lock_key in self.held:
            return self.acquire_result  # type: ignore[return-value]
        self.held.add(lock_key)
        return True

    def release(self, lock_key: str) -> None:
        self.release_count += 1
        if self.release_error is not None:
            raise self.release_error
        self.held.remove(lock_key)


class RecordingSleeper:
    def __init__(self) -> None:
        self.calls = []

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)


class RetryOnceProvider:
    provider_name = "retry_once_provider"
    provider_version = "1"
    endpoint_name = "fake_endpoint"

    def __init__(
        self,
        dataset: EODDatasetKey,
        result: EODProviderResult,
    ) -> None:
        self.capabilities = (
            EODProviderCapability(
                market=dataset.market,
                venue=dataset.venue,
                asset_type=dataset.asset_type,
                frequency=dataset.frequency,
                adjustment_type=dataset.adjustment_type,
                revision_strategy=EODRevisionStrategy.FULL_REFRESH_REQUIRED,
            ),
        )
        self.result = result
        self.fetch_count = 0

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.fetch_count += 1
        if self.fetch_count == 1:
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The fake provider failed temporarily.",
            )
        assert request == self.result.request
        return self.result


class StaticResultProvider:
    endpoint_name = "fake_endpoint"

    def __init__(
        self,
        provider_name: str,
        dataset: EODDatasetKey,
        result: EODProviderResult,
    ) -> None:
        self.provider_name = provider_name
        self.provider_version = "1"
        self.capabilities = (
            EODProviderCapability(
                market=dataset.market,
                venue=dataset.venue,
                asset_type=dataset.asset_type,
                frequency=dataset.frequency,
                adjustment_type=dataset.adjustment_type,
                revision_strategy=EODRevisionStrategy.FULL_REFRESH_REQUIRED,
            ),
        )
        self.result = result
        self.fetch_count = 0

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.fetch_count += 1
        assert request == self.result.request
        return self.result


class RaisingLimiter:
    def acquire(self, provider_name: str, endpoint_name: str) -> float:
        raise RuntimeError("limiter failed")


class RaisingSleeper:
    def sleep(self, seconds: float) -> None:
        raise RuntimeError("sleeper failed")


def make_dataset(
    symbol: str = "600000.SH",
    adjustment: AdjustmentType = AdjustmentType.QFQ,
) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=adjustment,
    )


def make_bar(dataset: EODDatasetKey, trade_date: date, offset: int = 0) -> EODBar:
    base = Decimal(10 + offset)
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=base,
        high=base + Decimal("2"),
        low=base - Decimal("1"),
        close=base + Decimal("1"),
        volume=Decimal(1000 + offset),
        amount=Decimal(10000 + offset),
    )


def make_bars(
    dataset: EODDatasetKey,
    days: Tuple[date, ...],
    *,
    offset: int = 0,
) -> Tuple[EODBar, ...]:
    return tuple(make_bar(dataset, day, offset + index) for index, day in enumerate(days))


def make_stored(
    dataset: EODDatasetKey,
    days: Tuple[date, ...],
    *,
    generation_id: str = "generation-1",
    offset: int = 0,
) -> EODStoredGeneration:
    bars = make_bars(dataset, days, offset=offset)
    content_sha = calculate_eod_content_sha256(bars)
    manifest = EODGenerationManifest(
        manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
        eod_schema_version=1,
        generation_id=generation_id,
        dataset=dataset,
        created_at=UTC_TIME,
        row_count=len(bars),
        first_trade_date=bars[0].trade_date,
        last_trade_date=bars[-1].trade_date,
        data_version=f"sha256:{content_sha}",
        content_sha256=content_sha,
        parquet_sha256="b" * 64,
        previous_generation_id=None,
        parquet_file=EOD_PARQUET_FILE,
    )
    return EODStoredGeneration(manifest=manifest, bars=bars)


def make_chain_result(
    request: EODProviderRequest,
    bars: Tuple[EODBar, ...],
    *,
    status: EODProviderResultStatus = EODProviderResultStatus.SUCCESS,
) -> EODProviderChainResult:
    result = EODProviderResult(
        request=request,
        provider_name="fake_provider",
        provider_version="1",
        status=status,
        bars=bars,
    )
    attempt = EODProviderAttempt(
        position=0,
        provider_name=result.provider_name,
        provider_version=result.provider_version,
        endpoint_name="fake_endpoint",
        result_status=status,
        error_code=None,
        row_count=len(bars),
        effective_range=result.effective_range,
        warning_codes=tuple(warning.code for warning in result.warnings),
        selected=True,
        safe_message="The fake provider returned validated EOD data.",
    )
    return EODProviderChainResult(
        request=request,
        selected_result=result,
        selected_position=0,
        attempts=(attempt,),
    )


def eligible_setup(
    *,
    current_days: Tuple[date, ...] = (DAY_1, DAY_2),
    replacement_offset: int = 10,
) -> tuple[
    EODDatasetKey,
    EODDateRange,
    FakeRepository,
    FakeChain,
    RecordingLockManager,
]:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    current = make_stored(dataset, current_days)
    provider_request = EODProviderRequest(dataset, requested_range)
    replacement = make_bars(
        dataset,
        (DAY_1, DAY_2, DAY_3, DAY_4),
        offset=replacement_offset,
    )
    repository = FakeRepository(current)
    chain = FakeChain(make_chain_result(provider_request, replacement))
    return dataset, requested_range, repository, chain, RecordingLockManager()


def execute_real(
    executor: EODFullRefreshExecutor,
    dataset: EODDatasetKey,
    requested_range: EODDateRange,
) -> EODFullRefreshResult:
    return executor.execute(
        EODFullRefreshRequest(dataset, requested_range),
        generation_id="generation-2",
        created_at=UTC_TIME,
    )


def test_adjusted_dataset_is_eligible_and_dry_run_reports_full_effective_range() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(
        repository,
        chain,
        StaticCalendar(),
        lock_manager,
    )

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range, dry_run=True))

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PLANNED
    assert result.plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
    assert result.plan.provider_request is None
    assert result.provider_request == EODProviderRequest(dataset, requested_range)
    assert result.previous_manifest == repository.current.manifest  # type: ignore[union-attr]
    assert result.would_replace_generation_id == "generation-1"
    assert result.would_publish is False
    assert result.attempts == ()
    assert result.lock_key is None
    assert chain.fetch_count == lock_manager.acquire_count == repository.publish_count == 0


def test_history_gap_is_eligible_even_for_unadjusted_dataset() -> None:
    dataset = make_dataset(adjustment=AdjustmentType.NONE)
    requested_range = EODDateRange(DAY_1, DAY_4)
    current = make_stored(dataset, (DAY_2, DAY_3))
    repository = FakeRepository(current)
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(AssertionError("dry-run fetched")),
        StaticCalendar(),
        RecordingLockManager(),
    )

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range, dry_run=True))

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PLANNED
    assert result.plan.status is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
    assert result.provider_request == EODProviderRequest(dataset, requested_range)


@pytest.mark.parametrize(
    ("current_days", "requested_range", "expected_plan"),
    [
        ((DAY_1, DAY_2), EODDateRange(DAY_1, DAY_4), EODRequestPlanStatus.INCREMENTAL),
        (
            (DAY_1, DAY_2, DAY_3, DAY_4),
            EODDateRange(DAY_1, DAY_4),
            EODRequestPlanStatus.ALREADY_CURRENT,
        ),
    ],
)
def test_executor_refuses_plans_that_do_not_require_full_refresh(
    current_days: Tuple[date, ...],
    requested_range: EODDateRange,
    expected_plan: EODRequestPlanStatus,
) -> None:
    dataset = make_dataset(adjustment=AdjustmentType.NONE)
    repository = FakeRepository(make_stored(dataset, current_days))
    chain = FakeChain(AssertionError("not-eligible execution fetched"))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range))

    assert result.status is EODFullRefreshStatus.NOT_ELIGIBLE
    assert result.plan.status is expected_plan
    assert result.provider_request is None
    assert chain.fetch_count == repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_no_trading_days_is_not_eligible_and_dry_run_remains_observational() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_0, DAY_0)
    repository = FakeRepository(None)
    chain = FakeChain(AssertionError("no-trading-days fetched"))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range, dry_run=True))

    assert result.status is EODFullRefreshStatus.NOT_ELIGIBLE
    assert result.plan.status is EODRequestPlanStatus.NO_TRADING_DAYS
    assert result.provider_request is None
    assert chain.fetch_count == repository.publish_count == lock_manager.acquire_count == 0


def test_initial_import_remains_not_eligible_for_explicit_full_refresh() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    repository = FakeRepository(None)
    chain = FakeChain(AssertionError("initial import fetched through full refresh"))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range))

    assert result.status is EODFullRefreshStatus.NOT_ELIGIBLE
    assert result.plan.status is EODRequestPlanStatus.INITIAL_IMPORT
    assert result.previous_manifest is None
    assert chain.fetch_count == repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_planner_failure_is_not_converted_to_not_eligible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    def fail_planning(*args: object, **kwargs: object) -> None:
        raise EODRequestPlanningError(
            EODRequestPlanningErrorCode.INVALID_CALENDAR,
            "The fake calendar is invalid.",
        )

    monkeypatch.setattr(executor._operations, "_plan", fail_planning)

    with pytest.raises(EODRequestPlanningError):
        execute_real(executor, dataset, requested_range)

    assert chain.fetch_count == repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_successful_full_refresh_replaces_all_rows_and_preserves_lineage() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    original = repository.current
    original_snapshot = original.bars  # type: ignore[union-attr]
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = execute_real(executor, dataset, requested_range)

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert result.published is True
    assert result.row_count == 4
    assert result.replaced_row_count == 2
    assert chain.requests == [EODProviderRequest(dataset, requested_range)]
    assert repository.published_bars == make_bars(
        dataset,
        (DAY_1, DAY_2, DAY_3, DAY_4),
        offset=10,
    )
    assert repository.published_bars[:2] != original_snapshot
    assert repository.generations["generation-1"] is original
    assert repository.generations["generation-1"].bars == original_snapshot
    assert result.published_manifest is not None
    assert result.published_manifest.previous_generation_id == "generation-1"
    assert repository.current.manifest.generation_id == "generation-2"  # type: ignore[union-attr]
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held


def test_real_execution_acquires_lock_before_first_repository_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    events = []
    original_acquire = lock_manager.acquire
    original_load = repository.load_current

    def acquire(lock_key: str) -> bool:
        events.append("lock_acquire")
        return original_acquire(lock_key)

    def load_current(value: EODDatasetKey) -> Optional[EODStoredGeneration]:
        events.append("repository_load")
        assert eod_dataset_lock_key(value) in lock_manager.held
        return original_load(value)

    monkeypatch.setattr(lock_manager, "acquire", acquire)
    monkeypatch.setattr(repository, "load_current", load_current)
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = execute_real(executor, dataset, requested_range)

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert events[:2] == ["lock_acquire", "repository_load"]


def test_local_repository_publication_preserves_old_generation_and_advances_pointer(
    tmp_path: Path,
) -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    repository = LocalEODFileRepository(tmp_path / "repository")
    old_bars = make_bars(dataset, (DAY_1, DAY_2))
    old_manifest = repository.publish(
        dataset,
        old_bars,
        generation_id="generation-1",
        created_at=UTC_TIME,
    )
    old_generation = repository.load_generation(dataset, "generation-1")
    replacement = make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=25)
    provider_request = EODProviderRequest(dataset, requested_range)
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(make_chain_result(provider_request, replacement)),
        StaticCalendar(),
        RecordingLockManager(),
    )

    result = executor.execute(
        EODFullRefreshRequest(dataset, requested_range),
        generation_id="generation-2",
        created_at=UTC_TIME,
    )

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert repository.list_generation_ids(dataset) == ("generation-1", "generation-2")
    assert repository.load_generation(dataset, "generation-1") == old_generation
    assert repository.load_generation(dataset, "generation-1").manifest == old_manifest
    current = repository.load_current(dataset)
    assert current is not None
    assert current.manifest.generation_id == "generation-2"
    assert current.bars == replacement
    assert result.published_manifest is not None
    assert result.published_manifest.previous_generation_id == "generation-1"


def test_full_refresh_reuses_provider_chain_retry_budget_without_outer_retry() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    current = make_stored(dataset, (DAY_1, DAY_2))
    provider_request = EODProviderRequest(dataset, requested_range)
    provider_result = EODProviderResult(
        request=provider_request,
        provider_name=RetryOnceProvider.provider_name,
        provider_version=RetryOnceProvider.provider_version,
        status=EODProviderResultStatus.SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=10),
    )
    provider = RetryOnceProvider(dataset, provider_result)
    sleeper = RecordingSleeper()
    chain = EODProviderChain(
        (provider,),
        retry_policy=EODProviderRetryPolicy(
            max_attempts=2,
            initial_backoff_seconds=0.25,
            backoff_multiplier=2.0,
            max_backoff_seconds=1.0,
        ),
        rate_limiter=NoOpEODProviderRateLimiter(),
        retry_sleeper=sleeper,
    )
    repository = FakeRepository(current)
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = execute_real(executor, dataset, requested_range)

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert provider.fetch_count == 2
    assert sleeper.calls == [0.25]
    assert len(result.attempts) == 1
    assert len(result.attempts[0].invocations) == 2
    assert repository.publish_count == 1


def test_partial_primary_does_not_prevent_complete_fallback_publication() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    provider_request = EODProviderRequest(dataset, requested_range)
    primary_result = EODProviderResult(
        request=provider_request,
        provider_name="primary_provider",
        provider_version="1",
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_4), offset=10),
    )
    fallback_result = EODProviderResult(
        request=provider_request,
        provider_name="fallback_provider",
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=20),
    )
    primary = StaticResultProvider("primary_provider", dataset, primary_result)
    fallback = StaticResultProvider("fallback_provider", dataset, fallback_result)
    chain = EODProviderChain((primary, fallback))
    repository = FakeRepository(make_stored(dataset, (DAY_1, DAY_2)))
    executor = EODFullRefreshExecutor(
        repository,
        chain,
        StaticCalendar(),
        RecordingLockManager(),
    )

    result = execute_real(executor, dataset, requested_range)

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert result.attempts[0].result_status is EODProviderResultStatus.PARTIAL_SUCCESS
    assert result.attempts[1].result_status is EODProviderResultStatus.SUCCESS
    assert result.attempts[1].selected is True
    assert repository.published_bars == fallback_result.bars
    assert primary.fetch_count == fallback.fetch_count == 1


def test_all_partial_providers_are_rejected_without_publication() -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    provider_request = EODProviderRequest(dataset, requested_range)
    providers = []
    for name, days in (
        ("primary_provider", (DAY_1, DAY_2)),
        ("fallback_provider", (DAY_1, DAY_2, DAY_4)),
    ):
        result = EODProviderResult(
            request=provider_request,
            provider_name=name,
            provider_version="1",
            status=EODProviderResultStatus.PARTIAL_SUCCESS,
            bars=make_bars(dataset, days, offset=10),
        )
        providers.append(StaticResultProvider(name, dataset, result))
    repository = FakeRepository(make_stored(dataset, (DAY_1, DAY_2)))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(
        repository,
        EODProviderChain(tuple(providers)),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PARTIAL_RESULT_NOT_PUBLISHABLE
    assert repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_full_refresh_uses_effective_calendar_range_not_current_tail() -> None:
    dataset = make_dataset(adjustment=AdjustmentType.NONE)
    requested_range = EODDateRange(DAY_0, DAY_4)
    effective_range = EODDateRange(DAY_1, DAY_4)
    current = make_stored(dataset, (DAY_2, DAY_3))
    repository = FakeRepository(current)
    chain = FakeChain(
        make_chain_result(
            EODProviderRequest(dataset, effective_range),
            make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=20),
        )
    )
    executor = EODFullRefreshExecutor(
        repository,
        chain,
        StaticCalendar(),
        RecordingLockManager(),
    )

    result = execute_real(executor, dataset, requested_range)

    assert result.plan.effective_range == effective_range
    assert result.provider_request == EODProviderRequest(dataset, effective_range)
    assert chain.requests == [EODProviderRequest(dataset, effective_range)]


def test_identical_complete_content_is_defensive_noop_without_new_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    current = make_stored(dataset, (DAY_1, DAY_2, DAY_3, DAY_4))
    repository = FakeRepository(current)
    request = EODProviderRequest(dataset, requested_range)
    chain = FakeChain(make_chain_result(request, current.bars))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)
    full_refresh_plan = EODRequestPlan(
        dataset=dataset,
        requested_range=requested_range,
        effective_range=requested_range,
        revision_policy=EODRevisionPolicy(EODRevisionStrategy.FULL_REFRESH_REQUIRED),
        status=EODRequestPlanStatus.FULL_REFRESH_REQUIRED,
        provider_request=None,
    )
    monkeypatch.setattr(
        executor._operations,
        "_plan",
        lambda *args, **kwargs: full_refresh_plan,
    )

    result = executor.execute(
        EODFullRefreshRequest(dataset, requested_range),
        generation_id="unused-generation",
        created_at=UTC_TIME,
    )

    assert result.status is EODFullRefreshStatus.UNCHANGED_CONTENT
    assert result.unchanged is True
    assert result.published_manifest is None
    assert repository.publish_count == 0
    assert tuple(repository.generations) == ("generation-1",)
    assert repository.current is current
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_partial_provider_result_never_publishes_or_changes_current() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    current = repository.current
    provider_request = EODProviderRequest(dataset, requested_range)
    partial = make_chain_result(
        provider_request,
        make_bars(dataset, (DAY_1, DAY_2, DAY_4), offset=10),
        status=EODProviderResultStatus.PARTIAL_SUCCESS,
    )
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(partial),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PARTIAL_RESULT_NOT_PUBLISHABLE
    assert repository.publish_count == 0
    assert repository.current is current
    assert tuple(repository.generations) == ("generation-1",)
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held


def test_exhausted_provider_chain_releases_lock_and_preserves_current() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    current = repository.current
    provider_request = EODProviderRequest(dataset, requested_range)
    attempt = EODProviderAttempt(
        position=0,
        provider_name="fake_provider",
        provider_version="1",
        endpoint_name="fake_endpoint",
        result_status=None,
        error_code=EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        row_count=0,
        effective_range=None,
        warning_codes=(),
        selected=False,
        safe_message="The fake provider is unavailable.",
    )
    chain_error = EODProviderChainError(
        provider_request,
        (attempt,),
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        "The fake provider chain is unavailable.",
    )
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(chain_error),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PROVIDER_CHAIN_FAILED
    assert repository.current is current
    assert repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held


def test_missing_required_trading_day_fails_closed() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    current = repository.current
    provider_request = EODProviderRequest(dataset, requested_range)
    incomplete = make_chain_result(
        provider_request,
        make_bars(dataset, (DAY_1, DAY_2, DAY_4), offset=10),
    )
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(incomplete),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED
    assert "missing_trading_days" in raised.value.validation_codes
    assert repository.publish_count == 0
    assert repository.current is current
    assert lock_manager.release_count == 1


def test_normalization_does_not_hide_duplicate_or_missing_middle_date() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    current = repository.current
    provider_request = EODProviderRequest(dataset, requested_range)
    duplicated = make_chain_result(
        provider_request,
        make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=10),
    )
    corrupted_bars = make_bars(dataset, (DAY_1, DAY_2, DAY_2, DAY_4), offset=10)
    object.__setattr__(duplicated.selected_result, "bars", corrupted_bars)
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(duplicated),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert len(corrupted_bars) == 4
    assert DAY_3 not in {bar.trade_date for bar in corrupted_bars}
    assert raised.value.code is EODIncrementalCoordinatorErrorCode.VALIDATION_FAILED
    assert "duplicate_conflicting_bar" in raised.value.validation_codes
    assert repository.current is current
    assert repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_out_of_range_provider_bar_fails_closed_even_after_dependency_corruption() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    provider_request = EODProviderRequest(dataset, requested_range)
    valid = make_chain_result(
        provider_request,
        make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=10),
    )
    corrupted_bars = valid.selected_result.bars + (make_bar(dataset, DAY_5, 99),)
    object.__setattr__(valid.selected_result, "bars", corrupted_bars)
    executor = EODFullRefreshExecutor(
        repository,
        FakeChain(valid),
        StaticCalendar(),
        lock_manager,
    )

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PROVIDER_RESULT_MISMATCH
    assert repository.publish_count == 0
    assert lock_manager.release_count == 1


def test_dry_run_does_not_fetch_acquire_lock_or_require_publication_context() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = executor.execute(EODFullRefreshRequest(dataset, requested_range, dry_run=True))

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PLANNED
    assert chain.fetch_count == 0
    assert repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 0


def test_real_publication_requires_explicit_generation_context_after_fetch() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        executor.execute(EODFullRefreshRequest(dataset, requested_range))

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID
    assert chain.fetch_count == 1
    assert repository.publish_count == 0
    assert lock_manager.release_count == 1


@pytest.mark.parametrize(
    ("configuration", "expected_code"),
    [
        ("unavailable", EODFullRefreshErrorCode.LOCK_UNAVAILABLE),
        ("exception", EODFullRefreshErrorCode.LOCK_ACQUISITION_FAILED),
        ("invalid", EODFullRefreshErrorCode.LOCK_CONTRACT_VIOLATION),
    ],
)
def test_lock_acquisition_failures_stop_before_repository_access(
    configuration: str,
    expected_code: EODFullRefreshErrorCode,
) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    if configuration == "unavailable":
        lock_manager.acquire_result = False
    elif configuration == "exception":
        lock_manager.acquire_error = RuntimeError("C:\\private\\lock")
    else:
        lock_manager.acquire_result = 1
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(EODFullRefreshExecutorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is expected_code
    assert repository.load_count == chain.fetch_count == repository.publish_count == 0
    assert "private" not in raised.value.to_json().lower()


def test_same_dataset_lock_blocks_full_refresh_and_different_dataset_is_independent() -> None:
    shared_locks = InProcessEODDatasetLockManager()
    first, requested_range, first_repository, first_chain, _ = eligible_setup()
    first_key = eod_dataset_lock_key(first)
    assert shared_locks.acquire(first_key) is True
    first_executor = EODFullRefreshExecutor(
        first_repository,
        first_chain,
        StaticCalendar(),
        shared_locks,
    )

    with pytest.raises(EODFullRefreshExecutorError) as raised:
        execute_real(first_executor, first, requested_range)
    assert raised.value.code is EODFullRefreshErrorCode.LOCK_UNAVAILABLE

    second = make_dataset("600001.SH")
    second_current = make_stored(second, (DAY_1, DAY_2))
    second_request = EODProviderRequest(second, requested_range)
    second_repository = FakeRepository(second_current)
    second_chain = FakeChain(
        make_chain_result(
            second_request,
            make_bars(second, (DAY_1, DAY_2, DAY_3, DAY_4), offset=20),
        )
    )
    second_executor = EODFullRefreshExecutor(
        second_repository,
        second_chain,
        StaticCalendar(),
        shared_locks,
    )

    second_result = execute_real(second_executor, second, requested_range)

    assert second_result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    shared_locks.release(first_key)


@pytest.mark.parametrize(
    "failure_kind",
    [
        "partial",
        "validation",
        "content_hash",
        "publication",
        "publish_response",
        "unknown",
    ],
)
def test_lock_is_released_after_every_failure_path(
    failure_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    if failure_kind == "partial":
        provider_request = EODProviderRequest(dataset, requested_range)
        chain.outcome = make_chain_result(
            provider_request,
            make_bars(dataset, (DAY_1, DAY_2, DAY_4), offset=10),
            status=EODProviderResultStatus.PARTIAL_SUCCESS,
        )
    elif failure_kind == "validation":
        provider_request = EODProviderRequest(dataset, requested_range)
        chain.outcome = make_chain_result(
            provider_request,
            make_bars(dataset, (DAY_1, DAY_2, DAY_4), offset=10),
        )
    elif failure_kind == "content_hash":
        monkeypatch.setattr(
            "autowealth.market_data.full_refresh.calculate_eod_content_sha256",
            lambda bars: (_ for _ in ()).throw(RuntimeError("hash failed")),
        )
    elif failure_kind == "publication":
        repository.publish_error = RuntimeError("publish failed")
    elif failure_kind == "publish_response":
        repository.manifest_mutation = lambda manifest: object()
    else:
        repository.load_error = RuntimeError("unknown repository failure")

    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(Exception):
        execute_real(executor, dataset, requested_range)

    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held


def test_unknown_provider_chain_exception_propagates_after_lock_release() -> None:
    dataset, requested_range, repository, _, lock_manager = eligible_setup()
    chain = FakeChain(RuntimeError("unknown chain failure"))
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(RuntimeError, match="unknown chain failure"):
        execute_real(executor, dataset, requested_range)

    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert repository.publish_count == 0
    assert not lock_manager.held


@pytest.mark.parametrize("failure_source", ["limiter", "sleeper"])
def test_resilience_dependency_failure_propagates_after_lock_release(
    failure_source: str,
) -> None:
    dataset = make_dataset()
    requested_range = EODDateRange(DAY_1, DAY_4)
    provider_request = EODProviderRequest(dataset, requested_range)
    provider_result = EODProviderResult(
        request=provider_request,
        provider_name=(
            "static_provider" if failure_source == "limiter" else RetryOnceProvider.provider_name
        ),
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=make_bars(dataset, (DAY_1, DAY_2, DAY_3, DAY_4), offset=10),
    )
    if failure_source == "limiter":
        provider = StaticResultProvider("static_provider", dataset, provider_result)
        chain = EODProviderChain(
            (provider,),
            rate_limiter=RaisingLimiter(),
            retry_sleeper=RecordingSleeper(),
        )
    else:
        provider = RetryOnceProvider(dataset, provider_result)
        chain = EODProviderChain(
            (provider,),
            retry_policy=EODProviderRetryPolicy(max_attempts=2),
            rate_limiter=NoOpEODProviderRateLimiter(),
            retry_sleeper=RaisingSleeper(),
        )
    repository = FakeRepository(make_stored(dataset, (DAY_1, DAY_2)))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(RuntimeError, match=failure_source):
        execute_real(executor, dataset, requested_range)

    assert repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held


def test_lock_release_failure_is_safe_and_does_not_repeat_publication() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    lock_manager.release_error = RuntimeError("Authorization: Bearer secret")
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(EODFullRefreshExecutorError) as raised:
        execute_real(executor, dataset, requested_range)

    assert raised.value.code is EODFullRefreshErrorCode.LOCK_RELEASE_FAILED
    assert "secret" not in raised.value.to_json().lower()
    assert chain.fetch_count == repository.publish_count == 1


@pytest.mark.parametrize(
    "sensitive_cause",
    [
        "API_KEY=abc123",
        "SECRET=abc123",
        "TOKEN=abc123",
        "PASSWORD=abc123",
        "Authorization: Bearer abc123",
        "C:\\private\\provider.log",
        "D:\\private\\provider.log",
        "/home/private/provider.log",
        "Traceback (most recent call last): secret",
    ],
)
def test_public_lock_error_never_serializes_dependency_details(
    sensitive_cause: str,
) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    lock_manager.acquire_error = RuntimeError(sensitive_cause)
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(EODFullRefreshExecutorError) as raised:
        execute_real(executor, dataset, requested_range)

    payload = raised.value.to_json()
    assert sensitive_cause not in payload
    assert "abc123" not in payload
    assert "private" not in payload.lower()
    assert "traceback" not in payload.lower()


def test_incremental_coordinator_still_returns_full_refresh_required_without_fetch() -> None:
    dataset, requested_range, repository, _, _ = eligible_setup()
    chain = FakeChain(AssertionError("incremental path fetched full history"))

    result = EODIncrementalCoordinator(repository, chain, StaticCalendar()).update(
        dataset,
        requested_range,
    )

    assert result.status is EODIncrementalUpdateStatus.FULL_REFRESH_REQUIRED
    assert result.requires_full_refresh is True
    assert chain.fetch_count == repository.publish_count == 0


def test_request_and_result_are_frozen_deterministic_and_explicit() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)
    request = EODFullRefreshRequest(dataset, requested_range, dry_run=True)

    result = executor.execute(request)
    payload = json.loads(result.to_json())

    assert payload["request"]["execution_mode"] == "full_refresh"
    assert payload["status"] == "full_refresh_planned"
    assert payload["eligible"] is True
    assert payload["would_publish"] is False
    assert payload["would_replace_generation_id"] == "generation-1"
    assert result.to_json() == result.to_json()
    with pytest.raises(Exception):
        request.dry_run = False  # type: ignore[misc]
    with pytest.raises(Exception):
        result.status = EODFullRefreshStatus.NOT_ELIGIBLE  # type: ignore[misc]
    with pytest.raises(ValueError, match="row_count"):
        replace(result, row_count=result.row_count + 1)


@pytest.mark.parametrize(
    "value",
    [
        object(),
        {"dataset": "600000.SH"},
    ],
)
def test_executor_rejects_non_exact_request_before_side_effects(value: object) -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(TypeError, match="EODFullRefreshRequest"):
        executor.execute(value)  # type: ignore[arg-type]

    assert repository.load_count == chain.fetch_count == lock_manager.acquire_count == 0


def test_invalid_publication_context_fails_only_after_eligible_changed_content() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    with pytest.raises(EODIncrementalCoordinatorError) as raised:
        executor.execute(
            EODFullRefreshRequest(dataset, requested_range),
            generation_id="../unsafe",
            created_at=UTC_TIME,
        )

    assert raised.value.code is EODIncrementalCoordinatorErrorCode.PUBLICATION_CONTEXT_INVALID
    assert repository.load_count == chain.fetch_count == lock_manager.acquire_count == 1
    assert repository.publish_count == 0
    assert lock_manager.release_count == 1


def test_not_eligible_ignores_unused_publication_context() -> None:
    dataset = make_dataset(adjustment=AdjustmentType.NONE)
    requested_range = EODDateRange(DAY_1, DAY_4)
    repository = FakeRepository(make_stored(dataset, (DAY_1, DAY_2, DAY_3, DAY_4)))
    chain = FakeChain(AssertionError("not-eligible execution fetched"))
    lock_manager = RecordingLockManager()
    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    result = executor.execute(
        EODFullRefreshRequest(dataset, requested_range),
        generation_id="../unused",
        created_at=datetime(2024, 1, 9, 8, 0),
    )

    assert result.status is EODFullRefreshStatus.NOT_ELIGIBLE
    assert chain.fetch_count == repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 1


def test_full_refresh_constructor_performs_no_fetch_load_lock_or_publication() -> None:
    dataset, _, repository, chain, lock_manager = eligible_setup()

    executor = EODFullRefreshExecutor(repository, chain, StaticCalendar(), lock_manager)

    assert type(executor) is EODFullRefreshExecutor
    assert repository.current.manifest.dataset == dataset  # type: ignore[union-attr]
    assert repository.load_count == repository.publish_count == chain.fetch_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 0


def test_explicit_full_refresh_import_is_offline_and_has_no_file_write_side_effects() -> None:
    root = Path(__file__).resolve().parents[1]
    script = r"""
import builtins
from pathlib import Path
import socket

def blocked(*args, **kwargs):
    raise AssertionError("side effect during import")

def guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        blocked()
    return original_open(file, mode, *args, **kwargs)

original_open = builtins.open
builtins.open = guarded_open
Path.write_text = blocked
Path.write_bytes = blocked
Path.touch = blocked
socket.create_connection = blocked
socket.socket.connect = blocked

import autowealth.market_data.full_refresh

assert "akshare" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", "import sys\n" + script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "relative_path",
    [
        "autowealth/market_data/full_refresh.py",
        "autowealth/market_data/coordinator.py",
        "autowealth/market_data/composition.py",
        "autowealth/market_data/__init__.py",
        "tests/test_eod_full_refresh_executor.py",
    ],
)
def test_full_refresh_python_files_parse_with_python_39_grammar(relative_path: str) -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / relative_path).read_text(encoding="utf-8")

    ast.parse(source, filename=relative_path, feature_version=(3, 9))


def test_full_refresh_checkpoint_runs_immediately_before_publication() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    checkpoints = []

    def checkpoint(stage: EODCheckpointStage, value: Optional[EODDatasetKey]) -> None:
        checkpoints.append((stage, value, repository.publish_count))

    result = EODFullRefreshExecutor(
        repository,
        chain,
        StaticCalendar(),
        lock_manager,
    ).execute(
        EODFullRefreshRequest(dataset, requested_range),
        generation_id="generation-2",
        created_at=UTC_TIME,
        checkpoint=checkpoint,
    )

    assert result.status is EODFullRefreshStatus.FULL_REFRESH_PUBLISHED
    assert checkpoints == [(EODCheckpointStage.BEFORE_PUBLICATION, dataset, 0)]
    assert repository.publish_count == 1
    assert lock_manager.release_count == 1


def test_full_refresh_publication_checkpoint_error_propagates_unchanged() -> None:
    dataset, requested_range, repository, chain, lock_manager = eligible_setup()
    original_generation = repository.current
    error = EODOperationControlError("lease_control_failure")

    def checkpoint(stage: EODCheckpointStage, value: Optional[EODDatasetKey]) -> None:
        assert stage is EODCheckpointStage.BEFORE_PUBLICATION
        assert value == dataset
        raise error

    with pytest.raises(EODOperationControlError) as captured:
        EODFullRefreshExecutor(
            repository,
            chain,
            StaticCalendar(),
            lock_manager,
        ).execute(
            EODFullRefreshRequest(dataset, requested_range),
            generation_id="generation-2",
            created_at=UTC_TIME,
            checkpoint=checkpoint,
        )

    assert captured.value is error
    assert repository.publish_count == 0
    assert repository.current is original_generation
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert not lock_manager.held
