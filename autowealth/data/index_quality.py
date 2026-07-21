"""Strict quality validation for benchmark index daily bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, isfinite
from numbers import Real
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from autowealth.data.schema import normalize_market_data

MIN_BENCHMARK_COVERAGE_RATIO = 0.80
MAX_BENCHMARK_EDGE_GAP_BUSINESS_DAYS = 5


@dataclass(frozen=True)
class BenchmarkQualityResult:
    """Auditable validation result for one provider or cache response."""

    passed: bool
    reason_code: str
    reason: str
    data: pd.DataFrame = field(repr=False)
    raw_row_count: int = 0
    clean_row_count: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    coverage_ratio: Optional[float] = None
    minimum_coverage_ratio: float = MIN_BENCHMARK_COVERAGE_RATIO
    estimated_business_days: int = 0
    start_edge_gap_business_days: int = 0
    end_edge_gap_business_days: int = 0
    maximum_edge_gap_business_days: int = 0
    duplicate_date_count: int = 0
    source_metadata: Mapping[str, Any] = field(default_factory=dict)

    def audit_metadata(self) -> dict[str, Any]:
        return {
            "raw_row_count": self.raw_row_count,
            "clean_row_count": self.clean_row_count,
            "minimum_coverage_ratio": self.minimum_coverage_ratio,
            "estimated_business_days": self.estimated_business_days,
            "start_edge_gap_business_days": self.start_edge_gap_business_days,
            "end_edge_gap_business_days": self.end_edge_gap_business_days,
            "maximum_edge_gap_business_days": self.maximum_edge_gap_business_days,
            "duplicate_date_count": self.duplicate_date_count,
            **dict(self.source_metadata),
        }


def validate_minimum_coverage_ratio(value: object) -> float:
    """Return a finite numeric coverage ratio in the inclusive unit interval."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("minimum_coverage_ratio must be a real number in (0, 1]")
    ratio = float(value)
    if not isfinite(ratio) or not 0 < ratio <= 1:
        raise ValueError("minimum_coverage_ratio must be finite and in (0, 1]")
    return ratio


def validate_benchmark_data(
    data: pd.DataFrame,
    start_date: str,
    end_date: str,
    *,
    minimum_coverage_ratio: float = MIN_BENCHMARK_COVERAGE_RATIO,
) -> BenchmarkQualityResult:
    """Validate and normalize benchmark bars without inventing observations.

    Coverage uses weekdays as an estimate because the project does not yet ship
    a historical A-share exchange calendar.
    """
    ratio = validate_minimum_coverage_ratio(minimum_coverage_ratio)

    frame = pd.DataFrame(data).copy()
    raw_count = len(frame)
    empty = pd.DataFrame()
    if frame.empty:
        return _failure(
            "empty_response",
            "provider returned no rows",
            empty,
            minimum_coverage_ratio=ratio,
        )
    if "date" not in frame.columns or "close" not in frame.columns:
        return _failure(
            "invalid_schema",
            "benchmark data must contain date and close columns",
            empty,
            raw_row_count=raw_count,
            minimum_coverage_ratio=ratio,
        )

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start > end:
        raise ValueError("benchmark start_date cannot be after end_date")

    parsed_dates = pd.to_datetime(
        frame["date"],
        errors="coerce",
        format="mixed",
    ).dt.normalize()
    invalid_dates = int(parsed_dates.isna().sum())
    if invalid_dates:
        return _failure(
            "invalid_dates",
            f"benchmark data contains {invalid_dates} unparseable dates",
            empty,
            raw_row_count=raw_count,
            minimum_coverage_ratio=ratio,
            source_metadata={"invalid_date_count": invalid_dates},
        )

    first_date = _date_text(parsed_dates.min())
    last_date = _date_text(parsed_dates.max())

    outside_range = int(((parsed_dates < start) | (parsed_dates > end)).sum())
    if outside_range:
        return _failure(
            "invalid_dates",
            f"benchmark data contains {outside_range} dates outside the requested range",
            empty,
            raw_row_count=raw_count,
            first_date=first_date,
            last_date=last_date,
            minimum_coverage_ratio=ratio,
            source_metadata={"outside_requested_range_count": outside_range},
        )

    numeric_close = pd.to_numeric(frame["close"], errors="coerce")
    missing_close = int(numeric_close.isna().sum())
    if missing_close:
        return _failure(
            "missing_close",
            f"benchmark data contains {missing_close} missing or non-numeric close values",
            empty,
            raw_row_count=raw_count,
            first_date=first_date,
            last_date=last_date,
            minimum_coverage_ratio=ratio,
            source_metadata={"missing_close_count": missing_close},
        )

    non_finite_close = int((~np.isfinite(numeric_close.to_numpy(dtype=float))).sum())
    if non_finite_close:
        return _failure(
            "non_finite_close",
            f"benchmark data contains {non_finite_close} non-finite close values",
            empty,
            raw_row_count=raw_count,
            first_date=first_date,
            last_date=last_date,
            minimum_coverage_ratio=ratio,
            source_metadata={"non_finite_close_count": non_finite_close},
        )

    non_positive_close = int((numeric_close <= 0).sum())
    if non_positive_close:
        return _failure(
            "non_positive_close",
            f"benchmark data contains {non_positive_close} non-positive close values",
            empty,
            raw_row_count=raw_count,
            first_date=first_date,
            last_date=last_date,
            minimum_coverage_ratio=ratio,
            source_metadata={"non_positive_close_count": non_positive_close},
        )

    duplicate_count = int(parsed_dates.duplicated(keep=False).sum())
    if duplicate_count:
        return _failure(
            "duplicate_dates",
            f"benchmark data contains {duplicate_count} rows on duplicated dates",
            empty,
            raw_row_count=raw_count,
            first_date=first_date,
            last_date=last_date,
            minimum_coverage_ratio=ratio,
            duplicate_date_count=duplicate_count,
        )

    frame["date"] = parsed_dates
    frame["close"] = numeric_close
    normalized = normalize_market_data(frame).sort_values("date").reset_index(drop=True)
    clean_count = len(normalized)
    expected_business_days = pd.bdate_range(start, end)
    estimated_days = max(len(expected_business_days), 1)
    coverage_ratio = min(clean_count / estimated_days, 1.0)
    minimum_rows = (
        1
        if estimated_days == 1
        else max(
            2,
            ceil(estimated_days * ratio),
        )
    )
    missing_row_budget = max(estimated_days - minimum_rows, 0)
    maximum_edge_gap = min(
        MAX_BENCHMARK_EDGE_GAP_BUSINESS_DAYS,
        max(missing_row_budget - 1, 0),
    )
    first_timestamp = pd.Timestamp(normalized["date"].iloc[0]).normalize()
    last_timestamp = pd.Timestamp(normalized["date"].iloc[-1]).normalize()
    start_edge_gap = int((expected_business_days < first_timestamp).sum())
    end_edge_gap = int((expected_business_days > last_timestamp).sum())

    coverage_values = {
        "raw_row_count": raw_count,
        "clean_row_count": clean_count,
        "first_date": first_date,
        "last_date": last_date,
        "coverage_ratio": coverage_ratio,
        "minimum_coverage_ratio": ratio,
        "estimated_business_days": estimated_days,
        "start_edge_gap_business_days": start_edge_gap,
        "end_edge_gap_business_days": end_edge_gap,
        "maximum_edge_gap_business_days": maximum_edge_gap,
    }
    if clean_count < minimum_rows or coverage_ratio < ratio:
        return _failure(
            "insufficient_coverage",
            (f"benchmark coverage {coverage_ratio:.4f} is below required " f"{ratio:.4f}"),
            normalized,
            **coverage_values,
        )

    if start_edge_gap > maximum_edge_gap or end_edge_gap > maximum_edge_gap:
        return _failure(
            "insufficient_coverage",
            (
                "benchmark request-window edge coverage failed: "
                f"start gap {start_edge_gap}, end gap {end_edge_gap}, "
                f"allowed {maximum_edge_gap} estimated business days"
            ),
            normalized,
            **coverage_values,
        )

    return BenchmarkQualityResult(
        passed=True,
        reason_code="success",
        reason="benchmark data passed validation",
        data=normalized,
        **coverage_values,
    )


def _failure(
    reason_code: str,
    reason: str,
    data: pd.DataFrame,
    **values: Any,
) -> BenchmarkQualityResult:
    return BenchmarkQualityResult(
        passed=False,
        reason_code=reason_code,
        reason=reason,
        data=data,
        **values,
    )


def _date_text(value: object) -> Optional[str]:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")
