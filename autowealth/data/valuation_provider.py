"""Provider protocol and deterministic results for historical valuation data."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import (
    Dict,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
    runtime_checkable,
)

from autowealth.data.valuation_schema import (
    VALUATION_REASON_CODES,
    VALUATION_STATUS_REASON_CODES,
    ValuationAvailability,
    ValuationMetric,
    ValuationRecord,
    _canonical_symbol,
    _date_only,
    _sorted_metrics,
    _source,
)

JsonScalar = Union[None, bool, int, float, str]
JsonValue = Union[JsonScalar, List["JsonValue"], Dict[str, "JsonValue"]]

VALUATION_DIAGNOSTICS_SCHEMA_VERSION = 1
VALUATION_DIAGNOSTICS_MAX_DEPTH = 3
VALUATION_DIAGNOSTICS_MAX_MAPPING_KEYS = 32
VALUATION_DIAGNOSTICS_MAX_LIST_LENGTH = 32
VALUATION_DIAGNOSTICS_MAX_STRING_LENGTH = 512
VALUATION_DIAGNOSTICS_MAX_JSON_BYTES = 16 * 1024

_DIAGNOSTIC_FIELDS = {
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
    "exception_type",
    "safe_summary",
}
_REQUIRED_DIAGNOSTIC_FIELDS = _DIAGNOSTIC_FIELDS - {
    "provider_symbol",
    "exception_type",
    "safe_summary",
}
_SENSITIVE_DIAGNOSTIC_KEYS = {
    "api_key",
    "api_token",
    "access_token",
    "refresh_token",
    "client_secret",
    "openai_api_key",
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "bearer_token",
    "secret",
    "token",
}
_SENSITIVE_DIAGNOSTIC_SUFFIXES = (
    "_api_key",
    "_api_token",
    "_access_token",
    "_refresh_token",
    "_client_secret",
    "_authorization",
    "_cookie",
    "_password",
    "_passwd",
    "_bearer_token",
    "_secret",
    "_token",
)
_FORBIDDEN_PAYLOAD_KEYS = {
    "raw_response",
    "response_body",
    "provider_response",
    "payload",
    "records",
    "rows",
    "raw_records",
    "traceback",
    "request_headers",
    "response_headers",
}
_FORBIDDEN_PAYLOAD_SUFFIXES = tuple(f"_{value}" for value in _FORBIDDEN_PAYLOAD_KEYS)
_URL_PATTERN = re.compile(r"(?i)https?://[^\s\"'<>]+")
_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)[A-Z]:[\\/]")
_UNC_ABSOLUTE_PATH = re.compile(r"\\\\[^\\/\s\"'<>]+[\\/]")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?<![#A-Za-z0-9._~/-])/(?!/)(?=[^\s\"'<>])")
_SECRET_VALUE = re.compile(
    r"(?ix)(?:"
    r"\bbearer\s+[^\s,;]+"
    r"|\b(?:"
    r"api(?:[_\s.-]*(?:key|token))"
    r"|openai[_\s.-]*api[_\s.-]*key"
    r"|access[_\s.-]*token"
    r"|refresh[_\s.-]*token"
    r"|client[_\s.-]*secret"
    r"|proxy[_\s.-]*authorization"
    r"|authorization"
    r"|set[_\s.-]*cookie"
    r"|cookie"
    r"|password"
    r"|passwd"
    r"|secret"
    r")\s*[:=]\s*[^\s,;]+"
    r"|https?://[^/@\s:]+:[^@\s]+@"
    r")"
)


def _normalize_diagnostic_key(value: str) -> str:
    candidate = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", value)
    candidate = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", candidate)
    candidate = re.sub(r"[^A-Za-z0-9]+", "_", candidate)
    return candidate.strip("_").lower()


def _is_sensitive_diagnostic_key(value: str) -> bool:
    normalized = _normalize_diagnostic_key(value)
    return normalized in _SENSITIVE_DIAGNOSTIC_KEYS or any(
        normalized.endswith(suffix) for suffix in _SENSITIVE_DIAGNOSTIC_SUFFIXES
    )


def _is_forbidden_payload_key(value: str) -> bool:
    normalized = _normalize_diagnostic_key(value)
    return normalized in _FORBIDDEN_PAYLOAD_KEYS or any(
        normalized.endswith(suffix) for suffix in _FORBIDDEN_PAYLOAD_SUFFIXES
    )


def _contains_absolute_path(value: str) -> bool:
    without_urls = _URL_PATTERN.sub("", value)
    return any(
        pattern.search(without_urls)
        for pattern in (
            _WINDOWS_ABSOLUTE_PATH,
            _UNC_ABSOLUTE_PATH,
            _POSIX_ABSOLUTE_PATH,
        )
    )


def _diagnostic_string(value: str) -> str:
    if len(value) > VALUATION_DIAGNOSTICS_MAX_STRING_LENGTH:
        raise ValueError("diagnostic strings exceed the 512-character limit")
    if _contains_absolute_path(value):
        raise ValueError("diagnostics must not contain absolute paths")
    if _SECRET_VALUE.search(value):
        raise ValueError("diagnostics must not contain credentials")
    return value


def _diagnostic_value(value: object, *, depth: int = 1) -> JsonValue:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, str):
        return _diagnostic_string(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("diagnostics must not contain non-finite numbers")
        return value
    if isinstance(value, (list, tuple)):
        if depth > VALUATION_DIAGNOSTICS_MAX_DEPTH:
            raise ValueError("diagnostics exceed the maximum nesting depth")
        if len(value) > VALUATION_DIAGNOSTICS_MAX_LIST_LENGTH:
            raise ValueError("diagnostic lists exceed the 32-item limit")
        return [_diagnostic_value(item, depth=depth + 1) for item in value]
    if isinstance(value, Mapping):
        if depth > VALUATION_DIAGNOSTICS_MAX_DEPTH:
            raise ValueError("diagnostics exceed the maximum nesting depth")
        if len(value) > VALUATION_DIAGNOSTICS_MAX_MAPPING_KEYS:
            raise ValueError("diagnostic mappings exceed the 32-key limit")
        if not all(isinstance(key, str) for key in value):
            raise ValueError("diagnostic keys must be strings")
        result: Dict[str, JsonValue] = {}
        for key in sorted(value):
            if _is_sensitive_diagnostic_key(key):
                raise ValueError("diagnostics must not contain credentials")
            if _is_forbidden_payload_key(key):
                raise ValueError("diagnostics must not contain raw provider payloads")
            result[key] = _diagnostic_value(value[key], depth=depth + 1)
        return result
    raise ValueError("diagnostics must be JSON-safe")


def _metric_values(values: Sequence[ValuationMetric]) -> list[str]:
    return [item.value for item in values]


def _reason_codes(*values: str) -> list[str]:
    selected = set(values)
    return [code for code in VALUATION_REASON_CODES if code in selected]


def _non_negative_count(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _metric_sequence(value: object, field_name: str) -> Tuple[ValuationMetric, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a valuation metric sequence")
    return _sorted_metrics(value)


def _string_sequence(value: object, field_name: str) -> Tuple[str, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a string sequence")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only strings")
    return tuple(value)


def _mapping_value(value: object, field_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return dict(value)  # type: ignore[arg-type]


@dataclass(frozen=True)
class ValuationDiagnostics:
    """Fixed, bounded diagnostics for a historical valuation request."""

    schema_version: int
    provider: str
    requested_symbol: str
    requested_metrics: Tuple[ValuationMetric, ...]
    requested_start_date: str
    requested_end_date: str
    as_of_date: str
    status: str
    available_metrics: Tuple[ValuationMetric, ...]
    missing_metrics: Tuple[ValuationMetric, ...]
    row_count: int
    accepted_row_count: int
    rejected_row_count: int
    coverage_ratio: float
    reason_codes: Tuple[str, ...]
    reason_counts: Mapping[str, int]
    source_metadata: Mapping[str, JsonValue] = field(default_factory=dict)
    provider_symbol: Optional[str] = None
    exception_type: Optional[str] = None
    safe_summary: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or (
            self.schema_version != VALUATION_DIAGNOSTICS_SCHEMA_VERSION
        ):
            raise ValueError("unsupported valuation diagnostics schema version")
        provider = _source(self.provider)
        requested_symbol = _canonical_symbol(self.requested_symbol)
        provider_symbol = self.provider_symbol
        if provider_symbol is not None:
            if (
                not isinstance(provider_symbol, str)
                or not provider_symbol
                or provider_symbol != provider_symbol.strip()
                or len(provider_symbol) > 128
            ):
                raise ValueError("provider_symbol must be non-empty bounded text")
            provider_symbol = _diagnostic_string(provider_symbol)

        requested = _sorted_metrics(self.requested_metrics)
        available = _sorted_metrics(self.available_metrics)
        missing = _sorted_metrics(self.missing_metrics)
        if not requested:
            raise ValueError("requested_metrics cannot be empty")
        if set(available) - set(requested) or set(missing) - set(requested):
            raise ValueError("diagnostic metrics must be subsets of requested_metrics")
        if set(available) & set(missing):
            raise ValueError("available_metrics and missing_metrics cannot overlap")
        if set(available) | set(missing) != set(requested):
            raise ValueError("diagnostic metrics must partition requested_metrics")
        if self.status == "available" and (missing or set(available) != set(requested)):
            raise ValueError("available diagnostics require all requested metrics")
        if self.status == "partial" and (not available or not missing):
            raise ValueError("partial diagnostics require available and missing metrics")
        if self.status in {"unavailable", "invalid"} and (
            available or set(missing) != set(requested)
        ):
            raise ValueError(f"{self.status} diagnostics require all metrics to be missing")

        start = _date_only(self.requested_start_date, "requested_start_date")
        end = _date_only(self.requested_end_date, "requested_end_date")
        cutoff = _date_only(self.as_of_date, "as_of_date")
        if start > end:
            raise ValueError("requested_start_date cannot be after requested_end_date")

        if self.status not in VALUATION_STATUS_REASON_CODES:
            raise ValueError(f"unsupported valuation diagnostics status: {self.status}")
        if any(reason not in VALUATION_REASON_CODES for reason in self.reason_codes):
            raise ValueError("reason_codes contain unsupported values")
        reasons = tuple(_reason_codes(*self.reason_codes))
        if not reasons:
            raise ValueError("reason_codes cannot be empty")
        if self.status == "available":
            if "success" not in reasons:
                raise ValueError("available diagnostics require success")
        elif "success" in reasons or not any(
            reason in VALUATION_STATUS_REASON_CODES[self.status] for reason in reasons
        ):
            raise ValueError("diagnostic reason codes do not match status")

        row_count = _non_negative_count(self.row_count, "row_count")
        accepted_count = _non_negative_count(self.accepted_row_count, "accepted_row_count")
        rejected_count = _non_negative_count(self.rejected_row_count, "rejected_row_count")
        if row_count != accepted_count + rejected_count:
            raise ValueError("row_count must equal accepted_row_count plus rejected_row_count")
        if self.status in {"available", "partial"} and accepted_count == 0:
            raise ValueError(f"{self.status} diagnostics require accepted records")
        if self.status in {"unavailable", "invalid"} and accepted_count:
            raise ValueError(f"{self.status} diagnostics cannot contain accepted records")

        if isinstance(self.coverage_ratio, bool):
            raise ValueError("coverage_ratio must be a finite number")
        try:
            coverage_ratio = float(self.coverage_ratio)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("coverage_ratio must be a finite number") from exc
        expected_coverage = len(available) / len(requested)
        if not math.isfinite(coverage_ratio) or not math.isclose(
            coverage_ratio, expected_coverage, rel_tol=0.0, abs_tol=1e-12
        ):
            raise ValueError("coverage_ratio must match available metric coverage")

        if not isinstance(self.reason_counts, Mapping):
            raise ValueError("reason_counts must be a mapping")
        normalized_reason_counts: dict[str, int] = {}
        for reason in VALUATION_REASON_CODES:
            if reason not in self.reason_counts:
                continue
            if reason not in reasons:
                raise ValueError("reason_counts keys must be listed in reason_codes")
            normalized_reason_counts[reason] = _non_negative_count(
                self.reason_counts[reason], f"reason_counts.{reason}"
            )
        if set(self.reason_counts) - set(VALUATION_REASON_CODES):
            raise ValueError("reason_counts contain unsupported reason codes")

        metadata = _diagnostic_value(self.source_metadata, depth=1)
        if not isinstance(metadata, dict):
            raise ValueError("source_metadata must be a JSON object")

        exception_type = self.exception_type
        safe_summary = self.safe_summary
        if (exception_type is None) != (safe_summary is None):
            raise ValueError("exception_type and safe_summary must be supplied together")
        if exception_type is not None:
            if not isinstance(exception_type, str) or not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_.]{0,127}", exception_type
            ):
                raise ValueError("exception_type must be a bounded class name")
            safe_summary = _diagnostic_string(str(safe_summary))
            if not {"provider_exception", "invalid_schema"} & set(reasons):
                raise ValueError("exception diagnostics require a matching reason code")

        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "requested_symbol", requested_symbol)
        object.__setattr__(self, "provider_symbol", provider_symbol)
        object.__setattr__(self, "requested_metrics", requested)
        object.__setattr__(self, "available_metrics", available)
        object.__setattr__(self, "missing_metrics", missing)
        object.__setattr__(self, "requested_start_date", start)
        object.__setattr__(self, "requested_end_date", end)
        object.__setattr__(self, "as_of_date", cutoff)
        object.__setattr__(self, "row_count", row_count)
        object.__setattr__(self, "accepted_row_count", accepted_count)
        object.__setattr__(self, "rejected_row_count", rejected_count)
        object.__setattr__(self, "coverage_ratio", coverage_ratio)
        object.__setattr__(self, "reason_codes", reasons)
        object.__setattr__(self, "reason_counts", normalized_reason_counts)
        object.__setattr__(self, "source_metadata", metadata)
        object.__setattr__(self, "exception_type", exception_type)
        object.__setattr__(self, "safe_summary", safe_summary)

        encoded = json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > VALUATION_DIAGNOSTICS_MAX_JSON_BYTES:
            raise ValueError("valuation diagnostics exceed the 16 KiB JSON limit")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "ValuationDiagnostics":
        if not isinstance(value, Mapping):
            raise ValueError("diagnostics must be a JSON object")
        if len(value) > VALUATION_DIAGNOSTICS_MAX_MAPPING_KEYS:
            raise ValueError("diagnostic mappings exceed the 32-key limit")
        if not all(isinstance(key, str) for key in value):
            raise ValueError("diagnostic keys must be strings")

        normalized: dict[str, JsonValue] = {}
        for key in sorted(value):
            if _is_sensitive_diagnostic_key(key):
                raise ValueError("diagnostics must not contain credentials")
            if _is_forbidden_payload_key(key):
                raise ValueError("diagnostics must not contain raw provider payloads")
            normalized[key] = _diagnostic_value(value[key], depth=1)

        unknown = set(normalized) - _DIAGNOSTIC_FIELDS
        missing = _REQUIRED_DIAGNOSTIC_FIELDS - set(normalized)
        if unknown:
            raise ValueError(f"unsupported valuation diagnostics fields: {sorted(unknown)}")
        if missing:
            raise ValueError(f"missing valuation diagnostics fields: {sorted(missing)}")

        return cls(
            schema_version=normalized["schema_version"],  # type: ignore[arg-type]
            provider=normalized["provider"],  # type: ignore[arg-type]
            requested_symbol=normalized["requested_symbol"],  # type: ignore[arg-type]
            provider_symbol=normalized.get("provider_symbol"),  # type: ignore[arg-type]
            requested_metrics=_metric_sequence(
                normalized["requested_metrics"], "requested_metrics"
            ),
            requested_start_date=normalized["requested_start_date"],  # type: ignore[arg-type]
            requested_end_date=normalized["requested_end_date"],  # type: ignore[arg-type]
            as_of_date=normalized["as_of_date"],  # type: ignore[arg-type]
            status=normalized["status"],  # type: ignore[arg-type]
            available_metrics=_metric_sequence(
                normalized["available_metrics"], "available_metrics"
            ),
            missing_metrics=_metric_sequence(normalized["missing_metrics"], "missing_metrics"),
            row_count=normalized["row_count"],  # type: ignore[arg-type]
            accepted_row_count=normalized["accepted_row_count"],  # type: ignore[arg-type]
            rejected_row_count=normalized["rejected_row_count"],  # type: ignore[arg-type]
            coverage_ratio=normalized["coverage_ratio"],  # type: ignore[arg-type]
            reason_codes=_string_sequence(normalized["reason_codes"], "reason_codes"),
            reason_counts=_mapping_value(normalized["reason_counts"], "reason_counts"),
            source_metadata=_mapping_value(normalized["source_metadata"], "source_metadata"),
            exception_type=normalized.get("exception_type"),  # type: ignore[arg-type]
            safe_summary=normalized.get("safe_summary"),  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "requested_symbol": self.requested_symbol,
            "provider_symbol": self.provider_symbol,
            "requested_metrics": _metric_values(self.requested_metrics),
            "requested_start_date": self.requested_start_date,
            "requested_end_date": self.requested_end_date,
            "as_of_date": self.as_of_date,
            "status": self.status,
            "available_metrics": _metric_values(self.available_metrics),
            "missing_metrics": _metric_values(self.missing_metrics),
            "row_count": self.row_count,
            "accepted_row_count": self.accepted_row_count,
            "rejected_row_count": self.rejected_row_count,
            "coverage_ratio": self.coverage_ratio,
            "reason_codes": list(self.reason_codes),
            "reason_counts": dict(self.reason_counts),
            "source_metadata": dict(self.source_metadata),
        }
        if self.exception_type is not None:
            result["exception_type"] = self.exception_type
            result["safe_summary"] = self.safe_summary
        return result


def _request_context(
    *,
    requested_symbol: str,
    requested_metrics: Sequence[ValuationMetric],
    start_date: Union[str, date],
    end_date: Union[str, date],
    as_of_date: Union[str, date],
    source: str,
) -> tuple[str, Tuple[ValuationMetric, ...], str, str, str, str]:
    symbol = _canonical_symbol(requested_symbol)
    metrics = _sorted_metrics(requested_metrics)
    if not metrics:
        raise ValueError("requested_metrics cannot be empty")
    start = _date_only(start_date, "start_date")
    end = _date_only(end_date, "end_date")
    if start > end:
        raise ValueError("start_date cannot be after end_date")
    cutoff = _date_only(as_of_date, "as_of_date")
    return symbol, metrics, start, end, cutoff, _source(source)


def _exception_fields(
    exception: Optional[BaseException],
    reason_code: str,
) -> tuple[Optional[str], Optional[str]]:
    if exception is None:
        return None, None
    if reason_code not in {"provider_exception", "invalid_schema"}:
        raise ValueError("exception details require provider_exception or invalid_schema")
    return (
        type(exception).__name__[:128],
        "valuation provider exception details were omitted for safe diagnostics",
    )


@dataclass(frozen=True)
class ValuationProviderResult:
    """Historical valuation records plus fixed, bounded diagnostics."""

    records: Tuple[ValuationRecord, ...]
    availability: ValuationAvailability
    diagnostics: Union[ValuationDiagnostics, Mapping[str, object]]

    def __post_init__(self) -> None:
        if not isinstance(self.availability, ValuationAvailability):
            raise ValueError("availability must be a ValuationAvailability")
        if not all(isinstance(item, ValuationRecord) for item in self.records):
            raise ValueError("records must contain only ValuationRecord values")
        records = tuple(
            sorted(
                self.records,
                key=lambda item: (
                    item.symbol,
                    item.metric.value,
                    item.observation_date,
                    item.available_date,
                    type(item.revision).__name__,
                    str(item.revision),
                ),
            )
        )
        diagnostics = (
            self.diagnostics
            if isinstance(self.diagnostics, ValuationDiagnostics)
            else ValuationDiagnostics.from_mapping(self.diagnostics)
        )

        availability = self.availability
        if diagnostics.status != availability.status:
            raise ValueError("diagnostic status must match availability")
        if diagnostics.provider != availability.source:
            raise ValueError("diagnostic provider must match availability source")
        if diagnostics.as_of_date != availability.as_of_date:
            raise ValueError("diagnostic as_of_date must match availability")
        if diagnostics.requested_metrics != availability.requested_metrics:
            raise ValueError("diagnostic requested_metrics must match availability")
        if diagnostics.available_metrics != availability.available_metrics:
            raise ValueError("diagnostic available_metrics must match availability")
        if diagnostics.missing_metrics != availability.missing_metrics:
            raise ValueError("diagnostic missing_metrics must match availability")
        if availability.reason_code not in diagnostics.reason_codes:
            raise ValueError("availability reason_code must be present in diagnostics")
        if diagnostics.accepted_row_count != len(records):
            raise ValueError("accepted_row_count must equal returned record count")

        available_metrics = set(availability.available_metrics)
        for record in records:
            if record.symbol != diagnostics.requested_symbol:
                raise ValueError("record symbol must match requested_symbol")
            if record.metric not in available_metrics:
                raise ValueError("record metric must be listed in available_metrics")
            if not (
                diagnostics.requested_start_date
                <= record.observation_date
                <= diagnostics.requested_end_date
            ):
                raise ValueError("record observation_date is outside the requested window")
            if record.available_date > diagnostics.as_of_date:
                raise ValueError("returned records must be available by as_of_date")

        represented_metrics = {item.metric for item in records}
        if availability.status in {"available", "partial"}:
            if not records or represented_metrics != available_metrics:
                raise ValueError(
                    f"{availability.status} results require records for every available metric"
                )
        elif records:
            raise ValueError(f"{availability.status} results cannot contain records")

        object.__setattr__(self, "records", records)
        object.__setattr__(self, "diagnostics", diagnostics.to_dict())

    @classmethod
    def from_records(
        cls,
        records: Sequence[ValuationRecord],
        *,
        requested_symbol: str,
        requested_metrics: Sequence[ValuationMetric],
        start_date: Union[str, date],
        end_date: Union[str, date],
        as_of_date: Union[str, date],
        source: str,
        provider_symbol: Optional[str] = None,
        source_metadata: Optional[Mapping[str, object]] = None,
    ) -> "ValuationProviderResult":
        symbol, requested, start, end, cutoff, safe_source = _request_context(
            requested_symbol=requested_symbol,
            requested_metrics=requested_metrics,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            source=source,
        )
        normalized_records = tuple(records)
        if not all(isinstance(item, ValuationRecord) for item in normalized_records):
            raise ValueError("records must contain only ValuationRecord values")
        requested_set = set(requested)
        for record in normalized_records:
            if record.symbol != symbol:
                raise ValueError("record symbol must match requested_symbol")
            if record.metric not in requested_set:
                raise ValueError("record metric is outside requested_metrics")
            if not start <= record.observation_date <= end:
                raise ValueError("record observation_date is outside the requested window")

        eligible = tuple(item for item in normalized_records if item.available_date <= cutoff)
        future_count = len(normalized_records) - len(eligible)
        available = _sorted_metrics(item.metric for item in eligible)
        available_set = set(available)
        missing = tuple(item for item in requested if item not in available_set)

        if len(available) == len(requested):
            status = "available"
            reason_code = "success"
        elif available:
            status = "partial"
            reason_code = (
                "future_available_date" if future_count else "historical_valuation_unavailable"
            )
        elif normalized_records and future_count:
            status = "unavailable"
            reason_code = "future_available_date"
        else:
            status = "unavailable"
            reason_code = "empty_response"

        availability = ValuationAvailability(
            status=status,
            reason_code=reason_code,
            requested_metrics=requested,
            available_metrics=available,
            missing_metrics=missing,
            as_of_date=cutoff,
            source=safe_source,
        )
        reasons = [reason_code]
        if future_count and reason_code != "future_available_date":
            reasons.append("future_available_date")
        reason_counts: dict[str, int] = {}
        if future_count:
            reason_counts["future_available_date"] = future_count
        if reason_code not in {"success", "future_available_date"}:
            reason_counts[reason_code] = max(1, len(missing))

        diagnostics = ValuationDiagnostics(
            schema_version=VALUATION_DIAGNOSTICS_SCHEMA_VERSION,
            provider=safe_source,
            requested_symbol=symbol,
            provider_symbol=provider_symbol,
            requested_metrics=requested,
            requested_start_date=start,
            requested_end_date=end,
            as_of_date=cutoff,
            status=status,
            available_metrics=available,
            missing_metrics=missing,
            row_count=len(normalized_records),
            accepted_row_count=len(eligible),
            rejected_row_count=future_count,
            coverage_ratio=len(available) / len(requested),
            reason_codes=tuple(reasons),
            reason_counts=reason_counts,
            source_metadata=dict(source_metadata or {}),
        )
        return cls(records=eligible, availability=availability, diagnostics=diagnostics)

    @classmethod
    def available(
        cls,
        records: Sequence[ValuationRecord],
        **request_context: object,
    ) -> "ValuationProviderResult":
        result = cls.from_records(records, **request_context)  # type: ignore[arg-type]
        if result.availability.status != "available":
            raise ValueError("available factory requires complete requested metric coverage")
        return result

    @classmethod
    def partial(
        cls,
        records: Sequence[ValuationRecord],
        **request_context: object,
    ) -> "ValuationProviderResult":
        result = cls.from_records(records, **request_context)  # type: ignore[arg-type]
        if result.availability.status != "partial":
            raise ValueError("partial factory requires partial requested metric coverage")
        return result

    @classmethod
    def _empty_result(
        cls,
        *,
        status: str,
        requested_symbol: str,
        requested_metrics: Sequence[ValuationMetric],
        start_date: Union[str, date],
        end_date: Union[str, date],
        as_of_date: Union[str, date],
        source: str,
        reason_code: str,
        provider_symbol: Optional[str],
        source_metadata: Optional[Mapping[str, object]],
        exception: Optional[BaseException],
    ) -> "ValuationProviderResult":
        symbol, requested, start, end, cutoff, safe_source = _request_context(
            requested_symbol=requested_symbol,
            requested_metrics=requested_metrics,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            source=source,
        )
        availability = ValuationAvailability(
            status=status,
            reason_code=reason_code,
            requested_metrics=requested,
            available_metrics=(),
            missing_metrics=requested,
            as_of_date=cutoff,
            source=safe_source,
        )
        exception_type, safe_summary = _exception_fields(exception, reason_code)
        diagnostics = ValuationDiagnostics(
            schema_version=VALUATION_DIAGNOSTICS_SCHEMA_VERSION,
            provider=safe_source,
            requested_symbol=symbol,
            provider_symbol=provider_symbol,
            requested_metrics=requested,
            requested_start_date=start,
            requested_end_date=end,
            as_of_date=cutoff,
            status=status,
            available_metrics=(),
            missing_metrics=requested,
            row_count=0,
            accepted_row_count=0,
            rejected_row_count=0,
            coverage_ratio=0.0,
            reason_codes=(reason_code,),
            reason_counts={reason_code: 1},
            source_metadata=dict(source_metadata or {}),
            exception_type=exception_type,
            safe_summary=safe_summary,
        )
        return cls(records=(), availability=availability, diagnostics=diagnostics)

    @classmethod
    def unavailable(
        cls,
        *,
        requested_symbol: str,
        requested_metrics: Sequence[ValuationMetric],
        start_date: Union[str, date],
        end_date: Union[str, date],
        as_of_date: Union[str, date],
        source: str,
        reason_code: str,
        provider_symbol: Optional[str] = None,
        source_metadata: Optional[Mapping[str, object]] = None,
        exception: Optional[BaseException] = None,
    ) -> "ValuationProviderResult":
        return cls._empty_result(
            status="unavailable",
            requested_symbol=requested_symbol,
            requested_metrics=requested_metrics,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            source=source,
            reason_code=reason_code,
            provider_symbol=provider_symbol,
            source_metadata=source_metadata,
            exception=exception,
        )

    @classmethod
    def invalid(
        cls,
        *,
        requested_symbol: str,
        requested_metrics: Sequence[ValuationMetric],
        start_date: Union[str, date],
        end_date: Union[str, date],
        as_of_date: Union[str, date],
        source: str,
        reason_code: str,
        provider_symbol: Optional[str] = None,
        source_metadata: Optional[Mapping[str, object]] = None,
        exception: Optional[BaseException] = None,
    ) -> "ValuationProviderResult":
        return cls._empty_result(
            status="invalid",
            requested_symbol=requested_symbol,
            requested_metrics=requested_metrics,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
            source=source,
            reason_code=reason_code,
            provider_symbol=provider_symbol,
            source_metadata=source_metadata,
            exception=exception,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "records": [item.to_dict() for item in self.records],
            "availability": self.availability.to_dict(),
            "diagnostics": dict(self.diagnostics),
        }


@runtime_checkable
class HistoricalValuationProvider(Protocol):
    """Interface for a future point-in-time historical valuation source."""

    def provider_symbol(self, canonical_symbol: str) -> str: ...

    def supports_metric(self, metric: ValuationMetric) -> bool: ...

    def fetch_historical_valuation(
        self,
        symbol: str,
        metric: ValuationMetric,
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> ValuationProviderResult: ...

    def source_metadata(self) -> Mapping[str, JsonValue]: ...
