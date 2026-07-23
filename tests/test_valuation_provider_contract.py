"""Offline tests for the historical valuation provider contract."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Mapping

import pytest

import autowealth.data.valuation_provider as provider_module
from autowealth.data.valuation_provider import (
    HistoricalValuationProvider,
    JsonValue,
    VALUATION_DIAGNOSTICS_MAX_JSON_BYTES,
    ValuationDiagnostics,
    ValuationProviderResult,
)
from autowealth.data.valuation_schema import (
    VALUATION_REASON_CODES,
    VALUATION_STATUS_REASON_CODES,
    ValuationAvailability,
    ValuationMetric,
    ValuationRecord,
)

REQUEST_CONTEXT = {
    "requested_symbol": "600519",
    "requested_metrics": [ValuationMetric.PE_TTM],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "as_of_date": "2024-02-05",
    "source": "fake_valuation",
}


def _valuation_record(**overrides: object) -> ValuationRecord:
    values: dict[str, object] = {
        "symbol": "600519",
        "metric": ValuationMetric.PE_TTM,
        "observation_date": "2024-01-31",
        "available_date": "2024-02-02",
        "value": 25.4,
        "source": "fake_valuation",
        "unit": "multiple",
        "revision": "initial",
    }
    values.update(overrides)
    return ValuationRecord(**values)  # type: ignore[arg-type]


class FakeHistoricalValuationProvider:
    def __init__(self, records: tuple[ValuationRecord, ...] = ()) -> None:
        self.records = records
        self.calls: list[dict[str, object]] = []

    def provider_symbol(self, canonical_symbol: str) -> str:
        return f"{canonical_symbol}.SH"

    def supports_metric(self, metric: ValuationMetric) -> bool:
        return metric in {ValuationMetric.PE_TTM, ValuationMetric.PB}

    def fetch_historical_valuation(
        self,
        symbol: str,
        metric: ValuationMetric,
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> ValuationProviderResult:
        self.calls.append(
            {
                "symbol": symbol,
                "metric": metric,
                "start_date": start_date,
                "end_date": end_date,
                "as_of_date": as_of_date,
            }
        )
        if not self.supports_metric(metric):
            return ValuationProviderResult.unavailable(
                requested_symbol=symbol,
                requested_metrics=[metric],
                start_date=start_date,
                end_date=end_date,
                as_of_date=as_of_date,
                source="fake_valuation",
                reason_code="unsupported_metric",
                provider_symbol=self.provider_symbol(symbol),
                source_metadata=self.source_metadata(),
            )
        return ValuationProviderResult.from_records(
            [item for item in self.records if item.symbol == symbol and item.metric == metric],
            requested_symbol=symbol,
            requested_metrics=[metric],
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            source="fake_valuation",
            provider_symbol=self.provider_symbol(symbol),
            source_metadata=self.source_metadata(),
        )

    def source_metadata(self) -> Mapping[str, JsonValue]:
        return {"provider": "fake_valuation", "network": False}


def test_protocol_runtime_compatibility() -> None:
    provider = FakeHistoricalValuationProvider()

    assert isinstance(provider, HistoricalValuationProvider)


def test_protocol_keyword_argument_compatibility() -> None:
    provider = FakeHistoricalValuationProvider((_valuation_record(),))

    result = provider.fetch_historical_valuation(
        symbol="600519",
        metric=ValuationMetric.PE_TTM,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        as_of_date=date(2024, 2, 5),
    )

    assert result.availability.status == "available"
    assert provider.calls[0]["symbol"] == "600519"


@pytest.mark.parametrize("symbol", ["600519", "000001", "300750"])
def test_record_accepts_only_six_digit_canonical_input(symbol: str) -> None:
    assert _valuation_record(symbol=symbol).symbol == symbol


@pytest.mark.parametrize(
    "symbol",
    [
        "SH600519",
        "sh600519",
        "600519.SH",
        "600519.sh",
        "SZ000001",
        "sz000001",
        "000001.SZ",
        "600519SH",
        "sh.600519",
        "600519-XSHG",
    ],
)
def test_record_rejects_provider_symbol_formats(symbol: str) -> None:
    with pytest.raises(ValueError, match="canonical six-digit"):
        _valuation_record(symbol=symbol)


@pytest.mark.parametrize(
    "symbol",
    ["", "12345", "1234567", " 600519 ", "60051A", "600 519"],
)
def test_record_rejects_malformed_or_trimmed_symbols(symbol: str) -> None:
    with pytest.raises(ValueError, match="canonical six-digit"):
        _valuation_record(symbol=symbol)


def test_provider_symbol_conversion_is_confined_to_provider_adapter() -> None:
    provider = FakeHistoricalValuationProvider()

    assert provider.provider_symbol("600519") == "600519.SH"
    with pytest.raises(ValueError, match="canonical six-digit"):
        _valuation_record(symbol=provider.provider_symbol("600519"))


def test_metric_catalog_is_stable() -> None:
    assert [item.value for item in ValuationMetric] == [
        "pe_ttm",
        "pb",
        "ps_ttm",
        "dividend_yield",
        "market_cap",
    ]


def _availability_for(status: str, reason_code: str) -> ValuationAvailability:
    requested = (ValuationMetric.PE_TTM, ValuationMetric.PB)
    if status == "available":
        available = requested
        missing = ()
    elif status == "partial":
        available = (ValuationMetric.PE_TTM,)
        missing = (ValuationMetric.PB,)
    else:
        available = ()
        missing = requested
    return ValuationAvailability(
        status=status,
        reason_code=reason_code,
        requested_metrics=requested,
        available_metrics=available,
        missing_metrics=missing,
        as_of_date="2024-02-05",
        source="fake_valuation",
    )


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (status, reason_code)
        for status, reason_codes in VALUATION_STATUS_REASON_CODES.items()
        for reason_code in reason_codes
    ],
)
def test_allowed_availability_status_reason_matrix(
    status: str,
    reason_code: str,
) -> None:
    availability = _availability_for(status, reason_code)

    assert availability.status == status
    assert availability.reason_code == reason_code


@pytest.mark.parametrize(
    ("status", "reason_code"),
    [
        (status, reason_code)
        for status in VALUATION_STATUS_REASON_CODES
        for reason_code in VALUATION_REASON_CODES
        if reason_code not in VALUATION_STATUS_REASON_CODES[status]
    ],
)
def test_forbidden_availability_status_reason_matrix(
    status: str,
    reason_code: str,
) -> None:
    with pytest.raises(ValueError, match="invalid for valuation status"):
        _availability_for(status, reason_code)


def test_availability_metric_sets_are_deduplicated_and_stably_sorted() -> None:
    availability = ValuationAvailability(
        status="available",
        reason_code="success",
        requested_metrics=(
            ValuationMetric.PE_TTM,
            ValuationMetric.PB,
            ValuationMetric.PE_TTM,
        ),
        available_metrics=(
            ValuationMetric.PE_TTM,
            ValuationMetric.PB,
            ValuationMetric.PB,
        ),
        missing_metrics=(),
        as_of_date="2024-02-05",
        source="fake_valuation",
    )

    assert availability.requested_metrics == (ValuationMetric.PB, ValuationMetric.PE_TTM)
    assert availability.available_metrics == (ValuationMetric.PB, ValuationMetric.PE_TTM)


@pytest.mark.parametrize(
    ("requested", "available", "missing", "message"),
    [
        ((), (), (), "cannot be empty"),
        (
            (ValuationMetric.PE_TTM,),
            (ValuationMetric.PB,),
            (),
            "subsets",
        ),
        (
            (ValuationMetric.PE_TTM, ValuationMetric.PB),
            (ValuationMetric.PE_TTM,),
            (ValuationMetric.PE_TTM, ValuationMetric.PB),
            "overlap",
        ),
        (
            (ValuationMetric.PE_TTM, ValuationMetric.PB),
            (ValuationMetric.PE_TTM,),
            (),
            "partition",
        ),
    ],
)
def test_availability_rejects_invalid_metric_partitions(
    requested: tuple[ValuationMetric, ...],
    available: tuple[ValuationMetric, ...],
    missing: tuple[ValuationMetric, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ValuationAvailability(
            status="available",
            reason_code="success",
            requested_metrics=requested,
            available_metrics=available,
            missing_metrics=missing,
            as_of_date="2024-02-05",
            source="fake_valuation",
        )


def test_fake_provider_valid_result() -> None:
    record = _valuation_record()
    result = FakeHistoricalValuationProvider((record,)).fetch_historical_valuation(
        "600519",
        ValuationMetric.PE_TTM,
        date(2024, 1, 1),
        date(2024, 12, 31),
        date(2024, 2, 5),
    )

    assert result.records == (record,)
    assert result.availability.reason_code == "success"
    assert result.diagnostics["coverage_ratio"] == 1.0
    assert result.diagnostics["requested_symbol"] == "600519"
    assert result.diagnostics["provider_symbol"] == "600519.SH"
    assert result.diagnostics["accepted_row_count"] == 1


def test_unsupported_metric_is_explicitly_unavailable() -> None:
    result = FakeHistoricalValuationProvider().fetch_historical_valuation(
        "600519",
        ValuationMetric.MARKET_CAP,
        date(2024, 1, 1),
        date(2024, 12, 31),
        date(2024, 2, 5),
    )

    assert result.availability.status == "unavailable"
    assert result.availability.reason_code == "unsupported_metric"


def test_empty_response_is_explicitly_unavailable() -> None:
    result = ValuationProviderResult.from_records(
        [],
        **REQUEST_CONTEXT,
    )

    assert result.availability.status == "unavailable"
    assert result.availability.reason_code == "empty_response"


def test_missing_available_date_is_rejected() -> None:
    with pytest.raises(ValueError, match="available_date is required"):
        _valuation_record(available_date=None)


def test_available_before_observation_is_rejected() -> None:
    with pytest.raises(ValueError, match="cannot be before"):
        _valuation_record(available_date="2024-01-01")


def test_available_after_as_of_date_is_not_pit_eligible() -> None:
    result = ValuationProviderResult.from_records(
        [_valuation_record(available_date="2024-03-01")],
        **REQUEST_CONTEXT,
    )

    assert result.records == ()
    assert result.availability.reason_code == "future_available_date"
    assert result.diagnostics["reason_counts"] == {"future_available_date": 1}
    assert result.diagnostics["accepted_row_count"] == 0
    assert result.diagnostics["rejected_row_count"] == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_valuation_value_is_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        _valuation_record(value=value)


def test_partial_metrics_are_explicit_and_sorted() -> None:
    result = ValuationProviderResult.from_records(
        [_valuation_record(metric=ValuationMetric.PE_TTM)],
        requested_symbol="600519",
        requested_metrics=[ValuationMetric.PE_TTM, ValuationMetric.PB],
        start_date="2024-01-01",
        end_date="2024-12-31",
        as_of_date="2024-02-05",
        source="fake_valuation",
    )

    assert result.availability.status == "partial"
    assert result.availability.reason_code == "historical_valuation_unavailable"
    assert result.availability.to_dict()["requested_metrics"] == ["pb", "pe_ttm"]
    assert result.availability.to_dict()["missing_metrics"] == ["pb"]


def test_explicit_unavailable_and_invalid_contracts() -> None:
    unavailable = ValuationProviderResult.unavailable(
        **REQUEST_CONTEXT,
        reason_code="historical_valuation_unavailable",
    )
    invalid = ValuationProviderResult.invalid(
        **REQUEST_CONTEXT,
        reason_code="invalid_schema",
    )

    assert unavailable.availability.status == "unavailable"
    assert invalid.availability.status == "invalid"


def test_no_provider_configured_contract() -> None:
    result = ValuationProviderResult.unavailable(
        **{**REQUEST_CONTEXT, "source": "valuation_contract"},
        reason_code="provider_not_configured",
    )

    assert result.availability.reason_code == "provider_not_configured"
    assert result.records == ()


def test_requires_explicit_historical_dates() -> None:
    with pytest.raises(TypeError):
        ValuationRecord(  # type: ignore[call-arg]
            symbol="600519",
            metric=ValuationMetric.PE_TTM,
            value=25.4,
            source="fake_valuation",
            unit="multiple",
        )


@pytest.mark.parametrize("missing_field", ["observation_date", "available_date"])
def test_rejects_missing_observation_or_available_dates(missing_field: str) -> None:
    with pytest.raises((TypeError, ValueError)):
        _valuation_record(**{missing_field: None})


def test_available_and_partial_factories_share_result_invariants() -> None:
    available = ValuationProviderResult.available([_valuation_record()], **REQUEST_CONTEXT)
    partial = ValuationProviderResult.partial(
        [_valuation_record()],
        **{
            **REQUEST_CONTEXT,
            "requested_metrics": [ValuationMetric.PE_TTM, ValuationMetric.PB],
        },
    )

    assert available.availability.status == "available"
    assert partial.availability.status == "partial"
    with pytest.raises(ValueError, match="complete requested metric coverage"):
        ValuationProviderResult.available(
            [_valuation_record()],
            **{
                **REQUEST_CONTEXT,
                "requested_metrics": [ValuationMetric.PE_TTM, ValuationMetric.PB],
            },
        )
    with pytest.raises(ValueError, match="partial requested metric coverage"):
        ValuationProviderResult.partial([_valuation_record()], **REQUEST_CONTEXT)


@pytest.mark.parametrize(
    ("factory", "reason_code"),
    [
        (ValuationProviderResult.unavailable, "invalid_schema"),
        (ValuationProviderResult.invalid, "provider_not_configured"),
        (ValuationProviderResult.invalid, "empty_response"),
        (ValuationProviderResult.invalid, "historical_valuation_unavailable"),
    ],
)
def test_factories_cannot_bypass_status_reason_invariants(factory, reason_code: str) -> None:
    with pytest.raises(ValueError, match="invalid for valuation status"):
        factory(**REQUEST_CONTEXT, reason_code=reason_code)


def test_direct_result_requires_records_for_available_status() -> None:
    valid = ValuationProviderResult.available([_valuation_record()], **REQUEST_CONTEXT)

    with pytest.raises(ValueError, match="accepted_row_count"):
        ValuationProviderResult((), valid.availability, valid.diagnostics)


@pytest.mark.parametrize(
    ("records", "message"),
    [
        ([_valuation_record(symbol="000001")], "requested_symbol"),
        ([_valuation_record(observation_date="2023-12-31")], "outside the requested window"),
        (
            [
                _valuation_record(
                    observation_date="2025-01-01",
                    available_date="2025-01-02",
                )
            ],
            "outside the requested window",
        ),
        ([_valuation_record(metric=ValuationMetric.PB)], "outside requested_metrics"),
    ],
)
def test_from_records_validates_requested_symbol_metrics_and_window(
    records: list[ValuationRecord],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        ValuationProviderResult.from_records(records, **REQUEST_CONTEXT)


def test_from_records_rejects_invalid_request_window() -> None:
    with pytest.raises(ValueError, match="start_date cannot be after end_date"):
        ValuationProviderResult.from_records(
            [],
            **{
                **REQUEST_CONTEXT,
                "start_date": "2024-12-31",
                "end_date": "2024-01-01",
            },
        )


def test_requested_available_and_missing_metrics_have_stable_order() -> None:
    result = ValuationProviderResult.from_records(
        [_valuation_record(metric=ValuationMetric.PE_TTM)],
        **{
            **REQUEST_CONTEXT,
            "requested_metrics": [
                ValuationMetric.PE_TTM,
                ValuationMetric.PB,
                ValuationMetric.PE_TTM,
                ValuationMetric.DIVIDEND_YIELD,
            ],
        },
    )

    assert result.availability.to_dict()["requested_metrics"] == [
        "dividend_yield",
        "pb",
        "pe_ttm",
    ]
    assert result.availability.to_dict()["available_metrics"] == ["pe_ttm"]
    assert result.availability.to_dict()["missing_metrics"] == ["dividend_yield", "pb"]


def test_diagnostics_are_deterministic_and_do_not_include_records() -> None:
    arguments = {
        "records": [_valuation_record()],
        **REQUEST_CONTEXT,
        "requested_metrics": [ValuationMetric.PE_TTM, ValuationMetric.PB],
        "provider_symbol": "600519.SH",
        "source_metadata": {"endpoint": "historical_valuation", "network": False},
    }

    first = ValuationProviderResult.from_records(**arguments).to_dict()
    second = ValuationProviderResult.from_records(**arguments).to_dict()

    assert json.dumps(first["diagnostics"], sort_keys=True) == json.dumps(
        second["diagnostics"], sort_keys=True
    )
    assert "records" not in first["diagnostics"]
    assert "raw_response" not in first["diagnostics"]
    assert "generated_at" not in first["diagnostics"]
    assert set(first["diagnostics"]) == {
        "schema_version",
        "provider",
        "requested_symbol",
        "provider_symbol",
        "requested_metrics",
        "requested_start_date",
        "requested_end_date",
        "as_of_date",
        "status",
        "available_metrics",
        "missing_metrics",
        "row_count",
        "accepted_row_count",
        "rejected_row_count",
        "coverage_ratio",
        "reason_codes",
        "reason_counts",
        "source_metadata",
    }


def _unavailable_with_metadata(metadata: Mapping[str, object]) -> ValuationProviderResult:
    return ValuationProviderResult.unavailable(
        **REQUEST_CONTEXT,
        reason_code="empty_response",
        source_metadata=metadata,
    )


@pytest.mark.parametrize(
    "key",
    [
        "apiKey",
        "apiToken",
        "accessToken",
        "refreshToken",
        "clientSecret",
        "openaiApiKey",
        "authorization",
        "proxyAuthorization",
        "cookie",
        "setCookie",
        "password",
        "passwd",
        "bearerToken",
        "secret",
        "client_secret",
        "api_key",
        "access_token",
    ],
)
def test_diagnostics_reject_sensitive_keys_after_name_normalization(key: str) -> None:
    with pytest.raises(ValueError, match="credentials"):
        _unavailable_with_metadata({key: "redacted"})


@pytest.mark.parametrize(
    "key",
    [
        "token_count",
        "authorization_status",
        "cookie_policy",
        "secret_rotation_status",
        "password_policy",
        "api_key_status",
        "token_usage",
    ],
)
def test_diagnostics_allow_noncredential_status_and_count_keys(key: str) -> None:
    result = _unavailable_with_metadata({key: "healthy"})

    assert result.diagnostics["source_metadata"][key] == "healthy"


@pytest.mark.parametrize(
    "value",
    [
        "Bearer abc123",
        "Authorization: abc123",
        "Cookie: session=abc",
        "apiKey=abc123",
        "apiToken: abc123",
        "accessToken=abc123",
        "clientSecret=abc123",
        "https://name:password@example.com/path",
    ],
)
def test_diagnostics_reject_sensitive_values(value: str) -> None:
    with pytest.raises(ValueError, match="credentials"):
        _unavailable_with_metadata({"detail": value})


@pytest.mark.parametrize(
    "value",
    [
        "failed(/tmp/private.json)",
        "error: /home/user/private.csv",
        "failed,/tmp/private.json",
        "error;/home/user/private.csv",
        "message|/var/data/x.json",
        r"C:\Users\name\secret.txt",
        r"failed(C:\Users\name\secret.txt)",
        r"failed,C:\Users\name\secret.txt",
        "error;D:/private/data.csv",
        r"message|E:\temp\x.json",
        r"\\server\share\secret.txt",
        r'failed("\\server\share\secret.txt")',
        r"failed,\\server\share\secret.txt",
        r'error;"\\server\share\private.csv"',
    ],
)
def test_diagnostics_reject_embedded_absolute_paths(value: str) -> None:
    with pytest.raises(ValueError, match="absolute paths"):
        _unavailable_with_metadata({"detail": value})


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/path",
        "http://example.com/a/b",
        "warnings.json",
        "warnings.json#/structured_warnings/0",
        "docs/macro-valuation-contract.md",
        "autowealth/data/valuation_schema.py",
        "pe_ttm/pb",
    ],
)
def test_diagnostics_allow_urls_and_relative_references(value: str) -> None:
    result = _unavailable_with_metadata({"reference": value})

    assert result.diagnostics["source_metadata"]["reference"] == value


@pytest.mark.parametrize(
    "key",
    [
        "raw_response",
        "responseBody",
        "provider-response",
        "payload",
        "records",
        "rows",
        "rawRecords",
        "traceback",
        "requestHeaders",
        "response.headers",
    ],
)
def test_diagnostics_reject_raw_payload_fields(key: str) -> None:
    with pytest.raises(ValueError, match="raw provider payloads"):
        _unavailable_with_metadata({key: []})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_diagnostics_reject_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="non-finite"):
        _unavailable_with_metadata({"coverage": value})


def test_diagnostics_reject_excessive_list_mapping_depth_and_string() -> None:
    with pytest.raises(ValueError, match="32-item"):
        _unavailable_with_metadata({"items": list(range(33))})
    with pytest.raises(ValueError, match="32-key"):
        _unavailable_with_metadata({f"key_{index}": index for index in range(33)})
    with pytest.raises(ValueError, match="nesting depth"):
        _unavailable_with_metadata({"a": {"b": {"c": {"d": "value"}}}})
    with pytest.raises(ValueError, match="512-character"):
        _unavailable_with_metadata({"detail": "x" * 513})


def test_diagnostics_reject_total_json_larger_than_16_kib() -> None:
    metadata = {
        f"key_{index}": [f"value-{item}-" + ("x" * 100) for item in range(32)]
        for index in range(32)
    }

    with pytest.raises(ValueError, match="16 KiB"):
        _unavailable_with_metadata(metadata)


def test_diagnostics_exception_summary_never_copies_exception_text() -> None:
    result = ValuationProviderResult.unavailable(
        **REQUEST_CONTEXT,
        reason_code="provider_exception",
        exception=RuntimeError(r"Bearer abc123 failed(C:\Users\name\private.csv)"),
    )
    diagnostics = result.diagnostics
    serialized = json.dumps(diagnostics, ensure_ascii=False)

    assert diagnostics["exception_type"] == "RuntimeError"
    assert diagnostics["safe_summary"] == (
        "valuation provider exception details were omitted for safe diagnostics"
    )
    assert "traceback" not in serialized.lower()
    assert "abc123" not in serialized
    assert "private.csv" not in serialized


def test_diagnostics_mapping_constructor_rejects_unknown_top_level_fields() -> None:
    base = _unavailable_with_metadata({})
    diagnostics = dict(base.diagnostics)
    diagnostics["unexpected"] = "value"

    with pytest.raises(ValueError, match="unsupported valuation diagnostics fields"):
        ValuationProviderResult((), base.availability, diagnostics)


def test_diagnostics_schema_has_a_bounded_serialized_form() -> None:
    result = _unavailable_with_metadata(
        {
            "provider_version": "fixture-v1",
            "capabilities": ["historical", "point_in_time"],
        }
    )
    encoded = json.dumps(result.diagnostics, ensure_ascii=False).encode("utf-8")

    assert len(encoded) <= VALUATION_DIAGNOSTICS_MAX_JSON_BYTES
    assert ValuationDiagnostics.from_mapping(result.diagnostics).to_dict() == result.diagnostics


def test_import_has_no_network_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden during import")

    monkeypatch.setattr(socket, "socket", fail_socket)
    importlib.reload(provider_module)


def test_top_level_data_import_has_no_network_client_or_file_write_side_effect() -> None:
    script = r"""
import builtins
import os
import socket
import sys

original_import = builtins.__import__
original_open = builtins.open
original_os_open = os.open
blocked_modules = {"akshare", "tushare", "pyarrow", "requests", "httpx", "aiohttp", "yfinance"}

def guarded_import(name, *args, **kwargs):
    root = name.split(".", 1)[0]
    if root in blocked_modules:
        raise AssertionError(f"blocked network or optional data client import: {name}")
    return original_import(name, *args, **kwargs)

def guarded_open(file, mode="r", *args, **kwargs):
    if any(flag in mode for flag in "wax+"):
        raise AssertionError(f"write attempted during package import: {file}")
    return original_open(file, mode, *args, **kwargs)

def guarded_os_open(path, flags, *args, **kwargs):
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    if flags & write_flags:
        raise AssertionError(f"os.open write attempted during package import: {path}")
    return original_os_open(path, flags, *args, **kwargs)

def fail_network(*args, **kwargs):
    raise AssertionError("network access is forbidden during package import")

builtins.open = guarded_open
os.open = guarded_os_open
socket.socket.connect = fail_network
socket.socket.connect_ex = fail_network
socket.create_connection = fail_network
socket.getaddrinfo = fail_network

import autowealth

baseline_modules = set(sys.modules)
builtins.__import__ = guarded_import

import autowealth.data as package

assert package.ValuationRecord.__name__ == "ValuationRecord"
assert package.ValuationProviderResult.__name__ == "ValuationProviderResult"
new_module_roots = {name.split(".", 1)[0] for name in set(sys.modules) - baseline_modules}
assert not blocked_modules.intersection(new_module_roots)
"""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
