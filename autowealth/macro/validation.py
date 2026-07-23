"""Non-blocking contracts for shadow validation of macro observations."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Mapping, Optional, Sequence, Tuple, Union

import pandas as pd

MacroRevision = Union[str, int]

MACRO_INDICATORS: Tuple[str, ...] = (
    "pmi",
    "cpi_yoy",
    "ppi_yoy",
    "m2_yoy",
    "social_financing_yoy",
    "ten_year_yield",
    "usd_cny",
    "policy_score",
    "external_risk_score",
)

MACRO_REASON_CODES: Tuple[str, ...] = (
    "success",
    "empty_input",
    "invalid_schema",
    "missing_indicator",
    "missing_observation_date",
    "missing_available_date",
    "invalid_observation_date",
    "invalid_available_date",
    "available_before_observation",
    "non_finite_value",
    "duplicate_observation",
    "duplicate_version",
    "unsorted_dates",
)

PIT_REASON_CODES: Tuple[str, ...] = (
    "future_observation",
    "future_available_date",
    "no_pit_eligible_record",
)

_TECHNICAL_COLUMNS = {
    "date",
    "observation_date",
    "available_date",
    "source",
    "revision",
    "unit",
    "frequency",
}
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SOURCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@dataclass(frozen=True)
class MacroObservation:
    """One versioned macro observation with an explicit publication date."""

    indicator: str
    observation_date: str
    available_date: str
    value: float
    source: str
    revision: Optional[MacroRevision] = None
    unit: Optional[str] = None
    frequency: Optional[str] = None

    def __post_init__(self) -> None:
        values = self.to_dict()
        reason = _record_reason(values)
        if reason is not None:
            raise ValueError(f"invalid macro observation: {reason}")
        observation_date = _parse_date_only(self.observation_date)
        available_date = _parse_date_only(self.available_date)
        source = _safe_source(self.source)
        if source is None:
            raise ValueError("invalid macro observation: invalid_schema")
        object.__setattr__(self, "observation_date", observation_date.isoformat())
        object.__setattr__(self, "available_date", available_date.isoformat())
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "revision", _stable_revision(self.revision))
        object.__setattr__(self, "unit", _optional_text(self.unit))
        object.__setattr__(self, "frequency", _optional_text(self.frequency))

    def to_dict(self) -> dict[str, object]:
        return {
            "indicator": self.indicator,
            "observation_date": self.observation_date,
            "available_date": self.available_date,
            "value": self.value,
            "source": self.source,
            "revision": self.revision,
            "unit": self.unit,
            "frequency": self.frequency,
        }


@dataclass(frozen=True)
class MacroValidationResult:
    """Deterministic shadow-validation output, separate from research status."""

    status: str
    reason_codes: Tuple[str, ...]
    valid_observations: Tuple[MacroObservation, ...]
    diagnostics: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return dict(self.diagnostics)


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    try:
        return bool(missing)
    except (TypeError, ValueError):
        return False


def _parse_date_only(value: object) -> date:
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is not None or value.time() != datetime.min.time():
            raise ValueError("date must be timezone-free and date-only")
        return value.date()
    if isinstance(value, datetime):
        if value.tzinfo is not None or value.time() != datetime.min.time():
            raise ValueError("date must be timezone-free and date-only")
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        raise ValueError("date must use ISO YYYY-MM-DD")
    return date.fromisoformat(value)


def _safe_source(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _SOURCE_PATTERN.fullmatch(candidate) else None


def _stable_revision(value: object) -> Optional[MacroRevision]:
    if _is_missing(value):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("revision must be a stable string or integer")
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            raise ValueError("revision cannot be empty")
        return candidate
    return value


def _optional_text(value: object) -> Optional[str]:
    if _is_missing(value):
        return None
    if not isinstance(value, str):
        raise ValueError("optional metadata must be text")
    return value


def _ordered_reason_codes(values: Iterable[str]) -> Tuple[str, ...]:
    seen = set(values)
    return tuple(code for code in MACRO_REASON_CODES if code in seen)


def _empty_pit_summary() -> dict[str, object]:
    return {
        "signal_date_count": 0,
        "fully_available_count": 0,
        "partially_available_count": 0,
        "unavailable_count": 0,
        "reason_counts": {},
    }


def _base_diagnostics(source: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "validation_mode": "shadow",
        "status": "empty",
        "reason_codes": ["empty_input"],
        "raw_row_count": 0,
        "valid_row_count": 0,
        "rejected_row_count": 0,
        "coverage_ratio": 0.0,
        "rejected_counts": {},
        "source": source,
        "indicators": {},
        "pit_summary": _empty_pit_summary(),
    }


def _invalid_result(source: object, exc: BaseException) -> MacroValidationResult:
    safe_source = _safe_source(source) or "unknown"
    diagnostics = _base_diagnostics(safe_source)
    diagnostics.update(
        {
            "status": "invalid",
            "reason_codes": ["invalid_schema"],
            "exception_type": type(exc).__name__[:100],
            "safe_summary": "macro shadow validation could not safely process the input",
        }
    )
    return MacroValidationResult(
        status="invalid",
        reason_codes=("invalid_schema",),
        valid_observations=(),
        diagnostics=diagnostics,
    )


def adapt_macro_wide_frame(
    data: pd.DataFrame,
    *,
    source: str = "macro_wide_frame",
) -> list[dict[str, object]]:
    """Expand the existing macro wide frame without mutating it.

    Missing publication dates are deliberately retained so the validator can
    reject them explicitly instead of substituting observation dates.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("macro wide-frame input must be a pandas DataFrame")

    frame = data.copy(deep=True)
    records: list[dict[str, object]] = []
    observation_column = "observation_date" if "observation_date" in frame.columns else "date"
    indicator_columns = [name for name in MACRO_INDICATORS if name in frame.columns]
    if not frame.empty and not indicator_columns:
        return [
            {
                "indicator": "__invalid_macro_schema__",
                "source": source,
                "technical_columns": sorted(
                    str(name) for name in frame.columns if str(name) in _TECHNICAL_COLUMNS
                ),
            }
        ]

    for _, row in frame.iterrows():
        row_source = row.get("source")
        resolved_source = source if _is_missing(row_source) else row_source
        for indicator in indicator_columns:
            value = row.get(indicator)
            if _is_missing(value):
                continue
            records.append(
                {
                    "indicator": indicator,
                    "observation_date": row.get(observation_column),
                    "available_date": row.get("available_date"),
                    "value": value,
                    "source": resolved_source,
                    "revision": row.get("revision"),
                    "unit": row.get("unit"),
                    "frequency": row.get("frequency"),
                }
            )
    return records


def _record_reason(values: Mapping[str, object]) -> Optional[str]:
    indicator = values.get("indicator")
    if _is_missing(indicator):
        return "missing_indicator"
    if not isinstance(indicator, str) or indicator not in MACRO_INDICATORS:
        return "invalid_schema"

    observation_value = values.get("observation_date")
    if _is_missing(observation_value):
        return "missing_observation_date"
    try:
        observation_date = _parse_date_only(observation_value)
    except (TypeError, ValueError, OverflowError):
        return "invalid_observation_date"

    available_value = values.get("available_date")
    if _is_missing(available_value):
        return "missing_available_date"
    try:
        available_date = _parse_date_only(available_value)
    except (TypeError, ValueError, OverflowError):
        return "invalid_available_date"
    if available_date < observation_date:
        return "available_before_observation"

    try:
        number = float(values.get("value"))
    except (TypeError, ValueError, OverflowError):
        return "non_finite_value"
    if not math.isfinite(number):
        return "non_finite_value"

    if _safe_source(values.get("source")) is None:
        return "invalid_schema"
    try:
        _stable_revision(values.get("revision"))
        _optional_text(values.get("unit"))
        _optional_text(values.get("frequency"))
    except ValueError:
        return "invalid_schema"
    return None


def _observation_from_mapping(values: Mapping[str, object]) -> MacroObservation:
    observation_date = _parse_date_only(values["observation_date"])
    available_date = _parse_date_only(values["available_date"])
    source = _safe_source(values["source"])
    if source is None:
        raise ValueError("invalid source")
    return MacroObservation(
        indicator=str(values["indicator"]),
        observation_date=observation_date.isoformat(),
        available_date=available_date.isoformat(),
        value=float(values["value"]),
        source=source,
        revision=_stable_revision(values.get("revision")),
        unit=_optional_text(values.get("unit")),
        frequency=_optional_text(values.get("frequency")),
    )


def _duplicate_key(observation: MacroObservation) -> tuple[object, ...]:
    return (
        observation.indicator,
        observation.observation_date,
        observation.available_date,
        type(observation.revision).__name__,
        observation.revision,
        observation.value,
        observation.source,
    )


def _revision_key(revision: Optional[MacroRevision]) -> tuple[str, object]:
    return (type(revision).__name__, revision)


def _sort_key(observation: MacroObservation) -> tuple[object, ...]:
    return (
        observation.indicator,
        observation.observation_date,
        observation.available_date,
        type(observation.revision).__name__,
        str(observation.revision),
        observation.source,
        observation.value,
    )


def _apply_duplicate_rules(
    candidates: Sequence[tuple[int, MacroObservation]],
) -> tuple[list[MacroObservation], dict[int, str]]:
    rejected: dict[int, str] = {}
    exact_groups: dict[tuple[object, ...], list[tuple[int, MacroObservation]]] = {}
    for item in candidates:
        exact_groups.setdefault(_duplicate_key(item[1]), []).append(item)

    retained: list[tuple[int, MacroObservation]] = []
    for group in exact_groups.values():
        retained.append(group[0])
        for index, _ in group[1:]:
            rejected[index] = "duplicate_version"

    observation_groups: dict[tuple[str, str], list[tuple[int, MacroObservation]]] = {}
    for item in retained:
        observation = item[1]
        observation_groups.setdefault(
            (observation.indicator, observation.observation_date), []
        ).append(item)

    accepted: list[MacroObservation] = []
    for group in observation_groups.values():
        if len(group) == 1:
            accepted.append(group[0][1])
            continue
        revisions = [_revision_key(item[1].revision) for item in group]
        has_missing_revision = any(item[1].revision is None for item in group)
        if has_missing_revision or len(set(revisions)) != len(revisions):
            for index, _ in group:
                rejected[index] = "duplicate_observation"
            continue
        accepted.extend(item[1] for item in group)

    return sorted(accepted, key=_sort_key), rejected


def _indicator_diagnostics(
    raw_values: Sequence[Mapping[str, object]],
    valid: Sequence[MacroObservation],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for indicator in MACRO_INDICATORS:
        raw_count = sum(item.get("indicator") == indicator for item in raw_values)
        observations = [item for item in valid if item.indicator == indicator]
        if raw_count == 0 and not observations:
            continue
        observation_dates = sorted(item.observation_date for item in observations)
        available_dates = sorted(item.available_date for item in observations)
        versions = {
            (item.observation_date, type(item.revision).__name__, str(item.revision))
            for item in observations
        }
        result[indicator] = {
            "raw_row_count": int(raw_count),
            "valid_row_count": len(observations),
            "version_count": len(versions),
            "first_observation_date": observation_dates[0] if observation_dates else None,
            "last_observation_date": observation_dates[-1] if observation_dates else None,
            "first_available_date": available_dates[0] if available_dates else None,
            "last_available_date": available_dates[-1] if available_dates else None,
        }
    return result


def _pit_summary(
    observations: Sequence[MacroObservation],
    signal_dates: Iterable[object],
) -> dict[str, object]:
    signals = sorted({_parse_date_only(value) for value in signal_dates})
    if not signals:
        return _empty_pit_summary()

    indicators = sorted({item.indicator for item in observations})
    reason_counts = {code: 0 for code in PIT_REASON_CODES}
    fully_available_count = 0
    partially_available_count = 0
    unavailable_count = 0

    for signal_date in signals:
        eligible_indicators = {
            item.indicator
            for item in observations
            if date.fromisoformat(item.observation_date) <= signal_date
            and date.fromisoformat(item.available_date) <= signal_date
        }
        if indicators and len(eligible_indicators) == len(indicators):
            fully_available_count += 1
        elif eligible_indicators:
            partially_available_count += 1
        else:
            unavailable_count += 1
            reason_counts["no_pit_eligible_record"] += 1

        if any(date.fromisoformat(item.observation_date) > signal_date for item in observations):
            reason_counts["future_observation"] += 1
        if any(
            date.fromisoformat(item.observation_date) <= signal_date
            and date.fromisoformat(item.available_date) > signal_date
            for item in observations
        ):
            reason_counts["future_available_date"] += 1

    return {
        "signal_date_count": len(signals),
        "fully_available_count": fully_available_count,
        "partially_available_count": partially_available_count,
        "unavailable_count": unavailable_count,
        "reason_counts": {
            code: reason_counts[code] for code in PIT_REASON_CODES if reason_counts[code]
        },
    }


def _validate_macro_observations(
    records: Iterable[Union[MacroObservation, Mapping[str, object]]],
    *,
    signal_dates: Iterable[object],
    source: object,
) -> MacroValidationResult:
    safe_source = _safe_source(source) or "unknown"
    raw_records = list(records)
    if not raw_records:
        diagnostics = _base_diagnostics(safe_source)
        diagnostics["pit_summary"] = _pit_summary((), signal_dates)
        return MacroValidationResult(
            status="empty",
            reason_codes=("empty_input",),
            valid_observations=(),
            diagnostics=diagnostics,
        )

    normalized: list[Mapping[str, object]] = []
    candidates: list[tuple[int, MacroObservation]] = []
    rejected: dict[int, str] = {}
    parsed_date_order: list[str] = []
    for index, value in enumerate(raw_records):
        if isinstance(value, MacroObservation):
            mapping = value.to_dict()
        elif isinstance(value, Mapping):
            mapping = dict(value)
        else:
            mapping = {}
            rejected[index] = "invalid_schema"
        normalized.append(mapping)
        if index in rejected:
            continue
        reason = _record_reason(mapping)
        if reason is not None:
            rejected[index] = reason
            continue
        observation = _observation_from_mapping(mapping)
        candidates.append((index, observation))
        parsed_date_order.append(observation.observation_date)

    unsorted = parsed_date_order != sorted(parsed_date_order)
    valid, duplicate_rejections = _apply_duplicate_rules(candidates)
    rejected.update(duplicate_rejections)

    rejected_counts: dict[str, int] = {}
    for reason in rejected.values():
        rejected_counts[reason] = rejected_counts.get(reason, 0) + 1

    reasons = set(rejected_counts)
    if unsorted:
        reasons.add("unsorted_dates")
    if not reasons:
        reasons.add("success")
    ordered_reasons = _ordered_reason_codes(reasons)

    if valid and rejected:
        status = "partial"
    elif valid:
        status = "valid"
    else:
        status = "invalid"

    raw_count = len(raw_records)
    diagnostics: dict[str, object] = {
        "schema_version": 1,
        "validation_mode": "shadow",
        "status": status,
        "reason_codes": list(ordered_reasons),
        "raw_row_count": raw_count,
        "valid_row_count": len(valid),
        "rejected_row_count": len(rejected),
        "coverage_ratio": len(valid) / raw_count,
        "rejected_counts": {
            code: rejected_counts[code] for code in MACRO_REASON_CODES if rejected_counts.get(code)
        },
        "source": safe_source,
        "indicators": _indicator_diagnostics(normalized, valid),
        "pit_summary": _pit_summary(valid, signal_dates),
    }
    return MacroValidationResult(
        status=status,
        reason_codes=ordered_reasons,
        valid_observations=tuple(valid),
        diagnostics=diagnostics,
    )


def validate_macro_observations(
    records: Iterable[Union[MacroObservation, Mapping[str, object]]],
    *,
    signal_dates: Iterable[object] = (),
    source: str = "macro_validator",
) -> MacroValidationResult:
    """Validate records and summarize PIT eligibility without changing inputs."""
    try:
        return _validate_macro_observations(
            records,
            signal_dates=signal_dates,
            source=source,
        )
    except Exception as exc:  # Shadow diagnostics must never become a business failure.
        return _invalid_result(source, exc)
