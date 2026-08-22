from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import os
import shutil
from typing import Optional, Tuple

import pytest

import autowealth.market_data.maintenance as maintenance_module
import autowealth.market_data.repositories as repositories_module
from autowealth.market_data.batch import (
    InProcessEODDatasetLockManager,
    eod_dataset_lock_key,
)
from autowealth.market_data.maintenance import (
    EODRepositoryArtifactClass,
    EODRepositoryMaintenanceError,
    EODRepositoryMaintenanceErrorCode,
    EODRepositoryMaintenanceExecutor,
    EODRepositoryMaintenanceRequest,
    EODRepositoryMaintenanceStatus,
    EODRepositoryMaintenanceWarningCode,
    MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS,
)
from autowealth.market_data.repositories import (
    EODRepositoryError,
    LocalEODFileRepository,
)
from autowealth.market_data.schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_POINTER_SCHEMA_VERSION,
    EODCurrentPointer,
    calculate_file_sha256,
)

GENERATION_ONE = "generation_20240103"
GENERATION_TWO = "generation_20240104"
GENERATION_THREE = "generation_20240105"
CREATED_ONE = datetime(2024, 1, 3, 8, tzinfo=timezone.utc)
CREATED_TWO = datetime(2024, 1, 4, 8, tzinfo=timezone.utc)
CREATED_THREE = datetime(2024, 1, 5, 8, tzinfo=timezone.utc)
STAGING_ONE = f".{GENERATION_TWO}.0123456789abcdef.staging"
STAGING_TWO = f".{GENERATION_THREE}.fedcba9876543210.staging"
POINTER_TEMP = ".current.0123456789abcdef.tmp"


@pytest.fixture
def dataset() -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol="600000.SH",
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


@pytest.fixture
def other_dataset() -> EODDatasetKey:
    return EODDatasetKey(
        market=Market.CN,
        venue=Venue.SZSE,
        asset_type=AssetType.EQUITY,
        canonical_symbol="000001.SZ",
        frequency=BarFrequency.DAILY,
        adjustment_type=AdjustmentType.NONE,
    )


def make_bar(dataset: EODDatasetKey, trade_date: date, close: str) -> EODBar:
    close_value = Decimal(close)
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=close_value,
        high=close_value + Decimal("1"),
        low=close_value - Decimal("1"),
        close=close_value,
        volume=Decimal("1000"),
        amount=close_value * Decimal("1000"),
    )


def bars(dataset: EODDatasetKey, count: int) -> Tuple[EODBar, ...]:
    dates = (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    return tuple(make_bar(dataset, dates[index], str(10 + index)) for index in range(count))


def dataset_directory(root: Path, dataset: EODDatasetKey) -> Path:
    return root.joinpath(
        dataset.market.value,
        dataset.venue.value,
        dataset.asset_type.value,
        dataset.canonical_symbol,
        dataset.frequency.value,
        dataset.adjustment_type.value,
    )


def generation_directory(root: Path, dataset: EODDatasetKey, generation_id: str) -> Path:
    return dataset_directory(root, dataset) / "generations" / generation_id


def publish_generations(
    repository: LocalEODFileRepository,
    dataset: EODDatasetKey,
    count: int,
) -> None:
    values = (
        (GENERATION_ONE, CREATED_ONE, 1),
        (GENERATION_TWO, CREATED_TWO, 2),
        (GENERATION_THREE, CREATED_THREE, 3),
    )
    for generation_id, created_at, row_count in values[:count]:
        repository.publish(
            dataset,
            bars(dataset, row_count),
            generation_id=generation_id,
            created_at=created_at,
        )


def write_current_pointer(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
    committed_at: datetime,
) -> None:
    generation_dir = generation_directory(root, dataset, generation_id)
    manifest_sha = calculate_file_sha256(generation_dir / "manifest.json")
    pointer = EODCurrentPointer(
        pointer_schema_version=EOD_POINTER_SCHEMA_VERSION,
        dataset=dataset,
        generation_id=generation_id,
        manifest_sha256=manifest_sha,
        committed_at=committed_at,
    )
    (dataset_directory(root, dataset) / "current.json").write_text(
        pointer.to_json(),
        encoding="utf-8",
    )


def snapshot_files(directory: Path) -> dict[str, bytes]:
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


class RecordingLockManager:
    def __init__(self) -> None:
        self.held = set()
        self.events = []
        self.acquire_count = 0
        self.release_count = 0

    def acquire(self, lock_key: str) -> bool:
        self.acquire_count += 1
        self.events.append(("acquire", lock_key))
        if lock_key in self.held:
            return False
        self.held.add(lock_key)
        return True

    def release(self, lock_key: str) -> None:
        self.release_count += 1
        self.events.append(("release", lock_key))
        self.held.remove(lock_key)


@pytest.mark.parametrize(
    ("artifact_name", "is_directory", "result_field"),
    (
        (STAGING_ONE, True, "staging_candidates"),
        (POINTER_TEMP, False, "pointer_temp_candidates"),
    ),
)
def test_exact_ephemeral_dry_run_reports_without_delete(
    tmp_path: Path,
    dataset: EODDatasetKey,
    artifact_name: str,
    is_directory: bool,
    result_field: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / artifact_name
    candidate.mkdir() if is_directory else candidate.write_text("temporary", encoding="utf-8")
    lock_manager = RecordingLockManager()

    result = EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
        EODRepositoryMaintenanceRequest(dataset)
    )

    assert result.status is EODRepositoryMaintenanceStatus.INSPECTED
    assert getattr(result, result_field) == (artifact_name,)
    assert candidate.exists()
    assert lock_manager.acquire_count == 0
    assert lock_manager.release_count == 0


@pytest.mark.parametrize(
    ("artifact_name", "is_directory", "deleted_field"),
    (
        (STAGING_ONE, True, "deleted_staging"),
        (POINTER_TEMP, False, "deleted_pointer_temps"),
    ),
)
def test_exact_ephemeral_real_cleanup_deletes_only_candidate(
    tmp_path: Path,
    dataset: EODDatasetKey,
    artifact_name: str,
    is_directory: bool,
    deleted_field: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / artifact_name
    candidate.mkdir() if is_directory else candidate.write_text("temporary", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.CLEANED
    assert getattr(result, deleted_field) == (artifact_name,)
    assert not candidate.exists()
    assert repository.load_current_manifest(dataset).generation_id == GENERATION_ONE


def test_second_real_cleanup_is_idempotent(tmp_path: Path, dataset: EODDatasetKey) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    staging = dataset_directory(root, dataset) / STAGING_ONE
    staging.mkdir()
    executor = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    )
    request = EODRepositoryMaintenanceRequest(dataset, dry_run=False)

    first = executor.execute(request)
    second = executor.execute(request)

    assert first.deleted_staging == (STAGING_ONE,)
    assert second.status is EODRepositoryMaintenanceStatus.INSPECTED
    assert second.deleted_staging == ()
    assert second.deleted_pointer_temps == ()


@pytest.mark.parametrize(
    "name",
    (
        ".generation_20240104.0123456789abcde.staging",
        ".generation_20240104.0123456789abcdefg.staging",
        ".generation_20240104.0123456789ABCDEf.staging",
        "generation_20240104.0123456789abcdef.staging",
        ".notes.staging",
        "foo.staging",
        ".current.0123456789abcde.tmp",
        ".current.0123456789abcdefg.tmp",
        ".current.0123456789ABCDEf.tmp",
        "current.0123456789abcdef.tmp",
        "manual.tmp",
    ),
)
def test_near_match_names_are_unknown_and_preserved(
    tmp_path: Path,
    dataset: EODDatasetKey,
    name: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / name
    candidate.write_text("keep", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert name in result.unknown_artifacts
    assert candidate.read_text(encoding="utf-8") == "keep"
    assert result.deleted_staging == ()
    assert result.deleted_pointer_temps == ()


@pytest.mark.parametrize("is_directory", (False, True))
def test_unknown_artifacts_are_reported_and_preserved(
    tmp_path: Path,
    dataset: EODDatasetKey,
    is_directory: bool,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / (
        "unexpected-dir" if is_directory else "README.txt"
    )
    candidate.mkdir() if is_directory else candidate.write_text("keep", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert candidate.name in result.unknown_artifacts
    assert candidate.exists()
    assert EODRepositoryMaintenanceWarningCode.UNKNOWN_ARTIFACT_PRESERVED in result.warnings


def test_missing_dataset_inspection_and_cleanup_create_nothing(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "missing-eod"
    executor = EODRepositoryMaintenanceExecutor(
        LocalEODFileRepository(root),
        InProcessEODDatasetLockManager(),
    )

    dry_result = executor.execute(EODRepositoryMaintenanceRequest(dataset))
    real_result = executor.execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert dry_result.status is EODRepositoryMaintenanceStatus.EMPTY
    assert real_result.status is EODRepositoryMaintenanceStatus.EMPTY
    assert not root.exists()


def test_valid_current_lineage_classifies_all_reachable(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 3)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset))

    assert result.current_generation_id == GENERATION_THREE
    assert result.reachable_generation_ids == (
        GENERATION_THREE,
        GENERATION_TWO,
        GENERATION_ONE,
    )
    assert result.unreachable_complete_generation_ids == ()
    classes = {item.name: item.artifact_class for item in result.artifacts}
    assert classes[GENERATION_THREE] is EODRepositoryArtifactClass.ACTIVE_CURRENT_GENERATION
    assert classes[GENERATION_TWO] is EODRepositoryArtifactClass.REACHABLE_HISTORICAL_GENERATION
    assert classes[GENERATION_ONE] is EODRepositoryArtifactClass.REACHABLE_HISTORICAL_GENERATION


def test_rollback_generation_is_unreachable_and_preserved(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 3)
    write_current_pointer(root, dataset, GENERATION_TWO, CREATED_THREE)
    generation_three_before = snapshot_files(generation_directory(root, dataset, GENERATION_THREE))

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.current_generation_id == GENERATION_TWO
    assert result.unreachable_complete_generation_ids == (GENERATION_THREE,)
    assert snapshot_files(generation_directory(root, dataset, GENERATION_THREE)) == (
        generation_three_before
    )
    assert result.deleted_artifacts == ()


def test_pointer_publication_failure_orphan_is_reported_and_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    original_replace = repositories_module.os.replace

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("injected pointer failure")

    monkeypatch.setattr(repositories_module.os, "replace", fail_replace)
    with pytest.raises(EODRepositoryError):
        repository.publish(
            dataset,
            bars(dataset, 2),
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    monkeypatch.setattr(repositories_module.os, "replace", original_replace)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.current_generation_id == GENERATION_ONE
    assert result.unreachable_complete_generation_ids == (GENERATION_TWO,)
    assert generation_directory(root, dataset, GENERATION_TWO).is_dir()
    assert result.deleted_artifacts == ()


def test_broken_previous_generation_fails_closed(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 2)
    shutil.rmtree(generation_directory(root, dataset, GENERATION_ONE))
    staging = dataset_directory(root, dataset) / STAGING_TWO
    staging.mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert staging.is_dir()
    assert EODRepositoryMaintenanceWarningCode.BROKEN_GENERATION_LINEAGE in result.warnings
    assert result.deleted_artifacts == ()


def test_generation_lineage_cycle_fails_closed(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 2)
    first = repository.load_generation(dataset, GENERATION_ONE)
    cyclic_manifest = replace(first.manifest, previous_generation_id=GENERATION_TWO)
    (generation_directory(root, dataset, GENERATION_ONE) / "manifest.json").write_text(
        cyclic_manifest.to_json(),
        encoding="utf-8",
    )
    staging = dataset_directory(root, dataset) / STAGING_TWO
    staging.mkdir()
    before = snapshot_files(dataset_directory(root, dataset))

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert staging.is_dir()
    assert snapshot_files(dataset_directory(root, dataset)) == before
    assert EODRepositoryMaintenanceWarningCode.GENERATION_LINEAGE_CYCLE in result.warnings


def test_generation_lineage_bound_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 3)
    staging = dataset_directory(root, dataset) / STAGING_ONE
    staging.mkdir()
    before = snapshot_files(dataset_directory(root, dataset))
    monkeypatch.setattr(maintenance_module, "MAX_EOD_GENERATION_LINEAGE_DEPTH", 2)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert staging.is_dir()
    assert snapshot_files(dataset_directory(root, dataset)) == before
    assert EODRepositoryMaintenanceWarningCode.GENERATION_LINEAGE_LIMIT_EXCEEDED in result.warnings


def test_malformed_current_fails_closed_before_cleanup(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    current = dataset_dir / "current.json"
    current.write_text("{not-json", encoding="utf-8")
    staging = dataset_dir / STAGING_ONE
    staging.mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert staging.is_dir()
    assert current.read_text(encoding="utf-8") == "{not-json"
    assert EODRepositoryMaintenanceWarningCode.CURRENT_INTEGRITY_INVALID in result.warnings


def test_current_pointing_to_missing_generation_fails_closed(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    missing_pointer = EODCurrentPointer(
        pointer_schema_version=EOD_POINTER_SCHEMA_VERSION,
        dataset=dataset,
        generation_id="missing_generation",
        manifest_sha256="a" * 64,
        committed_at=CREATED_TWO,
    )
    dataset_dir = dataset_directory(root, dataset)
    (dataset_dir / "current.json").write_text(
        missing_pointer.to_json(),
        encoding="utf-8",
    )
    staging = dataset_dir / STAGING_ONE
    staging.mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert staging.is_dir()
    assert EODRepositoryMaintenanceWarningCode.CURRENT_INTEGRITY_INVALID in result.warnings


def test_complete_generations_without_current_are_ambiguous_and_block_cleanup(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    (dataset_dir / "current.json").unlink()
    staging = dataset_dir / STAGING_ONE
    staging.mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert result.unreachable_complete_generation_ids == (GENERATION_ONE,)
    assert staging.is_dir()
    assert (
        EODRepositoryMaintenanceWarningCode.AMBIGUOUS_GENERATIONS_WITHOUT_CURRENT in result.warnings
    )


def test_incomplete_generation_artifact_blocks_cleanup_and_is_preserved(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    incomplete = dataset_directory(root, dataset) / "generations" / "incomplete"
    incomplete.mkdir()
    staging = dataset_directory(root, dataset) / STAGING_ONE
    staging.mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert incomplete.is_dir()
    assert staging.is_dir()
    assert EODRepositoryMaintenanceWarningCode.INVALID_GENERATION_ARTIFACT in result.warnings


def create_symlink_or_skip(target: Path, link: Path, *, is_directory: bool) -> None:
    try:
        os.symlink(target, link, target_is_directory=is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc.__class__.__name__}")


@pytest.mark.parametrize(
    ("artifact_name", "is_directory"),
    ((STAGING_ONE, True), (POINTER_TEMP, False)),
)
def test_ephemeral_symlink_fails_closed_without_deleting_target(
    tmp_path: Path,
    dataset: EODDatasetKey,
    artifact_name: str,
    is_directory: bool,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    external = tmp_path / ("external-dir" if is_directory else "external-file")
    external.mkdir() if is_directory else external.write_text("keep", encoding="utf-8")
    link = dataset_directory(root, dataset) / artifact_name
    create_symlink_or_skip(external, link, is_directory=is_directory)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert link.is_symlink()
    assert external.exists()
    assert artifact_name in result.unsafe_artifacts


def test_generation_symlink_fails_closed_without_following_target(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    external = tmp_path / "external-generation"
    external.mkdir()
    (external / "secret.txt").write_text("keep", encoding="utf-8")
    link = dataset_directory(root, dataset) / "generations" / GENERATION_TWO
    create_symlink_or_skip(external, link, is_directory=True)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert link.is_symlink()
    assert (external / "secret.txt").read_text(encoding="utf-8") == "keep"


def test_current_symlink_fails_closed_without_following_target(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    current = dataset_directory(root, dataset) / "current.json"
    current.unlink()
    external = tmp_path / "external-current.json"
    external.write_text("keep", encoding="utf-8")
    create_symlink_or_skip(external, current, is_directory=False)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert current.is_symlink()
    assert external.read_text(encoding="utf-8") == "keep"


def test_real_cleanup_acquires_lock_before_first_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    lock_manager = RecordingLockManager()
    lock_key = eod_dataset_lock_key(dataset)
    original = repository._find_existing_dataset_directory
    inspection_count = 0

    def guarded_inspection(value: EODDatasetKey) -> Optional[Path]:
        nonlocal inspection_count
        inspection_count += 1
        assert lock_key in lock_manager.held
        lock_manager.events.append(("inspect", lock_key))
        return original(value)

    monkeypatch.setattr(repository, "_find_existing_dataset_directory", guarded_inspection)

    EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
        EODRepositoryMaintenanceRequest(dataset, dry_run=False)
    )

    assert inspection_count == 2
    assert lock_manager.events[0] == ("acquire", lock_key)
    assert lock_manager.events[-1] == ("release", lock_key)


@pytest.mark.parametrize("writer", ("incremental", "full_refresh"))
def test_same_dataset_writer_lock_blocks_maintenance(
    tmp_path: Path,
    dataset: EODDatasetKey,
    writer: str,
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    lock_manager = InProcessEODDatasetLockManager()
    lock_key = eod_dataset_lock_key(dataset)
    assert lock_manager.acquire(lock_key)

    with pytest.raises(EODRepositoryMaintenanceError) as captured:
        EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
            EODRepositoryMaintenanceRequest(dataset, dry_run=False)
        )

    assert writer in {"incremental", "full_refresh"}
    assert captured.value.code is EODRepositoryMaintenanceErrorCode.LOCK_UNAVAILABLE
    lock_manager.release(lock_key)


def test_different_dataset_lock_is_independent(
    tmp_path: Path,
    dataset: EODDatasetKey,
    other_dataset: EODDatasetKey,
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    lock_manager = InProcessEODDatasetLockManager()
    first_key = eod_dataset_lock_key(dataset)
    assert lock_manager.acquire(first_key)

    result = EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
        EODRepositoryMaintenanceRequest(other_dataset, dry_run=False)
    )

    assert result.status is EODRepositoryMaintenanceStatus.EMPTY
    lock_manager.release(first_key)


def test_dry_run_does_not_mutate_any_repository_bytes(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 2)
    dataset_dir = dataset_directory(root, dataset)
    (dataset_dir / STAGING_TWO).mkdir()
    (dataset_dir / POINTER_TEMP).write_text("temporary", encoding="utf-8")
    before = snapshot_files(dataset_dir)

    EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset))

    assert snapshot_files(dataset_dir) == before


def test_real_cleanup_reinspects_after_dry_run(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    executor = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    )
    dataset_dir = dataset_directory(root, dataset)
    dry_candidate = dataset_dir / STAGING_ONE
    dry_candidate.mkdir()
    dry_result = executor.execute(EODRepositoryMaintenanceRequest(dataset))
    shutil.rmtree(dry_candidate)
    real_candidate = dataset_dir / STAGING_TWO
    real_candidate.mkdir()

    real_result = executor.execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert dry_result.staging_candidates == (STAGING_ONE,)
    assert real_result.deleted_staging == (STAGING_TWO,)
    assert not dry_candidate.exists()
    assert not real_candidate.exists()


@pytest.mark.parametrize(
    ("artifact_name", "is_directory", "helper_name"),
    (
        (STAGING_ONE, True, "_remove_maintenance_staging_directory"),
        (POINTER_TEMP, False, "_remove_maintenance_pointer_temporary_file"),
    ),
)
def test_delete_error_is_explicit_and_releases_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    artifact_name: str,
    is_directory: bool,
    helper_name: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / artifact_name
    candidate.mkdir() if is_directory else candidate.write_text("temporary", encoding="utf-8")
    lock_manager = RecordingLockManager()

    def fail(*args: object, **kwargs: object) -> bool:
        raise EODRepositoryError("injected maintenance cleanup failure")

    monkeypatch.setattr(repository, helper_name, fail)
    with pytest.raises(EODRepositoryMaintenanceError) as captured:
        EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
            EODRepositoryMaintenanceRequest(dataset, dry_run=False)
        )

    assert captured.value.code is EODRepositoryMaintenanceErrorCode.CLEANUP_FAILED
    assert captured.value.remaining_artifacts == (artifact_name,)
    assert candidate.exists()
    assert lock_manager.acquire_count == 1
    assert lock_manager.release_count == 1


def test_partial_cleanup_failure_reports_deleted_and_remaining(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    staging = dataset_dir / STAGING_ONE
    pointer_temp = dataset_dir / POINTER_TEMP
    staging.mkdir()
    pointer_temp.write_text("temporary", encoding="utf-8")
    lock_manager = RecordingLockManager()

    def fail_staging(*args: object, **kwargs: object) -> bool:
        raise EODRepositoryError("injected staging failure")

    monkeypatch.setattr(repository, "_remove_maintenance_staging_directory", fail_staging)
    with pytest.raises(EODRepositoryMaintenanceError) as captured:
        EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
            EODRepositoryMaintenanceRequest(dataset, dry_run=False)
        )

    assert captured.value.deleted_artifacts == (POINTER_TEMP,)
    assert captured.value.remaining_artifacts == (STAGING_ONE,)
    assert not pointer_temp.exists()
    assert staging.is_dir()
    assert lock_manager.release_count == 1


def test_cleanup_preserves_current_and_complete_generation_bytes(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 3)
    write_current_pointer(root, dataset, GENERATION_TWO, CREATED_THREE)
    dataset_dir = dataset_directory(root, dataset)
    current_before = (dataset_dir / "current.json").read_bytes()
    generations_before = snapshot_files(dataset_dir / "generations")
    (dataset_dir / STAGING_ONE).mkdir()
    (dataset_dir / POINTER_TEMP).write_text("temporary", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.CLEANED
    assert (dataset_dir / "current.json").read_bytes() == current_before
    assert snapshot_files(dataset_dir / "generations") == generations_before
    assert generation_directory(root, dataset, GENERATION_THREE).is_dir()


def test_result_serialization_is_deterministic_json_safe_and_path_free(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "Authorization=Bearer-test-secret"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    (dataset_dir / STAGING_ONE).mkdir()
    (dataset_dir / POINTER_TEMP).write_text("temporary", encoding="utf-8")
    (dataset_dir / "README.txt").write_text("keep", encoding="utf-8")
    executor = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    )

    first = executor.execute(EODRepositoryMaintenanceRequest(dataset))
    second = executor.execute(EODRepositoryMaintenanceRequest(dataset))
    serialized = first.to_json()

    assert serialized == second.to_json()
    assert json.loads(serialized) == first.to_dict()
    assert str(root) not in serialized
    assert str(tmp_path) not in serialized
    assert "Bearer-test-secret" not in serialized
    assert "README.txt" in serialized


def test_artifact_limit_blocks_cleanup_without_unreported_deletion(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    staging = dataset_dir / STAGING_ONE
    staging.mkdir()
    for index in range(MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS):
        (dataset_dir / f"unknown-{index:03d}").write_text("keep", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert result.artifacts == ()
    assert staging.is_dir()
    assert EODRepositoryMaintenanceWarningCode.ARTIFACT_LIMIT_EXCEEDED in result.warnings


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("dry_run", 1),
        ("cleanup_staging", 1),
        ("cleanup_pointer_temps", None),
    ),
)
def test_request_flags_require_strict_booleans(
    dataset: EODDatasetKey,
    field_name: str,
    value: object,
) -> None:
    values = {
        "dry_run": True,
        "cleanup_staging": True,
        "cleanup_pointer_temps": True,
    }
    values[field_name] = value

    with pytest.raises(ValueError, match="strict boolean"):
        EODRepositoryMaintenanceRequest(dataset, **values)


def test_request_has_no_generation_cleanup_or_retention_contract(
    dataset: EODDatasetKey,
) -> None:
    request = EODRepositoryMaintenanceRequest(dataset)

    assert request.dry_run is True
    assert not hasattr(request, "cleanup_generations")
    assert not hasattr(request, "prune_generations")
    assert not hasattr(request, "retention_days")


def test_selective_cleanup_flags_only_remove_authorized_ephemeral_class(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    staging = dataset_dir / STAGING_ONE
    pointer_temp = dataset_dir / POINTER_TEMP
    staging.mkdir()
    pointer_temp.write_text("temporary", encoding="utf-8")

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(
        EODRepositoryMaintenanceRequest(
            dataset,
            dry_run=False,
            cleanup_staging=False,
            cleanup_pointer_temps=True,
        )
    )

    assert result.deleted_staging == ()
    assert result.deleted_pointer_temps == (POINTER_TEMP,)
    assert staging.is_dir()
    assert not pointer_temp.exists()


def test_blocked_real_inspection_releases_lock(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    (dataset_directory(root, dataset) / "current.json").write_text(
        "invalid",
        encoding="utf-8",
    )
    lock_manager = RecordingLockManager()

    result = EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
        EODRepositoryMaintenanceRequest(dataset, dry_run=False)
    )

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert lock_manager.acquire_count == 1
    assert lock_manager.release_count == 1
    assert lock_manager.held == set()


def test_executor_construction_has_no_repository_or_lock_side_effects(
    tmp_path: Path,
) -> None:
    root = tmp_path / "missing"
    repository = LocalEODFileRepository(root)
    lock_manager = RecordingLockManager()

    executor = EODRepositoryMaintenanceExecutor(repository, lock_manager)

    assert type(executor) is EODRepositoryMaintenanceExecutor
    assert not root.exists()
    assert lock_manager.events == []


def test_unknown_artifact_remains_after_successful_ephemeral_cleanup(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    dataset_dir = dataset_directory(root, dataset)
    unknown = dataset_dir / "manual-backup"
    unknown.write_text("keep", encoding="utf-8")
    (dataset_dir / STAGING_ONE).mkdir()

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.CLEANED
    assert unknown.read_text(encoding="utf-8") == "keep"
    remaining_names = {item.name for item in result.remaining_artifacts}
    assert "manual-backup" in remaining_names


def test_error_serialization_contains_no_filesystem_path(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    error = EODRepositoryMaintenanceError(
        EODRepositoryMaintenanceErrorCode.CLEANUP_FAILED,
        dataset,
        lock_key=eod_dataset_lock_key(dataset),
        deleted_artifacts=(POINTER_TEMP,),
        remaining_artifacts=(STAGING_ONE,),
    )

    serialized = error.to_json()
    assert str(tmp_path) not in serialized
    assert "cleanup_failed" in serialized
    assert POINTER_TEMP in serialized
    assert STAGING_ONE in serialized


def test_broken_lineage_blocks_pointer_temp_before_any_deletion(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 2)
    shutil.rmtree(generation_directory(root, dataset, GENERATION_ONE))
    pointer_temp = dataset_directory(root, dataset) / POINTER_TEMP
    pointer_temp.write_text("temporary", encoding="utf-8")
    before = snapshot_files(dataset_directory(root, dataset))

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert pointer_temp.is_file()
    assert snapshot_files(dataset_directory(root, dataset)) == before
    assert EODRepositoryMaintenanceWarningCode.BROKEN_GENERATION_LINEAGE in result.warnings


@pytest.mark.parametrize(
    ("artifact_name", "is_directory", "helper_name"),
    (
        (STAGING_ONE, True, "_remove_maintenance_staging_directory"),
        (POINTER_TEMP, False, "_remove_maintenance_pointer_temporary_file"),
    ),
)
def test_delete_primitive_revalidates_symlink_state_after_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    artifact_name: str,
    is_directory: bool,
    helper_name: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    candidate = dataset_directory(root, dataset) / artifact_name
    candidate.mkdir() if is_directory else candidate.write_text("temporary", encoding="utf-8")
    lock_manager = RecordingLockManager()
    original_helper = getattr(repository, helper_name)
    original_is_symlink = Path.is_symlink

    def replace_with_symlink_view(value_dataset: EODDatasetKey, value_name: str) -> bool:
        def is_symlink_at_delete_time(path: Path) -> bool:
            if path == candidate:
                return True
            return original_is_symlink(path)

        monkeypatch.setattr(Path, "is_symlink", is_symlink_at_delete_time)
        return original_helper(value_dataset, value_name)

    monkeypatch.setattr(repository, helper_name, replace_with_symlink_view)

    with pytest.raises(EODRepositoryMaintenanceError) as captured:
        EODRepositoryMaintenanceExecutor(repository, lock_manager).execute(
            EODRepositoryMaintenanceRequest(dataset, dry_run=False)
        )

    assert captured.value.code is EODRepositoryMaintenanceErrorCode.CLEANUP_FAILED
    assert candidate.exists()
    assert lock_manager.acquire_count == 1
    assert lock_manager.release_count == 1


def test_complete_generation_is_never_passed_to_recursive_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 3)
    write_current_pointer(root, dataset, GENERATION_TWO, CREATED_THREE)
    dataset_dir = dataset_directory(root, dataset)
    staging = dataset_dir / STAGING_ONE
    staging.mkdir()
    original_rmtree = repositories_module.shutil.rmtree
    removed = []

    def guarded_rmtree(path: Path) -> None:
        candidate = Path(path)
        assert candidate.parent == dataset_dir
        assert candidate.name == STAGING_ONE
        removed.append(candidate.name)
        original_rmtree(candidate)

    monkeypatch.setattr(repositories_module.shutil, "rmtree", guarded_rmtree)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.deleted_staging == (STAGING_ONE,)
    assert removed == [STAGING_ONE]
    assert generation_directory(root, dataset, GENERATION_ONE).is_dir()
    assert generation_directory(root, dataset, GENERATION_TWO).is_dir()
    assert generation_directory(root, dataset, GENERATION_THREE).is_dir()


def test_unknown_symlink_fails_closed_without_following_or_deleting_target(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    publish_generations(repository, dataset, 1)
    external = tmp_path / "external-unknown.txt"
    external.write_text("keep", encoding="utf-8")
    link = dataset_directory(root, dataset) / "manual-link"
    create_symlink_or_skip(external, link, is_directory=False)

    result = EODRepositoryMaintenanceExecutor(
        repository,
        InProcessEODDatasetLockManager(),
    ).execute(EODRepositoryMaintenanceRequest(dataset, dry_run=False))

    assert result.status is EODRepositoryMaintenanceStatus.BLOCKED
    assert link.is_symlink()
    assert external.read_text(encoding="utf-8") == "keep"
    assert "manual-link" in result.unsafe_artifacts
