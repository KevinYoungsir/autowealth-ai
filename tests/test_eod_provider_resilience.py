from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Optional

import pytest

import autowealth.market_data as market_data
from autowealth.market_data.provider_chain import (
    EODProviderChain,
    EODProviderChainError,
)
from autowealth.market_data.provider_resilience import (
    EODProviderRateLimitPolicy,
    EODProviderRetryPolicy,
    MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER,
    MinimumIntervalEODProviderRateLimiter,
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

ROOT = Path(__file__).resolve().parents[1]
DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)


def make_dataset() -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.INDEX,
        canonical_symbol="000300.SH",
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


def make_request() -> EODProviderRequest:
    return EODProviderRequest(make_dataset(), EODDateRange(DAY_1, DAY_2))


def make_success(request: EODProviderRequest, provider_name: str) -> EODProviderResult:
    bars = tuple(
        EODBar(
            dataset=request.dataset,
            trade_date=trade_date,
            open=Decimal(10 + offset),
            high=Decimal(11 + offset),
            low=Decimal(9 + offset),
            close=Decimal("10.5") + offset,
            volume=Decimal(1000 + offset),
            amount=Decimal(10000 + offset),
        )
        for offset, trade_date in enumerate((DAY_1, DAY_2))
    )
    return EODProviderResult(
        request=request,
        provider_name=provider_name,
        provider_version="1",
        status=EODProviderResultStatus.SUCCESS,
        bars=bars,
    )


CAPABILITIES = (
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.INDEX,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
)


class SequenceProvider:
    provider_version = "1"
    endpoint_name = "fake_endpoint"
    capabilities = CAPABILITIES

    def __init__(self, provider_name: str, responses: list[object]) -> None:
        self.provider_name = provider_name
        self._responses = list(responses)
        self.calls: list[EODProviderRequest] = []

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.calls.append(request)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response  # type: ignore[return-value]


@dataclass
class FakeMonotonicClock:
    value: float = 0.0

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class RecordingSleeper:
    def __init__(self, clock: Optional[FakeMonotonicClock] = None) -> None:
        self.clock = clock
        self.delays: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)
        if self.clock is not None:
            self.clock.advance(seconds)


class RecordingRateLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Optional[str]]] = []

    def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
        self.calls.append((provider_name, endpoint_name))
        return 0.0


class FixedRateLimiter:
    def __init__(self, wait_seconds: object) -> None:
        self.wait_seconds = wait_seconds

    def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> object:
        return self.wait_seconds


def temporary_failure() -> EODProviderError:
    return EODProviderError(
        EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
        "The provider failed temporarily.",
    )


def test_retry_policy_is_bounded_and_backoff_is_deterministic() -> None:
    policy = EODProviderRetryPolicy(
        max_attempts=5,
        initial_backoff_seconds=1,
        backoff_multiplier=2,
        max_backoff_seconds=5,
    )
    assert [policy.delay_for_retry(index) for index in range(5)] == [1.0, 2.0, 4.0, 5.0, 5.0]
    assert MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER == 5


@pytest.mark.parametrize("max_attempts", [0, 6, -1, True, 1.0, None])
def test_retry_policy_rejects_unbounded_or_ambiguous_attempt_counts(
    max_attempts: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        EODProviderRetryPolicy(max_attempts=max_attempts)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("initial_backoff_seconds", -1),
        ("initial_backoff_seconds", True),
        ("backoff_multiplier", 0),
        ("backoff_multiplier", float("inf")),
        ("max_backoff_seconds", 61),
    ],
)
def test_retry_policy_rejects_invalid_numeric_values(field_name: str, value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        EODProviderRetryPolicy(**{field_name: value})


def test_default_max_attempts_one_preserves_no_retry_behavior() -> None:
    request = make_request()
    provider = SequenceProvider("primary", [temporary_failure(), make_success(request, "primary")])
    sleeper = RecordingSleeper()

    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain([provider], retry_sleeper=sleeper).fetch(request)

    assert len(provider.calls) == 1
    assert sleeper.delays == []
    assert captured.value.attempts[0].invocation_count == 1


def test_default_chain_preserves_single_call_fallback_sequence_without_waiting() -> None:
    request = make_request()
    primary = SequenceProvider(
        "primary",
        [
            EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The primary provider is unavailable.",
            )
        ],
    )
    fallback = SequenceProvider("fallback", [make_success(request, "fallback")])
    sleeper = RecordingSleeper()

    result = EODProviderChain(
        [primary, fallback],
        retry_sleeper=sleeper,
    ).fetch(request)

    assert [len(primary.calls), len(fallback.calls)] == [1, 1]
    assert [attempt.position for attempt in result.attempts] == [0, 1]
    assert [attempt.invocation_count for attempt in result.attempts] == [1, 1]
    assert [attempt.retry_count for attempt in result.attempts] == [0, 0]
    assert [
        invocation.rate_limit_wait_seconds
        for attempt in result.attempts
        for invocation in attempt.invocations
    ] == [0.0, 0.0]
    assert sleeper.delays == []
    assert result.selected_provider_name == "fallback"


def test_temporary_failure_then_success_retries_primary_and_stops_fallback() -> None:
    request = make_request()
    primary = SequenceProvider("primary", [temporary_failure(), make_success(request, "primary")])
    fallback = SequenceProvider(
        "fallback",
        [AssertionError("fallback must not run after primary retry success")],
    )
    sleeper = RecordingSleeper()
    limiter = RecordingRateLimiter()

    result = EODProviderChain(
        [primary, fallback],
        retry_policy=EODProviderRetryPolicy(max_attempts=2),
        retry_sleeper=sleeper,
        rate_limiter=limiter,
    ).fetch(request)

    attempt = result.attempts[0]
    assert result.selected_provider_name == "primary"
    assert len(primary.calls) == 2
    assert fallback.calls == []
    assert sleeper.delays == [1.0]
    assert limiter.calls == [("primary", "fake_endpoint")] * 2
    assert attempt.position == 0
    assert attempt.retry_count == 1
    assert attempt.to_dict()["retry_count"] == 1
    assert attempt.succeeded_after_retry is True
    assert [item.invocation_number for item in attempt.invocations] == [1, 2]
    assert [item.retry_number for item in attempt.invocations] == [0, 1]
    assert [item.reason_code for item in attempt.invocations] == [
        "temporary_provider_failure",
        "success",
    ]


def test_two_temporary_failures_then_success_records_exact_backoff_sequence() -> None:
    request = make_request()
    provider = SequenceProvider(
        "primary",
        [temporary_failure(), temporary_failure(), make_success(request, "primary")],
    )
    sleeper = RecordingSleeper()

    result = EODProviderChain(
        [provider],
        retry_policy=EODProviderRetryPolicy(max_attempts=3),
        retry_sleeper=sleeper,
    ).fetch(request)

    assert sleeper.delays == [1.0, 2.0]
    assert result.attempts[0].retry_backoff_seconds == (1.0, 2.0)
    assert result.attempts[0].invocation_count == 3


@pytest.mark.parametrize(
    "error_code",
    [
        EODProviderErrorCode.UNSUPPORTED_REQUEST,
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
    ],
)
def test_non_retryable_provider_errors_never_retry(error_code: EODProviderErrorCode) -> None:
    request = make_request()
    primary = SequenceProvider(
        "primary",
        [EODProviderError(error_code, "The provider failed safely.")],
    )
    fallback = SequenceProvider("fallback", [make_success(request, "fallback")])
    sleeper = RecordingSleeper()

    result = EODProviderChain(
        [primary, fallback],
        retry_policy=EODProviderRetryPolicy(max_attempts=5),
        retry_sleeper=sleeper,
    ).fetch(request)

    assert result.selected_provider_name == "fallback"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1
    assert sleeper.delays == []


def test_primary_retry_exhaustion_precedes_fallback_success() -> None:
    request = make_request()
    primary = SequenceProvider(
        "primary",
        [temporary_failure(), temporary_failure(), temporary_failure()],
    )
    fallback = SequenceProvider("fallback", [make_success(request, "fallback")])
    limiter = RecordingRateLimiter()

    result = EODProviderChain(
        [primary, fallback],
        retry_policy=EODProviderRetryPolicy(max_attempts=3),
        retry_sleeper=RecordingSleeper(),
        rate_limiter=limiter,
    ).fetch(request)

    assert result.selected_position == 1
    assert [len(primary.calls), len(fallback.calls)] == [3, 1]
    assert [call[0] for call in limiter.calls] == ["primary", "primary", "primary", "fallback"]
    assert result.attempts[0].invocation_count == 3
    assert result.attempts[1].invocation_count == 1


def test_all_providers_exhaust_with_finite_n_times_m_invocation_bound() -> None:
    request = make_request()
    providers = [
        SequenceProvider(
            name,
            [temporary_failure() for _ in range(MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER)],
        )
        for name in ("primary", "fallback")
    ]

    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain(
            providers,
            retry_policy=EODProviderRetryPolicy(
                max_attempts=MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER
            ),
            retry_sleeper=RecordingSleeper(),
        ).fetch(request)

    assert sum(len(provider.calls) for provider in providers) == 2 * 5
    assert [attempt.invocation_count for attempt in captured.value.attempts] == [5, 5]
    assert captured.value.final_code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE


def test_minimum_interval_limiter_is_scoped_by_provider_and_endpoint() -> None:
    clock = FakeMonotonicClock()
    sleeper = RecordingSleeper(clock)
    limiter = MinimumIntervalEODProviderRateLimiter(
        EODProviderRateLimitPolicy(minimum_interval_seconds=3),
        clock=clock,
        sleeper=sleeper,
    )

    assert limiter.acquire("primary", "endpoint_one") == 0.0
    assert limiter.acquire("primary", "endpoint_one") == 3.0
    assert limiter.acquire("fallback", "endpoint_one") == 0.0
    assert limiter.acquire("primary", "endpoint_two") == 0.0
    clock.advance(3.0)
    assert limiter.acquire("primary", "endpoint_one") == 0.0
    assert sleeper.delays == [3.0]


def test_minimum_interval_limiter_serializes_same_identity_within_one_process() -> None:
    clock = FakeMonotonicClock()
    sleeper = RecordingSleeper(clock)
    limiter = MinimumIntervalEODProviderRateLimiter(
        EODProviderRateLimitPolicy(minimum_interval_seconds=2),
        clock=clock,
        sleeper=sleeper,
    )
    waits: list[float] = []
    start = threading.Barrier(3)

    def acquire() -> None:
        start.wait()
        waits.append(limiter.acquire("primary", "endpoint_one"))

    threads = [threading.Thread(target=acquire) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in threads)
    assert sorted(waits) == [0.0, 2.0]
    assert sleeper.delays == [2.0]


def test_waiting_identity_does_not_block_a_different_provider_identity() -> None:
    clock = FakeMonotonicClock()
    sleeper_entered = threading.Event()
    release_sleeper = threading.Event()

    class BlockingSleeper:
        def sleep(self, seconds: float) -> None:
            sleeper_entered.set()
            if not release_sleeper.wait(timeout=2):
                raise AssertionError("test did not release the fake sleeper")
            clock.advance(seconds)

    limiter = MinimumIntervalEODProviderRateLimiter(
        EODProviderRateLimitPolicy(minimum_interval_seconds=5),
        clock=clock,
        sleeper=BlockingSleeper(),
    )
    assert limiter.acquire("primary", "endpoint_one") == 0.0
    primary_wait: list[float] = []
    fallback_wait: list[float] = []
    fallback_done = threading.Event()

    primary_thread = threading.Thread(
        target=lambda: primary_wait.append(limiter.acquire("primary", "endpoint_one"))
    )

    def acquire_fallback() -> None:
        fallback_wait.append(limiter.acquire("fallback", "endpoint_one"))
        fallback_done.set()

    fallback_thread = threading.Thread(target=acquire_fallback)
    primary_thread.start()
    assert sleeper_entered.wait(timeout=1)
    fallback_thread.start()
    completed_without_global_sleep_lock = fallback_done.wait(timeout=1)
    release_sleeper.set()
    primary_thread.join(timeout=2)
    fallback_thread.join(timeout=2)

    assert completed_without_global_sleep_lock is True
    assert primary_wait == [5.0]
    assert fallback_wait == [0.0]
    assert not primary_thread.is_alive()
    assert not fallback_thread.is_alive()


def test_retry_backoff_and_rate_limit_only_sleep_residual_interval() -> None:
    request = make_request()
    provider = SequenceProvider("primary", [temporary_failure(), make_success(request, "primary")])
    clock = FakeMonotonicClock()
    sleeper = RecordingSleeper(clock)
    limiter = MinimumIntervalEODProviderRateLimiter(
        EODProviderRateLimitPolicy(minimum_interval_seconds=3),
        clock=clock,
        sleeper=sleeper,
    )

    result = EODProviderChain(
        [provider],
        retry_policy=EODProviderRetryPolicy(max_attempts=2, initial_backoff_seconds=1),
        retry_sleeper=sleeper,
        rate_limiter=limiter,
    ).fetch(request)

    assert sleeper.delays == [1.0, 2.0]
    assert clock.value == 3.0
    assert result.attempts[0].invocations[1].backoff_seconds == 1.0
    assert result.attempts[0].invocations[1].rate_limit_wait_seconds == 2.0


def test_sleeper_failure_propagates_without_extra_provider_retry() -> None:
    request = make_request()
    provider = SequenceProvider(
        "primary",
        [temporary_failure(), make_success(request, "primary")],
    )

    class FailingSleeper:
        def sleep(self, seconds: float) -> None:
            raise RuntimeError("retry sleeper failed")

    with pytest.raises(RuntimeError, match="retry sleeper failed"):
        EODProviderChain(
            [provider],
            retry_policy=EODProviderRetryPolicy(max_attempts=2),
            retry_sleeper=FailingSleeper(),
        ).fetch(request)

    assert len(provider.calls) == 1


def test_rate_limiter_failure_propagates_before_provider_invocation() -> None:
    request = make_request()
    provider = SequenceProvider("primary", [make_success(request, "primary")])

    class FailingRateLimiter:
        def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
            raise RuntimeError("rate limiter failed")

    with pytest.raises(RuntimeError, match="rate limiter failed"):
        EODProviderChain([provider], rate_limiter=FailingRateLimiter()).fetch(request)

    assert provider.calls == []


def test_monotonic_clock_failure_propagates_without_provider_invocation() -> None:
    request = make_request()
    provider = SequenceProvider("primary", [make_success(request, "primary")])

    class FailingClock:
        def now(self) -> float:
            raise RuntimeError("clock failed")

    limiter = MinimumIntervalEODProviderRateLimiter(
        EODProviderRateLimitPolicy(minimum_interval_seconds=1),
        clock=FailingClock(),
        sleeper=RecordingSleeper(),
    )
    with pytest.raises(RuntimeError, match="clock failed"):
        EODProviderChain([provider], rate_limiter=limiter).fetch(request)

    assert provider.calls == []


def test_retry_diagnostics_are_deterministic_bounded_and_secret_free() -> None:
    request = make_request()
    secret = (
        "apiKey=hidden token=secret Authorization: Bearer private "
        "C:\\private\\secret /home/user/private Traceback (most recent call last)"
    )
    provider = SequenceProvider("primary", [RuntimeError(secret)])

    with pytest.raises(EODProviderChainError) as captured:
        EODProviderChain(
            [provider],
            retry_policy=EODProviderRetryPolicy(max_attempts=5),
            retry_sleeper=RecordingSleeper(),
        ).fetch(request)

    payload = captured.value.to_json()
    assert payload == captured.value.to_json()
    assert len(captured.value.attempts[0].invocations) == 1
    assert "hidden" not in payload
    assert "private" not in payload
    assert "token=" not in payload
    assert "traceback" not in payload.lower()
    assert json.loads(payload)["attempts"][0]["invocation_count"] == 1


@pytest.mark.parametrize("wait_seconds", [61, float("inf"), True, "1"])
def test_untrusted_rate_limiter_cannot_create_unbounded_diagnostics(
    wait_seconds: object,
) -> None:
    request = make_request()
    provider = SequenceProvider("primary", [make_success(request, "primary")])

    with pytest.raises((TypeError, ValueError)):
        EODProviderChain(
            [provider],
            rate_limiter=FixedRateLimiter(wait_seconds),  # type: ignore[arg-type]
        ).fetch(request)

    assert provider.calls == []


def test_public_exports_and_python_39_grammar() -> None:
    expected = {
        "EODMonotonicClock",
        "EODProviderInvocation",
        "EODProviderRateLimitPolicy",
        "EODProviderRateLimiter",
        "EODProviderRetryPolicy",
        "EODRetrySleeper",
        "MinimumIntervalEODProviderRateLimiter",
    }
    assert expected <= set(market_data.__all__)

    for relative_path in (
        "autowealth/market_data/provider_resilience.py",
        "autowealth/market_data/provider_chain.py",
        "tests/test_eod_provider_resilience.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        ast.parse(source, filename=relative_path, feature_version=(3, 9))


def test_resilience_import_has_no_network_write_or_sleep_side_effects() -> None:
    script = r"""
import builtins
from pathlib import Path
import socket
import time

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
time.sleep = blocked

import autowealth.market_data.provider_resilience
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
