"""Offline contract tests for shadow macro validation."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import autowealth.macro.validation as validation_module
from autowealth.macro.validation import (
    MacroObservation,
    adapt_macro_wide_frame,
    validate_macro_observations,
)


def _record(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "indicator": "pmi",
        "observation_date": "2024-01-31",
        "available_date": "2024-02-02",
        "value": 50.8,
        "source": "mock_macro",
        "revision": "initial",
        "unit": "index",
        "frequency": "monthly",
    }
    values.update(overrides)
    return values


def test_valid_record_contract() -> None:
    result = validate_macro_observations([_record()])

    assert result.status == "valid"
    assert result.reason_codes == ("success",)
    assert result.valid_observations == (
        MacroObservation(
            indicator="pmi",
            observation_date="2024-01-31",
            available_date="2024-02-02",
            value=50.8,
            source="mock_macro",
            revision="initial",
            unit="index",
            frequency="monthly",
        ),
    )
    assert result.to_dict()["coverage_ratio"] == 1.0


def test_macro_observation_schema_rejects_missing_publication_date() -> None:
    with pytest.raises(ValueError, match="missing_available_date"):
        MacroObservation(
            indicator="pmi",
            observation_date="2024-01-31",
            available_date=None,  # type: ignore[arg-type]
            value=50.8,
            source="mock_macro",
        )


@pytest.mark.parametrize("signal_date_count", [0, 1, 100, 100_000])
def test_empty_input_preserves_bounded_signal_date_counts(signal_date_count: int) -> None:
    signal_dates = (
        (date(1900, 1, 1) + timedelta(days=index)).isoformat() for index in range(signal_date_count)
    )

    result = validate_macro_observations([], signal_dates=signal_dates)
    diagnostics = result.to_dict()
    pit_summary = diagnostics["pit_summary"]
    serialized = json.dumps(diagnostics, sort_keys=True)

    assert result.status == "empty"
    assert result.reason_codes == ("empty_input",)
    assert diagnostics["raw_row_count"] == 0
    assert diagnostics["valid_row_count"] == 0
    assert diagnostics["rejected_row_count"] == 0
    assert diagnostics["coverage_ratio"] == 0.0
    assert pit_summary["signal_date_count"] == signal_date_count
    assert pit_summary["fully_available_count"] == 0
    assert pit_summary["partially_available_count"] == 0
    assert pit_summary["unavailable_count"] == signal_date_count
    assert pit_summary["reason_counts"] == (
        {"no_pit_eligible_record": signal_date_count} if signal_date_count else {}
    )
    assert len(serialized) < 1_024
    assert "signal_dates" not in serialized
    assert "1900-01-01" not in serialized


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"indicator": None}, "missing_indicator"),
        ({"observation_date": None}, "missing_observation_date"),
        ({"available_date": None}, "missing_available_date"),
        ({"observation_date": "2024/01/31"}, "invalid_observation_date"),
        ({"available_date": "2024/02/02"}, "invalid_available_date"),
        ({"available_date": "2024-01-01"}, "available_before_observation"),
        ({"indicator": "future_placeholder"}, "invalid_schema"),
    ],
)
def test_invalid_record_reasons(overrides: dict[str, object], reason: str) -> None:
    result = validate_macro_observations([_record(**overrides)])

    assert result.status == "invalid"
    assert result.reason_codes == (reason,)
    assert result.to_dict()["rejected_counts"] == {reason: 1}


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_are_rejected(value: float) -> None:
    result = validate_macro_observations([_record(value=value)])

    assert result.status == "invalid"
    assert result.reason_codes == ("non_finite_value",)


def test_duplicate_version_keeps_one_deterministic_record() -> None:
    result = validate_macro_observations([_record(), _record()])

    assert result.status == "partial"
    assert len(result.valid_observations) == 1
    assert result.to_dict()["rejected_counts"] == {"duplicate_version": 1}


def test_ambiguous_duplicate_observation_is_rejected() -> None:
    records = [
        _record(revision=None, value=50.0),
        _record(revision=None, value=51.0, available_date="2024-02-03"),
    ]
    result = validate_macro_observations(records)

    assert result.status == "invalid"
    assert not result.valid_observations
    assert result.to_dict()["rejected_counts"] == {"duplicate_observation": 2}


def test_unique_revisions_are_valid_versions() -> None:
    records = [
        _record(revision="initial", value=50.0),
        _record(revision="revised", value=50.4, available_date="2024-02-10"),
    ]
    result = validate_macro_observations(records)

    assert result.status == "valid"
    assert len(result.valid_observations) == 2
    assert result.to_dict()["indicators"]["pmi"]["version_count"] == 2


def test_unsorted_input_is_diagnostic_only() -> None:
    records = [
        _record(observation_date="2024-02-29", available_date="2024-03-02"),
        _record(observation_date="2024-01-31", available_date="2024-02-02"),
    ]
    result = validate_macro_observations(records)

    assert result.status == "valid"
    assert result.reason_codes == ("unsorted_dates",)
    assert [item.observation_date for item in result.valid_observations] == [
        "2024-01-31",
        "2024-02-29",
    ]


def test_validation_result_is_deterministic_and_json_safe() -> None:
    records = [_record(indicator="cpi_yoy", value=2.1), _record()]

    first = validate_macro_observations(records, signal_dates=["2024-02-05"]).to_dict()
    second = validate_macro_observations(records, signal_dates=["2024-02-05"]).to_dict()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert "generated_at" not in first


def test_wide_frame_adapter_expands_only_catalog_indicators() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": "2024-01-31",
                "available_date": None,
                "pmi": 50.8,
                "cpi_yoy": 2.0,
                "source": "mock_macro",
                "technical_note": 123,
            }
        ]
    )

    records = adapt_macro_wide_frame(frame)
    result = validate_macro_observations(records)

    assert [item["indicator"] for item in records] == ["pmi", "cpi_yoy"]
    assert all(item["available_date"] is None for item in records)
    assert result.to_dict()["rejected_counts"] == {"missing_available_date": 2}


def test_wide_frame_adapter_does_not_modify_input() -> None:
    frame = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-31"),
                "available_date": pd.Timestamp("2024-02-02"),
                "pmi": 50.8,
                "source": "mock_macro",
            }
        ]
    )
    original = frame.copy(deep=True)

    adapt_macro_wide_frame(frame)

    pd.testing.assert_frame_equal(frame, original)


def test_nonempty_wide_frame_without_catalog_indicators_is_invalid() -> None:
    records = adapt_macro_wide_frame(
        pd.DataFrame([{"date": "2024-01-31", "available_date": "2024-02-02", "gdp": 5.0}])
    )

    result = validate_macro_observations(records)

    assert result.status == "invalid"
    assert result.reason_codes == ("invalid_schema",)


def test_pit_future_observation_does_not_invalidate_record() -> None:
    result = validate_macro_observations(
        [_record(observation_date="2024-03-31", available_date="2024-04-02")],
        signal_dates=["2024-03-01"],
    )

    assert result.status == "valid"
    assert result.to_dict()["pit_summary"]["reason_counts"] == {
        "future_observation": 1,
        "no_pit_eligible_record": 1,
    }


def test_pit_future_available_date_does_not_invalidate_record() -> None:
    result = validate_macro_observations(
        [_record(available_date="2024-03-02")],
        signal_dates=["2024-02-15"],
    )

    assert result.status == "valid"
    assert result.to_dict()["pit_summary"]["reason_counts"] == {
        "future_available_date": 1,
        "no_pit_eligible_record": 1,
    }


def test_pit_eligible_record_and_signal_aggregation() -> None:
    records = [
        _record(indicator="pmi"),
        _record(
            indicator="cpi_yoy",
            value=2.1,
            observation_date="2024-02-29",
            available_date="2024-03-02",
        ),
    ]
    result = validate_macro_observations(
        records,
        signal_dates=["2024-02-05", "2024-03-05", "2024-01-15"],
    )

    assert result.status == "valid"
    assert result.to_dict()["pit_summary"] == {
        "signal_date_count": 3,
        "fully_available_count": 1,
        "partially_available_count": 1,
        "unavailable_count": 1,
        "reason_counts": {
            "future_observation": 2,
            "no_pit_eligible_record": 1,
        },
    }


def test_pit_diagnostics_are_bounded_for_100_and_100000_signal_dates() -> None:
    def signal_dates(count: int):
        return ((date(1900, 1, 1) + timedelta(days=index)).isoformat() for index in range(count))

    small = validate_macro_observations([_record()], signal_dates=signal_dates(100)).to_dict()
    large = validate_macro_observations([_record()], signal_dates=signal_dates(100_000)).to_dict()
    small_json = json.dumps(small, sort_keys=True)
    large_json = json.dumps(large, sort_keys=True)

    assert small["pit_summary"]["signal_date_count"] == 100
    assert large["pit_summary"]["signal_date_count"] == 100_000
    assert set(large["pit_summary"]) == {
        "signal_date_count",
        "fully_available_count",
        "partially_available_count",
        "unavailable_count",
        "reason_counts",
    }
    assert "signal_dates" not in large_json
    assert "1900-01-01" not in large_json
    assert abs(len(large_json) - len(small_json)) < 128


def test_validator_exception_is_bounded_and_non_throwing() -> None:
    result = validate_macro_observations([_record()], signal_dates=[object()])

    diagnostics = result.to_dict()
    assert result.status == "invalid"
    assert diagnostics["reason_codes"] == ["invalid_schema"]
    assert diagnostics["exception_type"] == "ValueError"
    assert "traceback" not in json.dumps(diagnostics).lower()


def test_import_has_no_network_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_socket(*args: object, **kwargs: object) -> socket.socket:
        raise AssertionError("network access is forbidden during import")

    monkeypatch.setattr(socket, "socket", fail_socket)
    importlib.reload(validation_module)


def test_top_level_macro_import_has_no_network_client_or_file_write_side_effect() -> None:
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

import autowealth.macro as package

assert package.MacroObservation.__name__ == "MacroObservation"
assert package.validate_macro_observations.__name__ == "validate_macro_observations"
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
