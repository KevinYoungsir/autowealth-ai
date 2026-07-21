"""Resilient benchmark provider chain and cache-first loader."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import isclose, isfinite
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

import pandas as pd

from autowealth.data.cache import ParquetCache
from autowealth.data.index_provider import (
    IndexDataProvider,
    UnsupportedIndexEndpointError,
    canonical_index_symbol,
    default_index_providers,
)
from autowealth.data.index_quality import (
    MIN_BENCHMARK_COVERAGE_RATIO,
    BenchmarkQualityResult,
    validate_benchmark_data,
    validate_minimum_coverage_ratio,
)
from autowealth.data.schema import normalize_market_data

MAX_DIAGNOSTIC_REASON_LENGTH = 500
CACHE_LAYOUT_VERSION = 2
CACHE_METADATA_MISMATCH = "cache_metadata_mismatch"


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    endpoint: str
    canonical_symbol: str
    provider_symbol: str
    status: str
    started_at: str
    completed_at: str
    row_count: int = 0
    first_date: Optional[str] = None
    last_date: Optional[str] = None
    coverage_ratio: Optional[float] = None
    reason_code: str = "provider_exception"
    reason: str = ""
    exception_type: Optional[str] = None
    source_metadata: dict[str, Any] = field(default_factory=dict)
    requested_symbol: str = ""
    requested_start_date: str = ""
    requested_end_date: str = ""
    minimum_coverage_ratio: Optional[float] = None
    exception: Optional[str] = None

    @property
    def rows(self) -> int:
        return self.row_count

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rows"] = self.rows
        return payload


@dataclass(frozen=True)
class IndexProviderResult:
    data: pd.DataFrame = field(repr=False)
    canonical_symbol: str
    selected_provider: str
    selected_endpoint: str
    attempts: tuple[ProviderAttempt, ...]
    quality: BenchmarkQualityResult = field(repr=False)


@dataclass(frozen=True)
class BenchmarkLoadResult:
    status: str
    data: pd.DataFrame = field(repr=False)
    canonical_symbol: str
    diagnostic: dict[str, Any]
    source_record: dict[str, Any]
    warnings: tuple[str, ...] = ()
    reason_code: Optional[str] = None
    reason: Optional[str] = None


class IndexProviderChainError(RuntimeError):
    """Raised after every configured provider has failed validation."""

    def __init__(
        self,
        canonical_symbol: str,
        attempts: Sequence[ProviderAttempt],
    ) -> None:
        self.canonical_symbol = canonical_symbol
        self.attempts = tuple(attempts)
        codes = ", ".join(attempt.reason_code for attempt in attempts) or "none"
        super().__init__(f"all benchmark providers failed ({codes})")


class IndexProviderChain:
    """Try index providers in order and select the first valid response."""

    def __init__(
        self,
        providers: Sequence[IndexDataProvider],
        *,
        minimum_coverage_ratio: float = MIN_BENCHMARK_COVERAGE_RATIO,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if not providers:
            raise ValueError("index provider chain cannot be empty")
        self.providers = tuple(providers)
        self.minimum_coverage_ratio = validate_minimum_coverage_ratio(minimum_coverage_ratio)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def get_daily(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        return self.fetch_daily(symbol, start_date, end_date).data

    def fetch_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> IndexProviderResult:
        canonical = canonical_index_symbol(symbol)
        requested_symbol = str(symbol)
        requested_start_date = _required_date_text(start_date)
        requested_end_date = _required_date_text(end_date)
        attempts: list[ProviderAttempt] = []
        for position, provider in enumerate(self.providers):
            attempt, quality = self._attempt(
                provider,
                canonical,
                requested_symbol,
                requested_start_date,
                requested_end_date,
                position,
            )
            attempts.append(attempt)
            if quality is not None and quality.passed:
                return IndexProviderResult(
                    data=quality.data,
                    canonical_symbol=canonical,
                    selected_provider=attempt.provider,
                    selected_endpoint=attempt.endpoint,
                    attempts=tuple(attempts),
                    quality=quality,
                )
        raise IndexProviderChainError(canonical, attempts)

    def _attempt(
        self,
        provider: IndexDataProvider,
        canonical_symbol: str,
        requested_symbol: str,
        requested_start_date: str,
        requested_end_date: str,
        position: int,
    ) -> tuple[ProviderAttempt, Optional[BenchmarkQualityResult]]:
        provider_name = str(getattr(provider, "provider_name", provider.__class__.__name__))
        endpoint = str(getattr(provider, "endpoint", "get_daily"))
        started = _utc_text(self._clock())
        role = "primary" if position == 0 else "fallback"
        try:
            provider_symbol = _provider_symbol(provider, canonical_symbol)
        except Exception as exc:
            return (
                _exception_attempt(
                    provider_name,
                    endpoint,
                    canonical_symbol,
                    "",
                    started,
                    _utc_text(self._clock()),
                    role,
                    "provider_exception",
                    exc,
                    requested_symbol=requested_symbol,
                    requested_start_date=requested_start_date,
                    requested_end_date=requested_end_date,
                    minimum_coverage_ratio=self.minimum_coverage_ratio,
                    source_metadata={
                        "chain_position": position,
                        "failure_stage": "symbol_resolution",
                    },
                ),
                None,
            )
        try:
            raw = provider.get_daily(
                canonical_symbol,
                requested_start_date,
                requested_end_date,
            )
            quality = validate_benchmark_data(
                raw,
                requested_start_date,
                requested_end_date,
                minimum_coverage_ratio=self.minimum_coverage_ratio,
            )
        except Exception as exc:
            reason_code = (
                "unsupported_endpoint"
                if isinstance(exc, UnsupportedIndexEndpointError)
                else "provider_exception"
            )
            return (
                _exception_attempt(
                    provider_name,
                    endpoint,
                    canonical_symbol,
                    provider_symbol,
                    started,
                    _utc_text(self._clock()),
                    role,
                    reason_code,
                    exc,
                    requested_symbol=requested_symbol,
                    requested_start_date=requested_start_date,
                    requested_end_date=requested_end_date,
                    minimum_coverage_ratio=self.minimum_coverage_ratio,
                    source_metadata={
                        "chain_position": position,
                        "failure_stage": "provider_request",
                    },
                ),
                None,
            )

        attempt = ProviderAttempt(
            provider=provider_name,
            endpoint=endpoint,
            canonical_symbol=canonical_symbol,
            provider_symbol=provider_symbol,
            status="success" if quality.passed else "failed",
            started_at=started,
            completed_at=_utc_text(self._clock()),
            row_count=quality.raw_row_count,
            first_date=quality.first_date,
            last_date=quality.last_date,
            coverage_ratio=quality.coverage_ratio,
            reason_code=quality.reason_code,
            reason=_sanitize_reason(quality.reason),
            source_metadata={
                "chain_position": position,
                "role": role,
                **quality.audit_metadata(),
            },
            requested_symbol=requested_symbol,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            minimum_coverage_ratio=self.minimum_coverage_ratio,
        )
        return attempt, quality


def load_benchmark_with_cache(
    cache_directory: str | Path,
    provider_chain: IndexProviderChain,
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    clock: Optional[Callable[[], datetime]] = None,
) -> BenchmarkLoadResult:
    """Load one benchmark from a validated cache or the provider chain."""
    canonical = canonical_index_symbol(symbol)
    requested_symbol = str(symbol)
    requested_start_date = _required_date_text(start_date)
    requested_end_date = _required_date_text(end_date)
    now = clock or (lambda: datetime.now(timezone.utc))
    cache = ParquetCache(Path(cache_directory))
    cache_symbol = f"benchmark_{canonical}"
    cache_path = cache.path_for(
        cache_symbol,
        requested_start_date,
        requested_end_date,
        "none",
    )
    metadata_path = cache_path.with_suffix(".meta.json")
    attempts: list[ProviderAttempt] = []
    warnings: list[str] = []
    cache_status = "miss"

    if _cache_entry_exists(cache_path, metadata_path):
        cache_status = "invalid_preserved"
        cache_attempt, cache_quality = _read_validated_cache(
            cache,
            cache_path,
            metadata_path,
            canonical,
            cache_symbol,
            requested_symbol,
            requested_start_date,
            requested_end_date,
            provider_chain.minimum_coverage_ratio,
            now,
        )
        attempts.append(cache_attempt)
        if cache_attempt.status == "success" and cache_quality is not None:
            cached_provider = str(
                cache_attempt.source_metadata.get("cached_source") or "unknown_cached_source"
            )
            cached_endpoint = str(
                cache_attempt.source_metadata.get("cached_endpoint") or "unknown_cached_endpoint"
            )
            diagnostic = _benchmark_diagnostic(
                "success",
                canonical,
                cached_provider,
                cached_endpoint,
                cache_quality,
                "hit_valid",
                attempts,
                requested_symbol=requested_symbol,
                requested_start_date=requested_start_date,
                requested_end_date=requested_end_date,
                minimum_coverage_ratio=provider_chain.minimum_coverage_ratio,
            )
            return BenchmarkLoadResult(
                status="success",
                data=cache_quality.data,
                canonical_symbol=canonical,
                diagnostic=diagnostic,
                source_record=_source_record(diagnostic, cache_path),
            )
        warnings.append(f"benchmark {canonical} cache rejected: {cache_attempt.reason_code}")

    try:
        provider_result = provider_chain.fetch_daily(
            requested_symbol,
            requested_start_date,
            requested_end_date,
        )
    except IndexProviderChainError as exc:
        attempts.extend(exc.attempts)
        warnings.extend(_failed_attempt_warnings(canonical, exc.attempts))
        reason_code = exc.attempts[-1].reason_code if exc.attempts else "provider_exception"
        reason = exc.attempts[-1].reason if exc.attempts else _sanitize_reason(str(exc))
        diagnostic = _benchmark_diagnostic(
            "unavailable",
            canonical,
            None,
            None,
            None,
            cache_status,
            attempts,
            requested_symbol=requested_symbol,
            requested_start_date=requested_start_date,
            requested_end_date=requested_end_date,
            minimum_coverage_ratio=provider_chain.minimum_coverage_ratio,
            reason_code=reason_code,
            reason=reason,
        )
        return BenchmarkLoadResult(
            status="unavailable",
            data=pd.DataFrame(),
            canonical_symbol=canonical,
            diagnostic=diagnostic,
            source_record=_source_record(diagnostic, cache_path),
            warnings=tuple(warnings),
            reason_code=reason_code,
            reason=reason,
        )

    attempts.extend(provider_result.attempts)
    warnings.extend(_failed_attempt_warnings(canonical, provider_result.attempts))
    if _cache_entry_exists(cache_path, metadata_path):
        cache_status = "invalid_preserved"
    else:
        try:
            _write_benchmark_cache(
                cache_path,
                metadata_path,
                provider_result,
                requested_start_date,
                requested_end_date,
                now(),
            )
            cache_status = "written"
        except Exception as exc:
            cache_status = "write_failed"
            warnings.append(
                f"benchmark {canonical} cache write failed: {_sanitize_reason(str(exc))}"
            )

    diagnostic = _benchmark_diagnostic(
        "success",
        canonical,
        provider_result.selected_provider,
        provider_result.selected_endpoint,
        provider_result.quality,
        cache_status,
        attempts,
        requested_symbol=requested_symbol,
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        minimum_coverage_ratio=provider_chain.minimum_coverage_ratio,
    )
    return BenchmarkLoadResult(
        status="success",
        data=provider_result.data,
        canonical_symbol=canonical,
        diagnostic=diagnostic,
        source_record=_source_record(diagnostic, cache_path),
        warnings=tuple(warnings),
    )


def _read_validated_cache(
    cache: ParquetCache,
    cache_path: Path,
    metadata_path: Path,
    canonical_symbol: str,
    cache_symbol: str,
    requested_symbol: str,
    requested_start_date: str,
    requested_end_date: str,
    minimum_coverage_ratio: float,
    clock: Callable[[], datetime],
) -> tuple[ProviderAttempt, Optional[BenchmarkQualityResult]]:
    started = _utc_text(clock())
    try:
        metadata = _read_metadata(metadata_path)
        data_path = _cache_data_path(cache_path, metadata_path, metadata)
        if data_path == cache_path:
            raw = cache.read(
                cache_symbol,
                requested_start_date,
                requested_end_date,
                "none",
            )
        else:
            raw = normalize_market_data(pd.read_parquet(data_path))
    except Exception as exc:
        return (
            _exception_attempt(
                "ParquetCache",
                "local_parquet",
                canonical_symbol,
                cache_symbol,
                started,
                _utc_text(clock()),
                "cache",
                "cache_unreadable",
                exc,
                requested_symbol=requested_symbol,
                requested_start_date=requested_start_date,
                requested_end_date=requested_end_date,
                minimum_coverage_ratio=minimum_coverage_ratio,
                source_metadata={"failure_stage": "cache_read"},
            ),
            None,
        )

    quality = validate_benchmark_data(
        raw,
        requested_start_date,
        requested_end_date,
        minimum_coverage_ratio=minimum_coverage_ratio,
    )
    metadata_errors = _cache_metadata_errors(
        metadata,
        data_path,
        canonical_symbol,
        requested_start_date,
        requested_end_date,
        quality,
    )
    passed = quality.passed and not metadata_errors
    reason_code = _cache_reason_code(quality, metadata_errors)
    reason = (
        "benchmark cache passed validation"
        if passed
        else "; ".join(metadata_errors) or quality.reason
    )
    attempt = ProviderAttempt(
        provider="ParquetCache",
        endpoint="local_parquet",
        canonical_symbol=canonical_symbol,
        provider_symbol=cache_symbol,
        status="success" if passed else "failed",
        started_at=started,
        completed_at=_utc_text(clock()),
        row_count=quality.raw_row_count,
        first_date=quality.first_date,
        last_date=quality.last_date,
        coverage_ratio=quality.coverage_ratio,
        reason_code="cache_hit" if passed else reason_code,
        reason=_sanitize_reason(reason),
        source_metadata={
            "role": "cache",
            "cached_source": metadata.get("source"),
            "cached_endpoint": metadata.get("endpoint"),
            "cached_minimum_coverage_ratio": metadata.get("minimum_coverage_ratio"),
            "cache_layout_version": metadata.get("cache_layout_version", 1),
            "cache_data_file": data_path.name,
            "quality_reason_code": quality.reason_code,
            "metadata_errors": metadata_errors,
            **quality.audit_metadata(),
        },
        requested_symbol=requested_symbol,
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        minimum_coverage_ratio=minimum_coverage_ratio,
    )
    return attempt, quality if passed else None


def _read_metadata(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("benchmark cache metadata must be a JSON object")
    return value


def _cache_entry_exists(cache_path: Path, metadata_path: Path) -> bool:
    return cache_path.exists() or metadata_path.exists()


def _cache_data_path(
    legacy_cache_path: Path,
    metadata_path: Path,
    metadata: Mapping[str, Any],
) -> Path:
    data_file = metadata.get("data_file")
    if data_file in (None, ""):
        return legacy_cache_path
    name = str(data_file)
    if Path(name).name != name or Path(name).is_absolute():
        raise ValueError("benchmark cache metadata data_file is unsafe")
    parent = metadata_path.parent.resolve(strict=False)
    candidate = (parent / name).resolve(strict=False)
    if candidate.parent != parent or candidate.suffix != ".parquet":
        raise ValueError("benchmark cache metadata data_file is invalid")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"benchmark cache generation is missing: {name}")
    return candidate


def _cache_reason_code(
    quality: BenchmarkQualityResult,
    metadata_errors: Sequence[str],
) -> str:
    if any("sha256 mismatch" in error for error in metadata_errors):
        return "cache_sha_mismatch"
    if quality.reason_code == "insufficient_coverage":
        return "cache_insufficient_coverage"
    metadata_only_errors = [
        error for error in metadata_errors if not error.startswith("cache quality failed:")
    ]
    if metadata_only_errors:
        return CACHE_METADATA_MISMATCH
    return "cache_unreadable"


def _cache_metadata_errors(
    metadata: Mapping[str, Any],
    data_path: Path,
    canonical_symbol: str,
    start_date: str,
    end_date: str,
    quality: BenchmarkQualityResult,
) -> list[str]:
    errors: list[str] = []
    cache_layout_version = _optional_int(metadata.get("cache_layout_version")) or 1
    if str(metadata.get("symbol") or "") != canonical_symbol:
        errors.append("cache metadata symbol mismatch")
    if _metadata_date(metadata, "fetch_start_date", "start_date") != _date_text(start_date):
        errors.append("cache metadata fetch_start_date mismatch")
    if _metadata_date(metadata, "fetch_end_date", "end_date") != _date_text(end_date):
        errors.append("cache metadata fetch_end_date mismatch")
    if str(metadata.get("sha256") or "") != _sha256(data_path):
        errors.append("cache metadata sha256 mismatch")
    if _optional_int(metadata.get("rows")) != quality.clean_row_count:
        errors.append("cache metadata row count mismatch")
    if _metadata_date(metadata, "first_date", "actual_start_date") != quality.first_date:
        errors.append("cache metadata first_date mismatch")
    if _metadata_date(metadata, "last_date", "actual_end_date") != quality.last_date:
        errors.append("cache metadata last_date mismatch")
    if not str(metadata.get("source") or "").strip():
        errors.append("cache metadata source is missing")
    source_fingerprint = metadata.get("source_fingerprint")
    expected_source_fingerprint = _source_fingerprint(
        metadata.get("source"),
        metadata.get("endpoint"),
    )
    if cache_layout_version >= CACHE_LAYOUT_VERSION and (
        source_fingerprint in (None, "") or str(source_fingerprint) != expected_source_fingerprint
    ):
        errors.append("cache metadata source mismatch")
    metadata_coverage = _optional_float(metadata.get("coverage_ratio"))
    if cache_layout_version >= CACHE_LAYOUT_VERSION and metadata_coverage is None:
        errors.append("cache metadata coverage ratio is missing or invalid")
    elif metadata_coverage is not None and (
        quality.coverage_ratio is None
        or not isclose(metadata_coverage, quality.coverage_ratio, rel_tol=1e-9, abs_tol=1e-12)
    ):
        errors.append("cache metadata coverage ratio mismatch")
    expected_fingerprint = metadata.get("metadata_fingerprint")
    if cache_layout_version >= CACHE_LAYOUT_VERSION and expected_fingerprint in (None, ""):
        errors.append("cache metadata fingerprint is missing")
    elif expected_fingerprint not in (None, "") and str(
        expected_fingerprint
    ) != _metadata_fingerprint(metadata):
        errors.append("cache metadata fingerprint mismatch")
    if cache_layout_version >= CACHE_LAYOUT_VERSION:
        try:
            validate_minimum_coverage_ratio(metadata.get("minimum_coverage_ratio"))
        except ValueError:
            errors.append("cache metadata minimum coverage ratio is missing or invalid")
    if not quality.passed:
        errors.append(f"cache quality failed: {quality.reason_code}")
    return errors


def _metadata_date(metadata: Mapping[str, Any], *names: str) -> Optional[str]:
    for name in names:
        if metadata.get(name) not in (None, ""):
            return _date_text(metadata[name])
    return None


def _write_benchmark_cache(
    cache_path: Path,
    metadata_path: Path,
    result: IndexProviderResult,
    start_date: str,
    end_date: str,
    fetched_at: datetime,
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if _cache_entry_exists(cache_path, metadata_path):
        raise FileExistsError("benchmark cache key already exists")
    token = uuid.uuid4().hex
    generation_path = cache_path.parent / f"{cache_path.stem}.{token}.data.parquet"
    parquet_temp = cache_path.parent / f".{cache_path.stem}.{token}.tmp.parquet"
    metadata_temp = metadata_path.parent / f".{metadata_path.name}.{token}.tmp"
    committed = False
    try:
        result.data.to_parquet(parquet_temp, index=False)
        metadata = {
            "cache_layout_version": CACHE_LAYOUT_VERSION,
            "data_type": "benchmark",
            "data_file": generation_path.name,
            "symbol": result.canonical_symbol,
            "source": result.selected_provider,
            "endpoint": result.selected_endpoint,
            "fetch_start_date": _date_text(start_date),
            "fetch_end_date": _date_text(end_date),
            "start_date": _date_text(start_date),
            "end_date": _date_text(end_date),
            "rows": result.quality.clean_row_count,
            "first_date": result.quality.first_date,
            "last_date": result.quality.last_date,
            "coverage_ratio": result.quality.coverage_ratio,
            "minimum_coverage_ratio": result.quality.minimum_coverage_ratio,
            "coverage_basis": "weekday_estimate",
            "fetched_at": _utc_text(fetched_at),
            "sha256": _sha256(parquet_temp),
        }
        metadata["source_fingerprint"] = _source_fingerprint(
            result.selected_provider,
            result.selected_endpoint,
        )
        metadata["metadata_fingerprint"] = _metadata_fingerprint(metadata)
        metadata_temp.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parquet_temp.replace(generation_path)
        # The metadata sidecar is the commit marker for immutable generation data.
        metadata_temp.replace(metadata_path)
        committed = True
    finally:
        parquet_temp.unlink(missing_ok=True)
        metadata_temp.unlink(missing_ok=True)
        if not committed and generation_path.exists():
            try:
                published = _read_metadata(metadata_path).get("data_file") == generation_path.name
            except Exception:
                published = False
            if not published:
                generation_path.unlink(missing_ok=True)


def _benchmark_diagnostic(
    status: str,
    canonical_symbol: str,
    selected_provider: Optional[str],
    selected_endpoint: Optional[str],
    quality: Optional[BenchmarkQualityResult],
    cache_status: str,
    attempts: Sequence[ProviderAttempt],
    *,
    requested_symbol: str,
    requested_start_date: str,
    requested_end_date: str,
    minimum_coverage_ratio: float,
    reason_code: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "canonical_symbol": canonical_symbol,
        "requested_symbol": requested_symbol,
        "requested_start_date": requested_start_date,
        "requested_end_date": requested_end_date,
        "selected_provider": selected_provider,
        "selected_endpoint": selected_endpoint,
        "row_count": quality.clean_row_count if quality is not None else 0,
        "raw_row_count": quality.raw_row_count if quality is not None else 0,
        "first_date": quality.first_date if quality is not None else None,
        "last_date": quality.last_date if quality is not None else None,
        "coverage_ratio": quality.coverage_ratio if quality is not None else None,
        "coverage_basis": "weekday_estimate",
        "minimum_coverage_ratio": minimum_coverage_ratio,
        "cache_status": cache_status,
        "reason_code": reason_code,
        "reason": reason,
        "attempts": [attempt.to_dict() for attempt in attempts],
    }


def _source_record(diagnostic: Mapping[str, Any], cache_path: Path) -> dict[str, Any]:
    return {
        "data_type": "benchmark",
        "symbol": diagnostic.get("canonical_symbol"),
        "requested_symbol": diagnostic.get("requested_symbol"),
        "requested_start_date": diagnostic.get("requested_start_date"),
        "requested_end_date": diagnostic.get("requested_end_date"),
        "source": diagnostic.get("selected_provider"),
        "endpoint": diagnostic.get("selected_endpoint"),
        "status": diagnostic.get("status"),
        "rows": diagnostic.get("row_count"),
        "first_date": diagnostic.get("first_date"),
        "last_date": diagnostic.get("last_date"),
        "coverage_ratio": diagnostic.get("coverage_ratio"),
        "coverage_basis": diagnostic.get("coverage_basis"),
        "minimum_coverage_ratio": diagnostic.get("minimum_coverage_ratio"),
        "cache_status": diagnostic.get("cache_status"),
        "cache_path": str(cache_path),
    }


def _failed_attempt_warnings(
    canonical_symbol: str,
    attempts: Sequence[ProviderAttempt],
) -> list[str]:
    return [
        (
            f"benchmark {canonical_symbol} provider attempt "
            f"{attempt.provider}/{attempt.endpoint} failed: {attempt.reason_code}"
        )
        for attempt in attempts
        if attempt.status != "success"
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_text(value: object) -> Optional[str]:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _required_date_text(value: object) -> str:
    parsed = _date_text(value)
    if parsed is None:
        raise ValueError(f"invalid benchmark request date: {value!r}")
    return parsed


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _metadata_fingerprint(metadata: Mapping[str, Any]) -> str:
    payload = {
        str(key): value for key, value in metadata.items() if str(key) != "metadata_fingerprint"
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fingerprint(source: object, endpoint: object) -> str:
    encoded = f"{source or ''}\0{endpoint or ''}".encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def default_index_provider_chain() -> IndexProviderChain:
    """Build the production primary/fallback chain without network access."""
    return IndexProviderChain(default_index_providers())


def _provider_symbol(provider: object, canonical_symbol: str) -> str:
    resolver = getattr(provider, "provider_symbol", None)
    if not callable(resolver):
        return canonical_symbol
    return str(resolver(canonical_symbol))


def _exception_attempt(
    provider: str,
    endpoint: str,
    canonical_symbol: str,
    provider_symbol: str,
    started_at: str,
    completed_at: str,
    role: str,
    reason_code: str,
    exc: Exception,
    *,
    requested_symbol: str = "",
    requested_start_date: str = "",
    requested_end_date: str = "",
    minimum_coverage_ratio: Optional[float] = None,
    source_metadata: Optional[Mapping[str, Any]] = None,
) -> ProviderAttempt:
    sanitized_exception = _sanitize_reason(str(exc))
    return ProviderAttempt(
        provider=provider,
        endpoint=endpoint,
        canonical_symbol=canonical_symbol,
        provider_symbol=provider_symbol,
        status="failed",
        started_at=started_at,
        completed_at=completed_at,
        reason_code=reason_code,
        reason=sanitized_exception,
        exception_type=type(exc).__name__,
        source_metadata={"role": role, **dict(source_metadata or {})},
        requested_symbol=requested_symbol,
        requested_start_date=requested_start_date,
        requested_end_date=requested_end_date,
        minimum_coverage_ratio=minimum_coverage_ratio,
        exception=sanitized_exception,
    )


def _utc_text(value: datetime) -> str:
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc).isoformat()


def _sanitize_reason(value: str) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = re.sub(r"https?://\S+", "[redacted-url]", text, flags=re.IGNORECASE)
    text = re.sub(
        (
            r"(?i)\b(authorization|proxy-authorization|x-api-key|"
            r"api[_-]?key|token|password)\b\s*[:=]\s*"
            r"(?:bearer\s+)?[^\s,&;]+"
        ),
        r"\1=[redacted]",
        text,
    )
    text = re.sub(r"//[^/@\s:]+:[^/@\s]+@", "//[redacted]@", text)
    return text[:MAX_DIAGNOSTIC_REASON_LENGTH]
