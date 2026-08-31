"""Explicit, bounded maintenance for local immutable EOD repositories."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Optional, Tuple

from .batch import EODDatasetLockManager, eod_dataset_lock_key
from .operation_control import (
    EODCheckpointStage,
    EODExecutionCheckpoint,
    run_eod_checkpoint,
)
from .repositories import (
    EODIntegrityError,
    EODRepositoryError,
    EODUnsafePathError,
    LocalEODFileRepository,
    _CURRENT_FILE,
    _GENERATIONS_DIRECTORY,
    _is_maintenance_pointer_temporary_file,
    _maintenance_staging_generation_id,
)
from .schemas import EODDatasetKey
from .versioning import EOD_PARQUET_FILE, calculate_file_sha256, validate_generation_id

MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS = 256
MAX_EOD_GENERATION_LINEAGE_DEPTH = 256
_MAX_ARTIFACT_NAME_LENGTH = 256


class EODRepositoryArtifactClass(str, Enum):
    """Stable classification for one repository-local maintenance artifact."""

    ACTIVE_CURRENT_GENERATION = "active_current_generation"
    REACHABLE_HISTORICAL_GENERATION = "reachable_historical_generation"
    UNREACHABLE_COMPLETE_GENERATION = "unreachable_complete_generation"
    STAGING_DIRECTORY = "staging_directory"
    POINTER_TEMP_FILE = "pointer_temp_file"
    UNKNOWN_ARTIFACT = "unknown_artifact"
    UNSAFE_ARTIFACT = "unsafe_artifact"


class EODRepositoryArtifactLocation(str, Enum):
    """Bounded relative location without exposing a filesystem path."""

    DATASET = "dataset"
    GENERATIONS = "generations"


class EODRepositoryMaintenanceStatus(str, Enum):
    """Stable outcomes for inspection and explicit cleanup."""

    EMPTY = "empty"
    INSPECTED = "inspected"
    CLEANED = "cleaned"
    BLOCKED = "blocked"


class EODRepositoryMaintenanceWarningCode(str, Enum):
    """Stable warning codes that never contain provider or filesystem payloads."""

    UNKNOWN_ARTIFACT_PRESERVED = "unknown_artifact_preserved"
    UNSAFE_ARTIFACT_DETECTED = "unsafe_artifact_detected"
    INVALID_GENERATION_ARTIFACT = "invalid_generation_artifact"
    CURRENT_INTEGRITY_INVALID = "current_integrity_invalid"
    AMBIGUOUS_GENERATIONS_WITHOUT_CURRENT = "ambiguous_generations_without_current"
    BROKEN_GENERATION_LINEAGE = "broken_generation_lineage"
    GENERATION_LINEAGE_CYCLE = "generation_lineage_cycle"
    GENERATION_LINEAGE_LIMIT_EXCEEDED = "generation_lineage_limit_exceeded"
    UNREACHABLE_COMPLETE_GENERATION_PRESERVED = "unreachable_complete_generation_preserved"
    ARTIFACT_LIMIT_EXCEEDED = "artifact_limit_exceeded"
    REPOSITORY_INSPECTION_FAILED = "repository_inspection_failed"


class EODRepositoryMaintenanceErrorCode(str, Enum):
    """Finite failures unique to the explicit maintenance boundary."""

    LOCK_ACQUISITION_FAILED = "lock_acquisition_failed"
    LOCK_CONTRACT_VIOLATION = "lock_contract_violation"
    LOCK_UNAVAILABLE = "lock_unavailable"
    LOCK_RELEASE_FAILED = "lock_release_failed"
    CLEANUP_FAILED = "cleanup_failed"
    VERIFICATION_FAILED = "verification_failed"


def _json_text(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _artifact_name(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > _MAX_ARTIFACT_NAME_LENGTH
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError("artifact name must be a safe bounded basename")
    return value


def _artifact_sort_key(
    artifact: "EODRepositoryMaintenanceArtifact",
) -> Tuple[str, str, str]:
    return (
        artifact.location.value,
        artifact.name,
        artifact.artifact_class.value,
    )


def _artifact_tuple(
    value: object, field_name: str
) -> Tuple["EODRepositoryMaintenanceArtifact", ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{field_name} must be an exact list or exact tuple")
    artifacts = tuple(value)
    if any(type(item) is not EODRepositoryMaintenanceArtifact for item in artifacts):
        raise TypeError(f"{field_name} must contain exact maintenance artifacts")
    if len(artifacts) > MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS:
        raise ValueError(f"{field_name} exceeds the maintenance artifact limit")
    if artifacts != tuple(sorted(artifacts, key=_artifact_sort_key)):
        raise ValueError(f"{field_name} must be in deterministic order")
    identities = tuple((item.location, item.name) for item in artifacts)
    if len(set(identities)) != len(identities):
        raise ValueError(f"{field_name} must not contain duplicate artifacts")
    return artifacts


def _generation_id_tuple(value: object, field_name: str) -> Tuple[str, ...]:
    if type(value) not in (list, tuple):
        raise TypeError(f"{field_name} must be an exact list or exact tuple")
    values = tuple(validate_generation_id(item) for item in value)
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicate generation ids")
    return values


@dataclass(frozen=True)
class EODRepositoryMaintenanceArtifact:
    """One safe basename classified within a fixed repository location."""

    name: str
    artifact_class: EODRepositoryArtifactClass
    location: EODRepositoryArtifactLocation
    generation_id: Optional[str] = None

    def __post_init__(self) -> None:
        name = _artifact_name(self.name)
        if type(self.artifact_class) is not EODRepositoryArtifactClass:
            raise TypeError("artifact_class must be an exact maintenance enum")
        if type(self.location) is not EODRepositoryArtifactLocation:
            raise TypeError("location must be an exact maintenance location enum")
        generation_id = self.generation_id
        if generation_id is not None:
            generation_id = validate_generation_id(generation_id)
        generation_classes = {
            EODRepositoryArtifactClass.ACTIVE_CURRENT_GENERATION,
            EODRepositoryArtifactClass.REACHABLE_HISTORICAL_GENERATION,
            EODRepositoryArtifactClass.UNREACHABLE_COMPLETE_GENERATION,
        }
        if self.artifact_class in generation_classes:
            if self.location is not EODRepositoryArtifactLocation.GENERATIONS:
                raise ValueError("generation artifacts must use the generations location")
            if generation_id != name:
                raise ValueError("generation artifact name and generation_id must match")
        elif self.artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY:
            parsed = _maintenance_staging_generation_id(name)
            if self.location is not EODRepositoryArtifactLocation.DATASET or parsed is None:
                raise ValueError("staging artifacts must have one exact dataset-local name")
            if generation_id != parsed:
                raise ValueError("staging artifact generation_id must match its name")
        elif self.artifact_class is EODRepositoryArtifactClass.POINTER_TEMP_FILE:
            if self.location is not EODRepositoryArtifactLocation.DATASET or not (
                _is_maintenance_pointer_temporary_file(name)
            ):
                raise ValueError("pointer temp artifacts must have one exact dataset-local name")
            if generation_id is not None:
                raise ValueError("pointer temp artifacts cannot contain a generation_id")
        elif generation_id is not None:
            raise ValueError("unknown or unsafe artifacts cannot contain a generation_id")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "generation_id", generation_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "artifact_class": self.artifact_class.value,
            "location": self.location.value,
            "generation_id": self.generation_id,
        }


@dataclass(frozen=True)
class EODRepositoryMaintenanceRequest:
    """Explicit caller intent for one repository inspection or cleanup."""

    dataset: EODDatasetKey
    dry_run: bool = True
    cleanup_staging: bool = True
    cleanup_pointer_temps: bool = True

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.dry_run) is not bool:
            raise ValueError("dry_run must be a strict boolean")
        if type(self.cleanup_staging) is not bool:
            raise ValueError("cleanup_staging must be a strict boolean")
        if type(self.cleanup_pointer_temps) is not bool:
            raise ValueError("cleanup_pointer_temps must be a strict boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "dataset": self.dataset.to_dict(),
            "dry_run": self.dry_run,
            "cleanup_staging": self.cleanup_staging,
            "cleanup_pointer_temps": self.cleanup_pointer_temps,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


class EODRepositoryMaintenanceError(RuntimeError):
    """Safe failure that records only bounded artifact basenames."""

    def __init__(
        self,
        code: EODRepositoryMaintenanceErrorCode,
        dataset: EODDatasetKey,
        *,
        lock_key: Optional[str],
        deleted_artifacts: Tuple[str, ...] = (),
        remaining_artifacts: Tuple[str, ...] = (),
    ) -> None:
        if type(code) is not EODRepositoryMaintenanceErrorCode:
            raise TypeError("code must be an exact maintenance error code")
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if lock_key is not None and lock_key != eod_dataset_lock_key(dataset):
            raise ValueError("lock_key must be the canonical dataset lock key or None")
        deleted = tuple(_artifact_name(name) for name in deleted_artifacts)
        remaining = tuple(_artifact_name(name) for name in remaining_artifacts)
        if (
            len(deleted) > MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS
            or len(remaining) > MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS
        ):
            raise ValueError("maintenance error artifact details exceed the limit")
        self.code = code
        self.dataset = dataset
        self.lock_key = lock_key
        self.deleted_artifacts = deleted
        self.remaining_artifacts = remaining
        super().__init__("The EOD repository maintenance operation failed safely.")

    @property
    def retryable(self) -> bool:
        return self.code is EODRepositoryMaintenanceErrorCode.LOCK_UNAVAILABLE

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": str(self),
            "dataset": self.dataset.to_dict(),
            "lock_key": self.lock_key,
            "retryable": self.retryable,
            "deleted_artifacts": list(self.deleted_artifacts),
            "remaining_artifacts": list(self.remaining_artifacts),
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODRepositoryMaintenanceResult:
    """Deterministic bounded result with no absolute filesystem paths."""

    request: EODRepositoryMaintenanceRequest
    status: EODRepositoryMaintenanceStatus
    artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...]
    cleanup_candidates: Tuple[EODRepositoryMaintenanceArtifact, ...]
    deleted_artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...]
    remaining_artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...]
    current_generation_id: Optional[str]
    reachable_generation_ids: Tuple[str, ...]
    unreachable_complete_generation_ids: Tuple[str, ...]
    warnings: Tuple[EODRepositoryMaintenanceWarningCode, ...]
    lock_key: Optional[str] = None

    def __post_init__(self) -> None:
        if type(self.request) is not EODRepositoryMaintenanceRequest:
            raise TypeError("request must be an exact maintenance request")
        if type(self.status) is not EODRepositoryMaintenanceStatus:
            raise TypeError("status must be an exact maintenance status")
        artifacts = _artifact_tuple(self.artifacts, "artifacts")
        candidates = _artifact_tuple(self.cleanup_candidates, "cleanup_candidates")
        deleted = _artifact_tuple(self.deleted_artifacts, "deleted_artifacts")
        remaining = _artifact_tuple(self.remaining_artifacts, "remaining_artifacts")
        artifact_identities = {(item.location, item.name) for item in artifacts}
        candidate_identities = {(item.location, item.name) for item in candidates}
        deleted_identities = {(item.location, item.name) for item in deleted}
        remaining_identities = {(item.location, item.name) for item in remaining}
        if not candidate_identities.issubset(artifact_identities):
            raise ValueError("cleanup candidates must come from the inspected artifacts")
        if not deleted_identities.issubset(candidate_identities):
            raise ValueError("deleted artifacts must come from cleanup candidates")
        if deleted_identities & remaining_identities:
            raise ValueError("deleted artifacts cannot remain after cleanup")
        deletable_classes = {
            EODRepositoryArtifactClass.STAGING_DIRECTORY,
            EODRepositoryArtifactClass.POINTER_TEMP_FILE,
        }
        if any(item.artifact_class not in deletable_classes for item in candidates):
            raise ValueError("only exact ephemeral artifacts can be cleanup candidates")
        current_generation_id = self.current_generation_id
        if current_generation_id is not None:
            current_generation_id = validate_generation_id(current_generation_id)
        reachable = _generation_id_tuple(
            self.reachable_generation_ids,
            "reachable_generation_ids",
        )
        unreachable = _generation_id_tuple(
            self.unreachable_complete_generation_ids,
            "unreachable_complete_generation_ids",
        )
        if unreachable != tuple(sorted(unreachable)):
            raise ValueError("unreachable generation ids must be sorted")
        if set(reachable) & set(unreachable):
            raise ValueError("reachable and unreachable generations must be disjoint")
        if current_generation_id is None:
            if reachable:
                raise ValueError("reachable generations require one current generation")
        elif not reachable or reachable[0] != current_generation_id:
            raise ValueError("reachable lineage must start with the current generation")
        if type(self.warnings) not in (list, tuple):
            raise TypeError("warnings must be an exact list or exact tuple")
        warnings = tuple(self.warnings)
        if any(type(item) is not EODRepositoryMaintenanceWarningCode for item in warnings):
            raise TypeError("warnings must contain exact maintenance warning codes")
        if len(set(warnings)) != len(warnings) or warnings != tuple(
            sorted(warnings, key=lambda item: item.value)
        ):
            raise ValueError("warnings must be unique and deterministic")
        expected_lock_key = eod_dataset_lock_key(self.request.dataset)
        if self.request.dry_run:
            if self.lock_key is not None or deleted:
                raise ValueError("dry-run results cannot contain lock or deletion state")
            if self.status is EODRepositoryMaintenanceStatus.CLEANED:
                raise ValueError("dry-run cannot report cleaned status")
        elif self.lock_key != expected_lock_key:
            raise ValueError("real maintenance requires the canonical dataset lock key")
        if self.status is EODRepositoryMaintenanceStatus.BLOCKED and (candidates or deleted):
            raise ValueError("blocked maintenance cannot select or delete artifacts")
        if self.status is EODRepositoryMaintenanceStatus.CLEANED and not deleted:
            raise ValueError("cleaned status requires at least one deleted artifact")
        if deleted and self.status is not EODRepositoryMaintenanceStatus.CLEANED:
            raise ValueError("deleted artifacts require cleaned status")
        if self.status is EODRepositoryMaintenanceStatus.EMPTY and (
            artifacts or current_generation_id is not None or reachable or unreachable
        ):
            raise ValueError("empty status cannot contain repository artifacts")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "cleanup_candidates", candidates)
        object.__setattr__(self, "deleted_artifacts", deleted)
        object.__setattr__(self, "remaining_artifacts", remaining)
        object.__setattr__(self, "current_generation_id", current_generation_id)
        object.__setattr__(self, "reachable_generation_ids", reachable)
        object.__setattr__(self, "unreachable_complete_generation_ids", unreachable)
        object.__setattr__(self, "warnings", warnings)

    @property
    def staging_candidates(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.artifacts
            if item.artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY
        )

    @property
    def pointer_temp_candidates(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.artifacts
            if item.artifact_class is EODRepositoryArtifactClass.POINTER_TEMP_FILE
        )

    @property
    def unknown_artifacts(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.artifacts
            if item.artifact_class is EODRepositoryArtifactClass.UNKNOWN_ARTIFACT
        )

    @property
    def unsafe_artifacts(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.artifacts
            if item.artifact_class is EODRepositoryArtifactClass.UNSAFE_ARTIFACT
        )

    @property
    def deleted_staging(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.deleted_artifacts
            if item.artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY
        )

    @property
    def deleted_pointer_temps(self) -> Tuple[str, ...]:
        return tuple(
            item.name
            for item in self.deleted_artifacts
            if item.artifact_class is EODRepositoryArtifactClass.POINTER_TEMP_FILE
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "request": self.request.to_dict(),
            "dataset": self.request.dataset.to_dict(),
            "dry_run": self.request.dry_run,
            "status": self.status.value,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "cleanup_candidates": [item.to_dict() for item in self.cleanup_candidates],
            "staging_candidates": list(self.staging_candidates),
            "pointer_temp_candidates": list(self.pointer_temp_candidates),
            "current_generation_id": self.current_generation_id,
            "reachable_generation_ids": list(self.reachable_generation_ids),
            "unreachable_complete_generation_ids": list(self.unreachable_complete_generation_ids),
            "unknown_artifacts": list(self.unknown_artifacts),
            "unsafe_artifacts": list(self.unsafe_artifacts),
            "deleted_staging": list(self.deleted_staging),
            "deleted_pointer_temps": list(self.deleted_pointer_temps),
            "remaining_artifacts": [item.to_dict() for item in self.remaining_artifacts],
            "warnings": [item.value for item in self.warnings],
            "lock_key": self.lock_key,
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())


@dataclass(frozen=True)
class _RepositoryInspection:
    dataset_exists: bool
    artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...]
    current_generation_id: Optional[str]
    reachable_generation_ids: Tuple[str, ...]
    unreachable_complete_generation_ids: Tuple[str, ...]
    warnings: Tuple[EODRepositoryMaintenanceWarningCode, ...]
    blocked: bool
    protected_fingerprint: Tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.dataset_exists) is not bool or type(self.blocked) is not bool:
            raise TypeError("inspection flags must be strict booleans")
        artifacts = _artifact_tuple(self.artifacts, "inspection artifacts")
        reachable = _generation_id_tuple(
            self.reachable_generation_ids,
            "inspection reachable generations",
        )
        unreachable = _generation_id_tuple(
            self.unreachable_complete_generation_ids,
            "inspection unreachable generations",
        )
        if type(self.warnings) is not tuple or any(
            type(item) is not EODRepositoryMaintenanceWarningCode for item in self.warnings
        ):
            raise TypeError("inspection warnings must be exact warning tuples")
        if type(self.protected_fingerprint) is not tuple or any(
            type(item) is not str or not item for item in self.protected_fingerprint
        ):
            raise TypeError("protected_fingerprint must be a tuple of safe strings")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "reachable_generation_ids", reachable)
        object.__setattr__(self, "unreachable_complete_generation_ids", unreachable)


class EODRepositoryMaintenanceExecutor:
    """Inspect or clean exact ephemeral artifacts without touching generations."""

    def __init__(
        self,
        repository: LocalEODFileRepository,
        lock_manager: EODDatasetLockManager,
    ) -> None:
        if type(repository) is not LocalEODFileRepository:
            raise TypeError("repository must be an exact LocalEODFileRepository")
        if not isinstance(lock_manager, EODDatasetLockManager):
            raise TypeError("lock_manager must implement EODDatasetLockManager")
        self._repository = repository
        self._lock_manager = lock_manager

    def execute(
        self,
        request: EODRepositoryMaintenanceRequest,
        *,
        checkpoint: Optional[EODExecutionCheckpoint] = None,
    ) -> EODRepositoryMaintenanceResult:
        """Run one observational dry-run or one lock-protected cleanup."""

        if type(request) is not EODRepositoryMaintenanceRequest:
            raise TypeError("request must be an exact maintenance request")
        if request.dry_run:
            inspection = self._inspect(request.dataset)
            candidates = self._cleanup_candidates(inspection, request)
            return self._result(
                request,
                inspection,
                status=self._inspection_status(inspection),
                cleanup_candidates=candidates,
                deleted_artifacts=(),
                remaining_artifacts=inspection.artifacts,
                lock_key=None,
            )

        lock_key = eod_dataset_lock_key(request.dataset)
        try:
            acquired = self._lock_manager.acquire(lock_key)
        except Exception as exc:
            raise self._error(
                EODRepositoryMaintenanceErrorCode.LOCK_ACQUISITION_FAILED,
                request.dataset,
                lock_key,
            ) from exc
        if type(acquired) is not bool:
            raise self._error(
                EODRepositoryMaintenanceErrorCode.LOCK_CONTRACT_VIOLATION,
                request.dataset,
                lock_key,
            )
        if not acquired:
            raise self._error(
                EODRepositoryMaintenanceErrorCode.LOCK_UNAVAILABLE,
                request.dataset,
                lock_key,
            )

        try:
            result = self._execute_locked(
                request,
                lock_key,
                checkpoint,
            )
        except BaseException as original:
            try:
                self._lock_manager.release(lock_key)
            except Exception as release_exc:
                deleted = (
                    original.deleted_artifacts
                    if type(original) is EODRepositoryMaintenanceError
                    else ()
                )
                remaining = (
                    original.remaining_artifacts
                    if type(original) is EODRepositoryMaintenanceError
                    else ()
                )
                raise EODRepositoryMaintenanceError(
                    EODRepositoryMaintenanceErrorCode.LOCK_RELEASE_FAILED,
                    request.dataset,
                    lock_key=lock_key,
                    deleted_artifacts=deleted,
                    remaining_artifacts=remaining,
                ) from release_exc
            raise
        try:
            self._lock_manager.release(lock_key)
        except Exception as exc:
            raise EODRepositoryMaintenanceError(
                EODRepositoryMaintenanceErrorCode.LOCK_RELEASE_FAILED,
                request.dataset,
                lock_key=lock_key,
                deleted_artifacts=tuple(item.name for item in result.deleted_artifacts),
            ) from exc
        return result

    def _execute_locked(
        self,
        request: EODRepositoryMaintenanceRequest,
        lock_key: str,
        checkpoint: Optional[EODExecutionCheckpoint],
    ) -> EODRepositoryMaintenanceResult:
        inspection = self._inspect(request.dataset)
        if inspection.blocked:
            return self._result(
                request,
                inspection,
                status=EODRepositoryMaintenanceStatus.BLOCKED,
                cleanup_candidates=(),
                deleted_artifacts=(),
                remaining_artifacts=inspection.artifacts,
                lock_key=lock_key,
            )

        candidates = self._cleanup_candidates(inspection, request)
        deleted = []
        for index, artifact in enumerate(candidates):
            run_eod_checkpoint(
                checkpoint,
                EODCheckpointStage.BEFORE_MAINTENANCE_DELETE,
                request.dataset,
            )
            try:
                removed = self._remove(request.dataset, artifact)
            except EODRepositoryError as exc:
                raise EODRepositoryMaintenanceError(
                    EODRepositoryMaintenanceErrorCode.CLEANUP_FAILED,
                    request.dataset,
                    lock_key=lock_key,
                    deleted_artifacts=tuple(item.name for item in deleted),
                    remaining_artifacts=tuple(item.name for item in candidates[index:]),
                ) from exc
            if removed:
                deleted.append(artifact)

        post_cleanup = self._inspect(request.dataset)
        deleted_tuple = tuple(sorted(deleted, key=_artifact_sort_key))
        if post_cleanup.blocked or (
            post_cleanup.protected_fingerprint != inspection.protected_fingerprint
        ):
            raise EODRepositoryMaintenanceError(
                EODRepositoryMaintenanceErrorCode.VERIFICATION_FAILED,
                request.dataset,
                lock_key=lock_key,
                deleted_artifacts=tuple(item.name for item in deleted_tuple),
            )
        remaining_identities = {(item.location, item.name) for item in post_cleanup.artifacts}
        not_removed = tuple(
            item.name for item in candidates if (item.location, item.name) in remaining_identities
        )
        if not_removed:
            raise EODRepositoryMaintenanceError(
                EODRepositoryMaintenanceErrorCode.VERIFICATION_FAILED,
                request.dataset,
                lock_key=lock_key,
                deleted_artifacts=tuple(item.name for item in deleted_tuple),
                remaining_artifacts=not_removed,
            )
        status = (
            EODRepositoryMaintenanceStatus.CLEANED
            if deleted_tuple
            else self._inspection_status(post_cleanup)
        )
        return self._result(
            request,
            inspection,
            status=status,
            cleanup_candidates=candidates,
            deleted_artifacts=deleted_tuple,
            remaining_artifacts=post_cleanup.artifacts,
            lock_key=lock_key,
        )

    def _inspect(self, dataset: EODDatasetKey) -> _RepositoryInspection:
        artifacts = {}
        warnings = set()
        blocked = False
        try:
            dataset_directory = self._repository._find_existing_dataset_directory(dataset)
        except EODUnsafePathError:
            return self._blocked_inspection(
                EODRepositoryMaintenanceWarningCode.UNSAFE_ARTIFACT_DETECTED
            )
        except EODRepositoryError:
            return self._blocked_inspection(
                EODRepositoryMaintenanceWarningCode.REPOSITORY_INSPECTION_FAILED
            )
        if dataset_directory is None:
            return _RepositoryInspection(False, (), None, (), (), (), False, ())

        try:
            root_entries, root_overflow = self._bounded_children(
                dataset_directory,
                MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS,
            )
        except EODRepositoryError:
            return self._blocked_inspection(
                EODRepositoryMaintenanceWarningCode.REPOSITORY_INSPECTION_FAILED,
                dataset_exists=True,
            )
        if root_overflow:
            return self._blocked_inspection(
                EODRepositoryMaintenanceWarningCode.ARTIFACT_LIMIT_EXCEEDED,
                dataset_exists=True,
            )

        current_path = dataset_directory / _CURRENT_FILE
        generations_directory = dataset_directory / _GENERATIONS_DIRECTORY
        generations_available = False
        current_can_load = not current_path.exists()
        for candidate in root_entries:
            name = candidate.name
            try:
                _artifact_name(name)
            except ValueError:
                warnings.add(EODRepositoryMaintenanceWarningCode.ARTIFACT_LIMIT_EXCEEDED)
                blocked = True
                continue
            if candidate.is_symlink():
                self._set_artifact(
                    artifacts,
                    name,
                    EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                    EODRepositoryArtifactLocation.DATASET,
                )
                warnings.add(EODRepositoryMaintenanceWarningCode.UNSAFE_ARTIFACT_DETECTED)
                blocked = True
                continue
            if name == _CURRENT_FILE:
                current_can_load = candidate.is_file()
                if not current_can_load:
                    self._set_artifact(
                        artifacts,
                        name,
                        EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                        EODRepositoryArtifactLocation.DATASET,
                    )
                    warnings.add(EODRepositoryMaintenanceWarningCode.CURRENT_INTEGRITY_INVALID)
                    blocked = True
                continue
            if name == _GENERATIONS_DIRECTORY:
                generations_available = candidate.is_dir()
                if not generations_available:
                    self._set_artifact(
                        artifacts,
                        name,
                        EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                        EODRepositoryArtifactLocation.DATASET,
                    )
                    warnings.add(EODRepositoryMaintenanceWarningCode.UNSAFE_ARTIFACT_DETECTED)
                    blocked = True
                continue
            staging_generation_id = _maintenance_staging_generation_id(name)
            if staging_generation_id is not None:
                artifact_class = (
                    EODRepositoryArtifactClass.STAGING_DIRECTORY
                    if candidate.is_dir()
                    else EODRepositoryArtifactClass.UNSAFE_ARTIFACT
                )
                self._set_artifact(
                    artifacts,
                    name,
                    artifact_class,
                    EODRepositoryArtifactLocation.DATASET,
                    generation_id=(
                        staging_generation_id
                        if artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY
                        else None
                    ),
                )
                if artifact_class is EODRepositoryArtifactClass.UNSAFE_ARTIFACT:
                    warnings.add(EODRepositoryMaintenanceWarningCode.UNSAFE_ARTIFACT_DETECTED)
                    blocked = True
                continue
            if _is_maintenance_pointer_temporary_file(name):
                artifact_class = (
                    EODRepositoryArtifactClass.POINTER_TEMP_FILE
                    if candidate.is_file()
                    else EODRepositoryArtifactClass.UNSAFE_ARTIFACT
                )
                self._set_artifact(
                    artifacts,
                    name,
                    artifact_class,
                    EODRepositoryArtifactLocation.DATASET,
                )
                if artifact_class is EODRepositoryArtifactClass.UNSAFE_ARTIFACT:
                    warnings.add(EODRepositoryMaintenanceWarningCode.UNSAFE_ARTIFACT_DETECTED)
                    blocked = True
                continue
            self._set_artifact(
                artifacts,
                name,
                EODRepositoryArtifactClass.UNKNOWN_ARTIFACT,
                EODRepositoryArtifactLocation.DATASET,
            )
            warnings.add(EODRepositoryMaintenanceWarningCode.UNKNOWN_ARTIFACT_PRESERVED)

        loaded_generations = {}
        generation_fingerprints = {}
        if generations_available:
            remaining_limit = MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS - len(artifacts)
            try:
                generation_entries, generation_overflow = self._bounded_children(
                    generations_directory,
                    remaining_limit,
                )
            except EODRepositoryError:
                generation_entries, generation_overflow = (), False
                warnings.add(EODRepositoryMaintenanceWarningCode.REPOSITORY_INSPECTION_FAILED)
                blocked = True
            if generation_overflow:
                warnings.add(EODRepositoryMaintenanceWarningCode.ARTIFACT_LIMIT_EXCEEDED)
                blocked = True
            else:
                for candidate in generation_entries:
                    name = candidate.name
                    try:
                        generation_id = validate_generation_id(name)
                        _artifact_name(name)
                    except ValueError:
                        self._set_artifact(
                            artifacts,
                            name,
                            EODRepositoryArtifactClass.UNKNOWN_ARTIFACT,
                            EODRepositoryArtifactLocation.GENERATIONS,
                        )
                        warnings.add(
                            EODRepositoryMaintenanceWarningCode.INVALID_GENERATION_ARTIFACT
                        )
                        blocked = True
                        continue
                    manifest_path = candidate / "manifest.json"
                    parquet_path = candidate / EOD_PARQUET_FILE
                    unsafe = (
                        candidate.is_symlink()
                        or not candidate.is_dir()
                        or manifest_path.is_symlink()
                        or parquet_path.is_symlink()
                        or not manifest_path.is_file()
                        or not parquet_path.is_file()
                    )
                    if unsafe:
                        self._set_artifact(
                            artifacts,
                            name,
                            EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                            EODRepositoryArtifactLocation.GENERATIONS,
                        )
                        warnings.add(
                            EODRepositoryMaintenanceWarningCode.INVALID_GENERATION_ARTIFACT
                        )
                        blocked = True
                        continue
                    try:
                        stored = self._repository.load_generation(dataset, generation_id)
                        manifest_sha = calculate_file_sha256(manifest_path)
                        parquet_sha = calculate_file_sha256(parquet_path)
                    except EODRepositoryError:
                        self._set_artifact(
                            artifacts,
                            name,
                            EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                            EODRepositoryArtifactLocation.GENERATIONS,
                        )
                        warnings.add(
                            EODRepositoryMaintenanceWarningCode.INVALID_GENERATION_ARTIFACT
                        )
                        blocked = True
                        continue
                    loaded_generations[generation_id] = stored
                    generation_fingerprints[generation_id] = (
                        f"generation:{generation_id}:{manifest_sha}:{parquet_sha}"
                    )

        current = None
        pointer_fingerprint = None
        if current_can_load:
            try:
                current = self._repository.load_current(dataset)
                if current is not None:
                    pointer_fingerprint = f"current:{calculate_file_sha256(current_path)}"
            except EODRepositoryError:
                self._set_artifact(
                    artifacts,
                    _CURRENT_FILE,
                    EODRepositoryArtifactClass.UNSAFE_ARTIFACT,
                    EODRepositoryArtifactLocation.DATASET,
                )
                warnings.add(EODRepositoryMaintenanceWarningCode.CURRENT_INTEGRITY_INVALID)
                blocked = True

        current_generation_id = None if current is None else current.manifest.generation_id
        reachable = []
        if current_generation_id is not None:
            cursor = current_generation_id
            seen = set()
            while cursor is not None:
                if cursor in seen:
                    warnings.add(EODRepositoryMaintenanceWarningCode.GENERATION_LINEAGE_CYCLE)
                    blocked = True
                    break
                if len(reachable) >= MAX_EOD_GENERATION_LINEAGE_DEPTH:
                    warnings.add(
                        EODRepositoryMaintenanceWarningCode.GENERATION_LINEAGE_LIMIT_EXCEEDED
                    )
                    blocked = True
                    break
                stored = loaded_generations.get(cursor)
                if stored is None:
                    warnings.add(EODRepositoryMaintenanceWarningCode.BROKEN_GENERATION_LINEAGE)
                    blocked = True
                    break
                seen.add(cursor)
                reachable.append(cursor)
                cursor = stored.manifest.previous_generation_id
        elif loaded_generations:
            warnings.add(EODRepositoryMaintenanceWarningCode.AMBIGUOUS_GENERATIONS_WITHOUT_CURRENT)
            blocked = True

        reachable_set = set(reachable)
        unreachable = tuple(sorted(set(loaded_generations).difference(reachable_set)))
        if unreachable:
            warnings.add(
                EODRepositoryMaintenanceWarningCode.UNREACHABLE_COMPLETE_GENERATION_PRESERVED
            )
        for generation_id in sorted(loaded_generations):
            if generation_id == current_generation_id:
                artifact_class = EODRepositoryArtifactClass.ACTIVE_CURRENT_GENERATION
            elif generation_id in reachable_set:
                artifact_class = EODRepositoryArtifactClass.REACHABLE_HISTORICAL_GENERATION
            else:
                artifact_class = EODRepositoryArtifactClass.UNREACHABLE_COMPLETE_GENERATION
            self._set_artifact(
                artifacts,
                generation_id,
                artifact_class,
                EODRepositoryArtifactLocation.GENERATIONS,
                generation_id=generation_id,
            )

        ordered_artifacts = tuple(sorted(artifacts.values(), key=_artifact_sort_key))
        fingerprints = tuple(
            ([pointer_fingerprint] if pointer_fingerprint is not None else [])
            + [generation_fingerprints[key] for key in sorted(generation_fingerprints)]
        )
        return _RepositoryInspection(
            True,
            ordered_artifacts,
            current_generation_id,
            tuple(reachable),
            unreachable,
            tuple(sorted(warnings, key=lambda item: item.value)),
            blocked,
            fingerprints,
        )

    @staticmethod
    def _bounded_children(directory: object, limit: int) -> Tuple[Tuple[object, ...], bool]:
        if type(limit) is not int or limit < 0:
            raise ValueError("artifact inspection limit must be non-negative")
        entries = []
        try:
            for candidate in directory.iterdir():
                if len(entries) >= limit:
                    return (), True
                entries.append(candidate)
        except OSError as exc:
            raise EODRepositoryError("repository maintenance inspection failed") from exc
        return tuple(sorted(entries, key=lambda item: item.name)), False

    @staticmethod
    def _set_artifact(
        artifacts: dict[
            Tuple[EODRepositoryArtifactLocation, str], EODRepositoryMaintenanceArtifact
        ],
        name: str,
        artifact_class: EODRepositoryArtifactClass,
        location: EODRepositoryArtifactLocation,
        *,
        generation_id: Optional[str] = None,
    ) -> None:
        artifact = EODRepositoryMaintenanceArtifact(
            name=name,
            artifact_class=artifact_class,
            location=location,
            generation_id=generation_id,
        )
        artifacts[(location, name)] = artifact

    @staticmethod
    def _blocked_inspection(
        warning: EODRepositoryMaintenanceWarningCode,
        *,
        dataset_exists: bool = False,
    ) -> _RepositoryInspection:
        return _RepositoryInspection(
            dataset_exists,
            (),
            None,
            (),
            (),
            (warning,),
            True,
            (),
        )

    @staticmethod
    def _cleanup_candidates(
        inspection: _RepositoryInspection,
        request: EODRepositoryMaintenanceRequest,
    ) -> Tuple[EODRepositoryMaintenanceArtifact, ...]:
        if inspection.blocked:
            return ()
        selected = []
        for artifact in inspection.artifacts:
            if (
                artifact.artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY
                and request.cleanup_staging
            ) or (
                artifact.artifact_class is EODRepositoryArtifactClass.POINTER_TEMP_FILE
                and request.cleanup_pointer_temps
            ):
                selected.append(artifact)
        return tuple(sorted(selected, key=_artifact_sort_key))

    def _remove(
        self,
        dataset: EODDatasetKey,
        artifact: EODRepositoryMaintenanceArtifact,
    ) -> bool:
        if artifact.artifact_class is EODRepositoryArtifactClass.STAGING_DIRECTORY:
            return self._repository._remove_maintenance_staging_directory(
                dataset,
                artifact.name,
            )
        if artifact.artifact_class is EODRepositoryArtifactClass.POINTER_TEMP_FILE:
            return self._repository._remove_maintenance_pointer_temporary_file(
                dataset,
                artifact.name,
            )
        raise ValueError("maintenance attempted to remove a non-ephemeral artifact")

    @staticmethod
    def _inspection_status(
        inspection: _RepositoryInspection,
    ) -> EODRepositoryMaintenanceStatus:
        if inspection.blocked:
            return EODRepositoryMaintenanceStatus.BLOCKED
        if not inspection.dataset_exists:
            return EODRepositoryMaintenanceStatus.EMPTY
        return EODRepositoryMaintenanceStatus.INSPECTED

    @staticmethod
    def _result(
        request: EODRepositoryMaintenanceRequest,
        inspection: _RepositoryInspection,
        *,
        status: EODRepositoryMaintenanceStatus,
        cleanup_candidates: Tuple[EODRepositoryMaintenanceArtifact, ...],
        deleted_artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...],
        remaining_artifacts: Tuple[EODRepositoryMaintenanceArtifact, ...],
        lock_key: Optional[str],
    ) -> EODRepositoryMaintenanceResult:
        return EODRepositoryMaintenanceResult(
            request=request,
            status=status,
            artifacts=inspection.artifacts,
            cleanup_candidates=cleanup_candidates,
            deleted_artifacts=deleted_artifacts,
            remaining_artifacts=remaining_artifacts,
            current_generation_id=inspection.current_generation_id,
            reachable_generation_ids=inspection.reachable_generation_ids,
            unreachable_complete_generation_ids=(inspection.unreachable_complete_generation_ids),
            warnings=inspection.warnings,
            lock_key=lock_key,
        )

    @staticmethod
    def _error(
        code: EODRepositoryMaintenanceErrorCode,
        dataset: EODDatasetKey,
        lock_key: str,
    ) -> EODRepositoryMaintenanceError:
        return EODRepositoryMaintenanceError(
            code,
            dataset,
            lock_key=lock_key,
        )


__all__ = [
    "EODRepositoryArtifactClass",
    "EODRepositoryArtifactLocation",
    "EODRepositoryMaintenanceArtifact",
    "EODRepositoryMaintenanceError",
    "EODRepositoryMaintenanceErrorCode",
    "EODRepositoryMaintenanceExecutor",
    "EODRepositoryMaintenanceRequest",
    "EODRepositoryMaintenanceResult",
    "EODRepositoryMaintenanceStatus",
    "EODRepositoryMaintenanceWarningCode",
    "MAX_EOD_GENERATION_LINEAGE_DEPTH",
    "MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS",
]
