from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from autowealth.market_data.composition import (
    AKSHARE_EQUITY_PROVIDER,
    EODCompositionError,
    EODCompositionErrorCode,
    TUSHARE_EQUITY_PROVIDER,
    build_eod_runtime,
    load_eod_production_config,
)
from autowealth.market_data.local_calendar import EOD_CALENDAR_SCHEMA_VERSION
from autowealth.market_data.operation_catalog import build_eod_operation_catalog

ROOT = Path(__file__).resolve().parents[1]


def calendar_payload() -> dict[str, object]:
    return {
        "schema_version": EOD_CALENDAR_SCHEMA_VERSION,
        "calendar_id": "cn_a_share_test_fixture",
        "calendar_version": "fixture-v1",
        "timezone": "Asia/Shanghai",
        "coverage_start": "2024-01-01",
        "coverage_end": "2024-01-03",
        "days": [
            {"trade_date": "2024-01-01", "is_trading_day": False},
            {"trade_date": "2024-01-02", "is_trading_day": True},
            {"trade_date": "2024-01-03", "is_trading_day": True},
        ],
    }


def config_payload(provider_order: list[str]) -> dict[str, object]:
    return {
        "config_schema_version": 2,
        "repository_root": "repository",
        "calendar_source": "calendar.json",
        "dataset": {
            "market": "CN",
            "venue": "SSE",
            "asset_type": "equity",
            "canonical_symbol": "600000.SH",
            "frequency": "1d",
            "adjustment_type": "none",
        },
        "provider_order": provider_order,
        "retry_policy": {
            "max_attempts": 1,
            "initial_backoff_seconds": 1.0,
            "backoff_multiplier": 2.0,
            "max_backoff_seconds": 5.0,
        },
        "rate_limit_policy": {"minimum_interval_seconds": 0.0},
    }


def write_files(tmp_path: Path, payload: dict[str, object]) -> Path:
    calendar_path = (tmp_path / "calendar.json").resolve()
    calendar_path.write_text(json.dumps(calendar_payload()), encoding="utf-8")
    selected = dict(payload)
    selected["repository_root"] = str((tmp_path / "repository").resolve())
    selected["calendar_source"] = str(calendar_path)
    path = tmp_path / "production.yaml"
    path.write_text(yaml.safe_dump(selected, sort_keys=False), encoding="utf-8")
    return path


def test_tushare_config_constructs_without_token_read_or_sdk_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_files(tmp_path, config_payload([TUSHARE_EQUITY_PROVIDER]))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    before = dict(os.environ)
    config = load_eod_production_config(path)
    runtime = build_eod_runtime(config)
    assert runtime.provider_order == (TUSHARE_EQUITY_PROVIDER,)
    assert runtime.providers[0].provider_version == "1"
    assert runtime.providers[0].endpoint_name == "daily"
    assert "tushare" not in sys.modules
    assert dict(os.environ) == before
    assert not config.repository_root.exists()


def test_mixed_tushare_akshare_equity_chain_fails_closed(tmp_path: Path) -> None:
    path = write_files(
        tmp_path,
        config_payload([TUSHARE_EQUITY_PROVIDER, AKSHARE_EQUITY_PROVIDER]),
    )
    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(path)
    assert captured.value.code is EODCompositionErrorCode.MIXED_EQUITY_UNITS_UNVERIFIED
    assert captured.value.to_dict() == {
        "code": "mixed_equity_units_unverified",
        "message": "The configured equity provider chain has incompatible unverified units.",
    }


@pytest.mark.parametrize("field", ["token", "api_key", "secret"])
def test_config_rejects_credential_fields(tmp_path: Path, field: str) -> None:
    payload = config_payload([TUSHARE_EQUITY_PROVIDER])
    payload[field] = "SENTINEL_TUSHARE_SECRET"
    with pytest.raises(EODCompositionError) as captured:
        load_eod_production_config(write_files(tmp_path, payload))
    assert captured.value.code is EODCompositionErrorCode.INVALID_CONFIG
    assert "SENTINEL_TUSHARE_SECRET" not in json.dumps(captured.value.to_dict())


def test_tushare_identity_enters_existing_catalog_fingerprint_without_secret(
    tmp_path: Path,
) -> None:
    config = load_eod_production_config(
        write_files(tmp_path, config_payload([TUSHARE_EQUITY_PROVIDER]))
    )
    catalog = build_eod_operation_catalog(
        (config,),
        storage_identities={config.dataset: "cn-sse-equity-600000-none"},
    )
    payload = catalog.fingerprint_dict()
    assert payload["datasets"][0]["providers"] == [
        {"provider_name": "tushare_eod_equity", "provider_version": "1"}
    ]
    serialized = json.dumps(payload, sort_keys=True)
    assert "TUSHARE_TOKEN" not in serialized
    assert "SENTINEL_TUSHARE_SECRET" not in serialized


def test_example_config_is_tushare_equity_without_credentials() -> None:
    example = ROOT / "configs/eod_production.example.yaml"
    text = example.read_text(encoding="utf-8")
    parsed = load_eod_production_config(example)
    assert parsed.dataset.canonical_symbol == "600000.SH"
    assert parsed.provider_order == (TUSHARE_EQUITY_PROVIDER,)
    assert "api_key" not in text.casefold()
    assert "token:" not in text.casefold()


def test_import_parse_and_construction_do_not_load_tushare_sdk(tmp_path: Path) -> None:
    config_path = write_files(tmp_path, config_payload([TUSHARE_EQUITY_PROVIDER]))
    script = """
import os
import sys
from pathlib import Path
from autowealth.market_data.composition import build_eod_runtime, load_eod_production_config
before = dict(os.environ)
runtime = build_eod_runtime(load_eod_production_config(Path(sys.argv[1])))
assert runtime.provider_order == ("tushare_eod_equity",)
assert "tushare" not in sys.modules
assert dict(os.environ) == before
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
