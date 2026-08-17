"""Bounded retry and local rate-limit contracts for EOD provider calls."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import math
from threading import Lock
from typing import Dict, Optional, Protocol, Tuple

MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER = 5
MAX_EOD_PROVIDER_DELAY_SECONDS = 60.0
_TIME = import_module("time")


def _bounded_seconds(value: object, field_name: str, *, allow_zero: bool) -> float:
    if type(value) not in (int, float):
        raise TypeError(f"{field_name} must be an exact integer or float")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0.0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    if not allow_zero and normalized == 0.0:
        raise ValueError(f"{field_name} must be greater than zero")
    if normalized > MAX_EOD_PROVIDER_DELAY_SECONDS:
        raise ValueError(f"{field_name} cannot exceed {MAX_EOD_PROVIDER_DELAY_SECONDS:g} seconds")
    return normalized


@dataclass(frozen=True)
class EODProviderRetryPolicy:
    """Deterministic retry budget for one provider before fallback begins."""

    max_attempts: int = 1
    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 5.0

    def __post_init__(self) -> None:
        if type(self.max_attempts) is not int:
            raise TypeError("max_attempts must be an exact integer")
        if not 1 <= self.max_attempts <= MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER:
            raise ValueError(
                "max_attempts must be between 1 and " f"{MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER}"
            )
        initial = _bounded_seconds(
            self.initial_backoff_seconds,
            "initial_backoff_seconds",
            allow_zero=True,
        )
        multiplier = _bounded_seconds(
            self.backoff_multiplier,
            "backoff_multiplier",
            allow_zero=False,
        )
        maximum = _bounded_seconds(
            self.max_backoff_seconds,
            "max_backoff_seconds",
            allow_zero=True,
        )
        if initial > maximum:
            raise ValueError("initial_backoff_seconds cannot exceed max_backoff_seconds")
        object.__setattr__(self, "initial_backoff_seconds", initial)
        object.__setattr__(self, "backoff_multiplier", multiplier)
        object.__setattr__(self, "max_backoff_seconds", maximum)

    def delay_for_retry(self, retry_index: int) -> float:
        """Return the capped delay for a zero-based retry index."""

        if type(retry_index) is not int or retry_index < 0:
            raise ValueError("retry_index must be a non-negative exact integer")
        return min(
            self.initial_backoff_seconds * (self.backoff_multiplier**retry_index),
            self.max_backoff_seconds,
        )


@dataclass(frozen=True)
class EODProviderRateLimitPolicy:
    """Minimum start-to-start interval for one provider endpoint identity."""

    minimum_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        interval = _bounded_seconds(
            self.minimum_interval_seconds,
            "minimum_interval_seconds",
            allow_zero=True,
        )
        object.__setattr__(self, "minimum_interval_seconds", interval)


class EODRetrySleeper(Protocol):
    """Sleep contract injected at the provider invocation boundary."""

    def sleep(self, seconds: float) -> None:
        """Wait for a validated non-negative duration."""


class EODMonotonicClock(Protocol):
    """Monotonic time source used by local rate limiting."""

    def now(self) -> float:
        """Return monotonic seconds."""


class EODProviderRateLimiter(Protocol):
    """Acquire permission immediately before one real provider invocation."""

    def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
        """Return the actual local wait applied in seconds."""


class SystemEODRetrySleeper:
    """Production sleeper backed by ``time.sleep``."""

    def sleep(self, seconds: float) -> None:
        _TIME.sleep(_bounded_seconds(seconds, "seconds", allow_zero=True))


class SystemEODMonotonicClock:
    """Production clock backed by ``time.monotonic``."""

    def now(self) -> float:
        return _TIME.monotonic()


class NoOpEODProviderRateLimiter:
    """Compatibility limiter that never waits or retains state."""

    def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
        return 0.0


class _MinimumIntervalState:
    def __init__(self) -> None:
        self.lock = Lock()
        self.last_invocation: Optional[float] = None


class MinimumIntervalEODProviderRateLimiter:
    """Thread-safe, process-local minimum-interval limiter."""

    def __init__(
        self,
        policy: EODProviderRateLimitPolicy,
        *,
        clock: EODMonotonicClock,
        sleeper: EODRetrySleeper,
    ) -> None:
        if type(policy) is not EODProviderRateLimitPolicy:
            raise TypeError("policy must be an exact EODProviderRateLimitPolicy")
        if not callable(getattr(clock, "now", None)):
            raise TypeError("clock must implement the EODMonotonicClock contract")
        if not callable(getattr(sleeper, "sleep", None)):
            raise TypeError("sleeper must implement the EODRetrySleeper contract")
        self._policy = policy
        self._clock = clock
        self._sleeper = sleeper
        self._states: Dict[Tuple[str, Optional[str]], _MinimumIntervalState] = {}
        self._registry_lock = Lock()

    def acquire(self, provider_name: str, endpoint_name: Optional[str]) -> float:
        identity = _rate_limit_identity(provider_name, endpoint_name)
        with self._registry_lock:
            state = self._states.get(identity)
            if state is None:
                state = _MinimumIntervalState()
                self._states[identity] = state
        with state.lock:
            now = _monotonic_seconds(self._clock.now())
            previous = state.last_invocation
            wait_seconds = 0.0
            if previous is not None:
                elapsed = now - previous
                if elapsed < 0.0:
                    raise RuntimeError("monotonic clock moved backwards")
                wait_seconds = max(0.0, self._policy.minimum_interval_seconds - elapsed)
                if wait_seconds > 0.0:
                    self._sleeper.sleep(wait_seconds)
                    now = _monotonic_seconds(self._clock.now())
                    if now < previous:
                        raise RuntimeError("monotonic clock moved backwards")
            state.last_invocation = now
            return wait_seconds


def _rate_limit_identity(
    provider_name: object,
    endpoint_name: object,
) -> Tuple[str, Optional[str]]:
    if type(provider_name) is not str or not provider_name:
        raise ValueError("provider_name must be non-empty exact text")
    if endpoint_name is not None and (type(endpoint_name) is not str or not endpoint_name):
        raise ValueError("endpoint_name must be non-empty exact text or None")
    return provider_name, endpoint_name


def _monotonic_seconds(value: object) -> float:
    if type(value) not in (int, float):
        raise TypeError("monotonic clock must return an exact integer or float")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError("monotonic clock must return a finite value")
    return normalized


__all__ = [
    "EODMonotonicClock",
    "EODProviderRateLimitPolicy",
    "EODProviderRateLimiter",
    "EODProviderRetryPolicy",
    "EODRetrySleeper",
    "MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER",
    "MAX_EOD_PROVIDER_DELAY_SECONDS",
    "MinimumIntervalEODProviderRateLimiter",
    "NoOpEODProviderRateLimiter",
    "SystemEODMonotonicClock",
    "SystemEODRetrySleeper",
]
