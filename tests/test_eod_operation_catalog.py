from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from autowealth.market_data.composition import (
    AKSHARE_EQUITY_PROVIDER,
    EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
    EODProductionConfig,
    EODRuntimeStack,
)
from autowealth.market_data.local_calendar import (
    EOD_CALENDAR_SCHEMA_VERSION,
    MARKET_TIMEZONE,
    VersionedLocalTradingCalendar,
)
from autowealth.market_data.operation_catalog import (
    EOD_OPERATION_CATALOG_SCHEMA_VERSION,
    EOD_RUNTIME_CONTRACT_VERSION,
    MAX_EOD_OPERATION_CATALOG_ENTRIES,
    EODOperationCatalog,
    EODOperationCatalogEntry,
    EODOperationCatalogError,
    EODOperationCatalogErrorCode,
    build_eod_operation_catalog,
)
from autowealth.market_data.operation_control import eod_calendar_identity
from autowealth.market_data.provider_resilience import (
    EODProviderRateLimitPolicy,
    EODProviderRetryPolicy,
)
from autowealth.market_data.providers import EODProviderCapability, EODRevisionStrategy
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    Market,
    Venue,
)

DAY_1 = date(2024, 1, 1)
DAY_5 = date(2024, 1, 5)


class OfflineProvider:
    provider_name = AKSHARE_EQUITY_PROVIDER
    endpoint_name = "fixture_endpoint_must_not_enter_fingerprint"

    def __init__(self, dataset: EODDatasetKey, version: str = "fixture-v1") -> None:
        self.provider_version = version
        self.fetch_calls = 0
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

    def fetch(self, request):
        self.fetch_calls += 1
        raise AssertionError("offline catalog tests must never fetch provider data")


def dataset(symbol: str = "600000.SH") -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE if symbol.endswith(".SH") else Venue.SZSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol=symbol,
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


def write_calendar(
    root: Path,
    *,
    name: str = "calendar",
    version: str = "fixture-v1",
    coverage_end: date = DAY_5,
) -> Path:
    path = root / f"{name}.json"
    days = []
    current = DAY_1
    while current <= coverage_end:
        days.append({"trade_date": current.isoformat(), "is_trading_day": True})
        current += timedelta(days=1)
    path.write_text(
        json.dumps(
            {
                "schema_version": EOD_CALENDAR_SCHEMA_VERSION,
                "calendar_id": "cn_a_share_fixture",
                "calendar_version": version,
                "timezone": MARKET_TIMEZONE,
                "coverage_start": DAY_1.isoformat(),
                "coverage_end": coverage_end.isoformat(),
                "days": days,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def runtime(
    root: Path,
    calendar: VersionedLocalTradingCalendar,
    selected: EODDatasetKey,
    *,
    storage_suffix: str = "one",
    provider_version: str = "fixture-v1",
    retry_policy: EODProviderRetryPolicy = EODProviderRetryPolicy(),
    rate_limit_policy: EODProviderRateLimitPolicy = EODProviderRateLimitPolicy(),
) -> EODRuntimeStack:
    provider = OfflineProvider(selected, provider_version)
    config = EODProductionConfig(
        config_schema_version=EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
        repository_root=(root / f"repository-{storage_suffix}").resolve(),
        calendar_source=(root / f"calendar-source-{storage_suffix}.json").resolve(),
        dataset=selected,
        provider_order=(AKSHARE_EQUITY_PROVIDER,),
        retry_policy=retry_policy,
        rate_limit_policy=rate_limit_policy,
    )
    return EODRuntimeStack(config, calendar, object(), (provider,), object(), object())


def entry(
    root: Path,
    calendar: VersionedLocalTradingCalendar,
    selected: EODDatasetKey,
    *,
    storage_identity: str = "cn-equity-one",
    enabled: bool = True,
    provider_version: str = "fixture-v1",
    retry_policy: EODProviderRetryPolicy = EODProviderRetryPolicy(),
    rate_limit_policy: EODProviderRateLimitPolicy = EODProviderRateLimitPolicy(),
) -> EODOperationCatalogEntry:
    return EODOperationCatalogEntry(
        dataset=selected,
        enabled=enabled,
        storage_identity=storage_identity,
        runtime=runtime(
            root,
            calendar,
            selected,
            storage_suffix=storage_identity,
            provider_version=provider_version,
            retry_policy=retry_policy,
            rate_limit_policy=rate_limit_policy,
        ),
    )


def assert_catalog_error(code: EODOperationCatalogErrorCode, call) -> None:
    with pytest.raises(EODOperationCatalogError) as captured:
        call()
    assert captured.value.code is code


def test_catalog_orders_datasets_canonically_and_fingerprint_is_deterministic(
    tmp_path: Path,
) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    first = entry(tmp_path, calendar, dataset("600001.SH"), storage_identity="two")
    second = entry(tmp_path, calendar, dataset("600000.SH"), storage_identity="one")

    left = EODOperationCatalog((first, second))
    right = EODOperationCatalog((second, first))

    assert tuple(item.dataset for item in left.entries) == (second.dataset, first.dataset)
    assert left.execution_config_fingerprint == right.execution_config_fingerprint
    assert left.fingerprint_dict() == right.fingerprint_dict()
    assert left.fingerprint_dict()["catalog_schema_version"] == EOD_OPERATION_CATALOG_SCHEMA_VERSION
    assert left.fingerprint_dict()["runtime_contract_version"] == EOD_RUNTIME_CONTRACT_VERSION
    assert left.fingerprint_dict()["calendar_identity"] == calendar.identity.to_dict()


def test_duplicate_dataset_and_storage_identity_fail_closed(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    first = entry(tmp_path, calendar, dataset(), storage_identity="one")
    duplicate_dataset = entry(tmp_path, calendar, dataset(), storage_identity="two")
    duplicate_storage = entry(
        tmp_path,
        calendar,
        dataset("600001.SH"),
        storage_identity="one",
    )

    assert_catalog_error(
        EODOperationCatalogErrorCode.DUPLICATE_DATASET,
        lambda: EODOperationCatalog((first, duplicate_dataset)),
    )
    assert_catalog_error(
        EODOperationCatalogErrorCode.DUPLICATE_STORAGE_IDENTITY,
        lambda: EODOperationCatalog((first, duplicate_storage)),
    )


def test_catalog_enforces_256_entry_limit(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    entries = tuple(
        entry(
            tmp_path,
            calendar,
            dataset(f"{600000 + index:06d}.SH"),
            storage_identity=f"storage-{index}",
        )
        for index in range(MAX_EOD_OPERATION_CATALOG_ENTRIES + 1)
    )

    assert_catalog_error(
        EODOperationCatalogErrorCode.CATALOG_TOO_LARGE,
        lambda: EODOperationCatalog(entries),
    )


def test_unknown_disabled_and_all_disabled_are_distinct(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    selected = dataset()
    catalog = EODOperationCatalog((entry(tmp_path, calendar, selected, enabled=False),))

    assert_catalog_error(
        EODOperationCatalogErrorCode.DATASET_DISABLED,
        lambda: catalog.require_enabled(selected),
    )
    assert_catalog_error(
        EODOperationCatalogErrorCode.DATASET_NOT_IN_CATALOG,
        lambda: catalog.require_enabled(dataset("600001.SH")),
    )
    assert catalog.calendar_identity is None
    assert_catalog_error(
        EODOperationCatalogErrorCode.NO_ENABLED_DATASET, lambda: catalog.execution_context
    )


def test_enabled_must_be_exact_bool(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    valid = entry(tmp_path, calendar, dataset())
    with pytest.raises(TypeError):
        replace(valid, enabled=1)


def test_mixed_enabled_calendar_identity_fails_closed(tmp_path: Path) -> None:
    first_calendar = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="first", version="fixture-v1")
    )
    second_calendar = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="second", version="fixture-v2")
    )
    entries = (
        entry(tmp_path, first_calendar, dataset(), storage_identity="one"),
        entry(
            tmp_path,
            second_calendar,
            dataset("600001.SH"),
            storage_identity="two",
        ),
    )

    assert_catalog_error(
        EODOperationCatalogErrorCode.MIXED_CALENDAR_IDENTITY,
        lambda: EODOperationCatalog(entries),
    )


def test_calendar_identity_is_deterministic_and_changes_with_version_or_coverage(
    tmp_path: Path,
) -> None:
    first = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="first", version="fixture-v1")
    )
    same = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="same", version="fixture-v1")
    )
    changed_version = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="version", version="fixture-v2")
    )
    changed_coverage = VersionedLocalTradingCalendar.from_file(
        write_calendar(tmp_path, name="coverage", coverage_end=DAY_5 + timedelta(days=1))
    )

    assert eod_calendar_identity(first.identity) == eod_calendar_identity(same.identity)
    assert eod_calendar_identity(first.identity) != eod_calendar_identity(changed_version.identity)
    assert eod_calendar_identity(first.identity) != eod_calendar_identity(changed_coverage.identity)
    assert len(eod_calendar_identity(first.identity)) <= 256


@pytest.mark.parametrize(
    "mutation",
    ("enabled", "provider_version", "retry_policy", "rate_limit_policy"),
)
def test_catalog_fingerprint_changes_for_execution_inputs(
    tmp_path: Path,
    mutation: str,
) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    selected = dataset()
    baseline = entry(tmp_path, calendar, selected)
    kwargs = {}
    if mutation == "enabled":
        kwargs["enabled"] = False
    elif mutation == "provider_version":
        kwargs["provider_version"] = "fixture-v2"
    elif mutation == "retry_policy":
        kwargs["retry_policy"] = EODProviderRetryPolicy(max_attempts=2)
    else:
        kwargs["rate_limit_policy"] = EODProviderRateLimitPolicy(1.0)
    changed = entry(tmp_path, calendar, selected, **kwargs)

    assert (
        EODOperationCatalog((baseline,)).execution_config_fingerprint
        != EODOperationCatalog((changed,)).execution_config_fingerprint
    )


def test_fingerprint_is_path_independent_and_has_no_endpoint_field(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first_calendar = VersionedLocalTradingCalendar.from_file(
        write_calendar(first_root, version="fixture-v1")
    )
    second_calendar = VersionedLocalTradingCalendar.from_file(
        write_calendar(second_root, version="fixture-v1")
    )
    first = EODOperationCatalog(
        (entry(first_root, first_calendar, dataset(), storage_identity="stable"),)
    )
    second = EODOperationCatalog(
        (entry(second_root, second_calendar, dataset(), storage_identity="stable"),)
    )

    assert first.execution_config_fingerprint == second.execution_config_fingerprint
    serialized = json.dumps(first.fingerprint_dict(), sort_keys=True)
    assert str(first_root.resolve()) not in serialized
    assert str(second_root.resolve()) not in serialized
    assert "repository_root" not in serialized
    assert "calendar_source" not in serialized
    assert "endpoint" not in serialized
    assert "fixture_endpoint_must_not_enter_fingerprint" not in serialized


def test_catalog_constructor_has_no_runtime_side_effects(tmp_path: Path) -> None:
    calendar = VersionedLocalTradingCalendar.from_file(write_calendar(tmp_path))
    item = entry(tmp_path, calendar, dataset())
    provider = item.runtime.providers[0]
    repository_root = item.runtime.config.repository_root

    catalog = EODOperationCatalog((item,))

    assert catalog.require_enabled(item.dataset) is item
    assert provider.fetch_calls == 0
    assert not repository_root.exists()
    assert tuple(tmp_path.rglob("*.sqlite3")) == ()


def test_builder_constructs_runtime_without_fetch_publish_or_operation_db(tmp_path: Path) -> None:
    selected = dataset()
    calendar_source = write_calendar(tmp_path)
    repository_root = (tmp_path / "repository").resolve()
    config = EODProductionConfig(
        config_schema_version=EOD_PRODUCTION_CONFIG_SCHEMA_VERSION,
        repository_root=repository_root,
        calendar_source=calendar_source.resolve(),
        dataset=selected,
        provider_order=(AKSHARE_EQUITY_PROVIDER,),
    )
    created = []

    def factory(calendar):
        provider = OfflineProvider(selected)
        created.append(provider)
        return provider

    catalog = build_eod_operation_catalog(
        (config,),
        storage_identities={selected: "cn-equity-primary"},
        provider_factories={AKSHARE_EQUITY_PROVIDER: factory},
    )

    assert catalog.require_enabled(selected).runtime.dataset == selected
    assert len(created) == 1 and created[0].fetch_calls == 0
    assert not repository_root.exists()
    assert tuple(tmp_path.rglob("*.sqlite3")) == ()
