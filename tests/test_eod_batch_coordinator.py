from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Callable, Optional

import pytest

import autowealth.market_data as market_data
from autowealth.market_data.batch import (
    EODBatchCoordinator,
    EODBatchDatasetRequest,
    EODBatchDatasetStatus,
    EODBatchFailurePolicy,
    EODBatchRequest,
    EODBatchResult,
    EODBatchStatus,
    EODBatchValidationError,
    EODBatchValidationErrorCode,
    InProcessEODDatasetLockManager,
    eod_dataset_lock_key,
)
from autowealth.market_data.coordinator import EODIncrementalCoordinator
from autowealth.market_data.operation_control import (
    EODCheckpointStage,
    EODOperationControlError,
)
from autowealth.market_data.planning import EODRequestPlanStatus, EODRevisionPolicy
from autowealth.market_data.provider_chain import (
    EODProviderAttempt,
    EODProviderChain,
    EODProviderChainResult,
)
from autowealth.market_data.provider_resilience import EODProviderRetryPolicy
from autowealth.market_data.providers import (
    EODProviderCapability,
    EODProviderError,
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
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_eod_content_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
DAY_4 = date(2024, 1, 5)
ALL_DAYS = (DAY_1, DAY_2, DAY_3, DAY_4)
UTC_TIME = datetime(2024, 1, 10, 1, 2, 3, tzinfo=timezone.utc)


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
        events: Optional[list[str]] = None,
    ) -> None:
        self.current = current
        self.events = [] if events is None else events
        self.load_count = 0
        self.publish_count = 0

    def load_current(self, dataset: EODDatasetKey) -> Optional[EODStoredGeneration]:
        self.load_count += 1
        self.events.append(f"load:{dataset.canonical_symbol}")
        return self.current

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: tuple[EODBar, ...],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> EODGenerationManifest:
        self.publish_count += 1
        self.events.append(f"publish:{dataset.canonical_symbol}")
        return make_manifest(
            tuple(bars),
            generation_id=generation_id,
            created_at=created_at,
            previous_generation_id=(
                None if self.current is None else self.current.manifest.generation_id
            ),
        )


class FailOnceRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    def load_current(self, dataset: EODDatasetKey) -> Optional[EODStoredGeneration]:
        if not self._failed:
            self._failed = True
            raise RuntimeError("repository inspection failed")
        return super().load_current(dataset)


class FailOncePublishRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self._failed = False

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: tuple[EODBar, ...],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> EODGenerationManifest:
        if not self._failed:
            self._failed = True
            raise RuntimeError("repository publication failed")
        return super().publish(
            dataset,
            bars,
            generation_id=generation_id,
            created_at=created_at,
        )


class DynamicChain:
    def __init__(
        self,
        responder: Callable[[EODProviderRequest], object],
        *,
        events: Optional[list[str]] = None,
    ) -> None:
        self.responder = responder
        self.events = [] if events is None else events
        self.fetch_count = 0

    def fetch(
        self,
        request: EODProviderRequest,
        *,
        checkpoint: object = None,
    ) -> object:
        self.fetch_count += 1
        self.events.append(f"fetch:{request.dataset.canonical_symbol}")
        response = self.responder(request)
        if isinstance(response, BaseException):
            raise response
        return response


class BlockingChain(DynamicChain):
    def __init__(self, entered: threading.Event, proceed: threading.Event) -> None:
        self.entered = entered
        self.proceed = proceed
        super().__init__(self._respond)

    def _respond(self, request: EODProviderRequest) -> EODProviderChainResult:
        self.entered.set()
        if not self.proceed.wait(timeout=5):
            raise AssertionError("concurrency test did not release the provider")
        return make_chain_result(request, trading_days(request.requested_range))


class CountingLockManager:
    def __init__(self) -> None:
        self.acquire_count = 0
        self.release_count = 0

    def acquire(self, lock_key: str) -> bool:
        self.acquire_count += 1
        return True

    def release(self, lock_key: str) -> None:
        self.release_count += 1


class ExplodingLockManager:
    def acquire(self, lock_key: str) -> bool:
        raise RuntimeError(
            r"C:\private\secret /home/user/private Bearer abc token=hidden traceback"
        )

    def release(self, lock_key: str) -> None:
        raise AssertionError("an unacquired lock must not be released")


def make_dataset(
    symbol: str,
    *,
    adjustment: AdjustmentType = AdjustmentType.NONE,
    asset_type: AssetType = AssetType.EQUITY,
) -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE if symbol.endswith(".SH") else Venue.SZSE,
        asset_type=asset_type,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=adjustment,
    )


def make_bar(dataset: EODDatasetKey, trade_date: date, value: int) -> EODBar:
    base = Decimal(value)
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=base,
        high=base + Decimal("1"),
        low=base - Decimal("1"),
        close=base + Decimal("0.5"),
        volume=Decimal("1000"),
        amount=Decimal("100"),
    )


def make_bars(dataset: EODDatasetKey, days: tuple[date, ...]) -> tuple[EODBar, ...]:
    return tuple(make_bar(dataset, day, 10 + index) for index, day in enumerate(days))


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
) -> EODStoredGeneration:
    bars = make_bars(dataset, days)
    return EODStoredGeneration(manifest=make_manifest(bars), bars=bars)


def trading_days(requested_range: EODDateRange) -> tuple[date, ...]:
    return tuple(day for day in ALL_DAYS if requested_range.contains(day))


def make_chain_result(
    request: EODProviderRequest,
    days: tuple[date, ...],
) -> EODProviderChainResult:
    bars = make_bars(request.dataset, days)
    result = EODProviderResult(
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


def make_coordinator(
    dataset: EODDatasetKey,
    repository: FakeRepository,
    chain: DynamicChain,
) -> EODIncrementalCoordinator:
    return EODIncrementalCoordinator(repository, chain, StaticCalendar())


def batch_dataset_request(
    dataset: EODDatasetKey,
    *,
    revision_policy: Optional[EODRevisionPolicy] = None,
    generation_id: str = "generation-2",
) -> EODBatchDatasetRequest:
    return EODBatchDatasetRequest(
        dataset=dataset,
        requested_range=EODDateRange(DAY_1, DAY_4),
        revision_policy=revision_policy,
        generation_id=generation_id,
        created_at=UTC_TIME,
    )


def assert_summary_invariants(result: EODBatchResult) -> None:
    assert result.requested_count == len(result.results)
    assert result.requested_count == (
        result.success_count
        + result.failure_count
        + result.skipped_count
        + result.full_refresh_required_count
    )
    assert result.attempted_count == result.requested_count - result.skipped_count
    assert result.attempted_count == (
        result.success_count + result.failure_count + result.full_refresh_required_count
    )


def assert_lock_can_be_reacquired(
    lock_manager: InProcessEODDatasetLockManager,
    dataset: EODDatasetKey,
) -> None:
    lock_key = eod_dataset_lock_key(dataset)
    assert lock_manager.acquire(lock_key) is True
    lock_manager.release(lock_key)


def test_batch_validation_rejects_empty_duplicate_and_malformed_requests() -> None:
    dataset = make_dataset("600000.SH")
    item = batch_dataset_request(dataset)
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    with pytest.raises(EODBatchValidationError) as empty:
        EODBatchRequest(())
    assert empty.value.code is EODBatchValidationErrorCode.EMPTY_BATCH

    with pytest.raises(EODBatchValidationError) as duplicate:
        EODBatchRequest((item, item))
    assert duplicate.value.code is EODBatchValidationErrorCode.DUPLICATE_DATASET
    assert repository.load_count == chain.fetch_count == repository.publish_count == 0

    with pytest.raises(TypeError, match="datasets"):
        EODBatchRequest(iter((item,)))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="contain"):
        EODBatchRequest((object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="failure_policy"):
        EODBatchRequest((item,), failure_policy="retry")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dry_run"):
        EODBatchRequest((item,), dry_run=1)  # type: ignore[arg-type]


def test_batch_request_order_and_identity_are_canonical_and_deterministic() -> None:
    first_item = batch_dataset_request(make_dataset("600000.SH"), generation_id="generation-first")
    second_item = batch_dataset_request(
        make_dataset("600036.SH"), generation_id="generation-second"
    )
    third_item = batch_dataset_request(make_dataset("000001.SZ"), generation_id="generation-third")
    expected = (first_item, second_item, third_item)
    permutations = (
        EODBatchRequest((first_item, second_item, third_item)),
        EODBatchRequest((third_item, first_item, second_item)),
        EODBatchRequest((second_item, third_item, first_item)),
    )
    assert all(request.datasets == expected for request in permutations)
    assert len({request.batch_id for request in permutations}) == 1
    assert len({request.to_json() for request in permutations}) == 1
    assert json.loads(permutations[0].to_json()) == permutations[0].to_dict()


def test_single_dataset_execution_reuses_incremental_coordinator() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    lock_manager = InProcessEODDatasetLockManager()
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        lock_manager,
    )

    result = coordinator.run(EODBatchRequest((batch_dataset_request(dataset),)))

    assert result.status is EODBatchStatus.SUCCESS
    assert result.requested_count == result.attempted_count == result.success_count == 1
    assert result.failure_count == result.skipped_count == 0
    assert chain.fetch_count == 1
    assert repository.publish_count == 1
    assert_summary_invariants(result)
    assert_lock_can_be_reacquired(lock_manager, dataset)


def test_batch_dry_run_never_fetches_publishes_or_acquires_write_lock() -> None:
    events: list[str] = []
    sh = make_dataset("600000.SH")
    sz = make_dataset("000001.SZ")
    sh_repository = FakeRepository(events=events)
    sz_current = make_stored(sz, ALL_DAYS)
    sz_repository = FakeRepository(sz_current, events=events)
    sh_chain = DynamicChain(lambda request: AssertionError("dry-run fetched"), events=events)
    sz_chain = DynamicChain(lambda request: AssertionError("dry-run fetched"), events=events)
    lock_manager = CountingLockManager()
    coordinator = EODBatchCoordinator(
        {
            sh: make_coordinator(sh, sh_repository, sh_chain),
            sz: make_coordinator(sz, sz_repository, sz_chain),
        },
        lock_manager,
    )

    result = coordinator.run(
        EODBatchRequest(
            (batch_dataset_request(sz), batch_dataset_request(sh)),
            dry_run=True,
        )
    )
    assert result.status is EODBatchStatus.DRY_RUN
    assert [item.status for item in result.results] == [
        EODBatchDatasetStatus.DRY_RUN,
        EODBatchDatasetStatus.DRY_RUN,
    ]
    assert result.success_count == 2
    assert result.attempted_count == 2
    assert result.failure_count == result.skipped_count == 0
    assert sh_chain.fetch_count == sz_chain.fetch_count == 0
    assert sh_repository.publish_count == sz_repository.publish_count == 0
    assert lock_manager.acquire_count == lock_manager.release_count == 0
    assert all(item.lock_key is None for item in result.results)
    assert events == ["load:600000.SH", "load:000001.SZ"]
    assert_summary_invariants(result)


def test_batch_dry_run_preserves_incremental_overlap_and_full_refresh_plans() -> None:
    incremental = make_dataset("600000.SH")
    overlap = make_dataset("600036.SH")
    adjusted = make_dataset("000001.SZ", adjustment=AdjustmentType.QFQ)
    datasets = (incremental, overlap, adjusted)
    repositories = {
        dataset: FakeRepository(make_stored(dataset, (DAY_1, DAY_2))) for dataset in datasets
    }
    chains = {
        dataset: DynamicChain(lambda request: AssertionError("dry-run fetched"))
        for dataset in datasets
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in datasets
        },
        InProcessEODDatasetLockManager(),
    )
    request = EODBatchRequest(
        (
            batch_dataset_request(adjusted),
            batch_dataset_request(
                overlap,
                revision_policy=EODRevisionPolicy(
                    EODRevisionStrategy.OVERLAP_WINDOW,
                    overlap_trading_days=2,
                ),
            ),
            batch_dataset_request(incremental),
        ),
        dry_run=True,
    )

    result = coordinator.run(request)
    plans = {
        item.request.dataset: item.update_result.plan.status
        for item in result.results
        if item.update_result is not None
    }
    assert plans[incremental] is EODRequestPlanStatus.INCREMENTAL
    assert plans[overlap] is EODRequestPlanStatus.OVERLAP_REFRESH
    assert plans[adjusted] is EODRequestPlanStatus.FULL_REFRESH_REQUIRED
    assert result.status is EODBatchStatus.DRY_RUN
    assert result.full_refresh_required_count == 1
    assert all(chain.fetch_count == 0 for chain in chains.values())
    assert all(repository.publish_count == 0 for repository in repositories.values())
    assert_summary_invariants(result)


def test_multiple_dataset_execution_is_serial_and_canonical() -> None:
    events: list[str] = []
    sh = make_dataset("600000.SH")
    sz = make_dataset("000001.SZ")
    repositories = {
        sh: FakeRepository(events=events),
        sz: FakeRepository(events=events),
    }
    chains = {
        dataset: DynamicChain(
            lambda request: make_chain_result(request, trading_days(request.requested_range)),
            events=events,
        )
        for dataset in (sh, sz)
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in (sh, sz)
        },
        InProcessEODDatasetLockManager(),
    )

    result = coordinator.run(
        EODBatchRequest(
            (
                batch_dataset_request(sz, generation_id="generation-sz"),
                batch_dataset_request(sh, generation_id="generation-sh"),
            )
        )
    )
    assert result.status is EODBatchStatus.SUCCESS
    assert result.success_count == result.requested_count == result.attempted_count == 2
    assert result.failure_count == result.skipped_count == 0
    assert events == [
        "load:600000.SH",
        "fetch:600000.SH",
        "publish:600000.SH",
        "load:000001.SZ",
        "fetch:000001.SZ",
        "publish:000001.SZ",
    ]
    assert_summary_invariants(result)


def test_serial_batch_keeps_dataset_lock_during_provider_retry() -> None:
    events: list[str] = []
    datasets = tuple(make_dataset(symbol) for symbol in ("600000.SH", "000001.SZ"))

    class RetryOnceProvider:
        provider_name = "retry_once"
        provider_version = "1"
        endpoint_name = "fake_endpoint"

        def __init__(self, dataset: EODDatasetKey) -> None:
            self.dataset = dataset
            self.calls = 0
            self.capabilities = (
                EODProviderCapability(
                    dataset.market,
                    dataset.venue,
                    dataset.asset_type,
                    dataset.frequency,
                    dataset.adjustment_type,
                    EODRevisionStrategy.APPEND_ONLY,
                ),
            )

        def fetch(self, request: EODProviderRequest) -> EODProviderResult:
            self.calls += 1
            events.append(f"provider:{self.dataset.canonical_symbol}:{self.calls}")
            if self.calls == 1:
                raise EODProviderError(
                    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                    "The fake provider failed temporarily.",
                )
            return EODProviderResult(
                request=request,
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                status=EODProviderResultStatus.SUCCESS,
                bars=make_bars(self.dataset, trading_days(request.requested_range)),
            )

    class LockManager:
        def __init__(self) -> None:
            self.active: set[str] = set()

        def acquire(self, lock_key: str) -> bool:
            assert not self.active
            self.active.add(lock_key)
            events.append("lock:acquire")
            return True

        def release(self, lock_key: str) -> None:
            assert lock_key in self.active
            self.active.remove(lock_key)
            events.append("lock:release")

    class LockAwareSleeper:
        def __init__(self, lock_manager: LockManager) -> None:
            self.lock_manager = lock_manager
            self.delays: list[float] = []

        def sleep(self, seconds: float) -> None:
            assert len(self.lock_manager.active) == 1
            self.delays.append(seconds)
            events.append("retry:backoff")

    lock_manager = LockManager()
    sleeper = LockAwareSleeper(lock_manager)
    providers = {dataset: RetryOnceProvider(dataset) for dataset in datasets}
    repositories = {dataset: FakeRepository(events=events) for dataset in datasets}
    coordinators = {
        dataset: EODIncrementalCoordinator(
            repositories[dataset],
            EODProviderChain(
                [providers[dataset]],
                retry_policy=EODProviderRetryPolicy(max_attempts=2),
                retry_sleeper=sleeper,
            ),
            StaticCalendar(),
        )
        for dataset in datasets
    }

    result = EODBatchCoordinator(coordinators, lock_manager).run(
        EODBatchRequest(tuple(batch_dataset_request(dataset) for dataset in reversed(datasets)))
    )

    assert result.status is EODBatchStatus.SUCCESS
    assert [providers[dataset].calls for dataset in datasets] == [2, 2]
    assert sleeper.delays == [1.0, 1.0]
    first_release = events.index("lock:release")
    assert events[:first_release] == [
        "lock:acquire",
        "load:600000.SH",
        "provider:600000.SH:1",
        "retry:backoff",
        "provider:600000.SH:2",
        "publish:600000.SH",
    ]
    assert events[first_release + 1 : first_release + 7] == [
        "lock:acquire",
        "load:000001.SZ",
        "provider:000001.SZ:1",
        "retry:backoff",
        "provider:000001.SZ:2",
        "publish:000001.SZ",
    ]
    assert lock_manager.active == set()


def test_stop_on_failure_is_default_and_never_reports_global_success() -> None:
    datasets = tuple(
        make_dataset(symbol) for symbol in ("600000.SH", "600001.SH", "600002.SH", "600003.SH")
    )
    repositories = {dataset: FakeRepository() for dataset in datasets}
    chains = {
        datasets[0]: DynamicChain(
            lambda request: make_chain_result(request, trading_days(request.requested_range))
        ),
        datasets[1]: DynamicChain(lambda request: RuntimeError("apiKey=hidden")),
        datasets[2]: DynamicChain(lambda request: AssertionError("skipped dataset fetched")),
        datasets[3]: DynamicChain(lambda request: AssertionError("skipped dataset fetched")),
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in datasets
        },
        InProcessEODDatasetLockManager(),
    )

    result = coordinator.run(
        EODBatchRequest(tuple(batch_dataset_request(dataset) for dataset in reversed(datasets)))
    )
    assert result.status is EODBatchStatus.PARTIAL_SUCCESS
    assert [item.status for item in result.results] == [
        EODBatchDatasetStatus.SUCCESS,
        EODBatchDatasetStatus.FAILED,
        EODBatchDatasetStatus.SKIPPED,
        EODBatchDatasetStatus.SKIPPED,
    ]
    assert result.requested_count == 4
    assert result.attempted_count == 2
    assert result.success_count == 1
    assert result.failure_count == 1
    assert result.skipped_count == 2
    assert chains[datasets[0]].fetch_count == chains[datasets[1]].fetch_count == 1
    assert chains[datasets[2]].fetch_count == chains[datasets[3]].fetch_count == 0
    assert_summary_invariants(result)
    assert "hidden" not in result.to_json()


def test_continue_on_failure_runs_later_datasets_and_returns_partial_success() -> None:
    datasets = tuple(make_dataset(symbol) for symbol in ("600000.SH", "600001.SH", "600002.SH"))
    repositories = {dataset: FakeRepository() for dataset in datasets}
    chains = {
        datasets[0]: DynamicChain(
            lambda request: make_chain_result(request, trading_days(request.requested_range))
        ),
        datasets[1]: DynamicChain(lambda request: RuntimeError("provider failed")),
        datasets[2]: DynamicChain(
            lambda request: make_chain_result(request, trading_days(request.requested_range))
        ),
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in datasets
        },
        InProcessEODDatasetLockManager(),
    )
    result = coordinator.run(
        EODBatchRequest(
            tuple(batch_dataset_request(dataset) for dataset in reversed(datasets)),
            failure_policy=EODBatchFailurePolicy.CONTINUE_ON_FAILURE,
        )
    )
    assert result.status is EODBatchStatus.PARTIAL_SUCCESS
    assert result.requested_count == result.attempted_count == 3
    assert result.success_count == 2
    assert result.failure_count == 1
    assert result.skipped_count == 0
    assert all(chain.fetch_count == 1 for chain in chains.values())
    assert_summary_invariants(result)


def test_later_failure_does_not_rollback_an_earlier_dataset_publication() -> None:
    first = make_dataset("600000.SH")
    second = make_dataset("000001.SZ")
    first_repository = FakeRepository()
    second_repository = FakeRepository()
    first_chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    second_chain = DynamicChain(lambda request: RuntimeError("later provider failure"))
    coordinator = EODBatchCoordinator(
        {
            first: make_coordinator(first, first_repository, first_chain),
            second: make_coordinator(second, second_repository, second_chain),
        },
        InProcessEODDatasetLockManager(),
    )

    result = coordinator.run(
        EODBatchRequest((batch_dataset_request(second), batch_dataset_request(first)))
    )

    assert result.status is EODBatchStatus.PARTIAL_SUCCESS
    assert [item.status for item in result.results] == [
        EODBatchDatasetStatus.SUCCESS,
        EODBatchDatasetStatus.FAILED,
    ]
    assert first_repository.publish_count == 1
    assert second_repository.publish_count == 0
    assert_summary_invariants(result)


def test_full_refresh_required_is_counted_and_not_treated_as_success() -> None:
    adjusted = make_dataset("600000.SH", adjustment=AdjustmentType.QFQ)
    normal = make_dataset("000001.SZ")
    adjusted_repository = FakeRepository(make_stored(adjusted, (DAY_1, DAY_2)))
    normal_repository = FakeRepository()
    adjusted_chain = DynamicChain(lambda request: AssertionError("full refresh fetched"))
    normal_chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    lock_manager = InProcessEODDatasetLockManager()
    coordinator = EODBatchCoordinator(
        {
            adjusted: make_coordinator(adjusted, adjusted_repository, adjusted_chain),
            normal: make_coordinator(normal, normal_repository, normal_chain),
        },
        lock_manager,
    )
    result = coordinator.run(
        EODBatchRequest((batch_dataset_request(normal), batch_dataset_request(adjusted)))
    )
    assert result.status is EODBatchStatus.PARTIAL_SUCCESS
    assert result.full_refresh_required_count == 1
    assert result.success_count == 1
    assert result.failure_count == 0
    assert adjusted_chain.fetch_count == 0
    assert normal_chain.fetch_count == 1
    assert_summary_invariants(result)
    assert_lock_can_be_reacquired(lock_manager, adjusted)


def test_only_full_refresh_required_has_distinct_global_status() -> None:
    dataset = make_dataset("600000.SH", adjustment=AdjustmentType.QFQ)
    repository = FakeRepository(make_stored(dataset, (DAY_1, DAY_2)))
    chain = DynamicChain(lambda request: AssertionError("full refresh fetched"))
    lock_manager = InProcessEODDatasetLockManager()
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        lock_manager,
    )

    result = coordinator.run(EODBatchRequest((batch_dataset_request(dataset),)))

    assert result.status is EODBatchStatus.FULL_REFRESH_REQUIRED
    assert result.full_refresh_required_count == 1
    assert result.success_count == result.failure_count == result.skipped_count == 0
    assert result.attempted_count == 1
    assert chain.fetch_count == repository.publish_count == 0
    assert_summary_invariants(result)
    assert_lock_can_be_reacquired(lock_manager, dataset)


def test_already_current_result_releases_lock() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository(make_stored(dataset, ALL_DAYS))
    chain = DynamicChain(lambda request: AssertionError("already-current dataset fetched"))
    lock_manager = InProcessEODDatasetLockManager()
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        lock_manager,
    )

    result = coordinator.run(EODBatchRequest((batch_dataset_request(dataset),)))

    assert result.status is EODBatchStatus.SUCCESS
    assert result.results[0].update_result is not None
    assert result.results[0].update_result.status.value == "already_current"
    assert chain.fetch_count == repository.publish_count == 0
    assert_summary_invariants(result)
    assert_lock_can_be_reacquired(lock_manager, dataset)


def test_missing_coordinator_fails_before_any_dataset_execution() -> None:
    sh = make_dataset("600000.SH")
    sz = make_dataset("000001.SZ")
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    coordinator = EODBatchCoordinator(
        {sh: make_coordinator(sh, repository, chain)},
        InProcessEODDatasetLockManager(),
    )
    with pytest.raises(EODBatchValidationError) as captured:
        coordinator.run(EODBatchRequest((batch_dataset_request(sh), batch_dataset_request(sz))))
    assert captured.value.code is EODBatchValidationErrorCode.COORDINATOR_UNAVAILABLE
    assert repository.load_count == chain.fetch_count == repository.publish_count == 0


def test_lock_keys_are_stable_and_distinct_for_dataset_identity_dimensions() -> None:
    none = make_dataset("600000.SH")
    qfq = make_dataset("600000.SH", adjustment=AdjustmentType.QFQ)
    other = make_dataset("000001.SZ")
    index = make_dataset("600000.SH", asset_type=AssetType.INDEX)
    canonical_material = json.dumps(
        list(none.identity),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    expected = f"eod-dataset-{hashlib.sha256(canonical_material).hexdigest()}"
    assert none.identity == ("CN", "SSE", "equity", "600000.SH", "1d", "none")
    assert eod_dataset_lock_key(none) == expected
    assert (
        len(
            {
                eod_dataset_lock_key(none),
                eod_dataset_lock_key(qfq),
                eod_dataset_lock_key(other),
                eod_dataset_lock_key(index),
            }
        )
        == 4
    )
    assert eod_dataset_lock_key(none).startswith("eod-dataset-")


def test_in_process_lock_registry_does_not_retain_released_dataset_keys() -> None:
    lock_manager = InProcessEODDatasetLockManager()
    for value in range(600000, 600100):
        lock_key = eod_dataset_lock_key(make_dataset(f"{value:06d}.SH"))
        assert lock_manager.acquire(lock_key) is True
        lock_manager.release(lock_key)
    assert lock_manager._held_keys == set()


def test_preheld_same_dataset_lock_fails_closed_without_fetch_or_publish() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    lock_manager = InProcessEODDatasetLockManager()
    lock_key = eod_dataset_lock_key(dataset)
    assert lock_manager.acquire(lock_key) is True
    try:
        result = EODBatchCoordinator(
            {dataset: make_coordinator(dataset, repository, chain)},
            lock_manager,
        ).run(EODBatchRequest((batch_dataset_request(dataset),)))
    finally:
        lock_manager.release(lock_key)
    assert result.status is EODBatchStatus.FAILED
    assert result.results[0].failure is not None
    assert result.results[0].failure.code == "lock_unavailable"
    assert repository.load_count == chain.fetch_count == repository.publish_count == 0


def test_lock_acquisition_error_is_structured_without_sensitive_exception_text() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    result = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        ExplodingLockManager(),
    ).run(EODBatchRequest((batch_dataset_request(dataset),)))

    serialized = result.to_json()
    assert result.status is EODBatchStatus.FAILED
    assert result.results[0].failure is not None
    assert result.results[0].failure.code == "lock_acquisition_failed"
    assert all(
        fragment not in serialized
        for fragment in (
            "C:\\private",
            "/home/user/private",
            "Bearer abc",
            "token=hidden",
            "traceback",
        )
    )
    assert repository.load_count == chain.fetch_count == repository.publish_count == 0
    assert_summary_invariants(result)


def test_concurrent_same_dataset_execution_allows_only_one_writer() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    entered = threading.Event()
    proceed = threading.Event()
    chain = BlockingChain(entered, proceed)
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        InProcessEODDatasetLockManager(),
    )
    request = EODBatchRequest((batch_dataset_request(dataset),))
    first_results: list[object] = []

    thread = threading.Thread(target=lambda: first_results.append(coordinator.run(request)))
    thread.start()
    assert entered.wait(timeout=5)
    second = coordinator.run(request)
    proceed.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert len(first_results) == 1
    first = first_results[0]
    assert first.status is EODBatchStatus.SUCCESS
    assert second.status is EODBatchStatus.FAILED
    assert second.results[0].failure is not None
    assert second.results[0].failure.code == "lock_unavailable"
    assert chain.fetch_count == 1
    assert repository.publish_count == 1


def test_unexpected_programming_error_propagates_after_lock_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    single = make_coordinator(dataset, repository, chain)
    lock_manager = InProcessEODDatasetLockManager()

    def explode(*args: object, **kwargs: object) -> object:
        raise RuntimeError("programming defect")

    monkeypatch.setattr(single, "execute", explode)
    coordinator = EODBatchCoordinator({dataset: single}, lock_manager)

    with pytest.raises(RuntimeError, match="programming defect"):
        coordinator.run(EODBatchRequest((batch_dataset_request(dataset),)))

    assert_lock_can_be_reacquired(lock_manager, dataset)


def test_provider_failure_releases_lock_for_safe_retry_by_caller() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    state = {"fail": True}

    def respond(request: EODProviderRequest) -> object:
        if state["fail"]:
            return RuntimeError("temporary provider failure")
        return make_chain_result(request, trading_days(request.requested_range))

    chain = DynamicChain(respond)
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        InProcessEODDatasetLockManager(),
    )
    request = EODBatchRequest((batch_dataset_request(dataset),))
    first = coordinator.run(request)
    state["fail"] = False
    second = coordinator.run(request)
    assert first.status is EODBatchStatus.FAILED
    assert second.status is EODBatchStatus.SUCCESS
    assert chain.fetch_count == 2
    assert repository.publish_count == 1


def test_provider_retry_exhaustion_releases_dataset_lock() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    lock_manager = CountingLockManager()

    class AlwaysTemporaryProvider:
        provider_name = "always_temporary"
        provider_version = "1"
        endpoint_name = "fake_endpoint"
        capabilities = (
            EODProviderCapability(
                dataset.market,
                dataset.venue,
                dataset.asset_type,
                dataset.frequency,
                dataset.adjustment_type,
                EODRevisionStrategy.APPEND_ONLY,
            ),
        )

        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, request: EODProviderRequest) -> EODProviderResult:
            self.calls += 1
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The fake provider failed temporarily.",
            )

    class RecordingSleeper:
        def __init__(self) -> None:
            self.delays: list[float] = []

        def sleep(self, seconds: float) -> None:
            self.delays.append(seconds)

    provider = AlwaysTemporaryProvider()
    sleeper = RecordingSleeper()
    single = EODIncrementalCoordinator(
        repository,
        EODProviderChain(
            [provider],
            retry_policy=EODProviderRetryPolicy(max_attempts=3),
            retry_sleeper=sleeper,
        ),
        StaticCalendar(),
    )

    result = EODBatchCoordinator({dataset: single}, lock_manager).run(
        EODBatchRequest((batch_dataset_request(dataset),))
    )

    assert result.status is EODBatchStatus.FAILED
    assert provider.calls == 3
    assert sleeper.delays == [1.0, 2.0]
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert repository.publish_count == 0


@pytest.mark.parametrize("failure_source", ["sleeper", "limiter"])
def test_resilience_infrastructure_failure_releases_dataset_lock(
    failure_source: str,
) -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    lock_manager = CountingLockManager()

    class Provider:
        provider_name = "temporary_once"
        provider_version = "1"
        endpoint_name = "fake_endpoint"
        capabilities = (
            EODProviderCapability(
                dataset.market,
                dataset.venue,
                dataset.asset_type,
                dataset.frequency,
                dataset.adjustment_type,
                EODRevisionStrategy.APPEND_ONLY,
            ),
        )

        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, request: EODProviderRequest) -> EODProviderResult:
            self.calls += 1
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The fake provider failed temporarily.",
            )

    class FailingSleeper:
        def sleep(self, seconds: float) -> None:
            raise RuntimeError("sleeper infrastructure failed")

    class FailingLimiter:
        def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
            raise RuntimeError("limiter infrastructure failed")

    provider = Provider()
    chain_kwargs: dict[str, object] = {
        "retry_policy": EODProviderRetryPolicy(max_attempts=2),
    }
    if failure_source == "sleeper":
        chain_kwargs["retry_sleeper"] = FailingSleeper()
    else:
        chain_kwargs["rate_limiter"] = FailingLimiter()
    single = EODIncrementalCoordinator(
        repository,
        EODProviderChain([provider], **chain_kwargs),
        StaticCalendar(),
    )

    result = EODBatchCoordinator({dataset: single}, lock_manager).run(
        EODBatchRequest((batch_dataset_request(dataset),))
    )

    assert result.status is EODBatchStatus.FAILED
    assert provider.calls == (1 if failure_source == "sleeper" else 0)
    assert lock_manager.acquire_count == lock_manager.release_count == 1
    assert repository.publish_count == 0


def test_repository_inspection_exception_releases_lock_for_safe_retry() -> None:
    dataset = make_dataset("600000.SH")
    repository = FailOnceRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        InProcessEODDatasetLockManager(),
    )
    request = EODBatchRequest((batch_dataset_request(dataset),))

    first = coordinator.run(request)
    second = coordinator.run(request)

    assert first.status is EODBatchStatus.FAILED
    assert first.results[0].failure is not None
    assert first.results[0].failure.code == "current_generation_invalid"
    assert second.status is EODBatchStatus.SUCCESS
    assert chain.fetch_count == 1
    assert repository.publish_count == 1


def test_repository_publication_failure_releases_lock_for_safe_retry() -> None:
    dataset = make_dataset("600000.SH")
    repository = FailOncePublishRepository()
    chain = DynamicChain(
        lambda request: make_chain_result(request, trading_days(request.requested_range))
    )
    lock_manager = InProcessEODDatasetLockManager()
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        lock_manager,
    )
    request = EODBatchRequest((batch_dataset_request(dataset),))

    first = coordinator.run(request)
    assert first.status is EODBatchStatus.FAILED
    assert first.results[0].failure is not None
    assert first.results[0].failure.code == "publication_failed"
    assert_lock_can_be_reacquired(lock_manager, dataset)

    second = coordinator.run(request)
    assert second.status is EODBatchStatus.SUCCESS
    assert chain.fetch_count == 2
    assert repository.publish_count == 1


def test_validation_failure_releases_lock_for_later_valid_execution() -> None:
    dataset = make_dataset("600000.SH")
    repository = FakeRepository()
    state = {"complete": False}

    def respond(request: EODProviderRequest) -> EODProviderChainResult:
        days = trading_days(request.requested_range)
        selected = days if state["complete"] else days[:-1]
        return make_chain_result(request, selected)

    chain = DynamicChain(respond)
    coordinator = EODBatchCoordinator(
        {dataset: make_coordinator(dataset, repository, chain)},
        InProcessEODDatasetLockManager(),
    )
    request = EODBatchRequest((batch_dataset_request(dataset),))
    first = coordinator.run(request)
    state["complete"] = True
    second = coordinator.run(request)
    assert first.status is EODBatchStatus.FAILED
    assert first.results[0].failure is not None
    assert first.results[0].failure.code == "validation_failed"
    assert second.status is EODBatchStatus.SUCCESS
    assert repository.publish_count == 1


def test_batch_public_contract_is_lazy_offline_and_python_39_compatible() -> None:
    expected = {
        "EODBatchCoordinator",
        "EODBatchRequest",
        "EODBatchResult",
        "EODDatasetLockManager",
        "InProcessEODDatasetLockManager",
        "eod_dataset_lock_key",
    }
    assert expected <= set(market_data.__all__)
    source = (ROOT / "autowealth/market_data/batch.py").read_text(encoding="utf-8")
    ast.parse(source, filename="batch.py", feature_version=(3, 9))
    forbidden = (
        "datetime.now",
        "datetime.utcnow",
        "date.today",
        "uuid",
        "secrets",
        "sleep(",
        "import akshare",
        "import pandas",
        "import pyarrow",
    )
    assert all(fragment not in source for fragment in forbidden)

    script = r"""
import socket
import sys

import autowealth

def blocked(*args, **kwargs):
    raise AssertionError("network access is forbidden during batch import")

socket.create_connection = blocked
socket.socket.connect = blocked

before_modules = set(sys.modules)
import autowealth.market_data.batch

new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before_modules}
assert {"akshare", "pandas", "pyarrow", "requests", "yfinance"}.isdisjoint(new_roots)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_batch_checkpoints_run_before_publication_and_each_next_dataset() -> None:
    datasets = (
        make_dataset("600000.SH"),
        make_dataset("000001.SZ"),
    )
    repositories = {dataset: FakeRepository() for dataset in datasets}
    chains = {
        dataset: DynamicChain(
            lambda request: make_chain_result(
                request,
                trading_days(request.requested_range),
            )
        )
        for dataset in datasets
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in datasets
        },
        InProcessEODDatasetLockManager(),
    )
    checkpoints = []

    def checkpoint(stage: EODCheckpointStage, dataset: Optional[EODDatasetKey]) -> None:
        checkpoints.append((stage, dataset))

    result = coordinator.run(
        EODBatchRequest(tuple(batch_dataset_request(dataset) for dataset in reversed(datasets))),
        checkpoint=checkpoint,
    )

    assert result.status is EODBatchStatus.SUCCESS
    assert checkpoints == [
        (EODCheckpointStage.BEFORE_PUBLICATION, datasets[0]),
        (EODCheckpointStage.BEFORE_NEXT_DATASET, datasets[1]),
        (EODCheckpointStage.BEFORE_PUBLICATION, datasets[1]),
    ]
    assert [repositories[dataset].publish_count for dataset in datasets] == [1, 1]


def test_batch_next_dataset_control_error_propagates_unchanged() -> None:
    datasets = (
        make_dataset("600000.SH"),
        make_dataset("000001.SZ"),
    )
    repositories = {dataset: FakeRepository() for dataset in datasets}
    chains = {
        dataset: DynamicChain(
            lambda request: make_chain_result(
                request,
                trading_days(request.requested_range),
            )
        )
        for dataset in datasets
    }
    coordinator = EODBatchCoordinator(
        {
            dataset: make_coordinator(dataset, repositories[dataset], chains[dataset])
            for dataset in datasets
        },
        InProcessEODDatasetLockManager(),
    )
    error = EODOperationControlError("lease_control_failure")

    def checkpoint(stage: EODCheckpointStage, dataset: Optional[EODDatasetKey]) -> None:
        if stage is EODCheckpointStage.BEFORE_NEXT_DATASET:
            assert dataset == datasets[1]
            raise error

    with pytest.raises(EODOperationControlError) as captured:
        coordinator.run(
            EODBatchRequest(tuple(batch_dataset_request(dataset) for dataset in datasets)),
            checkpoint=checkpoint,
        )

    assert captured.value is error
    assert [repositories[dataset].publish_count for dataset in datasets] == [1, 0]
    assert [chains[dataset].fetch_count for dataset in datasets] == [1, 0]
