from datetime import date
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

import pytest

from autowealth.market_data.quality_evidence import (
    FAIL,
    PASS,
    DataQualityEvidence,
    generate_quality_evidence,
)
from autowealth.market_data.local_observation import VersionedLocalObservationExpectation
from autowealth.market_data.observation import StrictTradingDayObservationExpectation
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    Market,
    Venue,
)

RANGE_START = date(2026, 1, 5)
RANGE_END = date(2026, 1, 7)
DATES = (RANGE_START, date(2026, 1, 6), RANGE_END)
FINGERPRINT = "sha256:" + "a" * 64
DATASET = EODDatasetKey(
    Market.CN,
    Venue.SSE,
    AssetType.EQUITY,
    "600000.SH",
    BarFrequency.DAILY,
    AdjustmentType.NONE,
)


class StaticCalendar:
    def __init__(self, days):
        self.days = tuple(days)

    def is_trading_day(self, value):
        return value in self.days

    def next_trading_day(self, value):
        return self.days[self.days.index(value) + 1]

    def previous_trading_day(self, value):
        return self.days[self.days.index(value) - 1]

    def trading_days(self, start_date, end_date):
        return tuple(value for value in self.days if start_date <= value <= end_date)


class ConfirmedAbsenceExpectation:
    def __init__(self, dataset, absent):
        self.dataset = dataset
        self.absent = frozenset(absent)
        self.called = False

    def expected_observation_dates(self, dataset, requested_range, calendar):
        self.called = True
        assert dataset == self.dataset
        return tuple(
            value
            for value in calendar.trading_days(requested_range.start_date, requested_range.end_date)
            if value not in self.absent
        )

    def identity_dict(self):
        return {"contract": "test-confirmed-absence", "version": 1}


CALENDAR = StaticCalendar(DATES)
OMIT_FRESHNESS = object()


def make(*, freshness_status="fresh", **changes):
    values = {
        "provider_id": "tushare_eod_equity",
        "dataset_id": DATASET,
        "symbol": "600000.SH",
        "observation_start": RANGE_START,
        "observation_end": RANGE_END,
        "expected_observations": DATES,
        "observed_observations": DATES,
        "source_fingerprint": FINGERPRINT,
        "observation_calendar": CALENDAR,
        "observation_expectation": StrictTradingDayObservationExpectation(),
    }
    if freshness_status is not OMIT_FRESHNESS:
        values["freshness_status"] = freshness_status
    values.update(changes)
    return generate_quality_evidence(**values)


@pytest.mark.parametrize(
    "freshness, expected_status, expected_state",
    [
        pytest.param(OMIT_FRESHNESS, "unknown", FAIL, id="F01-omitted"),
        pytest.param("unknown", "unknown", FAIL, id="F02-unknown"),
        pytest.param("stale", "stale", FAIL, id="F03-stale"),
        pytest.param("fresh", "fresh", PASS, id="F04-fresh"),
    ],
)
def test_freshness_requires_explicit_fresh_evidence(freshness, expected_status, expected_state):
    evidence = make(freshness_status=freshness)
    assert evidence.coverage_ratio == 1.0
    assert evidence.freshness_status == expected_status
    assert evidence.quality_state == expected_state
    assert json.loads(evidence.to_json())["freshness_status"] == expected_status


@pytest.mark.parametrize(
    "provider, supplied_unit, expected_unit, expected_state",
    [
        pytest.param("akshare_eod_equity", "mismatch", "mismatch", FAIL, id="U01-mismatch"),
        pytest.param("akshare_eod_equity", "unverified", "unverified", FAIL, id="U02-unverified"),
        pytest.param("akshare_eod_equity", "verified", "unverified", FAIL, id="U03-no-upgrade"),
        pytest.param("tushare_eod_equity", "verified", "verified", PASS, id="U04-verified"),
        pytest.param("tushare_eod_equity", "mismatch", "mismatch", FAIL, id="verified-mismatch"),
        pytest.param(
            "tushare_eod_equity", "unverified", "unverified", FAIL, id="verified-downgrade"
        ),
        pytest.param("unknown_provider", "mismatch", "mismatch", FAIL, id="unknown-mismatch"),
    ],
)
def test_unit_evidence_preserves_conflicts_without_upgrading_contracts(
    provider, supplied_unit, expected_unit, expected_state
):
    evidence = make(provider_id=provider, unit_status=supplied_unit)
    assert evidence.unit_status == expected_unit
    assert evidence.quality_state == expected_state
    assert evidence.to_dict()["unit_status"] == expected_unit
    assert json.loads(evidence.to_json())["unit_status"] == expected_unit
    assert replace(evidence) == evidence


@pytest.mark.parametrize("freshness", ["unknown", "stale", "fresh"])
@pytest.mark.parametrize("unit", ["mismatch", "unverified", "verified"])
def test_freshness_and_units_cannot_bypass_each_other(freshness, unit):
    evidence = make(freshness_status=freshness, unit_status=unit)
    expected_state = PASS if freshness == "fresh" and unit == "verified" else FAIL
    assert evidence.freshness_status == freshness
    assert evidence.unit_status == unit
    assert evidence.quality_state == expected_state
    assert json.loads(evidence.to_json())["quality_state"] == expected_state


def test_complete_evidence_is_deterministic_and_serializable():
    first = make()
    second = make()
    assert first == second
    assert first.quality_state == PASS
    assert first.identity == second.identity
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json())["schema_version"] == 1
    assert "timestamp" not in first.to_json()
    assert first.identity == "sha256:" + hashlib.sha256(first.to_json().encode("utf-8")).hexdigest()
    assert (
        json.loads(first.to_json(), parse_constant=lambda value: pytest.fail("non-standard JSON"))
        == first.to_dict()
    )


def test_legitimate_pr5a_absence_is_removed_from_required_observations():
    expectation = ConfirmedAbsenceExpectation(DATASET, (DATES[1],))
    evidence = make(
        expected_observations=(DATES[0], DATES[2]),
        observed_observations=(DATES[0], DATES[2]),
        observation_expectation=expectation,
    )
    assert expectation.called is True
    assert evidence.quality_state == PASS
    assert evidence.missing_observations == 0
    assert evidence.coverage_ratio == pytest.approx(1.0)


def test_real_versioned_pr5a_expectation_is_used():
    expectation = VersionedLocalObservationExpectation.from_dict(
        {
            "schema_version": 1,
            "source": "reviewed_fixture",
            "version": "v1",
            "dataset": DATASET.to_dict(),
            "confirmed_absent_dates": [DATES[1].isoformat()],
        },
        CALENDAR,
        expected_dataset=DATASET,
    )
    required = (DATES[0], DATES[2])
    assert (
        make(
            observation_expectation=expectation,
            expected_observations=required,
            observed_observations=required,
        ).quality_state
        == PASS
    )
    assert (
        make(
            observation_expectation=expectation,
            expected_observations=required,
            observed_observations=DATES,
        ).quality_state
        == FAIL
    )


def test_arbitrary_legal_gap_bypass_is_rejected():
    with pytest.raises(TypeError):
        make(legal_observation_gaps=(DATES[1],))


def test_expected_dates_must_match_observation_contract():
    with pytest.raises(ValueError):
        make(expected_observations=DATES[:2])


def test_unknown_missing_observation_fails_closed():
    evidence = make(observed_observations=DATES[:2])
    assert evidence.quality_state == FAIL


def test_unit_mismatch_fails_closed():
    assert make(unit_status="mismatch").quality_state == FAIL


def test_unverified_akshare_equity_unit_fails_closed():
    evidence = make(provider_id="akshare_eod_equity")
    assert evidence.unit_status == "unverified"
    assert evidence.quality_state == FAIL
    assert make(provider_id="akshare_eod_equity", unit_status="verified").quality_state == FAIL


def test_verified_tushare_unit_contract_is_accepted():
    assert make(unit_status="verified").quality_state == PASS


def test_unknown_provider_fails_closed():
    evidence = make(provider_id="unknown_provider")
    assert evidence.capability_status == "incompatible"
    assert evidence.quality_state == FAIL


def test_capability_mismatch_fails_closed():
    assert make(capability_status="incompatible").quality_state == FAIL


def test_registry_incompatibility_cannot_be_overridden():
    assert (
        make(
            provider_id="unknown_provider", capability_status="compatible", unit_status="verified"
        ).quality_state
        == FAIL
    )
    assert (
        make(
            dataset_id=replace(DATASET, adjustment_type=AdjustmentType.QFQ),
            capability_status="compatible",
        ).quality_state
        == FAIL
    )


def test_no_credential_or_network_access(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("external access is forbidden")

    monkeypatch.setattr("os.getenv", forbidden)
    monkeypatch.setattr("socket.socket", forbidden)
    assert make().quality_state == PASS


def test_model_is_immutable():
    evidence = make()
    with pytest.raises(AttributeError):
        evidence.quality_state = FAIL
    exported = evidence.to_dict()
    exported["quality_state"] = FAIL
    assert evidence.quality_state == PASS


def test_equivalent_input_ordering_has_same_identity():
    assert (
        make(
            expected_observations=list(reversed(DATES)), observed_observations=set(DATES)
        ).to_json()
        == make().to_json()
    )
    assert make(observed_observations=list(reversed(DATES))).identity == make().identity


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_coverage_is_rejected(value):
    with pytest.raises(TypeError):
        DataQualityEvidence(
            schema_version=1,
            provider_id="tushare_eod_equity",
            dataset_id=DATASET.to_json(),
            symbol="600000.SH",
            observation_start=RANGE_START,
            observation_end=RANGE_END,
            expected_observations=1,
            observed_observations=1,
            missing_observations=0,
            extra_observations=0,
            coverage_ratio=value,
            freshness_status="fresh",
            unit_status="verified",
            observation_status="valid",
            capability_status="compatible",
            quality_state=PASS,
            source_fingerprint=FINGERPRINT,
        )


@pytest.mark.parametrize("bad", ["fingerprint", "C:/secret", "TUSHARE_TOKEN=secret"])
def test_source_fingerprint_requires_structured_digest(bad):
    with pytest.raises(ValueError):
        make(source_fingerprint=bad)


def test_extra_observation_fails_closed():
    expectation = ConfirmedAbsenceExpectation(DATASET, (DATES[1],))
    evidence = make(
        expected_observations=(DATES[0], DATES[2]),
        observed_observations=DATES,
        observation_expectation=expectation,
    )
    assert evidence.extra_observations == 1
    assert evidence.quality_state == FAIL


def test_zero_expected_observations_are_deterministic():
    first = make(
        observation_start=RANGE_START,
        observation_end=RANGE_START,
        expected_observations=(),
        observed_observations=(),
        observation_calendar=StaticCalendar(()),
        observation_expectation=ConfirmedAbsenceExpectation(DATASET, ()),
    )
    second = make(
        observation_start=RANGE_START,
        observation_end=RANGE_START,
        expected_observations=(),
        observed_observations=(),
        observation_calendar=StaticCalendar(()),
        observation_expectation=ConfirmedAbsenceExpectation(DATASET, ()),
    )
    assert first.quality_state == PASS
    assert first.coverage_ratio == 1.0
    assert first.identity == second.identity
    assert (
        make(
            expected_observations=(),
            observed_observations=DATES,
            observation_calendar=StaticCalendar(()),
        ).quality_state
        == FAIL
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"observation_start": RANGE_END, "observation_end": RANGE_START},
        {"observed_observations": DATES + (date(2026, 1, 8),)},
        {"observed_observations": DATES + (DATES[0],)},
        {"expected_observations": DATES + (DATES[0],)},
        {"dataset_id": "C:/private"},
        {"symbol": "TUSHARE_TOKEN=synthetic"},
        {"provider_id": "C:/private"},
        {"observation_expectation": object()},
        {"observation_calendar": object()},
        {"capability_registry": object()},
        {"unit_status": "INVALID"},
        {"freshness_status": "INVALID"},
        {"capability_status": "INVALID"},
    ],
)
def test_invalid_declarations_are_rejected(changes):
    with pytest.raises((TypeError, ValueError)):
        make(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"dataset_id": "C:/private"},
        {"provider_id": "token=synthetic"},
        {"source_fingerprint": "raw-synthetic-token"},
        {"missing_observations": 1},
        {"extra_observations": 1},
        {"coverage_ratio": 0.5},
        {"quality_state": FAIL},
        {"unit_status": "unverified"},
    ],
)
def test_direct_model_rejects_contradictory_or_unsafe_evidence(changes):
    with pytest.raises((TypeError, ValueError)):
        replace(make(), **changes)


def test_import_and_evaluation_have_no_provider_credentials_or_network_side_effects(tmp_path):
    script = r"""
import autowealth
import importlib.abc
import os
import socket
import sys
def forbidden(*args, **kwargs):
    raise AssertionError("forbidden side effect")
class BlockSDK(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in ("tushare", "akshare"):
            forbidden()
sys.meta_path.insert(0, BlockSDK())
original_getitem = type(os.environ).__getitem__
def guarded(self, key):
    if key == "TUSHARE_TOKEN":
        forbidden()
    return original_getitem(self, key)
type(os.environ).__getitem__ = guarded
socket.socket.connect = forbidden
socket.socket.connect_ex = forbidden
socket.create_connection = forbidden
import runpy
fixture = runpy.run_path("tests/test_eod_quality_evidence.py")
evidence = fixture["make"]()
assert evidence.quality_state == "PASS"
evidence.to_json()
evidence.identity
assert "tushare" not in sys.modules and "akshare" not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_direct_model_rejects_invalid_quality_state():
    with pytest.raises(ValueError):
        DataQualityEvidence(
            schema_version=1,
            provider_id="tushare_eod_equity",
            dataset_id=DATASET.to_json(),
            symbol="600000.SH",
            observation_start=RANGE_START,
            observation_end=RANGE_END,
            expected_observations=1,
            observed_observations=1,
            missing_observations=0,
            extra_observations=0,
            coverage_ratio=1.0,
            freshness_status="fresh",
            unit_status="verified",
            observation_status="valid",
            capability_status="compatible",
            quality_state="INVALID",
            source_fingerprint=FINGERPRINT,
        )
