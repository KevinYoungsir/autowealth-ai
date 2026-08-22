"""Crash-safe single-writer local repository for immutable EOD generations."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import importlib
import json
import re
import secrets
import shutil
from typing import Optional, Protocol, Sequence, Tuple, runtime_checkable

import pyarrow as pa
import pyarrow.parquet as pq

from .normalization import normalize_eod_bars
from .schemas import EOD_SCHEMA_VERSION, EODBar, EODDatasetKey
from .versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EOD_PARQUET_FILE,
    EOD_POINTER_SCHEMA_VERSION,
    EODCurrentPointer,
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_eod_content_sha256,
    calculate_file_sha256,
    validate_generation_id,
)

os = importlib.import_module("os")
Path = importlib.import_module("pathlib").Path

EOD_PARQUET_COLUMNS = (
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
)
EOD_PARQUET_SCHEMA = pa.schema(
    [
        pa.field("trade_date", pa.string(), nullable=False),
        pa.field("open", pa.string(), nullable=False),
        pa.field("high", pa.string(), nullable=False),
        pa.field("low", pa.string(), nullable=False),
        pa.field("close", pa.string(), nullable=False),
        pa.field("volume", pa.string(), nullable=False),
        pa.field("amount", pa.string(), nullable=True),
    ]
)

_MANIFEST_FILE = "manifest.json"
_CURRENT_FILE = "current.json"
_GENERATIONS_DIRECTORY = "generations"
_STAGING_DIRECTORY_PATTERN = re.compile(
    r"^\.([A-Za-z0-9][A-Za-z0-9_.-]{0,127})\.([0-9a-f]{16})\.staging$"
)
_POINTER_TEMPORARY_FILE_PATTERN = re.compile(r"^\.current\.([0-9a-f]{16})\.tmp$")


def _maintenance_staging_generation_id(value: object) -> Optional[str]:
    if type(value) is not str:
        return None
    match = _STAGING_DIRECTORY_PATTERN.fullmatch(value)
    if match is None:
        return None
    try:
        return validate_generation_id(match.group(1))
    except ValueError:
        return None


def _is_maintenance_pointer_temporary_file(value: object) -> bool:
    return type(value) is str and _POINTER_TEMPORARY_FILE_PATTERN.fullmatch(value) is not None


class EODRepositoryError(RuntimeError):
    """Base error for stable EOD repository failures."""


class EODIntegrityError(EODRepositoryError):
    """Raised when stored EOD content fails strict integrity checks."""


class EODUnsafePathError(EODRepositoryError):
    """Raised when a path or symbolic link crosses a repository boundary."""


class EODGenerationExistsError(EODRepositoryError):
    """Raised when immutable generation publication would overwrite data."""


class EODNoCurrentGenerationError(EODRepositoryError):
    """Raised when a requested generation does not exist."""


@runtime_checkable
class EODFileRepository(Protocol):
    """Repository contract for versioned EOD generations."""

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: Sequence[EODBar],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> EODGenerationManifest: ...

    def load_current_manifest(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[EODGenerationManifest]: ...

    def load_current(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[EODStoredGeneration]: ...

    def load_generation(
        self,
        dataset: EODDatasetKey,
        generation_id: str,
    ) -> EODStoredGeneration: ...

    def list_generation_ids(self, dataset: EODDatasetKey) -> Tuple[str, ...]: ...


class LocalEODFileRepository:
    """Local single-writer repository with crash-safe atomic activation.

    Staging-directory rename and ``current.json`` replacement protect readers
    from partial publication. This class does not provide multi-process mutual
    exclusion, distributed locking, or safety for concurrent writers.
    """

    def __init__(self, root: Path) -> None:
        requested_root = Path(root)
        if requested_root.is_symlink():
            raise EODUnsafePathError("repository root must not be a symbolic link")
        self._root = requested_root.resolve(strict=False)
        if self._root.exists() and not self._root.is_dir():
            raise EODUnsafePathError("repository root must be a directory")

    def publish(
        self,
        dataset: EODDatasetKey,
        bars: Sequence[EODBar],
        *,
        generation_id: str,
        created_at: datetime,
    ) -> EODGenerationManifest:
        """Publish one immutable generation and atomically activate it."""

        self._require_dataset(dataset)
        safe_generation_id = validate_generation_id(generation_id)
        committed_at = self._require_aware_datetime(created_at)
        normalized_bars = self._normalize_publish_bars(dataset, bars)
        content_sha256 = calculate_eod_content_sha256(normalized_bars)

        previous_manifest = self.load_current_manifest(dataset)
        previous_generation_id = (
            None if previous_manifest is None else previous_manifest.generation_id
        )
        dataset_directory = self._ensure_dataset_directory(dataset)
        generations_directory = self._ensure_child_directory(
            dataset_directory,
            _GENERATIONS_DIRECTORY,
        )
        generation_directory = self._generation_directory(dataset, safe_generation_id)
        if generation_directory.is_symlink():
            raise EODUnsafePathError("generation path must not be a symbolic link")
        self._assert_within_root(generation_directory)
        if generation_directory.exists():
            raise EODGenerationExistsError("generation already exists")

        staging_directory = self._create_staging_directory(
            dataset_directory,
            safe_generation_id,
        )
        pointer_temporary_path: Optional[Path] = None
        generation_published = False
        try:
            parquet_path = staging_directory / EOD_PARQUET_FILE
            self._write_parquet(parquet_path, normalized_bars)
            parquet_sha256 = calculate_file_sha256(parquet_path)
            reloaded_bars = self._read_parquet(parquet_path, dataset)
            self._validate_reloaded_bars(
                normalized_bars,
                reloaded_bars,
                content_sha256,
            )

            manifest = EODGenerationManifest(
                manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
                eod_schema_version=EOD_SCHEMA_VERSION,
                generation_id=safe_generation_id,
                dataset=dataset,
                created_at=committed_at,
                row_count=len(normalized_bars),
                first_trade_date=normalized_bars[0].trade_date,
                last_trade_date=normalized_bars[-1].trade_date,
                data_version=f"sha256:{content_sha256}",
                content_sha256=content_sha256,
                parquet_sha256=parquet_sha256,
                previous_generation_id=previous_generation_id,
            )
            manifest_path = staging_directory / _MANIFEST_FILE
            self._write_manifest(manifest_path, manifest)
            parsed_manifest = self._read_manifest(manifest_path)
            if parsed_manifest != manifest:
                raise EODIntegrityError("written manifest failed deterministic validation")
            manifest_sha256 = calculate_file_sha256(manifest_path)

            self._publish_staging(staging_directory, generation_directory)
            generation_published = True

            pointer = EODCurrentPointer(
                pointer_schema_version=EOD_POINTER_SCHEMA_VERSION,
                dataset=dataset,
                generation_id=safe_generation_id,
                manifest_sha256=manifest_sha256,
                committed_at=committed_at,
            )
            pointer_temporary_path = self._new_pointer_temporary_path(dataset_directory)
            self._write_pointer(pointer_temporary_path, pointer)
            self._replace_current_pointer(
                pointer_temporary_path,
                self._current_path(dataset),
            )
            pointer_temporary_path = None
            return manifest
        finally:
            if pointer_temporary_path is not None and pointer_temporary_path.exists():
                pointer_temporary_path.unlink()
            if not generation_published and staging_directory.exists():
                self._remove_staging_directory(staging_directory)

    def load_current_manifest(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[EODGenerationManifest]:
        """Load the activated manifest, or return None when no pointer exists."""

        self._require_dataset(dataset)
        pointer = self._read_current_pointer(dataset)
        if pointer is None:
            return None
        return self._load_manifest_for_pointer(dataset, pointer)

    def load_current(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[EODStoredGeneration]:
        """Load and fully verify the activated generation without fallback."""

        self._require_dataset(dataset)
        pointer = self._read_current_pointer(dataset)
        if pointer is None:
            return None
        return self._load_generation(
            dataset,
            pointer.generation_id,
            expected_manifest_sha256=pointer.manifest_sha256,
            missing_message="current pointer references a missing generation",
        )

    def load_generation(
        self,
        dataset: EODDatasetKey,
        generation_id: str,
    ) -> EODStoredGeneration:
        """Load and fully verify one explicit immutable generation."""

        self._require_dataset(dataset)
        safe_generation_id = validate_generation_id(generation_id)
        return self._load_generation(
            dataset,
            safe_generation_id,
            expected_manifest_sha256=None,
            missing_message="requested generation does not exist",
        )

    def list_generation_ids(self, dataset: EODDatasetKey) -> Tuple[str, ...]:
        """Return valid complete generation IDs in deterministic order."""

        self._require_dataset(dataset)
        generations_directory = self._generations_directory(dataset)
        if generations_directory.is_symlink():
            raise EODUnsafePathError("generations path must not be a symbolic link")
        if not generations_directory.exists():
            return ()
        self._assert_within_root(generations_directory)
        if not generations_directory.is_dir():
            raise EODIntegrityError("generations path must be a directory")

        generation_ids = []
        for candidate in sorted(generations_directory.iterdir(), key=lambda path: path.name):
            try:
                generation_id = validate_generation_id(candidate.name)
            except ValueError:
                continue
            if candidate.is_symlink():
                raise EODUnsafePathError("generation path must not be a symbolic link")
            if not candidate.is_dir():
                continue
            self._assert_within_root(candidate)
            manifest_path = candidate / _MANIFEST_FILE
            parquet_path = candidate / EOD_PARQUET_FILE
            if manifest_path.is_symlink() or parquet_path.is_symlink():
                raise EODUnsafePathError("generation files must not be symbolic links")
            if manifest_path.is_file() and parquet_path.is_file():
                generation_ids.append(generation_id)
        return tuple(generation_ids)

    def _find_existing_dataset_directory(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[Path]:
        """Locate one dataset without creating directories or following symlinks."""

        dataset_directory = self._dataset_directory(dataset)
        try:
            relative_parts = dataset_directory.relative_to(self._root).parts
        except ValueError:
            raise EODUnsafePathError("repository path escapes its root") from None

        current = self._root
        if current.is_symlink():
            raise EODUnsafePathError("repository root must not be a symbolic link")
        if not current.exists():
            return None
        if not current.is_dir():
            raise EODIntegrityError("repository root must be a directory")
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                raise EODUnsafePathError("repository directory must not be a symbolic link")
            if not current.exists():
                return None
            if not current.is_dir():
                raise EODIntegrityError("repository directory path is invalid")
        return dataset_directory

    def _remove_maintenance_staging_directory(
        self,
        dataset: EODDatasetKey,
        artifact_name: str,
    ) -> bool:
        """Remove one exact stale staging directory after revalidating its identity."""

        if _maintenance_staging_generation_id(artifact_name) is None:
            raise ValueError("artifact_name must be an exact staging directory name")
        dataset_directory = self._find_existing_dataset_directory(dataset)
        if dataset_directory is None:
            return False
        candidate = dataset_directory / artifact_name
        if candidate.is_symlink():
            raise EODUnsafePathError("staging directory must not be a symbolic link")
        self._assert_within_root(candidate)
        if not candidate.exists():
            return False
        if not candidate.is_dir():
            raise EODIntegrityError("staging artifact must be a directory")
        self._remove_staging_directory(candidate)
        return True

    def _remove_maintenance_pointer_temporary_file(
        self,
        dataset: EODDatasetKey,
        artifact_name: str,
    ) -> bool:
        """Remove one exact pointer temporary regular file without reading its content."""

        if not _is_maintenance_pointer_temporary_file(artifact_name):
            raise ValueError("artifact_name must be an exact pointer temporary file name")
        dataset_directory = self._find_existing_dataset_directory(dataset)
        if dataset_directory is None:
            return False
        candidate = dataset_directory / artifact_name
        if candidate.is_symlink():
            raise EODUnsafePathError("pointer temporary file must not be a symbolic link")
        self._assert_within_root(candidate)
        if not candidate.exists():
            return False
        if not candidate.is_file():
            raise EODIntegrityError("pointer temporary artifact must be a regular file")
        try:
            candidate.unlink()
        except OSError as exc:
            raise EODRepositoryError("pointer temporary cleanup failed") from exc
        return True

    def _load_generation(
        self,
        dataset: EODDatasetKey,
        generation_id: str,
        *,
        expected_manifest_sha256: Optional[str],
        missing_message: str,
    ) -> EODStoredGeneration:
        generation_directory = self._generation_directory(dataset, generation_id)
        if generation_directory.is_symlink():
            raise EODUnsafePathError("generation path must not be a symbolic link")
        self._assert_within_root(generation_directory)
        if not generation_directory.is_dir():
            raise EODNoCurrentGenerationError(missing_message)

        manifest_path = generation_directory / _MANIFEST_FILE
        if expected_manifest_sha256 is not None:
            self._assert_regular_file(manifest_path, "manifest")
            if calculate_file_sha256(manifest_path) != expected_manifest_sha256:
                raise EODIntegrityError("manifest checksum does not match current pointer")
        manifest = self._read_manifest(manifest_path)
        if manifest.dataset != dataset:
            raise EODIntegrityError("manifest dataset does not match repository location")
        if manifest.generation_id != generation_id:
            raise EODIntegrityError("manifest generation does not match repository location")

        parquet_path = generation_directory / manifest.parquet_file
        self._assert_regular_file(parquet_path, "Parquet")
        if calculate_file_sha256(parquet_path) != manifest.parquet_sha256:
            raise EODIntegrityError("Parquet checksum does not match manifest")
        bars = self._read_parquet(parquet_path, dataset)
        self._validate_manifest_content(manifest, bars)
        return EODStoredGeneration(manifest=manifest, bars=bars)

    def _load_manifest_for_pointer(
        self,
        dataset: EODDatasetKey,
        pointer: EODCurrentPointer,
    ) -> EODGenerationManifest:
        generation_directory = self._generation_directory(dataset, pointer.generation_id)
        if generation_directory.is_symlink():
            raise EODUnsafePathError("generation path must not be a symbolic link")
        self._assert_within_root(generation_directory)
        if not generation_directory.is_dir():
            raise EODNoCurrentGenerationError("current pointer references a missing generation")
        manifest_path = generation_directory / _MANIFEST_FILE
        self._assert_regular_file(manifest_path, "manifest")
        if calculate_file_sha256(manifest_path) != pointer.manifest_sha256:
            raise EODIntegrityError("manifest checksum does not match current pointer")
        manifest = self._read_manifest(manifest_path)
        if manifest.dataset != dataset:
            raise EODIntegrityError("manifest dataset does not match repository location")
        if manifest.generation_id != pointer.generation_id:
            raise EODIntegrityError("manifest generation does not match current pointer")
        return manifest

    def _read_current_pointer(
        self,
        dataset: EODDatasetKey,
    ) -> Optional[EODCurrentPointer]:
        current_path = self._current_path(dataset)
        if current_path.is_symlink():
            raise EODUnsafePathError("current pointer must not be a symbolic link")
        self._assert_within_root(current_path)
        if not current_path.exists():
            return None
        self._assert_regular_file(current_path, "current pointer")
        try:
            payload = json.loads(current_path.read_text(encoding="utf-8"))
            pointer = EODCurrentPointer.from_dict(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise EODIntegrityError("current pointer is invalid") from exc
        if pointer.dataset != dataset:
            raise EODIntegrityError("current pointer dataset does not match repository location")
        return pointer

    def _read_manifest(self, manifest_path: Path) -> EODGenerationManifest:
        self._assert_regular_file(manifest_path, "manifest")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            return EODGenerationManifest.from_dict(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise EODIntegrityError("generation manifest is invalid") from exc

    def _write_parquet(
        self,
        parquet_path: Path,
        bars: Tuple[EODBar, ...],
    ) -> None:
        data = {
            "trade_date": [bar.trade_date.isoformat() for bar in bars],
            "open": [bar.to_dict()["open"] for bar in bars],
            "high": [bar.to_dict()["high"] for bar in bars],
            "low": [bar.to_dict()["low"] for bar in bars],
            "close": [bar.to_dict()["close"] for bar in bars],
            "volume": [bar.to_dict()["volume"] for bar in bars],
            "amount": [bar.to_dict()["amount"] for bar in bars],
        }
        arrays = [
            pa.array(data[column], type=EOD_PARQUET_SCHEMA.field(column).type)
            for column in EOD_PARQUET_COLUMNS
        ]
        table = pa.Table.from_arrays(arrays, schema=EOD_PARQUET_SCHEMA)
        try:
            pq.write_table(
                table,
                parquet_path,
                compression="snappy",
                use_dictionary=False,
                write_statistics=True,
            )
            with parquet_path.open("r+b") as handle:
                os.fsync(handle.fileno())
        except (OSError, pa.ArrowException) as exc:
            raise EODRepositoryError("Parquet staging write failed") from exc

    def _read_parquet(
        self,
        parquet_path: Path,
        dataset: EODDatasetKey,
    ) -> Tuple[EODBar, ...]:
        self._assert_regular_file(parquet_path, "Parquet")
        try:
            table = pq.ParquetFile(parquet_path).read()
        except (OSError, pa.ArrowException) as exc:
            raise EODIntegrityError("Parquet file is unreadable") from exc
        if tuple(table.column_names) != EOD_PARQUET_COLUMNS:
            raise EODIntegrityError("Parquet columns do not match the EOD v1 schema")
        if not table.schema.equals(EOD_PARQUET_SCHEMA, check_metadata=False):
            raise EODIntegrityError("Parquet types do not match the EOD v1 schema")

        bars = []
        try:
            for row in table.to_pylist():
                trade_date_value = row["trade_date"]
                if type(trade_date_value) is not str:
                    raise ValueError
                trade_date = date.fromisoformat(trade_date_value)
                numeric_values = {}
                for field_name in ("open", "high", "low", "close", "volume"):
                    value = row[field_name]
                    if type(value) is not str:
                        raise ValueError
                    numeric_values[field_name] = Decimal(value)
                amount_value = row["amount"]
                if amount_value is not None and type(amount_value) is not str:
                    raise ValueError
                amount = None if amount_value is None else Decimal(amount_value)
                bar = EODBar(
                    dataset=dataset,
                    trade_date=trade_date,
                    amount=amount,
                    **numeric_values,
                )
                canonical_row = bar.to_dict()
                if canonical_row["trade_date"] != trade_date_value or any(
                    canonical_row[field_name] != row[field_name]
                    for field_name in ("open", "high", "low", "close", "volume", "amount")
                ):
                    raise ValueError
                bars.append(bar)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise EODIntegrityError("Parquet row content is invalid") from exc
        return tuple(bars)

    def _validate_reloaded_bars(
        self,
        expected: Tuple[EODBar, ...],
        actual: Tuple[EODBar, ...],
        content_sha256: str,
    ) -> None:
        if actual != expected:
            raise EODIntegrityError("Parquet round-trip changed EOD content")
        if calculate_eod_content_sha256(actual) != content_sha256:
            raise EODIntegrityError("Parquet round-trip content checksum changed")

    def _validate_manifest_content(
        self,
        manifest: EODGenerationManifest,
        bars: Tuple[EODBar, ...],
    ) -> None:
        if not bars:
            raise EODIntegrityError("stored generation contains no EOD bars")
        if len(bars) != manifest.row_count:
            raise EODIntegrityError("stored row count does not match manifest")
        trade_dates = [bar.trade_date for bar in bars]
        if len(set(trade_dates)) != len(trade_dates):
            raise EODIntegrityError("stored EOD bars contain duplicate trade dates")
        if bars != normalize_eod_bars(bars):
            raise EODIntegrityError("stored EOD bars are not in canonical order")
        if bars[0].trade_date != manifest.first_trade_date or (
            bars[-1].trade_date != manifest.last_trade_date
        ):
            raise EODIntegrityError("stored date range does not match manifest")
        try:
            content_sha256 = calculate_eod_content_sha256(bars)
        except (TypeError, ValueError) as exc:
            raise EODIntegrityError("stored logical EOD content is invalid") from exc
        if content_sha256 != manifest.content_sha256:
            raise EODIntegrityError("content checksum does not match manifest")

    def _write_manifest(
        self,
        manifest_path: Path,
        manifest: EODGenerationManifest,
    ) -> None:
        self._write_exclusive_bytes(manifest_path, manifest.to_json().encode("utf-8"))

    def _write_pointer(
        self,
        pointer_path: Path,
        pointer: EODCurrentPointer,
    ) -> None:
        self._write_exclusive_bytes(pointer_path, pointer.to_json().encode("utf-8"))

    def _write_exclusive_bytes(self, path: Path, payload: bytes) -> None:
        if path.is_symlink():
            raise EODUnsafePathError("staging file must not be a symbolic link")
        self._assert_within_root(path)
        try:
            with path.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise EODRepositoryError("staging file write failed") from exc

    def _publish_staging(self, staging_path: Path, generation_path: Path) -> None:
        if staging_path.is_symlink():
            raise EODUnsafePathError("staging directory must not be a symbolic link")
        if generation_path.is_symlink():
            raise EODUnsafePathError("generation path must not be a symbolic link")
        self._assert_within_root(staging_path)
        self._assert_within_root(generation_path)
        if generation_path.exists():
            raise EODGenerationExistsError("generation already exists")
        try:
            os.rename(staging_path, generation_path)
        except OSError as exc:
            raise EODRepositoryError("generation publication rename failed") from exc

    def _replace_current_pointer(self, temporary_path: Path, current_path: Path) -> None:
        if temporary_path.is_symlink():
            raise EODUnsafePathError("current pointer staging file must not be a symbolic link")
        if current_path.is_symlink():
            raise EODUnsafePathError("current pointer must not be a symbolic link")
        self._assert_within_root(temporary_path)
        self._assert_within_root(current_path)
        if current_path.exists() and not current_path.is_file():
            raise EODIntegrityError("current pointer must be a regular file")
        try:
            os.replace(temporary_path, current_path)
        except OSError as exc:
            raise EODRepositoryError("current pointer replacement failed") from exc

    def _normalize_publish_bars(
        self,
        dataset: EODDatasetKey,
        bars: Sequence[EODBar],
    ) -> Tuple[EODBar, ...]:
        if type(bars) not in (list, tuple):
            raise TypeError("bars must be an exact list or exact tuple")
        if not bars:
            raise ValueError("bars must not be empty")
        if any(type(bar) is not EODBar for bar in bars):
            raise TypeError("bars must contain exact EODBar values")
        if any(bar.dataset != dataset for bar in bars):
            raise ValueError("bars must match the repository dataset")
        normalized = normalize_eod_bars(bars)
        trade_dates = [bar.trade_date for bar in normalized]
        if len(set(trade_dates)) != len(trade_dates):
            raise ValueError("bars must not contain duplicate trade dates")
        return normalized

    def _require_dataset(self, dataset: EODDatasetKey) -> None:
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")

    def _require_aware_datetime(self, value: object) -> datetime:
        if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def _dataset_directory(self, dataset: EODDatasetKey) -> Path:
        self._require_dataset(dataset)
        candidate = self._root.joinpath(
            dataset.market.value,
            dataset.venue.value,
            dataset.asset_type.value,
            dataset.canonical_symbol,
            dataset.frequency.value,
            dataset.adjustment_type.value,
        )
        self._assert_within_root(candidate)
        return candidate

    def _generations_directory(self, dataset: EODDatasetKey) -> Path:
        candidate = self._dataset_directory(dataset) / _GENERATIONS_DIRECTORY
        if candidate.is_symlink():
            raise EODUnsafePathError("generations path must not be a symbolic link")
        self._assert_within_root(candidate)
        return candidate

    def _generation_directory(
        self,
        dataset: EODDatasetKey,
        generation_id: str,
    ) -> Path:
        safe_generation_id = validate_generation_id(generation_id)
        candidate = self._generations_directory(dataset) / safe_generation_id
        return candidate

    def _current_path(self, dataset: EODDatasetKey) -> Path:
        return self._dataset_directory(dataset) / _CURRENT_FILE

    def _ensure_dataset_directory(self, dataset: EODDatasetKey) -> Path:
        dataset_directory = self._dataset_directory(dataset)
        self._ensure_directory_chain(dataset_directory)
        return dataset_directory

    def _ensure_child_directory(self, parent: Path, child_name: str) -> Path:
        candidate = parent / child_name
        if candidate.is_symlink():
            raise EODUnsafePathError("repository directory must not be a symbolic link")
        self._assert_within_root(candidate)
        try:
            candidate.mkdir(exist_ok=True)
        except OSError as exc:
            raise EODRepositoryError("repository directory creation failed") from exc
        if not candidate.is_dir():
            raise EODIntegrityError("repository directory path is invalid")
        return candidate

    def _ensure_directory_chain(self, directory: Path) -> None:
        self._assert_within_root(directory)
        try:
            relative_parts = directory.relative_to(self._root).parts
        except ValueError:
            raise EODUnsafePathError("repository path escapes its root") from None
        current = self._root
        if current.is_symlink():
            raise EODUnsafePathError("repository root must not be a symbolic link")
        if not current.exists():
            try:
                current.mkdir(parents=True)
            except OSError as exc:
                raise EODRepositoryError("repository root creation failed") from exc
        for part in relative_parts:
            current = current / part
            if current.is_symlink():
                raise EODUnsafePathError("repository directory must not be a symbolic link")
            if current.exists():
                if not current.is_dir():
                    raise EODIntegrityError("repository directory path is invalid")
                continue
            try:
                current.mkdir()
            except OSError as exc:
                raise EODRepositoryError("repository directory creation failed") from exc

    def _create_staging_directory(
        self,
        dataset_directory: Path,
        generation_id: str,
    ) -> Path:
        for _ in range(16):
            candidate = dataset_directory / (f".{generation_id}.{secrets.token_hex(8)}.staging")
            self._assert_within_root(candidate)
            try:
                candidate.mkdir()
            except FileExistsError:
                continue
            except OSError as exc:
                raise EODRepositoryError("staging directory creation failed") from exc
            return candidate
        raise EODRepositoryError("staging directory allocation failed")

    def _new_pointer_temporary_path(self, dataset_directory: Path) -> Path:
        for _ in range(16):
            candidate = dataset_directory / f".current.{secrets.token_hex(8)}.tmp"
            self._assert_within_root(candidate)
            if not candidate.exists() and not candidate.is_symlink():
                return candidate
        raise EODRepositoryError("current pointer staging allocation failed")

    def _remove_staging_directory(self, staging_directory: Path) -> None:
        if staging_directory.is_symlink():
            raise EODUnsafePathError("staging directory must not be a symbolic link")
        self._assert_within_root(staging_directory)
        try:
            shutil.rmtree(staging_directory)
        except OSError as exc:
            raise EODRepositoryError("staging cleanup failed") from exc

    def _assert_regular_file(self, path: Path, label: str) -> None:
        if path.is_symlink():
            raise EODUnsafePathError(f"{label} file must not be a symbolic link")
        self._assert_within_root(path)
        if not path.is_file():
            raise EODIntegrityError(f"{label} file is missing")

    def _assert_within_root(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._root)
        except (OSError, ValueError) as exc:
            raise EODUnsafePathError("repository path escapes its root") from exc
