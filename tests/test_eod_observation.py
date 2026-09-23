from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from autowealth.market_data.observation import (
    StrictTradingDayObservationExpectation,
    is_observation_expected,
    validate_expected_observation_dates,
)
from autowealth.market_data.planning import (
    EODRequestPlanStatus,
    plan_eod_request_window,
)
from autowealth.market_data.schemas import (
    EOD_SCHEMA_VERSION,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EODGenerationManifest,
)

D1 = date(2026, 9, 14)
D2 = date(2026, 9, 15)
D3 = date(2026, 9, 16)
D4 = date(2026, 9, 17)


class StaticCalendar:
    def __init__(self, days: tuple[date, ...]) -> None:
        self.days = days

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) + 1]

    def previous_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) - 1]

    def trading_days(self, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(value for value in self.days if start_date <= value <= end_date)


class ConfirmedAbsenceExpectation:
    def __init__(self, dataset: EODDatasetKey, absent: tuple[date, ...]) -> None:
        self.dataset = dataset
        self.absent = frozenset(absent)

    def expected_observation_dates(
        self,
        dataset: EODDatasetKey,
        requested_range: EODDateRange,
        calendar: StaticCalendar,
    ) -> tuple[date, ...]:
        if dataset != self.dataset:
            raise ValueError("dataset mismatch")
        return tuple(
            value
            for value in calendar.trading_days(requested_range.start_date, requested_range.end_date)
            if value not in self.absent
        )

    def identity_dict(self) -> dict[str, object]:
        return {
            "version": "test-v1",
            "dataset": self.dataset.to_dict(),
            "confirmed_absent_dates": sorted(value.isoformat() for value in self.absent),
        }


def dataset() -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        Venue.SSE,
        AssetType.EQUITY,
        "600000.SH",
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


def manifest(first_date: date, last_date: date) -> EODGenerationManifest:
    digest = "a" * 64
    return EODGenerationManifest(
        EOD_MANIFEST_SCHEMA_VERSION,
        EOD_SCHEMA_VERSION,
        "generation_observation_test",
        dataset(),
        datetime(2026, 9, 18, tzinfo=timezone.utc),
        1,
        first_date,
        last_date,
        f"sha256:{digest}",
        digest,
        "b" * 64,
    )


def test_strict_expectation_requires_every_exchange_trading_date() -> None:
    calendar = StaticCalendar((D1, D2, D3))
    expectation = StrictTradingDayObservationExpectation()
    assert validate_expected_observation_dates(
        expectation, dataset(), EODDateRange(D1, D3), calendar
    ) == (D1, D2, D3)
    assert is_observation_expected(expectation, dataset(), D2, calendar) is True


def test_non_trading_date_is_not_expected() -> None:
    calendar = StaticCalendar((D1, D3))
    assert (
        is_observation_expected(StrictTradingDayObservationExpectation(), dataset(), D2, calendar)
        is False
    )


def test_planning_skips_confirmed_suspension_and_resumes_at_next_expected_date() -> None:
    current = manifest(D1, D1)
    calendar = StaticCalendar((D1, D2, D3, D4))
    expectation = ConfirmedAbsenceExpectation(dataset(), (D2,))

    suspended_only = plan_eod_request_window(
        dataset(),
        EODDateRange(D2, D2),
        calendar,
        current,
        observation_expectation=expectation,
    )
    resumed = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D3),
        calendar,
        current,
        observation_expectation=expectation,
    )
    normal = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D4),
        calendar,
        manifest(D1, D3),
        observation_expectation=expectation,
    )

    assert suspended_only.status is EODRequestPlanStatus.NO_EXPECTED_OBSERVATIONS
    assert suspended_only.provider_request is None
    assert resumed.provider_request.requested_range == EODDateRange(D3, D3)
    assert normal.provider_request.requested_range == EODDateRange(D4, D4)


def test_leading_trailing_and_all_suspended_ranges_are_deterministic() -> None:
    calendar = StaticCalendar((D1, D2, D3))
    leading = ConfirmedAbsenceExpectation(dataset(), (D1, D2))
    trailing = ConfirmedAbsenceExpectation(dataset(), (D2, D3))
    all_absent = ConfirmedAbsenceExpectation(dataset(), (D1, D2, D3))

    initial = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D3),
        calendar,
        observation_expectation=leading,
    )
    current = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D3),
        calendar,
        manifest(D1, D1),
        observation_expectation=trailing,
    )
    empty = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D3),
        calendar,
        observation_expectation=all_absent,
    )

    assert initial.status is EODRequestPlanStatus.INITIAL_IMPORT
    assert initial.effective_range == EODDateRange(D3, D3)
    assert initial.provider_request.requested_range == EODDateRange(D3, D3)
    assert current.status is EODRequestPlanStatus.ALREADY_CURRENT
    assert current.provider_request is None
    assert empty.status is EODRequestPlanStatus.NO_EXPECTED_OBSERVATIONS
    assert empty.provider_request is None


def test_missing_is_not_inferred_as_suspension() -> None:
    calendar = StaticCalendar((D1, D2, D3))
    strict = plan_eod_request_window(
        dataset(),
        EODDateRange(D1, D3),
        calendar,
        manifest(D1, D1),
    )
    assert strict.provider_request.requested_range == EODDateRange(D2, D3)
