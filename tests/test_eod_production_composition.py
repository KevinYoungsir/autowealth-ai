from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, MISSING, fields
from datetime import date
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

import autowealth.market_data as market_data
from autowealth.market_data.batch import (
    EODBatchCoordinator,
    InProcessEODDatasetLockManager,
)
from autowealth.market_data.calendar import MARKET_TIMEZONE, TradingCalendar
from autowealth.market_data.composition import (
    AKSHARE_INDEX_DAILY_PROVIDER,
    AKSHARE_INDEX_PROVIDER,
    EODCompositionError,
    EODCompositionErrorCode,
    EODProductionConfig,
    EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
    build_eod_batch_coordinator,
    build_eod_full_refresh_executor,
    build_eod_repository_maintenance_executor,
    build_eod_runtime,
    load_eod_production_config,
)
from autowealth.market_data.coordinator import EODIncrementalCoordinator
from autowealth.market_data.full_refresh import EODFullRefreshExecutor
from autowealth.market_data.maintenance import EODRepositoryMaintenanceExecutor
from autowealth.market_data.local_calendar import (
    EOD_CALENDAR_SCHEMA_VERSION,
    LocalTradingCalendarError,
    LocalTradingCalendarErrorCode,
    VersionedLocalTradingCalendar,
)
from autowealth.market_data.provider_chain import EODProviderChain
from autowealth.market_data.provider_resilience import (
    EODProviderRateLimitPolicy,
    EODProviderRetryPolicy,
)
from autowealth.market_data.providers import (
    EODProviderCapability,
    EODProviderRequest,
    EODProviderResult,
    EODRevisionStrategy,
)
from autowealth.market_data.repositories import LocalEODFileRepository
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    Market,
    Venue,
)

ROOT = Path(__file__).resolve().parents[1]
DAY_1 = date(2024, 1, 1)
DAY_2 = date(2024, 1, 2)
DAY_3 = date(2024, 1, 3)
DAY_4 = date(2024, 1, 4)
DAY_5 = date(2024, 1, 5)
WEEKEND_1 = date(2024, 1, 6)
WEEKEND_2 = date(2024, 1, 7)


class FakeProvider:
    provider_version = "test-fixture-v1"

    def __init__(self, provider_name: str, dataset: EODDatasetKey) -> None:
        self.provider_name = provider_name
        self.fetch_calls = 0
        self._capabilities = (
            EODProviderCapability(
                market=dataset.market,
                venue=dataset.venue,
                asset_type=dataset.asset_type,
                frequency=dataset.frequency,
                adjustment_type=dataset.adjustment_type,
                revision_strategy=EODRevisionStrategy.APPEND_ONLY,
            ),
        )

    @property
    def capabilities(self) -> tuple[EODProviderCapability, ...]:
        return self._capabilities

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        self.fetch_calls += 1
        raise AssertionError("TEST FIXTURE ONLY provider must not be fetched during construction")


@pytest.fixture
def index_dataset() -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.INDEX,
        canonical_symbol="000300.SH",
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


def _calendar_payload() -> dict[str, object]:
    # TEST FIXTURE ONLY. This is not a production or historical exchange calendar.
    return {
        "schema_version": EOD_CALENDAR_SCHEMA_VERSION,
        "calendar_id": "cn_a_share_test_fixture",
        "calendar_version": "test-fixture-v1",
        "timezone": MARKET_TIMEZONE,
        "coverage_start": DAY_1.isoformat(),
        "coverage_end": WEEKEND_2.isoformat(),
        "days": [
            {"trade_date": DAY_1.isoformat(), "is_trading_day": False},
            {"trade_date": DAY_2.isoformat(), "is_trading_day": True},
            {"trade_date": DAY_3.isoformat(), "is_trading_day": True},
            {"trade_date": DAY_4.isoformat(), "is_trading_day": True},
            {"trade_date": DAY_5.isoformat(), "is_trading_day": True},
            {"trade_date": WEEKEND_1.isoformat(), "is_trading_day": False},
            {"trade_date": WEEKEND_2.isoformat(), "is_trading_day": False},
        ],
    }


def _write_calendar(tmp_path: Path, payload: object = None) -> Path:
    path = tmp_path / "test-calendar.json"
    selected = _calendar_payload() if payload is None else payload
    path.write_text(json.dumps(selected, sort_keys=True), encoding="utf-8")
    return path


def _config_payload(
    repository_root: str = "repository",
    calendar_source: str = "test-calendar.json",
) -> dict[str, object]:
    return {
        "config_schema_version": EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
        "repository_root": repository_root,
        "calendar_source": calendar_source,
        "dataset": {
            "market": "CN",
            "venue": "SSE",
            "asset_type": "index",
            "canonical_symbol": "000300.SH",
            "frequency": "1d",
            "adjustment_type": "none",
        },
        "provider_order": [
            AKSHARE_INDEX_PROVIDER,
            AKSHARE_INDEX_DAILY_PROVIDER,
        ],
    }


def _write_config(tmp_path: Path, payload: object = None) -> Path:
    path = tmp_path / "eod.yaml"
    selected = (
        _config_payload(
            repository_root=str((tmp_path / "repository").resolve()),
            calendar_source=str((tmp_path / "test-calendar.json").resolve()),
        )
        if payload is None
        else payload
    )
    path.write_text(yaml.safe_dump(selected, sort_keys=False), encoding="utf-8")
    return path


def test_valid_fixture_loads_and_only_explicit_days_are_trading(tmp_path: Path) -> None:
    source = _write_calendar(tmp_path)
    before = source.read_bytes()

    calendar = VersionedLocalTradingCalendar.from_file(source)

    assert isinstance(calendar, TradingCalendar)
    assert calendar.identity.to_dict() == {
        "schema_version": 1,
        "calendar_id": "cn_a_share_test_fixture",
        "calendar_version": "test-fixture-v1",
        "timezone": "Asia/Shanghai",
        "coverage_start": "2024-01-01",
        "coverage_end": "2024-01-07",
    }
    assert calendar.is_trading_day(DAY_2) is True
    assert calendar.is_trading_day(DAY_1) is False
    assert calendar.is_trading_day(WEEKEND_1) is False
    assert calendar.trading_days(DAY_1, WEEKEND_2) == (DAY_2, DAY_3, DAY_4, DAY_5)
    assert calendar.next_trading_day(DAY_2) == DAY_3
    assert calendar.previous_trading_day(DAY_3) == DAY_2
    assert source.read_bytes() == before
    with pytest.raises(FrozenInstanceError):
        calendar.identity = calendar.identity  # type: ignore[misc]


def test_calendar_load_and_queries_are_deterministic(tmp_path: Path) -> None:
    source = _write_calendar(tmp_path)
    first = VersionedLocalTradingCalendar.from_file(source)
    second = VersionedLocalTradingCalendar.from_file(source)

    assert first == second
    assert first.trading_days(DAY_2, DAY_5) == second.trading_days(DAY_2, DAY_5)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("duplicate", LocalTradingCalendarErrorCode.DUPLICATE_DATE),
        ("unordered", LocalTradingCalendarErrorCode.UNORDERED_DATES),
        ("malformed_date", LocalTradingCalendarErrorCode.MALFORMED_DAY),
        ("malformed_value", LocalTradingCalendarErrorCode.MALFORMED_DAY),
        ("incomplete", LocalTradingCalendarErrorCode.INCOMPLETE_COVERAGE),
        ("unsupported_schema", LocalTradingCalendarErrorCode.UNSUPPORTED_SCHEMA),
    ],
)
def test_invalid_calendar_artifacts_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected_code: LocalTradingCalendarErrorCode,
) -> None:
    payload = deepcopy(_calendar_payload())
    days = payload["days"]
    assert type(days) is list
    if mutation == "duplicate":
        days[2]["trade_date"] = days[1]["trade_date"]
    elif mutation == "unordered":
        days[1], days[2] = days[2], days[1]
    elif mutation == "malformed_date":
        days[1]["trade_date"] = "2024/01/02"
    elif mutation == "malformed_value":
        days[1]["is_trading_day"] = 1
    elif mutation == "incomplete":
        days.pop(3)
    elif mutation == "unsupported_schema":
        payload["schema_version"] = 2

    with pytest.raises(LocalTradingCalendarError) as captured:
        VersionedLocalTradingCalendar.from_file(_write_calendar(tmp_path, payload))
    assert captured.value.code is expected_code


def test_empty_missing_and_invalid_json_calendar_fail_safely(tmp_path: Path) -> None:
    empty = _calendar_payload()
    empty["days"] = []
    with pytest.raises(LocalTradingCalendarError) as empty_error:
        VersionedLocalTradingCalendar.from_file(_write_calendar(tmp_path, empty))
    assert empty_error.value.code is LocalTradingCalendarErrorCode.EMPTY_CALENDAR

    missing = tmp_path / "apiKey=calendar-secret.json"
    with pytest.raises(LocalTradingCalendarError) as missing_error:
        VersionedLocalTradingCalendar.from_file(missing)
    assert missing_error.value.code is LocalTradingCalendarErrorCode.SOURCE_MISSING
    assert "calendar-secret" not in str(missing_error.value)
    assert str(tmp_path) not in str(missing_error.value)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")
    with pytest.raises(LocalTradingCalendarError) as invalid_error:
        VersionedLocalTradingCalendar.from_file(invalid)
    assert invalid_error.value.code is LocalTradingCalendarErrorCode.INVALID_JSON


def test_unreadable_calendar_is_classified_without_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _write_calendar(tmp_path)

    def unreadable(*args: object, **kwargs: object) -> str:
        raise OSError("C:\\private\\calendar apiKey=calendar-secret")

    monkeypatch.setattr(Path, "read_text", unreadable)
    with pytest.raises(LocalTradingCalendarError) as captured:
        VersionedLocalTradingCalendar.from_file(source)
    assert captured.value.code is LocalTradingCalendarErrorCode.SOURCE_UNREADABLE
    assert "calendar-secret" not in str(captured.value)
    assert "private" not in str(captured.value)


def test_calendar_rejects_queries_outside_declared_coverage(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(_write_calendar(tmp_path))
    with pytest.raises(LocalTradingCalendarError) as captured:
        calendar.trading_days(date(2023, 12, 31), DAY_2)
    assert captured.value.code is LocalTradingCalendarErrorCode.OUTSIDE_COVERAGE
    with pytest.raises(LocalTradingCalendarError):
        calendar.next_trading_day(WEEKEND_2)


def test_valid_configuration_resolves_paths_without_loading_calendar(tmp_path: Path) -> None:
    config = load_eod_production_config(_write_config(tmp_path))

    assert config.repository_root == (tmp_path / "repository").resolve()
    assert config.calendar_source == (tmp_path / "test-calendar.json").resolve()
    assert config.dataset.canonical_symbol == "000300.SH"
    assert config.provider_order == (
        AKSHARE_INDEX_PROVIDER,
        AKSHARE_INDEX_DAILY_PROVIDER,
    )
    assert config.retry_policy == EODProviderRetryPolicy()
    assert config.rate_limit_policy == EODProviderRateLimitPolicy()


def test_legacy_v1_configuration_loads_with_behavior_compatible_defaults(
    tmp_path: Path,
) -> None:
    payload = _config_payload()
    payload["config_schema_version"] = 1

    config = load_eod_production_config(_write_config(tmp_path, payload))

    assert config.config_schema_version == 1
    assert config.retry_policy == EODProviderRetryPolicy(max_attempts=1)
    assert config.rate_limit_policy == EODProviderRateLimitPolicy(minimum_interval_seconds=0)


def test_legacy_v1_configuration_rejects_resilience_extension_fields(tmp_path: Path) -> None:
    payload = _config_payload()
    payload["config_schema_version"] = 1
    payload["retry_policy"] = {
        "max_attempts": 1,
        "initial_backoff_seconds": 1,
        "backoff_multiplier": 2,
        "max_backoff_seconds": 5,
    }

    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(_write_config(tmp_path, payload))

    assert captured.value.code is EODCompositionErrorCode.INVALID_CONFIG


def test_optional_resilience_configuration_is_strict_and_explicit(tmp_path: Path) -> None:
    payload = _config_payload()
    payload["retry_policy"] = {
        "max_attempts": 3,
        "initial_backoff_seconds": 0.5,
        "backoff_multiplier": 2.0,
        "max_backoff_seconds": 2.0,
    }
    payload["rate_limit_policy"] = {"minimum_interval_seconds": 1.5}

    config = load_eod_production_config(_write_config(tmp_path, payload))

    assert config.retry_policy == EODProviderRetryPolicy(
        max_attempts=3,
        initial_backoff_seconds=0.5,
        backoff_multiplier=2.0,
        max_backoff_seconds=2.0,
    )
    assert config.rate_limit_policy == EODProviderRateLimitPolicy(minimum_interval_seconds=1.5)


@pytest.mark.parametrize(
    ("section", "value"),
    [
        ("retry_policy", {"max_attempts": 3}),
        (
            "retry_policy",
            {
                "max_attempts": 6,
                "initial_backoff_seconds": 1,
                "backoff_multiplier": 2,
                "max_backoff_seconds": 5,
            },
        ),
        ("rate_limit_policy", {"minimum_interval_seconds": 0, "jitter": 1}),
        ("rate_limit_policy", {"minimum_interval_seconds": -1}),
    ],
)
def test_invalid_resilience_configuration_fails_closed(
    tmp_path: Path,
    section: str,
    value: object,
) -> None:
    payload = _config_payload()
    payload[section] = value
    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(_write_config(tmp_path, payload))
    assert captured.value.code is EODCompositionErrorCode.INVALID_CONFIG


@pytest.mark.parametrize("mutation", ["missing_calendar", "invalid_repository", "unsupported"])
def test_invalid_configuration_fails_closed(tmp_path: Path, mutation: str) -> None:
    payload = _config_payload()
    if mutation == "missing_calendar":
        del payload["calendar_source"]
    elif mutation == "invalid_repository":
        payload["repository_root"] = ""
    elif mutation == "unsupported":
        payload["provider_order"] = ["unknown_provider"]

    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(_write_config(tmp_path, payload))
    assert captured.value.code is EODCompositionErrorCode.INVALID_CONFIG


def test_configuration_has_no_machine_specific_path_defaults() -> None:
    field_map = {item.name: item for item in fields(EODProductionConfig)}
    assert field_map["repository_root"].default is MISSING
    assert field_map["calendar_source"].default is MISSING

    example = (ROOT / "configs/eod_production.example.yaml").read_text(encoding="utf-8")
    assert "C:\\" not in example
    assert "D:\\" not in example
    assert "Users/" not in example
    assert "api_key" not in example.lower()
    assert "token" not in example.lower()

    parsed = load_eod_production_config(ROOT / "configs/eod_production.example.yaml")
    assert parsed.config_schema_version == 2
    assert parsed.dataset.canonical_symbol == "000300.SH"
    assert parsed.provider_order == (
        AKSHARE_INDEX_PROVIDER,
        AKSHARE_INDEX_DAILY_PROVIDER,
    )
    assert parsed.retry_policy.max_attempts == 1
    assert parsed.rate_limit_policy.minimum_interval_seconds == 0.0


def test_configuration_errors_do_not_leak_paths_or_credentials(tmp_path: Path) -> None:
    missing = tmp_path / "apiKey=configuration-secret.yaml"
    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(missing)
    assert captured.value.code is EODCompositionErrorCode.CONFIG_MISSING
    assert "configuration-secret" not in str(captured.value)
    assert str(tmp_path) not in str(captured.value)


def test_composition_constructs_full_stack_without_fetch_or_publication(
    tmp_path: Path,
    index_dataset: EODDatasetKey,
) -> None:
    _write_calendar(tmp_path)
    config = load_eod_production_config(_write_config(tmp_path))
    created = []

    def factory(provider_name: str):
        def create(calendar: TradingCalendar) -> FakeProvider:
            assert isinstance(calendar, VersionedLocalTradingCalendar)
            provider = FakeProvider(provider_name, index_dataset)
            created.append(provider)
            return provider

        return create

    runtime = build_eod_runtime(
        config,
        provider_factories={
            AKSHARE_INDEX_PROVIDER: factory(AKSHARE_INDEX_PROVIDER),
            AKSHARE_INDEX_DAILY_PROVIDER: factory(AKSHARE_INDEX_DAILY_PROVIDER),
        },
    )

    assert runtime.config is config
    assert runtime.dataset == index_dataset
    assert runtime.provider_order == config.provider_order
    assert isinstance(runtime.calendar, VersionedLocalTradingCalendar)
    assert isinstance(runtime.repository, LocalEODFileRepository)
    assert isinstance(runtime.provider_chain, EODProviderChain)
    assert isinstance(runtime.coordinator, EODIncrementalCoordinator)
    assert [provider.fetch_calls for provider in created] == [0, 0]
    assert not config.repository_root.exists()


def test_composition_is_deterministic_with_fake_providers(
    tmp_path: Path,
    index_dataset: EODDatasetKey,
) -> None:
    _write_calendar(tmp_path)
    config = load_eod_production_config(_write_config(tmp_path))

    def factories() -> dict[str, object]:
        return {
            name: (lambda calendar, selected=name: FakeProvider(selected, index_dataset))
            for name in config.provider_order
        }

    first = build_eod_runtime(config, provider_factories=factories())
    second = build_eod_runtime(config, provider_factories=factories())

    assert first.config == second.config
    assert first.calendar == second.calendar
    assert first.provider_order == second.provider_order
    assert not config.repository_root.exists()


def test_composition_builds_explicit_batch_without_execution(
    tmp_path: Path,
    index_dataset: EODDatasetKey,
) -> None:
    _write_calendar(tmp_path)
    config = load_eod_production_config(_write_config(tmp_path))
    created = []

    def factory(provider_name: str):
        def create(calendar: TradingCalendar) -> FakeProvider:
            provider = FakeProvider(provider_name, index_dataset)
            created.append(provider)
            return provider

        return create

    runtime = build_eod_runtime(
        config,
        provider_factories={
            AKSHARE_INDEX_PROVIDER: factory(AKSHARE_INDEX_PROVIDER),
            AKSHARE_INDEX_DAILY_PROVIDER: factory(AKSHARE_INDEX_DAILY_PROVIDER),
        },
    )
    lock_manager = InProcessEODDatasetLockManager()

    batch = build_eod_batch_coordinator((runtime,), lock_manager=lock_manager)
    full_refresh = build_eod_full_refresh_executor(runtime, lock_manager=lock_manager)
    maintenance = build_eod_repository_maintenance_executor(runtime, lock_manager=lock_manager)

    assert isinstance(batch, EODBatchCoordinator)
    assert isinstance(full_refresh, EODFullRefreshExecutor)
    assert isinstance(maintenance, EODRepositoryMaintenanceExecutor)
    assert batch._lock_manager is lock_manager
    assert full_refresh._lock_manager is lock_manager
    assert maintenance._lock_manager is lock_manager
    assert maintenance._repository is runtime.repository
    assert [provider.fetch_calls for provider in created] == [0, 0]
    assert not config.repository_root.exists()
    with pytest.raises(ValueError, match="duplicate"):
        build_eod_batch_coordinator((runtime, runtime), lock_manager=lock_manager)


def test_composition_builds_explicit_full_refresh_executor_without_execution(
    tmp_path: Path,
    index_dataset: EODDatasetKey,
) -> None:
    _write_calendar(tmp_path)
    config = load_eod_production_config(_write_config(tmp_path))
    created = []

    def factory(provider_name: str):
        def create(calendar: TradingCalendar) -> FakeProvider:
            provider = FakeProvider(provider_name, index_dataset)
            created.append(provider)
            return provider

        return create

    runtime = build_eod_runtime(
        config,
        provider_factories={
            AKSHARE_INDEX_PROVIDER: factory(AKSHARE_INDEX_PROVIDER),
            AKSHARE_INDEX_DAILY_PROVIDER: factory(AKSHARE_INDEX_DAILY_PROVIDER),
        },
    )

    executor = build_eod_full_refresh_executor(
        runtime,
        lock_manager=InProcessEODDatasetLockManager(),
    )

    assert isinstance(executor, EODFullRefreshExecutor)
    assert [provider.fetch_calls for provider in created] == [0, 0]
    assert not config.repository_root.exists()


def test_repository_configuration_is_validated_before_provider_construction(
    tmp_path: Path,
    index_dataset: EODDatasetKey,
) -> None:
    _write_calendar(tmp_path)
    invalid_root = tmp_path / "repository-file"
    invalid_root.write_text("not a directory", encoding="utf-8")
    payload = _config_payload(
        repository_root=str(invalid_root.resolve()),
        calendar_source=str((tmp_path / "test-calendar.json").resolve()),
    )
    config = load_eod_production_config(_write_config(tmp_path, payload))
    factory_calls = []

    def factory(calendar: TradingCalendar) -> FakeProvider:
        factory_calls.append(calendar)
        return FakeProvider(AKSHARE_INDEX_PROVIDER, index_dataset)

    with pytest.raises(EODCompositionError) as captured:
        build_eod_runtime(
            config,
            provider_factories={
                AKSHARE_INDEX_PROVIDER: factory,
                AKSHARE_INDEX_DAILY_PROVIDER: factory,
            },
        )
    assert captured.value.code is EODCompositionErrorCode.REPOSITORY_INVALID
    assert factory_calls == []


def test_default_provider_composition_does_not_import_akshare_or_access_network(
    tmp_path: Path,
) -> None:
    _write_calendar(tmp_path)
    config_path = _write_config(tmp_path)
    script = r"""
import socket
import sys
from pathlib import Path

def blocked(*args, **kwargs):
    raise AssertionError("network access is forbidden during composition")

socket.create_connection = blocked
socket.socket.connect = blocked

from autowealth.market_data.composition import build_eod_runtime, load_eod_production_config

runtime = build_eod_runtime(load_eod_production_config(Path(sys.argv[1])))
assert runtime.provider_order == ("akshare_eod_index", "akshare_eod_index_daily")
assert "akshare" not in sys.modules
assert not runtime.config.repository_root.exists()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(config_path)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_composition_import_has_no_network_file_write_or_runtime_side_effects() -> None:
    script = r"""
import builtins
import os
from pathlib import Path
import socket
import sys

import autowealth

before_environment = dict(os.environ)
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

import autowealth.market_data.composition

assert dict(os.environ) == before_environment
new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before_modules}
assert {"akshare", "pandas", "pyarrow", "requests", "yfinance"}.isdisjoint(new_roots)
assert "autowealth.market_data.repositories" not in sys.modules
assert "autowealth.market_data.coordinator" not in sys.modules
assert "autowealth.market_data.maintenance" not in sys.modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_root_exports_remain_lazy_and_new_modules_parse_as_python_39() -> None:
    expected = {
        "EOD_CALENDAR_SCHEMA_VERSION",
        "EODFullRefreshExecutor",
        "EODRepositoryMaintenanceExecutor",
        "EODRepositoryMaintenanceRequest",
        "EOD_PRODUCTION_CONFIG_SCHEMA_VERSION",
        "EODProductionConfig",
        "EODProviderRateLimitPolicy",
        "EODProviderRetryPolicy",
        "EODRuntimeStack",
        "VersionedLocalTradingCalendar",
        "build_eod_batch_coordinator",
        "build_eod_full_refresh_executor",
        "build_eod_repository_maintenance_executor",
        "build_eod_runtime",
        "load_eod_production_config",
    }
    assert expected <= set(market_data.__all__)
    assert len(market_data.__all__) == len(set(market_data.__all__))

    for relative_path in (
        "autowealth/market_data/local_calendar.py",
        "autowealth/market_data/composition.py",
        "autowealth/market_data/full_refresh.py",
        "autowealth/market_data/maintenance.py",
        "autowealth/market_data/provider_resilience.py",
        "autowealth/market_data/batch.py",
        "autowealth/market_data/__init__.py",
        "tests/test_eod_batch_coordinator.py",
        "tests/test_eod_full_refresh_executor.py",
        "tests/test_eod_repository_maintenance.py",
        "tests/test_eod_production_composition.py",
    ):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        ast.parse(source, filename=relative_path, feature_version=(3, 9))
