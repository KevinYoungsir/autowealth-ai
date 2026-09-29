from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from itertools import permutations
from pathlib import Path
import subprocess
import sys

import pytest

from autowealth.market_data.capability_registry import (
    EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION,
    EODCapabilityRegistry,
    EODCapabilityRegistryError,
    build_default_eod_capability_registry,
    EODProviderCapabilityDeclaration,
)


def test_default_registry_is_stable_and_contains_only_current_providers() -> None:
    first = build_default_eod_capability_registry()
    second = build_default_eod_capability_registry()
    assert EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION == 1
    assert [item.provider_name for item in first.declarations] == [
        "akshare_eod_equity",
        "akshare_eod_index",
        "akshare_eod_index_daily",
        "tushare_eod_equity",
    ]
    assert first.identity == second.identity
    assert first.to_json() == second.to_json()
    assert "TUSHARE_TOKEN" in json.dumps(first.lookup("tushare_eod_equity").to_dict())
    assert "SENTINEL" not in first.to_json()


def test_registry_rejects_unknown_and_duplicate_provider_identities() -> None:
    registry = build_default_eod_capability_registry()
    with pytest.raises(EODCapabilityRegistryError):
        registry.lookup("unknown_provider")
    with pytest.raises(EODCapabilityRegistryError):
        EODCapabilityRegistry(registry.declarations + (registry.declarations[0],))
    restored = EODCapabilityRegistry.from_json(registry.to_json())
    assert restored.identity == registry.identity
    invalid = registry.to_dict()
    invalid["schema_version"] = 99
    with pytest.raises(EODCapabilityRegistryError):
        EODCapabilityRegistry.from_dict(invalid)


def test_registry_serialization_has_no_runtime_or_path_fields() -> None:
    registry = build_default_eod_capability_registry()
    payload = registry.to_json()
    for forbidden in ("secret", "hostname", "mtime", "PID", "filesystem", "runtime"):
        assert forbidden.casefold() not in payload.casefold()


def test_capability_metadata_keeps_tushare_verified_and_akshare_equity_unverified() -> None:
    registry = build_default_eod_capability_registry()
    assert registry.lookup("tushare_eod_equity").unit_verification == "verified"
    assert registry.lookup("tushare_eod_equity").observation_source_required is True
    assert registry.lookup("tushare_eod_equity").credential_environment_variable == "TUSHARE_TOKEN"
    assert registry.lookup("akshare_eod_equity").unit_verification == "unverified"


def test_every_input_order_and_nested_order_has_same_canonical_identity():
    registry = build_default_eod_capability_registry()
    for order in permutations(registry.declarations):
        changed = [
            replace(d, capabilities=list(reversed(d.capabilities)), venues=list(reversed(d.venues)))
            for d in order
        ]
        actual = EODCapabilityRegistry(changed)
        assert actual.identity == registry.identity
        assert actual.to_json() == registry.to_json()


def test_registry_and_declarations_are_immutable_and_exports_are_detached():
    registry = build_default_eod_capability_registry()
    declaration = registry.declarations[0]
    before = registry.identity
    with pytest.raises(FrozenInstanceError):
        registry._declarations = ()
    with pytest.raises(FrozenInstanceError):
        declaration.unit_verification = "verified"
    with pytest.raises(TypeError):
        registry._by_name[declaration.provider_name] = declaration
    exported = registry.to_dict()
    exported["providers"][0]["capabilities"].clear()
    assert registry.identity == before


@pytest.mark.parametrize("version", [True, False, 1.0, "1", None, 0, 2])
def test_invalid_registry_versions_are_rejected(version):
    payload = build_default_eod_capability_registry().to_dict()
    payload["schema_version"] = version
    with pytest.raises(EODCapabilityRegistryError):
        EODCapabilityRegistry.from_dict(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_name": "unknown_provider"},
        {"provider_version": "2"},
        {"provider_version": "C:/private"},
        {"provider_version": "host.example"},
        {"volume_unit": "lots"},
        {"unit_verification": []},
        {"observation_source_required": 1},
        {"credential_required": 1},
        {"credential_environment_variable": "SENTINEL_SECRET"},
        {"credential_required": False},
        {"capabilities": []},
        {"capabilities": [object()]},
        {"asset_types": ["index"]},
        {"frequencies": ["intraday"]},
    ],
)
def test_invalid_declarations_fail_closed(changes):
    declaration = build_default_eod_capability_registry().lookup("tushare_eod_equity")
    with pytest.raises((EODCapabilityRegistryError, TypeError, ValueError)):
        replace(declaration, **changes)


def test_duplicate_and_ambiguous_capability_rejected():
    from autowealth.market_data.providers import EODRevisionStrategy

    declaration = build_default_eod_capability_registry().declarations[0]
    first = declaration.capabilities[0]
    for extra in (
        first,
        replace(first, revision_strategy=EODRevisionStrategy.FULL_REFRESH_REQUIRED),
    ):
        with pytest.raises(EODCapabilityRegistryError):
            replace(declaration, capabilities=declaration.capabilities + (extra,))


def test_strict_serialization_rejects_unknown_fields_and_duplicate_json_keys():
    declaration = build_default_eod_capability_registry().declarations[0]
    payload = declaration.to_dict()
    payload["capabilities"][0]["secret"] = "SENTINEL_SECRET"
    with pytest.raises(EODCapabilityRegistryError):
        EODProviderCapabilityDeclaration.from_dict(payload)
    with pytest.raises(EODCapabilityRegistryError):
        EODCapabilityRegistry.from_json('{"schema_version":2,"schema_version":1,"providers":[]}')
    for name in ("unknown", None, []):
        with pytest.raises((EODCapabilityRegistryError, TypeError)):
            build_default_eod_capability_registry().get(name)


def test_composition_static_fail_closed_and_legacy_compatibility(tmp_path):
    from autowealth.market_data.composition import EODProductionConfig, EODCompositionError
    from autowealth.market_data.schemas import (
        EODDatasetKey,
        Market,
        Venue,
        AssetType,
        BarFrequency,
        AdjustmentType,
    )

    dataset = EODDatasetKey(
        Market.CN, Venue.SSE, AssetType.EQUITY, "600000.SH", BarFrequency.DAILY, AdjustmentType.NONE
    )

    def config(order, selected=dataset, observation=None, version=2):
        return EODProductionConfig(
            version,
            tmp_path / "repo",
            tmp_path / "calendar.json",
            selected,
            order,
            observation_source=observation,
        )

    with pytest.raises(ValueError):
        config(("unknown",))
    with pytest.raises(ValueError):
        config(("akshare_eod_index",))
    with pytest.raises(ValueError):
        config(
            ("tushare_eod_equity",),
            replace(dataset, adjustment_type=AdjustmentType.QFQ),
            tmp_path / "obs.json",
        )
    with pytest.raises(EODCompositionError) as captured:
        config(("tushare_eod_equity",))
    assert captured.value.code.value == "observation_expectation_required"
    for order in permutations(("tushare_eod_equity", "akshare_eod_equity")):
        with pytest.raises(EODCompositionError) as captured:
            config(order, observation=tmp_path / "obs.json")
        assert captured.value.code.value == "mixed_equity_units_unverified"
    for adjustment in AdjustmentType:
        config(("akshare_eod_equity",), replace(dataset, adjustment_type=adjustment), version=1)
    index = replace(dataset, asset_type=AssetType.INDEX, canonical_symbol="000300.SH")
    config(("akshare_eod_index", "akshare_eod_index_daily"), index, version=1)
    config(("tushare_eod_equity",), observation=tmp_path / "obs.json")


def test_adapters_use_the_same_capabilities_and_keep_index_units_unverified():
    from datetime import date
    from autowealth.market_data.akshare_adapters import (
        AKShareEODEquityProvider,
        AKShareEODIndexProvider,
        AKShareEODIndexDailyProvider,
    )
    from autowealth.market_data.tushare_adapters import TushareEODEquityProvider

    class StaticTradingCalendar:
        def is_trading_day(self, value):
            return value == date(2024, 1, 2)

        def next_trading_day(self, value):
            return date(2024, 1, 2)

        def previous_trading_day(self, value):
            return date(2024, 1, 2)

        def trading_days(self, start_date, end_date):
            return [date(2024, 1, 2)] if start_date <= date(2024, 1, 2) <= end_date else []

    DAY_1 = date(2024, 1, 2)

    registry = build_default_eod_capability_registry()
    for cls in (
        AKShareEODEquityProvider,
        AKShareEODIndexProvider,
        AKShareEODIndexDailyProvider,
        TushareEODEquityProvider,
    ):
        provider = cls(StaticTradingCalendar())
        declaration = registry.lookup(provider.provider_name)
        assert provider.capabilities == declaration.capabilities
        assert provider.provider_version == declaration.provider_version
        if "index" in provider.provider_name:
            assert declaration.unit_contract == {
                "volume": "source_value",
                "amount": "source_value",
                "verification": "unverified",
            }


def test_import_construction_lookup_parse_and_catalog_have_no_side_effects(tmp_path):
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from test_eod_tushare_composition import write_files, config_payload

    path = write_files(tmp_path, config_payload(["tushare_eod_equity"]))
    script = r"""
import autowealth
import sys, os, socket, importlib.abc
from pathlib import Path
assert "autowealth.market_data.capability_registry" not in sys.modules
def blocked(*args, **kwargs):
    raise AssertionError("forbidden external side effect")
class BlockSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in ("tushare", "akshare"):
            blocked()
sys.meta_path.insert(0, BlockSDK())
original_getitem = type(os.environ).__getitem__
def guarded_getitem(self, key):
    if key == "TUSHARE_TOKEN":
        raise AssertionError("TUSHARE_TOKEN_VALUE_READ")
    return original_getitem(self, key)
type(os.environ).__getitem__ = guarded_getitem
socket.create_connection = blocked
socket.socket.connect = blocked
socket.socket.connect_ex = blocked
original_scandir = os.scandir
os.scandir = blocked
from autowealth.market_data.capability_registry import build_default_eod_capability_registry
r = build_default_eod_capability_registry()
r.lookup("tushare_eod_equity").to_json()
assert r.identity == build_default_eod_capability_registry().identity
os.scandir = original_scandir
from autowealth.market_data.composition import load_eod_production_config
from autowealth.market_data.operation_catalog import build_eod_operation_catalog
from autowealth.market_data.repositories import LocalEODFileRepository
from autowealth.market_data.tushare_adapters import TushareEODEquityProvider
from autowealth.market_data.akshare_adapters import AKShareEODEquityProvider
LocalEODFileRepository.load_current = blocked
TushareEODEquityProvider.fetch = blocked
AKShareEODEquityProvider.fetch = blocked
config = load_eod_production_config(Path(sys.argv[1]))
catalog = build_eod_operation_catalog((config,), storage_identities={config.dataset: "equity-fixture"})
payload = catalog.fingerprint_dict()
assert "TUSHARE_TOKEN" not in str(payload)
assert "tushare" not in sys.modules and "akshare" not in sys.modules
assert not config.repository_root.exists()
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(path)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
