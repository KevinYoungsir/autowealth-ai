"""Offline tests for resilient benchmark providers and cache validation."""

from __future__ import annotations

import builtins
import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from autowealth.data.cache import ParquetCache
from autowealth.data.index_provider import (
    AKShareIndexDailyProvider,
    AShareIndexProvider,
    IndexDataProvider,
    UnsupportedIndexSymbolError,
    canonical_index_symbol,
    exchange_prefixed_index_symbol,
)
from autowealth.data.index_provider_chain import (
    IndexProviderChain,
    IndexProviderChainError,
    _write_benchmark_cache,
    default_index_provider_chain,
    load_benchmark_with_cache,
)
from autowealth.data.index_quality import validate_benchmark_data
from autowealth.data.schema import normalize_market_data

START = "2024-01-02"
END = "2024-01-31"
FIXED_TIME = datetime(2026, 7, 20, tzinfo=timezone.utc)


def _benchmark_frame(start: str = START, end: str = END) -> pd.DataFrame:
    dates = pd.bdate_range(start, end)
    return pd.DataFrame(
        {
            "date": dates,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": [100.0 + index for index in range(len(dates))],
            "volume": 1_000_000.0,
        }
    )


@dataclass
class FakeIndexProvider:
    response: object
    provider_name: str = "FakeIndexProvider"
    endpoint: str = "fake_daily"
    symbol_prefix: str = "fake:"
    calls: int = 0

    def provider_symbol(self, symbol: str) -> str:
        return f"{self.symbol_prefix}{symbol}"

    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        if callable(self.response):
            return self.response(symbol, start_date, end_date)
        return pd.DataFrame(self.response).copy()


class FakeAKShareModule:
    def __init__(self) -> None:
        self.primary_symbols: list[str] = []
        self.fallback_symbols: list[str] = []

    def index_zh_a_hist(self, *, symbol, period, start_date, end_date):
        self.primary_symbols.append(symbol)
        return _benchmark_frame(start_date, end_date)

    def stock_zh_index_daily(self, *, symbol):
        self.fallback_symbols.append(symbol)
        return _benchmark_frame()


@dataclass
class ResolverFailingProvider(FakeIndexProvider):
    resolver_error: Exception = RuntimeError("symbol resolver failed")

    def provider_symbol(self, symbol: str) -> str:
        raise self.resolver_error


def _chain(*providers: FakeIndexProvider) -> IndexProviderChain:
    return IndexProviderChain(providers, clock=lambda: FIXED_TIME)


def _chain_with_ratio(
    *providers: FakeIndexProvider,
    minimum_coverage_ratio: float,
) -> IndexProviderChain:
    return IndexProviderChain(
        providers,
        minimum_coverage_ratio=minimum_coverage_ratio,
        clock=lambda: FIXED_TIME,
    )


def _eighty_five_percent_frame() -> tuple[pd.DataFrame, str, str]:
    dates = pd.bdate_range("2024-01-02", periods=100)
    start = dates[0].strftime("%Y-%m-%d")
    end = dates[-1].strftime("%Y-%m-%d")
    frame = _benchmark_frame(start, end)
    interior_positions = list(range(5, 95, 6))
    assert len(interior_positions) == 15
    return frame.drop(index=interior_positions).reset_index(drop=True), start, end


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("000300", "000300"),
        ("000905", "000905"),
        ("000852", "000852"),
        ("000001", "000001"),
        ("399001", "399001"),
        ("399006", "399006"),
        ("沪深300", "000300"),
        ("沪深 300", "000300"),
        ("sh000300", "000300"),
        ("399001.SZ", "399001"),
    ],
)
def test_canonical_symbol_resolution(value: str, expected: str) -> None:
    assert canonical_index_symbol(value) == expected


def test_provider_symbol_conversion_and_unsupported_code() -> None:
    assert exchange_prefixed_index_symbol("000300") == "sh000300"
    assert exchange_prefixed_index_symbol("399001") == "sz399001"
    with pytest.raises(
        UnsupportedIndexSymbolError,
        match="unsupported A-share index",
    ) as captured:
        canonical_index_symbol("123456")
    assert captured.value.reason_code == "unsupported_symbol"


def test_index_provider_protocol_and_default_construction_are_offline(
    monkeypatch,
) -> None:
    fake = FakeIndexProvider(_benchmark_frame())
    assert isinstance(fake, IndexDataProvider)

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", maxsplit=1)[0] in {"akshare", "requests"}:
            raise AssertionError(f"unexpected network dependency import: {name}")
        return original_import(name, *args, **kwargs)

    def blocked_socket(*args, **kwargs):
        raise AssertionError("socket access is forbidden in offline tests")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "create_connection", blocked_socket)

    providers = default_index_provider_chain().providers
    result = _chain(fake).fetch_daily("000300", START, END)

    assert [provider.endpoint for provider in providers] == [
        "index_zh_a_hist",
        "stock_zh_index_daily",
    ]
    assert result.selected_provider == "FakeIndexProvider"


def test_production_providers_support_protocol_and_legacy_keywords() -> None:
    module = FakeAKShareModule()
    primary = AShareIndexProvider(akshare_module=module)
    fallback = AKShareIndexDailyProvider(akshare_module=module)

    by_symbol = primary.get_daily(symbol="000300", start_date=START, end_date=END)
    by_index = primary.get_daily(index="沪深300", start_date=START, end_date=END)
    fallback_data = fallback.get_daily(symbol="399001", start_date=START, end_date=END)

    assert not by_symbol.empty
    assert not by_index.empty
    assert not fallback_data.empty
    assert module.primary_symbols == ["000300", "000300"]
    assert module.fallback_symbols == ["sz399001"]
    with pytest.raises(TypeError, match="either symbol"):
        primary.get_daily(
            symbol="000300",
            index="沪深300",
            start_date=START,
            end_date=END,
        )


def test_primary_success_does_not_call_fallback() -> None:
    primary = FakeIndexProvider(_benchmark_frame(), provider_name="primary")
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = _chain(primary, fallback).fetch_daily("沪深 300", START, END)

    assert result.canonical_symbol == "000300"
    assert result.selected_provider == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert [attempt.reason_code for attempt in result.attempts] == ["success"]


def test_primary_exception_falls_back_and_preserves_sanitized_attempt() -> None:
    primary = FakeIndexProvider(
        RuntimeError("proxy https://user:secret@example.test/path?token=secret"),
        provider_name="primary",
    )
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = _chain(primary, fallback).fetch_daily("000300", START, END)

    assert result.selected_provider == "fallback"
    assert [attempt.status for attempt in result.attempts] == ["failed", "success"]
    assert result.attempts[0].reason_code == "provider_exception"
    assert result.attempts[0].source_metadata["role"] == "primary"
    assert result.attempts[1].source_metadata["role"] == "fallback"
    assert "secret" not in result.attempts[0].reason
    assert "secret" not in result.attempts[0].exception
    assert "[redacted-url]" in result.attempts[0].reason


def test_primary_resolver_exception_falls_back_with_auditable_attempt() -> None:
    primary = ResolverFailingProvider(
        _benchmark_frame(),
        provider_name="resolver_primary",
        resolver_error=RuntimeError("Authorization: Bearer resolver-secret"),
    )
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = _chain(primary, fallback).fetch_daily("沪深300", START, END)

    failed = result.attempts[0]
    assert result.selected_provider == "fallback"
    assert primary.calls == 0
    assert fallback.calls == 1
    assert failed.reason_code == "provider_exception"
    assert failed.provider_symbol == ""
    assert failed.source_metadata["failure_stage"] == "symbol_resolution"
    assert "resolver-secret" not in failed.exception
    assert failed.requested_symbol == "沪深300"
    assert json.loads(json.dumps(failed.to_dict(), ensure_ascii=False)) == failed.to_dict()


def test_all_resolvers_and_providers_fail_with_complete_attempts() -> None:
    resolver = ResolverFailingProvider(_benchmark_frame(), provider_name="resolver")
    provider = FakeIndexProvider(RuntimeError("provider failed"), provider_name="provider")

    with pytest.raises(IndexProviderChainError) as captured:
        _chain(resolver, provider).fetch_daily("000300", START, END)

    assert [attempt.reason_code for attempt in captured.value.attempts] == [
        "provider_exception",
        "provider_exception",
    ]
    assert captured.value.attempts[0].source_metadata["failure_stage"] == ("symbol_resolution")
    assert captured.value.attempts[1].source_metadata["failure_stage"] == "provider_request"


def test_provider_attempt_serialization_contains_stable_request_window() -> None:
    result = _chain(FakeIndexProvider(_benchmark_frame())).fetch_daily(
        "沪深300",
        "20240102",
        "2024-01-31",
    )

    payload = result.attempts[0].to_dict()

    assert payload["requested_symbol"] == "沪深300"
    assert payload["requested_start_date"] == START
    assert payload["requested_end_date"] == END
    assert payload["provider_symbol"] == "fake:000300"
    assert payload["rows"] == payload["row_count"]
    assert payload["minimum_coverage_ratio"] == 0.80
    assert payload["exception"] is None
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


def test_provider_exception_redacts_headers_and_limits_length() -> None:
    primary = FakeIndexProvider(
        RuntimeError("Authorization: Bearer topsecret " + "x" * 700),
        provider_name="primary",
    )
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = _chain(primary, fallback).fetch_daily("000300", START, END)

    reason = result.attempts[0].reason
    assert "topsecret" not in reason
    assert "authorization=[redacted]" in reason.lower()
    assert len(reason) <= 500


@pytest.mark.parametrize(
    ("response", "reason_code"),
    [
        (pd.DataFrame(), "empty_response"),
        (pd.DataFrame({"date": pd.bdate_range(START, END)}), "invalid_schema"),
        (_benchmark_frame().iloc[:2], "insufficient_coverage"),
    ],
)
def test_invalid_primary_response_falls_back(
    response: pd.DataFrame,
    reason_code: str,
) -> None:
    primary = FakeIndexProvider(response, provider_name="primary")
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = _chain(primary, fallback).fetch_daily("000300", START, END)

    assert result.selected_provider == "fallback"
    assert result.attempts[0].reason_code == reason_code
    assert result.attempts[0].row_count == len(response)
    assert result.attempts[0].source_metadata["raw_row_count"] == len(response)
    assert result.attempts[1].reason_code == "success"


def test_all_providers_fail_with_structured_attempts() -> None:
    primary = FakeIndexProvider(pd.DataFrame(), provider_name="primary")
    fallback = FakeIndexProvider(RuntimeError("disconnected"), provider_name="fallback")

    with pytest.raises(IndexProviderChainError) as captured:
        _chain(primary, fallback).fetch_daily("000300", START, END)

    assert [attempt.reason_code for attempt in captured.value.attempts] == [
        "empty_response",
        "provider_exception",
    ]


def test_unsupported_endpoint_is_skipped_by_capability_detection() -> None:
    primary = AShareIndexProvider(akshare_module=object())
    fallback = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = IndexProviderChain(
        [primary, fallback],
        clock=lambda: FIXED_TIME,
    ).fetch_daily("000300", START, END)

    assert result.selected_provider == "fallback"
    assert result.attempts[0].reason_code == "unsupported_endpoint"


@pytest.mark.parametrize(
    ("mutator", "reason_code"),
    [
        (lambda frame: pd.DataFrame(), "empty_response"),
        (lambda frame: frame.drop(columns="close"), "invalid_schema"),
        (lambda frame: frame.assign(close=0.0), "non_positive_close"),
        (lambda frame: frame.assign(date="not-a-date"), "invalid_dates"),
        (
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "duplicate_dates",
        ),
    ],
)
def test_benchmark_quality_rejects_invalid_data(mutator, reason_code: str) -> None:
    result = validate_benchmark_data(mutator(_benchmark_frame()), START, END)

    assert result.passed is False
    assert result.reason_code == reason_code


def test_missing_numeric_close_is_rejected() -> None:
    frame = _benchmark_frame()
    frame["close"] = frame["close"].astype(object)
    frame.loc[0, "close"] = "not-a-number"

    result = validate_benchmark_data(frame, START, END)

    assert result.reason_code == "missing_close"
    assert result.first_date == START
    assert result.last_date == END


@pytest.mark.parametrize(
    ("value", "reason_code"),
    [
        (float("nan"), "missing_close"),
        (float("inf"), "non_finite_close"),
        (float("-inf"), "non_finite_close"),
        (0.0, "non_positive_close"),
        (-1.0, "non_positive_close"),
    ],
)
def test_non_finite_and_non_positive_close_are_rejected(
    value: float,
    reason_code: str,
) -> None:
    frame = _benchmark_frame()
    frame.loc[0, "close"] = value

    result = validate_benchmark_data(frame, START, END)

    assert result.passed is False
    assert result.reason_code == reason_code


def test_duplicate_dates_are_audited() -> None:
    frame = _benchmark_frame()
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)

    result = validate_benchmark_data(frame, START, END)

    assert result.duplicate_date_count == 2
    assert result.raw_row_count == len(frame)


def test_dates_outside_requested_window_are_rejected() -> None:
    frame = _benchmark_frame()
    frame.loc[0, "date"] = pd.Timestamp(START) - pd.offsets.BDay(1)

    result = validate_benchmark_data(frame, START, END)

    assert result.passed is False
    assert result.reason_code == "invalid_dates"
    assert result.source_metadata["outside_requested_range_count"] == 1


def test_unsorted_dates_are_returned_in_stable_order() -> None:
    frame = _benchmark_frame().sample(frac=1.0, random_state=7).reset_index(drop=True)

    result = validate_benchmark_data(frame, START, END)

    assert result.passed is True
    assert result.data["date"].is_monotonic_increasing


@pytest.mark.parametrize("edge", ["start", "end"])
def test_truncated_request_window_edge_is_rejected_above_total_threshold(edge: str) -> None:
    start = "2024-01-02"
    end = "2024-06-28"
    frame = _benchmark_frame(start, end)
    removed = 10
    truncated = frame.iloc[removed:] if edge == "start" else frame.iloc[:-removed]

    result = validate_benchmark_data(truncated, start, end)

    assert len(truncated) / len(frame) > 0.80
    assert result.passed is False
    assert result.reason_code == "insufficient_coverage"
    assert "edge coverage failed" in result.reason


def test_small_request_window_edge_gaps_are_accepted() -> None:
    start = "2024-01-02"
    end = "2024-06-28"
    frame = _benchmark_frame(start, end).iloc[2:-2]

    result = validate_benchmark_data(frame, start, end)

    assert result.passed is True
    assert result.start_edge_gap_business_days == 2
    assert result.end_edge_gap_business_days == 2
    assert result.maximum_edge_gap_business_days == 5


@pytest.mark.parametrize(
    "ratio",
    [0, 1.01, float("nan"), float("inf"), True],
)
def test_provider_chain_rejects_invalid_coverage_ratio(ratio: object) -> None:
    with pytest.raises(ValueError, match="minimum_coverage_ratio"):
        IndexProviderChain(
            [FakeIndexProvider(_benchmark_frame())],
            minimum_coverage_ratio=ratio,
        )


def _load_to_cache(tmp_path: Path) -> tuple[Path, Path]:
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="seed_provider")
    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )
    assert result.status == "success"
    metadata_path = next(tmp_path.glob("*.meta.json"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    cache_path = tmp_path / metadata["data_file"]
    return cache_path, metadata_path


def _assert_no_committed_generation_cache(tmp_path: Path) -> None:
    assert list(tmp_path.glob("*.meta.json")) == []
    assert list(tmp_path.glob("*.data.parquet")) == []
    assert list(tmp_path.glob(".*.tmp*")) == []


def test_valid_cache_short_circuits_every_provider(tmp_path: Path) -> None:
    _, metadata_path = _load_to_cache(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    provider = FakeIndexProvider(AssertionError("provider must not run"))

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "沪深300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.status == "success"
    assert result.diagnostic["cache_status"] == "hit_valid"
    assert result.diagnostic["selected_provider"] == "seed_provider"
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_hit"
    assert result.diagnostic["minimum_coverage_ratio"] == 0.80
    assert result.diagnostic["requested_start_date"] == START
    assert result.diagnostic["requested_end_date"] == END
    assert json.loads(json.dumps(result.diagnostic, ensure_ascii=False)) == result.diagnostic
    assert metadata["fetched_at"] == FIXED_TIME.isoformat()
    assert metadata["cache_layout_version"] == 2
    assert metadata["minimum_coverage_ratio"] == 0.80
    assert metadata["coverage_ratio"] == 1.0
    assert metadata["data_file"]
    assert provider.calls == 0


def test_legacy_cache_layout_remains_readable(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    cache_path = cache.path_for("benchmark_000300", START, END, "none")
    metadata_path = cache_path.with_suffix(".meta.json")
    frame = _benchmark_frame()
    frame.to_parquet(cache_path, index=False)
    metadata_path.write_text(
        json.dumps(
            {
                "data_type": "benchmark",
                "symbol": "000300",
                "source": "legacy_provider",
                "endpoint": "legacy_endpoint",
                "fetch_start_date": START,
                "fetch_end_date": END,
                "rows": len(frame),
                "first_date": START,
                "last_date": END,
                "coverage_ratio": 1.0,
                "sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    provider = FakeIndexProvider(AssertionError("legacy cache must short-circuit"))

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.status == "success"
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_hit"
    assert result.diagnostic["attempts"][0]["source_metadata"]["cache_layout_version"] == 1
    assert provider.calls == 0


def test_cache_uses_the_requesting_chain_coverage_threshold(tmp_path: Path) -> None:
    frame, start, end = _eighty_five_percent_frame()
    seed = FakeIndexProvider(frame, provider_name="seed_provider")
    seeded = load_benchmark_with_cache(
        tmp_path,
        _chain_with_ratio(seed, minimum_coverage_ratio=0.80),
        "000300",
        start,
        end,
        clock=lambda: FIXED_TIME,
    )
    assert seeded.status == "success"

    strict_provider = FakeIndexProvider(_benchmark_frame(start, end), provider_name="strict")
    strict = load_benchmark_with_cache(
        tmp_path,
        _chain_with_ratio(strict_provider, minimum_coverage_ratio=0.90),
        "000300",
        start,
        end,
        clock=lambda: FIXED_TIME,
    )

    assert strict_provider.calls == 1
    assert strict.diagnostic["attempts"][0]["reason_code"] == ("cache_insufficient_coverage")
    assert strict.diagnostic["minimum_coverage_ratio"] == 0.90

    permissive_provider = FakeIndexProvider(AssertionError("valid cache must short-circuit"))
    permissive = load_benchmark_with_cache(
        tmp_path,
        _chain_with_ratio(permissive_provider, minimum_coverage_ratio=0.80),
        "000300",
        start,
        end,
        clock=lambda: FIXED_TIME,
    )

    assert permissive.status == "success"
    assert permissive.diagnostic["attempts"][0]["reason_code"] == "cache_hit"
    assert permissive_provider.calls == 0


def test_unreadable_cache_calls_provider_without_overwriting_old_file(
    tmp_path: Path,
) -> None:
    cache_path, _ = _load_to_cache(tmp_path)
    cache_path.write_bytes(b"not parquet")
    before = cache_path.read_bytes()
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert provider.calls == 1
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_unreadable"
    assert result.diagnostic["cache_status"] == "invalid_preserved"
    assert cache_path.read_bytes() == before


def test_unreadable_cache_metadata_calls_provider(tmp_path: Path) -> None:
    _, metadata_path = _load_to_cache(tmp_path)
    metadata_path.write_text("{not-json", encoding="utf-8")
    before = metadata_path.read_bytes()
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert provider.calls == 1
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_unreadable"
    assert metadata_path.read_bytes() == before


@pytest.mark.parametrize(
    ("field", "value", "reason_fragment"),
    [
        ("symbol", "399001", "symbol mismatch"),
        ("fetch_start_date", "2024-01-03", "fetch_start_date mismatch"),
        ("fetch_end_date", "2024-01-30", "fetch_end_date mismatch"),
        ("rows", 999, "row count mismatch"),
        ("first_date", "2024-01-03", "first_date mismatch"),
        ("last_date", "2024-01-30", "last_date mismatch"),
        ("source", "mutated_source", "source mismatch"),
        ("coverage_ratio", 0.123, "coverage ratio mismatch"),
    ],
)
def test_cache_metadata_mismatch_uses_stable_reason_code(
    tmp_path: Path,
    field: str,
    value: object,
    reason_fragment: str,
) -> None:
    _, metadata_path = _load_to_cache(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = metadata_path.read_bytes()
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    cache_attempt = result.diagnostic["attempts"][0]
    assert provider.calls == 1
    assert cache_attempt["reason_code"] == "cache_metadata_mismatch"
    assert reason_fragment in cache_attempt["reason"]
    assert metadata_path.read_bytes() == before


def test_cache_sha_mismatch_calls_provider(tmp_path: Path) -> None:
    cache_path, metadata_path = _load_to_cache(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert provider.calls == 1
    cache_attempt = result.diagnostic["attempts"][0]
    assert cache_attempt["reason_code"] == "cache_sha_mismatch"
    assert "sha256 mismatch" in cache_attempt["reason"]


def test_cache_insufficient_coverage_calls_provider(tmp_path: Path) -> None:
    cache_path, metadata_path = _load_to_cache(tmp_path)
    short = _benchmark_frame().iloc[:2].copy()
    short.to_parquet(cache_path, index=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata.update(
        {
            "sha256": hashlib.sha256(cache_path.read_bytes()).hexdigest(),
            "rows": len(short),
            "first_date": short["date"].min().strftime("%Y-%m-%d"),
            "last_date": short["date"].max().strftime("%Y-%m-%d"),
        }
    )
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    provider = FakeIndexProvider(_benchmark_frame(), provider_name="fallback")

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(provider),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert provider.calls == 1
    cache_attempt = result.diagnostic["attempts"][0]
    assert cache_attempt["reason_code"] == "cache_insufficient_coverage"
    assert cache_attempt["source_metadata"]["quality_reason_code"] == ("insufficient_coverage")


def test_cache_data_temporary_write_failure_leaves_no_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_to_parquet(*args, **kwargs):
        raise OSError("simulated data temporary write failure")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fail_to_parquet)

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(FakeIndexProvider(_benchmark_frame())),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.status == "success"
    assert result.diagnostic["cache_status"] == "write_failed"
    _assert_no_committed_generation_cache(tmp_path)


def test_cache_metadata_temporary_write_failure_leaves_no_commit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    original_write_text = Path.write_text

    def fail_metadata_temp(path: Path, *args, **kwargs):
        if path.name.endswith(".tmp"):
            raise OSError("simulated metadata temporary write failure")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_metadata_temp)

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(FakeIndexProvider(_benchmark_frame())),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.diagnostic["cache_status"] == "write_failed"
    _assert_no_committed_generation_cache(tmp_path)


@pytest.mark.parametrize("failure_target", ["data_generation", "commit_marker"])
def test_cache_publication_failure_leaves_no_half_published_success(
    tmp_path: Path,
    monkeypatch,
    failure_target: str,
) -> None:
    original_replace = Path.replace

    def fail_replace(path: Path, target: Path):
        target_path = Path(target)
        is_data_generation = target_path.name.endswith(".data.parquet")
        is_commit_marker = target_path.name.endswith(".meta.json")
        if (failure_target == "data_generation" and is_data_generation) or (
            failure_target == "commit_marker" and is_commit_marker
        ):
            raise OSError(f"simulated {failure_target} publication failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_replace)

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(FakeIndexProvider(_benchmark_frame())),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.diagnostic["cache_status"] == "write_failed"
    _assert_no_committed_generation_cache(tmp_path)


def test_existing_valid_cache_rejects_publish_overwrite_and_remains_readable(
    tmp_path: Path,
) -> None:
    data_path, metadata_path = _load_to_cache(tmp_path)
    data_before = data_path.read_bytes()
    metadata_before = metadata_path.read_bytes()
    provider_result = _chain(FakeIndexProvider(_benchmark_frame())).fetch_daily(
        "000300",
        START,
        END,
    )
    canonical_path = ParquetCache(tmp_path).path_for("benchmark_000300", START, END, "none")

    with pytest.raises(FileExistsError, match="already exists"):
        _write_benchmark_cache(
            canonical_path,
            metadata_path,
            provider_result,
            START,
            END,
            FIXED_TIME,
        )

    assert data_path.read_bytes() == data_before
    assert metadata_path.read_bytes() == metadata_before
    result = load_benchmark_with_cache(
        tmp_path,
        _chain(FakeIndexProvider(AssertionError("cache must remain readable"))),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_hit"


def test_uncommitted_generation_does_not_replace_old_valid_cache(tmp_path: Path) -> None:
    data_path, metadata_path = _load_to_cache(tmp_path)
    old_data = pd.read_parquet(data_path)
    uncommitted_path = data_path.with_name(f"{data_path.stem}.uncommitted.data.parquet")
    replacement = old_data.copy()
    replacement["close"] = replacement["close"] + 1000.0
    replacement.to_parquet(uncommitted_path, index=False)

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(FakeIndexProvider(AssertionError("committed cache must short-circuit"))),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["data_file"] == data_path.name
    assert result.diagnostic["attempts"][0]["reason_code"] == "cache_hit"
    pd.testing.assert_frame_equal(result.data, normalize_market_data(old_data))
    assert not result.data["close"].equals(replacement["close"])


def test_all_provider_failures_return_unavailable_diagnostics(tmp_path: Path) -> None:
    providers = [
        FakeIndexProvider(pd.DataFrame(), provider_name="primary"),
        FakeIndexProvider(RuntimeError("offline"), provider_name="fallback"),
    ]

    result = load_benchmark_with_cache(
        tmp_path,
        _chain(*providers),
        "000300",
        START,
        END,
        clock=lambda: FIXED_TIME,
    )

    assert result.status == "unavailable"
    assert result.data.empty
    assert result.diagnostic["selected_provider"] is None
    assert [item["reason_code"] for item in result.diagnostic["attempts"]] == [
        "empty_response",
        "provider_exception",
    ]
