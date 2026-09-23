from __future__ import annotations

from datetime import date
import json

import pytest

from autowealth.market_data.local_observation import (
    LocalObservationError,
    LocalObservationErrorCode,
    VersionedLocalObservationExpectation,
)
from autowealth.market_data.observation import observation_expectation_identity
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)

D1 = date(2026, 9, 14)
D2 = date(2026, 9, 15)
D3 = date(2026, 9, 16)
NON_TRADING = date(2026, 9, 19)


class StaticCalendar:
    days = (D1, D2, D3)

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) + 1]

    def previous_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) - 1]

    def trading_days(self, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(value for value in self.days if start_date <= value <= end_date)


def dataset(symbol: str = "600000.SH") -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        Venue.SSE,
        AssetType.EQUITY,
        symbol,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


def artifact(
    *,
    version: str = "2026-09-21",
    absent: list[str] = None,
    selected_dataset: EODDatasetKey = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source": "tushare_suspend_d",
        "version": version,
        "dataset": (selected_dataset or dataset()).to_dict(),
        "confirmed_absent_dates": [D2.isoformat()] if absent is None else absent,
    }


def test_local_artifact_omits_only_confirmed_absence() -> None:
    expectation = VersionedLocalObservationExpectation.from_dict(
        artifact(), StaticCalendar(), expected_dataset=dataset()
    )
    assert expectation.expected_observation_dates(
        dataset(), EODDateRange(D1, D3), StaticCalendar()
    ) == (D1, D3)


def test_dataset_mismatch_and_unknown_field_fail_closed() -> None:
    with pytest.raises(LocalObservationError) as mismatch:
        VersionedLocalObservationExpectation.from_dict(
            artifact(selected_dataset=dataset("600001.SH")),
            StaticCalendar(),
            expected_dataset=dataset(),
        )
    assert mismatch.value.code is LocalObservationErrorCode.DATASET_MISMATCH

    payload = artifact()
    payload["unknown"] = True
    with pytest.raises(LocalObservationError) as unknown:
        VersionedLocalObservationExpectation.from_dict(payload, StaticCalendar())
    assert unknown.value.code is LocalObservationErrorCode.UNSUPPORTED_SCHEMA


def test_duplicate_unordered_and_non_trading_absences_fail_closed() -> None:
    cases = (
        (
            [D2.isoformat(), D2.isoformat()],
            LocalObservationErrorCode.DUPLICATE_ABSENCE,
        ),
        (
            [D3.isoformat(), D2.isoformat()],
            LocalObservationErrorCode.UNORDERED_ABSENCES,
        ),
        ([NON_TRADING.isoformat()], LocalObservationErrorCode.NON_TRADING_ABSENCE),
    )
    for absences, code in cases:
        with pytest.raises(LocalObservationError) as captured:
            VersionedLocalObservationExpectation.from_dict(
                artifact(absent=absences), StaticCalendar()
            )
        assert captured.value.code is code


def test_identity_is_path_independent_and_changes_with_logical_content(tmp_path) -> None:
    first_path = tmp_path / "one" / "observation.json"
    second_path = tmp_path / "two" / "moved.json"
    first_path.parent.mkdir()
    second_path.parent.mkdir()
    payload = artifact()
    first_path.write_text(json.dumps(payload), encoding="utf-8")
    second_path.write_text(json.dumps(payload), encoding="utf-8")

    first = VersionedLocalObservationExpectation.from_file(first_path, StaticCalendar())
    moved = VersionedLocalObservationExpectation.from_file(second_path, StaticCalendar())
    changed_version = VersionedLocalObservationExpectation.from_dict(
        artifact(version="2026-09-22"), StaticCalendar()
    )
    changed_absence = VersionedLocalObservationExpectation.from_dict(
        artifact(absent=[D3.isoformat()]), StaticCalendar()
    )

    assert observation_expectation_identity(first) == observation_expectation_identity(moved)
    assert observation_expectation_identity(first) != observation_expectation_identity(
        changed_version
    )
    assert observation_expectation_identity(first) != observation_expectation_identity(
        changed_absence
    )
