"""Version and checksum contracts for immutable EOD file generations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import importlib
import json
import re
from typing import Mapping, Optional, Sequence, Tuple

from .normalization import normalize_eod_bars
from .schemas import EOD_SCHEMA_VERSION, EODBar, EODDatasetKey

Path = importlib.import_module("pathlib").Path

EOD_MANIFEST_SCHEMA_VERSION = 1
EOD_POINTER_SCHEMA_VERSION = 1
EOD_PARQUET_FILE = "bars.parquet"

_GENERATION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DATA_VERSION_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_DATASET_FIELDS = {
    "market",
    "venue",
    "asset_type",
    "canonical_symbol",
    "frequency",
    "adjustment_type",
}
_MANIFEST_FIELDS = {
    "manifest_schema_version",
    "eod_schema_version",
    "generation_id",
    "dataset",
    "created_at",
    "row_count",
    "first_trade_date",
    "last_trade_date",
    "data_version",
    "content_sha256",
    "parquet_sha256",
    "previous_generation_id",
    "parquet_file",
}
_POINTER_FIELDS = {
    "pointer_schema_version",
    "dataset",
    "generation_id",
    "manifest_sha256",
    "committed_at",
}


def validate_generation_id(value: object) -> str:
    """Return a path-safe generation identifier or raise a stable error."""

    if type(value) is not str or _GENERATION_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("generation_id must be a safe machine identifier")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError("generation_id must be a safe machine identifier")
    return value


def _sha256_value(value: object, field_name: str) -> str:
    if type(value) is not str or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _positive_row_count(value: object) -> int:
    if isinstance(value, bool) or type(value) is not int or value <= 0:
        raise ValueError("row_count must be a positive integer")
    return value


def _exact_date(value: object, field_name: str) -> date:
    if type(value) is not date:
        raise ValueError(f"{field_name} must be an exact date")
    return value


def _utc_datetime(value: object, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _parse_date(value: object, field_name: str) -> date:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be an ISO date string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO date string") from exc
    return _exact_date(parsed, field_name)


def _parse_datetime(value: object, field_name: str) -> datetime:
    if type(value) is not str:
        raise ValueError(f"{field_name} must be an ISO datetime string")
    candidate = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO datetime string") from exc
    return _utc_datetime(parsed, field_name)


def _strict_keys(payload: object, expected: set[str], field_name: str) -> dict[str, object]:
    if type(payload) is not dict:
        raise TypeError(f"{field_name} must be an exact dict")
    if set(payload) != expected:
        raise ValueError(f"{field_name} fields do not match the schema")
    return payload


def _dataset_from_dict(payload: object) -> EODDatasetKey:
    values = _strict_keys(payload, _DATASET_FIELDS, "dataset")
    return EODDatasetKey(
        market=values["market"],
        venue=values["venue"],
        asset_type=values["asset_type"],
        canonical_symbol=values["canonical_symbol"],
        frequency=values["frequency"],
        adjustment_type=values["adjustment_type"],
    )


def _json_text(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True)
class EODGenerationManifest:
    """Immutable metadata for one fully published EOD generation."""

    manifest_schema_version: int
    eod_schema_version: int
    generation_id: str
    dataset: EODDatasetKey
    created_at: datetime
    row_count: int
    first_trade_date: date
    last_trade_date: date
    data_version: str
    content_sha256: str
    parquet_sha256: str
    previous_generation_id: Optional[str] = None
    parquet_file: str = EOD_PARQUET_FILE

    def __post_init__(self) -> None:
        if type(self.manifest_schema_version) is not int or (
            self.manifest_schema_version != EOD_MANIFEST_SCHEMA_VERSION
        ):
            raise ValueError("manifest_schema_version is unsupported")
        if type(self.eod_schema_version) is not int or (
            self.eod_schema_version != EOD_SCHEMA_VERSION
        ):
            raise ValueError("eod_schema_version is unsupported")
        generation_id = validate_generation_id(self.generation_id)
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an EODDatasetKey")
        created_at = _utc_datetime(self.created_at, "created_at")
        row_count = _positive_row_count(self.row_count)
        first_date = _exact_date(self.first_trade_date, "first_trade_date")
        last_date = _exact_date(self.last_trade_date, "last_trade_date")
        if first_date > last_date:
            raise ValueError("first_trade_date cannot be after last_trade_date")
        content_sha256 = _sha256_value(self.content_sha256, "content_sha256")
        parquet_sha256 = _sha256_value(self.parquet_sha256, "parquet_sha256")
        if type(self.data_version) is not str or (
            _DATA_VERSION_PATTERN.fullmatch(self.data_version) is None
        ):
            raise ValueError("data_version must use the sha256 digest format")
        if self.data_version != f"sha256:{content_sha256}":
            raise ValueError("data_version must match content_sha256")
        previous_generation_id = self.previous_generation_id
        if previous_generation_id is not None:
            previous_generation_id = validate_generation_id(previous_generation_id)
            if previous_generation_id == generation_id:
                raise ValueError("previous_generation_id must differ from generation_id")
        if self.parquet_file != EOD_PARQUET_FILE:
            raise ValueError("parquet_file must be bars.parquet")

        object.__setattr__(self, "generation_id", generation_id)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "row_count", row_count)
        object.__setattr__(self, "first_trade_date", first_date)
        object.__setattr__(self, "last_trade_date", last_date)
        object.__setattr__(self, "content_sha256", content_sha256)
        object.__setattr__(self, "parquet_sha256", parquet_sha256)
        object.__setattr__(self, "previous_generation_id", previous_generation_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "eod_schema_version": self.eod_schema_version,
            "generation_id": self.generation_id,
            "dataset": self.dataset.to_dict(),
            "created_at": self.created_at.isoformat(),
            "row_count": self.row_count,
            "first_trade_date": self.first_trade_date.isoformat(),
            "last_trade_date": self.last_trade_date.isoformat(),
            "data_version": self.data_version,
            "content_sha256": self.content_sha256,
            "parquet_sha256": self.parquet_sha256,
            "previous_generation_id": self.previous_generation_id,
            "parquet_file": self.parquet_file,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> "EODGenerationManifest":
        """Parse a manifest without accepting missing or unknown fields."""

        values = _strict_keys(payload, _MANIFEST_FIELDS, "manifest")
        return cls(
            manifest_schema_version=values["manifest_schema_version"],
            eod_schema_version=values["eod_schema_version"],
            generation_id=values["generation_id"],
            dataset=_dataset_from_dict(values["dataset"]),
            created_at=_parse_datetime(values["created_at"], "created_at"),
            row_count=values["row_count"],
            first_trade_date=_parse_date(values["first_trade_date"], "first_trade_date"),
            last_trade_date=_parse_date(values["last_trade_date"], "last_trade_date"),
            data_version=values["data_version"],
            content_sha256=values["content_sha256"],
            parquet_sha256=values["parquet_sha256"],
            previous_generation_id=values["previous_generation_id"],
            parquet_file=values["parquet_file"],
        )


@dataclass(frozen=True)
class EODCurrentPointer:
    """Atomic activation pointer for one dataset generation."""

    pointer_schema_version: int
    dataset: EODDatasetKey
    generation_id: str
    manifest_sha256: str
    committed_at: datetime

    def __post_init__(self) -> None:
        if type(self.pointer_schema_version) is not int or (
            self.pointer_schema_version != EOD_POINTER_SCHEMA_VERSION
        ):
            raise ValueError("pointer_schema_version is unsupported")
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an EODDatasetKey")
        generation_id = validate_generation_id(self.generation_id)
        manifest_sha256 = _sha256_value(self.manifest_sha256, "manifest_sha256")
        committed_at = _utc_datetime(self.committed_at, "committed_at")

        object.__setattr__(self, "generation_id", generation_id)
        object.__setattr__(self, "manifest_sha256", manifest_sha256)
        object.__setattr__(self, "committed_at", committed_at)

    def to_dict(self) -> dict[str, object]:
        return {
            "pointer_schema_version": self.pointer_schema_version,
            "dataset": self.dataset.to_dict(),
            "generation_id": self.generation_id,
            "manifest_sha256": self.manifest_sha256,
            "committed_at": self.committed_at.isoformat(),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> "EODCurrentPointer":
        """Parse a current pointer without accepting missing or unknown fields."""

        values = _strict_keys(payload, _POINTER_FIELDS, "pointer")
        return cls(
            pointer_schema_version=values["pointer_schema_version"],
            dataset=_dataset_from_dict(values["dataset"]),
            generation_id=values["generation_id"],
            manifest_sha256=values["manifest_sha256"],
            committed_at=_parse_datetime(values["committed_at"], "committed_at"),
        )


@dataclass(frozen=True)
class EODStoredGeneration:
    """Validated immutable bars and metadata loaded from one generation."""

    manifest: EODGenerationManifest
    bars: Tuple[EODBar, ...]

    def __post_init__(self) -> None:
        if type(self.manifest) is not EODGenerationManifest:
            raise TypeError("manifest must be an EODGenerationManifest")
        if type(self.bars) not in (list, tuple):
            raise TypeError("bars must be an exact list or exact tuple")
        bars = tuple(self.bars)
        if any(type(bar) is not EODBar for bar in bars):
            raise TypeError("bars must contain exact EODBar values")
        if len(bars) != self.manifest.row_count:
            raise ValueError("bars must match manifest row_count")
        if any(bar.dataset != self.manifest.dataset for bar in bars):
            raise ValueError("bars must match the manifest dataset")
        object.__setattr__(self, "bars", bars)


def calculate_eod_content_sha256(bars: Sequence[EODBar]) -> str:
    """Hash normalized logical EOD content independently of Parquet bytes."""

    if type(bars) not in (list, tuple):
        raise TypeError("bars must be an exact list or exact tuple")
    normalized = normalize_eod_bars(bars)
    if not normalized:
        raise ValueError("bars must not be empty")
    dataset = normalized[0].dataset
    if any(bar.dataset != dataset for bar in normalized):
        raise ValueError("bars must belong to one dataset")
    trade_dates = [bar.trade_date for bar in normalized]
    if len(set(trade_dates)) != len(trade_dates):
        raise ValueError("bars must not contain duplicate trade dates")
    payload = b"".join(f"{bar.to_json()}\n".encode("utf-8") for bar in normalized)
    return hashlib.sha256(payload).hexdigest()


def calculate_bytes_sha256(value: bytes) -> str:
    """Return the lowercase SHA-256 digest of exact bytes."""

    if type(value) is not bytes:
        raise TypeError("value must be exact bytes")
    return hashlib.sha256(value).hexdigest()


def calculate_file_sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file in bounded chunks without loading it entirely into memory."""

    if isinstance(chunk_size, bool) or type(chunk_size) is not int or chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    candidate = Path(path)
    if not candidate.is_file():
        raise FileNotFoundError("checksum source file does not exist")
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()
