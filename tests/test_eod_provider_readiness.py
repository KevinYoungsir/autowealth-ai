from __future__ import annotations

from datetime import date, datetime, timezone
import inspect
from typing import Optional

import pytest

from autowealth.market_data.operation_catalog import EODOperationCatalogEntry
from autowealth.market_data.readiness import (
    EODProviderReadiness,
    EODProviderReadinessProbe,
    EODProviderReadinessStatus,
    EODReadinessScope,
    evaluate_eod_provider_readiness,
)
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    Market,
    Venue,
)

DAY_1 = date(2024, 1, 2)
DAY_2 = date(2024, 1, 3)
DAY_3 = date(2024, 1, 4)
WEEKEND = date(2024, 1, 6)
OBSERVED_AT = datetime(2024, 1, 4, 8, 30, tzinfo=timezone.utc)


class FakeCalendar:
    days = (DAY_1, DAY_2, DAY_3)

    def is_trading_day(self, value: date) -> bool:
        return value in self.days

    def next_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) + 1]

    def previous_trading_day(self, value: date) -> date:
        return self.days[self.days.index(value) - 1]

    def trading_days(self, start_date: date, end_date: date) -> tuple[date, ...]:
        return tuple(value for value in self.days if start_date <= value <= end_date)


def dataset(symbol: str, venue: Venue) -> EODDatasetKey:
    return EODDatasetKey(
        Market.CN,
        venue,
        AssetType.EQUITY,
        symbol,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
    )


SSE = dataset("600000.SH", Venue.SSE)
SZSE = dataset("000001.SZ", Venue.SZSE)


def scope(expected: date = DAY_3) -> EODReadinessScope:
    return EODReadinessScope((SZSE, SSE), expected)


def evaluate(
    observed: dict[EODDatasetKey, Optional[date]],
    *,
    selected_scope: EODReadinessScope = None,
    terminal: EODProviderReadinessStatus = None,
) -> EODProviderReadiness:
    return evaluate_eod_provider_readiness(
        provider_name="test_provider",
        provider_version="fixture-v1",
        endpoint_name="daily",
        scope=selected_scope or scope(),
        calendar=FakeCalendar(),
        observed_dates=observed,
        observed_at=OBSERVED_AT,
        terminal_status=terminal,
    )


def test_scope_is_canonical_and_configured_not_whole_market() -> None:
    value = scope()
    assert value.datasets == (SSE, SZSE)
    assert value.to_dict()["coverage_basis"] == "configured_datasets"


def test_complete_configured_scope_is_ready() -> None:
    result = evaluate({SSE: DAY_3, SZSE: DAY_3})
    assert result.status is EODProviderReadinessStatus.READY
    assert result.observed_count == 2
    assert result.publication_watermark == DAY_3


def test_partial_configured_scope_is_partial() -> None:
    result = evaluate({SSE: DAY_3, SZSE: DAY_2})
    assert result.status is EODProviderReadinessStatus.PARTIAL
    assert result.observed_count == 1
    assert result.diagnostic_code == "configured_scope_partial"


def test_previous_trading_day_watermark_is_not_ready() -> None:
    result = evaluate({SSE: DAY_2, SZSE: DAY_2})
    assert result.status is EODProviderReadinessStatus.NOT_READY
    assert result.publication_watermark == DAY_2


def test_older_watermark_is_stale() -> None:
    result = evaluate({SSE: DAY_1, SZSE: DAY_1})
    assert result.status is EODProviderReadinessStatus.STALE
    assert result.diagnostic_code == "publication_stale"


@pytest.mark.parametrize(
    ("observed", "expected_status", "expected_watermark"),
    [
        ({SSE: DAY_2, SZSE: DAY_1}, EODProviderReadinessStatus.STALE, DAY_1),
        ({SSE: None, SZSE: DAY_1}, EODProviderReadinessStatus.STALE, None),
        ({SSE: DAY_3, SZSE: DAY_1}, EODProviderReadinessStatus.STALE, DAY_1),
        ({SSE: DAY_3, SZSE: DAY_2}, EODProviderReadinessStatus.PARTIAL, DAY_2),
        ({SSE: DAY_2, SZSE: DAY_2}, EODProviderReadinessStatus.NOT_READY, DAY_2),
        ({SSE: DAY_3, SZSE: DAY_3}, EODProviderReadinessStatus.READY, DAY_3),
        ({SSE: None, SZSE: None}, EODProviderReadinessStatus.NOT_READY, None),
    ],
)
def test_scope_freshness_uses_the_least_recent_required_dataset(
    observed: dict[EODDatasetKey, Optional[date]],
    expected_status: EODProviderReadinessStatus,
    expected_watermark: Optional[date],
) -> None:
    result = evaluate(observed)
    assert result.status is expected_status
    assert result.publication_watermark == expected_watermark


def test_non_trading_date_is_not_expected_without_observations() -> None:
    result = evaluate_eod_provider_readiness(
        provider_name="test_provider",
        provider_version="fixture-v1",
        endpoint_name="daily",
        scope=scope(WEEKEND),
        calendar=FakeCalendar(),
        observed_dates=None,
        observed_at=OBSERVED_AT,
    )
    assert result.status is EODProviderReadinessStatus.NOT_EXPECTED
    assert result.observed_count == 0


@pytest.mark.parametrize(
    ("status", "diagnostic"),
    [
        (EODProviderReadinessStatus.UNAVAILABLE, "provider_unavailable"),
        (EODProviderReadinessStatus.UNSUPPORTED, "readiness_unsupported"),
    ],
)
def test_terminal_observation_states(status: EODProviderReadinessStatus, diagnostic: str) -> None:
    result = evaluate_eod_provider_readiness(
        provider_name="test_provider",
        provider_version="fixture-v1",
        endpoint_name="daily",
        scope=scope(),
        calendar=FakeCalendar(),
        observed_dates=None,
        observed_at=OBSERVED_AT,
        terminal_status=status,
    )
    assert result.status is status
    assert result.diagnostic_code == diagnostic


def test_observed_at_is_injected_utc_audit_evidence() -> None:
    local = datetime.fromisoformat("2024-01-04T16:30:00+08:00")
    result = evaluate_eod_provider_readiness(
        provider_name="test_provider",
        provider_version="fixture-v1",
        endpoint_name="daily",
        scope=scope(),
        calendar=FakeCalendar(),
        observed_dates={SSE: DAY_3, SZSE: DAY_3},
        observed_at=local,
    )
    assert result.observed_at == OBSERVED_AT
    assert result.to_dict()["observed_at"] == "2024-01-04T08:30:00Z"


def test_readiness_is_not_part_of_execution_fingerprint() -> None:
    source = inspect.getsource(EODOperationCatalogEntry.fingerprint_dict)
    assert "readiness" not in source
    assert "observed_at" not in source


def test_readiness_contract_is_side_effect_free_and_structural() -> None:
    class FakeProbe:
        provider_name = "test_provider"
        provider_version = "fixture-v1"
        endpoint_name = "daily"

        def probe_readiness(
            self,
            selected_scope: EODReadinessScope,
            *,
            observed_at: datetime,
        ) -> EODProviderReadiness:
            return evaluate_eod_provider_readiness(
                provider_name=self.provider_name,
                provider_version=self.provider_version,
                endpoint_name=self.endpoint_name,
                scope=selected_scope,
                calendar=FakeCalendar(),
                observed_dates={SSE: DAY_3, SZSE: DAY_3},
                observed_at=observed_at,
            )

    probe = FakeProbe()
    assert isinstance(probe, EODProviderReadinessProbe)
    assert probe.probe_readiness(scope(), observed_at=OBSERVED_AT).status is (
        EODProviderReadinessStatus.READY
    )


def test_invalid_scope_and_observations_fail_closed() -> None:
    with pytest.raises(ValueError, match="duplicates"):
        EODReadinessScope((SSE, SSE), DAY_3)
    with pytest.raises(ValueError, match="exactly cover"):
        evaluate({SSE: DAY_3})
    with pytest.raises(ValueError, match="after expected"):
        evaluate({SSE: date(2024, 1, 5), SZSE: DAY_3})
    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_eod_provider_readiness(
            provider_name="test_provider",
            provider_version="fixture-v1",
            endpoint_name="daily",
            scope=scope(),
            calendar=FakeCalendar(),
            observed_dates={SSE: DAY_3, SZSE: DAY_3},
            observed_at=datetime(2024, 1, 4, 8, 30),
        )
