from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import inspect
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import autowealth.market_data as market_data
import autowealth.market_data.repositories as repositories_module
from autowealth.market_data.repositories import (
    EOD_PARQUET_COLUMNS,
    EOD_PARQUET_SCHEMA,
    EODGenerationExistsError,
    EODIntegrityError,
    EODNoCurrentGenerationError,
    EODRepositoryError,
    EODUnsafePathError,
    LocalEODFileRepository,
)
from autowealth.market_data.schemas import (
    EOD_SCHEMA_VERSION,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    Market,
    Venue,
)
from autowealth.market_data.versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EOD_POINTER_SCHEMA_VERSION,
    EODCurrentPointer,
    EODGenerationManifest,
    calculate_bytes_sha256,
    calculate_eod_content_sha256,
    calculate_file_sha256,
)

GENERATION_ONE = "generation_20240103"
GENERATION_TWO = "generation_20240104"
CREATED_ONE = datetime(2024, 1, 3, 18, tzinfo=timezone(timedelta(hours=8)))
CREATED_TWO = datetime(2024, 1, 4, 18, tzinfo=timezone(timedelta(hours=8)))


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
        adjustment_type=AdjustmentType.QFQ,
    )


def make_bar(
    dataset: EODDatasetKey,
    trade_date: date,
    *,
    open_value: str = "10",
    high_value: str = "11",
    low_value: str = "9",
    close_value: str = "10.5",
    volume: str = "1000",
    amount: object = "10500",
) -> EODBar:
    return EODBar(
        dataset=dataset,
        trade_date=trade_date,
        open=Decimal(open_value),
        high=Decimal(high_value),
        low=Decimal(low_value),
        close=Decimal(close_value),
        volume=Decimal(volume),
        amount=None if amount is None else Decimal(str(amount)),
    )


@pytest.fixture
def bars(dataset: EODDatasetKey) -> list[EODBar]:
    return [
        make_bar(dataset, date(2024, 1, 2)),
        make_bar(
            dataset,
            date(2024, 1, 3),
            open_value="10.5",
            high_value="11.5",
            low_value="10",
            close_value="11",
            volume="1200",
            amount=None,
        ),
    ]


def dataset_directory(root: Path, dataset: EODDatasetKey) -> Path:
    return root.joinpath(
        dataset.market.value,
        dataset.venue.value,
        dataset.asset_type.value,
        dataset.canonical_symbol,
        dataset.frequency.value,
        dataset.adjustment_type.value,
    )


def generation_directory(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
) -> Path:
    return dataset_directory(root, dataset) / "generations" / generation_id


def current_path(root: Path, dataset: EODDatasetKey) -> Path:
    return dataset_directory(root, dataset) / "current.json"


def manifest_path(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
) -> Path:
    return generation_directory(root, dataset, generation_id) / "manifest.json"


def parquet_path(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
) -> Path:
    return generation_directory(root, dataset, generation_id) / "bars.parquet"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def update_manifest(
    root: Path,
    dataset_key: EODDatasetKey,
    generation_id: str,
    **updates: object,
) -> None:
    path = manifest_path(root, dataset_key, generation_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(updates)
    write_json(path, payload)


def update_current_manifest_sha(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
) -> None:
    path = current_path(root, dataset)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["manifest_sha256"] = calculate_file_sha256(manifest_path(root, dataset, generation_id))
    write_json(path, payload)


def rewrite_parquet_and_checksum(
    root: Path,
    dataset: EODDatasetKey,
    generation_id: str,
    table: pa.Table,
) -> None:
    path = parquet_path(root, dataset, generation_id)
    pq.write_table(table, path)
    update_manifest(
        root,
        dataset,
        generation_id,
        parquet_sha256=calculate_file_sha256(path),
    )


def snapshot_directory(path: Path) -> dict[str, bytes]:
    return {
        str(candidate.relative_to(path)): candidate.read_bytes()
        for candidate in sorted(path.rglob("*"))
        if candidate.is_file()
    }


def create_symlink_or_skip(
    target: Path,
    link: Path,
    *,
    target_is_directory: bool,
) -> None:
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symbolic links are unavailable: {type(exc).__name__}")


def simulate_symlink(
    monkeypatch: pytest.MonkeyPatch,
    unsafe_path: Path,
) -> None:
    """Make one exact path report as a symlink without OS symlink privileges."""

    path_type = type(unsafe_path)
    original_is_symlink = path_type.is_symlink

    def is_symlink(candidate: Path) -> bool:
        if candidate == unsafe_path:
            return True
        return original_is_symlink(candidate)

    monkeypatch.setattr(path_type, "is_symlink", is_symlink)


def manifest_for(
    dataset: EODDatasetKey,
    *,
    row_count: object = 2,
    created_at: object = CREATED_ONE,
) -> EODGenerationManifest:
    digest = "a" * 64
    return EODGenerationManifest(
        manifest_schema_version=EOD_MANIFEST_SCHEMA_VERSION,
        eod_schema_version=EOD_SCHEMA_VERSION,
        generation_id=GENERATION_ONE,
        dataset=dataset,
        created_at=created_at,
        row_count=row_count,
        first_trade_date=date(2024, 1, 2),
        last_trade_date=date(2024, 1, 3),
        data_version=f"sha256:{digest}",
        content_sha256=digest,
        parquet_sha256="b" * 64,
    )


def pointer_for(
    dataset: EODDatasetKey,
    *,
    committed_at: object = CREATED_ONE,
) -> EODCurrentPointer:
    return EODCurrentPointer(
        pointer_schema_version=EOD_POINTER_SCHEMA_VERSION,
        dataset=dataset,
        generation_id=GENERATION_ONE,
        manifest_sha256="c" * 64,
        committed_at=committed_at,
    )


def test_version_schema_constants_are_one() -> None:
    assert EOD_MANIFEST_SCHEMA_VERSION == 1
    assert EOD_POINTER_SCHEMA_VERSION == 1


def test_manifest_json_is_deterministic_strict_and_utc(
    dataset: EODDatasetKey,
) -> None:
    manifest = manifest_for(dataset)
    assert manifest.created_at == datetime(2024, 1, 3, 10, tzinfo=timezone.utc)
    assert manifest.to_json() == manifest.to_json()
    assert EODGenerationManifest.from_dict(manifest.to_dict()) == manifest
    payload = manifest.to_dict()
    payload["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        EODGenerationManifest.from_dict(payload)


def test_pointer_json_is_deterministic_strict_and_utc(
    dataset: EODDatasetKey,
) -> None:
    pointer = pointer_for(dataset)
    assert pointer.committed_at == datetime(2024, 1, 3, 10, tzinfo=timezone.utc)
    assert pointer.to_json() == pointer.to_json()
    assert EODCurrentPointer.from_dict(pointer.to_dict()) == pointer
    payload = pointer.to_dict()
    payload["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        EODCurrentPointer.from_dict(payload)


def test_manifest_and_pointer_reject_naive_datetimes(
    dataset: EODDatasetKey,
) -> None:
    naive = datetime(2024, 1, 3, 10)
    with pytest.raises(ValueError, match="timezone-aware"):
        manifest_for(dataset, created_at=naive)
    with pytest.raises(ValueError, match="timezone-aware"):
        pointer_for(dataset, committed_at=naive)


@pytest.mark.parametrize(
    "model,payload",
    [
        (EODGenerationManifest, []),
        (EODCurrentPointer, []),
    ],
)
def test_manifest_and_pointer_require_exact_dicts(
    model: object,
    payload: object,
) -> None:
    with pytest.raises(TypeError, match="exact dict"):
        model.from_dict(payload)


def test_manifest_and_pointer_reject_missing_fields_and_datetime_dates(
    dataset: EODDatasetKey,
) -> None:
    manifest_payload = manifest_for(dataset).to_dict()
    manifest_payload.pop("row_count")
    with pytest.raises(ValueError, match="fields"):
        EODGenerationManifest.from_dict(manifest_payload)

    pointer_payload = pointer_for(dataset).to_dict()
    pointer_payload.pop("manifest_sha256")
    with pytest.raises(ValueError, match="fields"):
        EODCurrentPointer.from_dict(pointer_payload)

    with pytest.raises(ValueError, match="exact date"):
        replace(
            manifest_for(dataset),
            first_trade_date=datetime(2024, 1, 2, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("row_count", [True, False, 0, -1])
def test_manifest_rejects_bool_and_non_positive_row_count(
    dataset: EODDatasetKey,
    row_count: object,
) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        manifest_for(dataset, row_count=row_count)


@pytest.mark.parametrize(
    "generation_id",
    [
        "",
        ".",
        "..",
        "../escape",
        "folder/name",
        "folder\\name",
        "C:\\escape",
        "/absolute",
        " generation_20240103",
        "generation_20240103 ",
    ],
)
def test_generation_id_rejects_path_traversal(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    generation_id: str,
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    with pytest.raises(ValueError, match="safe machine identifier"):
        repository.publish(
            dataset,
            bars,
            generation_id=generation_id,
            created_at=CREATED_ONE,
        )


def test_manifest_data_version_must_match_content_checksum(
    dataset: EODDatasetKey,
) -> None:
    values = manifest_for(dataset).to_dict()
    values["data_version"] = f"sha256:{'f' * 64}"
    with pytest.raises(ValueError, match="match content_sha256"):
        EODGenerationManifest.from_dict(values)


def test_content_checksum_is_order_independent(
    bars: list[EODBar],
) -> None:
    assert calculate_eod_content_sha256(bars) == calculate_eod_content_sha256(list(reversed(bars)))


def test_decimal_scale_does_not_change_content_checksum(
    dataset: EODDatasetKey,
) -> None:
    first = [make_bar(dataset, date(2024, 1, 2), close_value="10.50")]
    second = [make_bar(dataset, date(2024, 1, 2), close_value="10.5000")]
    assert calculate_eod_content_sha256(first) == calculate_eod_content_sha256(second)


def test_negative_zero_is_canonical_and_logical_changes_change_content_checksum(
    dataset: EODDatasetKey,
) -> None:
    zero = [make_bar(dataset, date(2024, 1, 2), volume="0")]
    negative_zero = [make_bar(dataset, date(2024, 1, 2), volume="-0")]
    changed = [make_bar(dataset, date(2024, 1, 2), volume="1")]

    assert negative_zero[0].to_dict()["volume"] == "0"
    assert calculate_eod_content_sha256(zero) == calculate_eod_content_sha256(negative_zero)
    assert calculate_eod_content_sha256(zero) != calculate_eod_content_sha256(changed)


def test_content_checksum_rejects_empty_mixed_and_duplicate_bars(
    dataset: EODDatasetKey,
    other_dataset: EODDatasetKey,
) -> None:
    with pytest.raises(ValueError, match="empty"):
        calculate_eod_content_sha256([])
    with pytest.raises(ValueError, match="one dataset"):
        calculate_eod_content_sha256(
            [
                make_bar(dataset, date(2024, 1, 2)),
                make_bar(other_dataset, date(2024, 1, 3)),
            ]
        )
    with pytest.raises(ValueError, match="duplicate"):
        calculate_eod_content_sha256(
            [
                make_bar(dataset, date(2024, 1, 2)),
                make_bar(dataset, date(2024, 1, 2), close_value="10.8"),
            ]
        )


def test_bytes_and_file_checksum_are_distinct_helpers(tmp_path: Path) -> None:
    payload = b"deterministic EOD bytes"
    path = tmp_path / "payload.bin"
    path.write_bytes(payload)
    assert calculate_bytes_sha256(payload) == calculate_file_sha256(path, chunk_size=3)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        calculate_file_sha256(tmp_path / "missing.bin")


def test_first_publish_creates_layout_manifest_and_current(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    manifest = repository.publish(
        dataset,
        list(reversed(bars)),
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    expected_generation = root / ("CN/SSE/equity/600000.SH/1d/none/generations/generation_20240103")
    assert generation_directory(root, dataset, GENERATION_ONE) == expected_generation
    assert (expected_generation / "bars.parquet").is_file()
    assert (expected_generation / "manifest.json").is_file()
    assert current_path(root, dataset).is_file()
    assert manifest.data_version == f"sha256:{manifest.content_sha256}"
    assert manifest.previous_generation_id is None
    for path in (manifest_path(root, dataset, GENERATION_ONE), current_path(root, dataset)):
        text = path.read_text(encoding="utf-8")
        assert str(root.resolve()) not in text
        assert "bars.parquet" in text or path.name == "current.json"


def test_publish_load_current_round_trip_is_complete_and_immutable(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    manifest = repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    loaded = repository.load_current(dataset)
    assert loaded is not None
    assert loaded.manifest == manifest
    assert loaded.bars == tuple(bars)
    assert type(loaded.bars) is tuple
    assert repository.load_current_manifest(dataset) == manifest


def test_parquet_v1_has_fixed_columns_and_string_types(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    table = pq.ParquetFile(parquet_path(root, dataset, GENERATION_ONE)).read()
    assert tuple(table.column_names) == EOD_PARQUET_COLUMNS
    assert table.schema.equals(EOD_PARQUET_SCHEMA, check_metadata=False)
    assert all(pa.types.is_string(field.type) for field in table.schema)
    assert table.to_pydict()["amount"] == ["10500", None]


def test_all_null_amount_keeps_explicit_string_schema(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    values = [
        make_bar(dataset, date(2024, 1, 2), amount=None),
        make_bar(dataset, date(2024, 1, 3), amount=None),
    ]
    repository.publish(
        dataset,
        values,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    schema = pq.ParquetFile(parquet_path(root, dataset, GENERATION_ONE)).schema_arrow
    assert pa.types.is_string(schema.field("amount").type)
    assert schema.field("amount").nullable


def test_parquet_file_bytes_can_change_without_changing_logical_content(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    root.mkdir()
    repository = LocalEODFileRepository(root)
    data = {
        "trade_date": [bar.trade_date.isoformat() for bar in bars],
        "open": [bar.to_dict()["open"] for bar in bars],
        "high": [bar.to_dict()["high"] for bar in bars],
        "low": [bar.to_dict()["low"] for bar in bars],
        "close": [bar.to_dict()["close"] for bar in bars],
        "volume": [bar.to_dict()["volume"] for bar in bars],
        "amount": [bar.to_dict()["amount"] for bar in bars],
    }
    table = pa.Table.from_arrays(
        [
            pa.array(data[column], type=EOD_PARQUET_SCHEMA.field(column).type)
            for column in EOD_PARQUET_COLUMNS
        ],
        schema=EOD_PARQUET_SCHEMA,
    )
    first_path = root / "first.parquet"
    second_path = root / "second.parquet"
    pq.write_table(table, first_path, compression=None)
    pq.write_table(table, second_path, compression="gzip")

    first_bars = repository._read_parquet(first_path, dataset)
    second_bars = repository._read_parquet(second_path, dataset)
    assert calculate_file_sha256(first_path) != calculate_file_sha256(second_path)
    assert calculate_eod_content_sha256(first_bars) == calculate_eod_content_sha256(second_bars)


def test_second_publish_advances_pointer_and_preserves_first_generation(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    first = repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    first_directory = generation_directory(root, dataset, GENERATION_ONE)
    first_bytes = snapshot_directory(first_directory)
    extended = bars + [
        make_bar(
            dataset,
            date(2024, 1, 4),
            open_value="11",
            high_value="12",
            low_value="10.5",
            close_value="11.5",
        )
    ]
    second = repository.publish(
        dataset,
        extended,
        generation_id=GENERATION_TWO,
        created_at=CREATED_TWO,
    )
    assert second.previous_generation_id == GENERATION_ONE
    assert repository.load_current_manifest(dataset) == second
    assert repository.load_generation(dataset, GENERATION_ONE).manifest == first
    assert snapshot_directory(first_directory) == first_bytes
    assert repository.list_generation_ids(dataset) == (
        GENERATION_ONE,
        GENERATION_TWO,
    )


def test_existing_generation_id_is_never_overwritten(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = snapshot_directory(generation_directory(root, dataset, GENERATION_ONE))
    with pytest.raises(EODGenerationExistsError, match="already exists"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_ONE,
            created_at=CREATED_TWO,
        )
    assert snapshot_directory(generation_directory(root, dataset, GENERATION_ONE)) == before


def test_list_generation_ids_is_sorted_and_ignores_staging_and_incomplete(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_TWO,
        created_at=CREATED_TWO,
    )
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    dataset_dir = dataset_directory(root, dataset)
    (dataset_dir / ".temporary.staging").mkdir()
    (dataset_dir / "generations" / "incomplete").mkdir()
    assert repository.list_generation_ids(dataset) == (
        GENERATION_ONE,
        GENERATION_TWO,
    )


@pytest.mark.parametrize("failure_point", ["parquet", "manifest"])
def test_staging_write_failures_are_cleaned_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    failure_point: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise EODRepositoryError("injected staging failure")

    monkeypatch.setattr(
        repository,
        "_write_parquet" if failure_point == "parquet" else "_write_manifest",
        fail,
    )
    with pytest.raises(EODRepositoryError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_ONE,
            created_at=CREATED_ONE,
        )
    dataset_dir = dataset_directory(root, dataset)
    assert list(dataset_dir.glob("*.staging")) == []
    assert not generation_directory(root, dataset, GENERATION_ONE).exists()
    assert not current_path(root, dataset).exists()


def test_staging_directory_creation_failure_keeps_old_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise EODRepositoryError("injected staging creation failure")

    monkeypatch.setattr(repository, "_create_staging_directory", fail)
    with pytest.raises(EODRepositoryError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert current_path(root, dataset).read_bytes() == before
    assert not generation_directory(root, dataset, GENERATION_TWO).exists()
    assert list(dataset_directory(root, dataset).glob("*.staging")) == []


def test_parquet_reread_failure_cleans_staging_and_keeps_old_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise EODIntegrityError("injected Parquet reread failure")

    monkeypatch.setattr(repository, "_read_parquet", fail)
    with pytest.raises(EODIntegrityError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert current_path(root, dataset).read_bytes() == before
    assert not generation_directory(root, dataset, GENERATION_TWO).exists()
    assert list(dataset_directory(root, dataset).glob("*.staging")) == []


def test_generation_rename_failure_keeps_old_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    secret = "Authorization=Bearer-unit-test-secret"
    root = tmp_path / secret
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError(f"injected generation rename failure at {root} with {secret}")

    monkeypatch.setattr(repositories_module.os, "rename", fail)
    with pytest.raises(EODRepositoryError, match="publication rename") as exc_info:
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert isinstance(exc_info.value.__cause__, OSError)
    message = str(exc_info.value)
    assert str(root) not in message
    assert str(tmp_path) not in message
    assert secret not in message
    assert current_path(root, dataset).read_bytes() == before
    assert not generation_directory(root, dataset, GENERATION_TWO).exists()
    assert list(dataset_directory(root, dataset).glob("*.staging")) == []
    assert repository.load_current_manifest(dataset).generation_id == GENERATION_ONE


def test_pointer_replace_failure_preserves_old_current_and_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected pointer replacement failure")

    monkeypatch.setattr(repositories_module.os, "replace", fail)
    with pytest.raises(EODRepositoryError, match="pointer replacement") as exc_info:
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert isinstance(exc_info.value.__cause__, OSError)
    assert current_path(root, dataset).read_bytes() == before
    assert generation_directory(root, dataset, GENERATION_TWO).is_dir()
    assert repository.load_generation(dataset, GENERATION_TWO).manifest.generation_id == (
        GENERATION_TWO
    )
    assert repository.load_current_manifest(dataset).generation_id == GENERATION_ONE
    assert list(dataset_directory(root, dataset).glob(".current.*.tmp")) == []


def test_pointer_temporary_write_failure_keeps_old_current_and_orphan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise EODRepositoryError("injected pointer write failure")

    monkeypatch.setattr(repository, "_write_pointer", fail)
    with pytest.raises(EODRepositoryError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert current_path(root, dataset).read_bytes() == before
    assert generation_directory(root, dataset, GENERATION_TWO).is_dir()
    assert repository.load_current_manifest(dataset).generation_id == GENERATION_ONE
    assert list(dataset_directory(root, dataset).glob(".current.*.tmp")) == []


def test_first_pointer_failure_leaves_no_partial_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)

    def fail(*args: object, **kwargs: object) -> None:
        raise EODRepositoryError("injected first pointer failure")

    monkeypatch.setattr(repository, "_replace_current_pointer", fail)
    with pytest.raises(EODRepositoryError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_ONE,
            created_at=CREATED_ONE,
        )
    assert not current_path(root, dataset).exists()
    assert generation_directory(root, dataset, GENERATION_ONE).is_dir()
    assert repository.load_current(dataset) is None


def test_write_failure_after_existing_generation_keeps_old_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    before = current_path(root, dataset).read_bytes()

    def fail(*args: object, **kwargs: object) -> None:
        raise EODRepositoryError("injected write failure")

    monkeypatch.setattr(repository, "_write_parquet", fail)
    with pytest.raises(EODRepositoryError, match="injected"):
        repository.publish(
            dataset,
            bars,
            generation_id=GENERATION_TWO,
            created_at=CREATED_TWO,
        )
    assert current_path(root, dataset).read_bytes() == before
    assert repository.load_current_manifest(dataset).generation_id == GENERATION_ONE


def test_missing_current_returns_none_without_scanning_generations(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    current_path(root, dataset).unlink()
    assert repository.load_current_manifest(dataset) is None
    assert repository.load_current(dataset) is None
    assert repository.list_generation_ids(dataset) == (GENERATION_ONE,)


def test_corrupt_current_pointer_fails_closed(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    current_path(root, dataset).write_text("{not-json", encoding="utf-8")
    with pytest.raises(EODIntegrityError, match="pointer is invalid"):
        repository.load_current(dataset)


def test_load_current_integrity_failure_never_falls_back_to_previous_generation(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_TWO,
        created_at=CREATED_TWO,
    )
    active_parquet = parquet_path(root, dataset, GENERATION_TWO)
    active_parquet.write_bytes(active_parquet.read_bytes() + b"tampered")

    with pytest.raises(EODIntegrityError, match="Parquet checksum"):
        repository.load_current(dataset)
    pointer_payload = json.loads(current_path(root, dataset).read_text(encoding="utf-8"))
    assert pointer_payload["generation_id"] == GENERATION_TWO
    assert repository.load_generation(dataset, GENERATION_ONE).manifest.generation_id == (
        GENERATION_ONE
    )


def test_current_pointer_to_missing_generation_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    payload = json.loads(current_path(root, dataset).read_text(encoding="utf-8"))
    payload["generation_id"] = "missing_generation"
    payload["manifest_sha256"] = "0" * 64
    write_json(current_path(root, dataset), payload)
    with pytest.raises(EODNoCurrentGenerationError, match="missing generation"):
        repository.load_current(dataset)


def test_corrupt_manifest_json_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    manifest_path(root, dataset, GENERATION_ONE).write_text("{bad", encoding="utf-8")
    with pytest.raises(EODIntegrityError, match="manifest is invalid"):
        repository.load_generation(dataset, GENERATION_ONE)


def test_current_manifest_checksum_mismatch_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    payload = json.loads(current_path(root, dataset).read_text(encoding="utf-8"))
    payload["manifest_sha256"] = "0" * 64
    write_json(current_path(root, dataset), payload)
    with pytest.raises(EODIntegrityError, match="manifest checksum"):
        repository.load_current(dataset)


def test_parquet_checksum_mismatch_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    path = parquet_path(root, dataset, GENERATION_ONE)
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(EODIntegrityError, match="Parquet checksum"):
        repository.load_generation(dataset, GENERATION_ONE)


def test_content_checksum_mismatch_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    update_manifest(
        root,
        dataset,
        GENERATION_ONE,
        content_sha256="0" * 64,
        data_version=f"sha256:{'0' * 64}",
    )
    with pytest.raises(EODIntegrityError, match="content checksum"):
        repository.load_generation(dataset, GENERATION_ONE)


def test_manifest_dataset_mismatch_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    other_dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    update_manifest(
        root,
        dataset,
        GENERATION_ONE,
        dataset=other_dataset.to_dict(),
    )
    with pytest.raises(EODIntegrityError, match="dataset"):
        repository.load_generation(dataset, GENERATION_ONE)


@pytest.mark.parametrize("schema_change", ["missing", "extra", "reordered", "type"])
def test_parquet_schema_changes_fail_closed(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    schema_change: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    table = pq.ParquetFile(parquet_path(root, dataset, GENERATION_ONE)).read()
    if schema_change == "missing":
        changed = table.drop(["amount"])
    elif schema_change == "extra":
        changed = table.append_column("unexpected", pa.array(["x", "y"]))
    elif schema_change == "reordered":
        changed = table.select(list(reversed(EOD_PARQUET_COLUMNS)))
    else:
        changed = table.set_column(
            EOD_PARQUET_COLUMNS.index("open"),
            "open",
            pa.array([10, 11], type=pa.int64()),
        )
    rewrite_parquet_and_checksum(root, dataset, GENERATION_ONE, changed)
    with pytest.raises(EODIntegrityError, match="columns|types"):
        repository.load_generation(dataset, GENERATION_ONE)


@pytest.mark.parametrize(
    ("field_name", "replacement", "message"),
    [
        ("open", ["10.0", "10.5"], "row content"),
        ("volume", ["-0", "1200"], "row content"),
        ("trade_date", ["2024-01-02", "2024-01-02"], "duplicate trade dates"),
    ],
)
def test_parquet_rejects_noncanonical_values_and_duplicate_dates(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    field_name: str,
    replacement: list[str],
    message: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    table = pq.ParquetFile(parquet_path(root, dataset, GENERATION_ONE)).read()
    changed = table.set_column(
        EOD_PARQUET_COLUMNS.index(field_name),
        EOD_PARQUET_SCHEMA.field(field_name),
        pa.array(replacement, type=pa.string()),
    )
    rewrite_parquet_and_checksum(root, dataset, GENERATION_ONE, changed)

    with pytest.raises(EODIntegrityError, match=message):
        repository.load_generation(dataset, GENERATION_ONE)


def test_specified_missing_generation_fails_explicitly(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    with pytest.raises(EODNoCurrentGenerationError, match="does not exist"):
        repository.load_generation(dataset, GENERATION_ONE)


def test_current_pointer_dataset_mismatch_fails(
    tmp_path: Path,
    dataset: EODDatasetKey,
    other_dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    payload = json.loads(current_path(root, dataset).read_text(encoding="utf-8"))
    payload["dataset"] = other_dataset.to_dict()
    write_json(current_path(root, dataset), payload)
    with pytest.raises(EODIntegrityError, match="pointer dataset"):
        repository.load_current(dataset)


def test_current_symlink_is_rejected(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    external = tmp_path / "external-current.json"
    external.write_bytes(current_path(root, dataset).read_bytes())
    current_path(root, dataset).unlink()
    create_symlink_or_skip(external, current_path(root, dataset), target_is_directory=False)
    with pytest.raises(EODUnsafePathError, match="symbolic link"):
        repository.load_current(dataset)


def test_generation_symlink_escape_is_rejected(
    tmp_path: Path,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "eod"
    generations = dataset_directory(root, dataset) / "generations"
    generations.mkdir(parents=True)
    external = tmp_path / "external-generation"
    external.mkdir()
    link = generations / GENERATION_ONE
    create_symlink_or_skip(external, link, target_is_directory=True)
    repository = LocalEODFileRepository(root)
    with pytest.raises(EODUnsafePathError, match="symbolic link|escapes"):
        repository.load_generation(dataset, GENERATION_ONE)


@pytest.mark.parametrize("filename", ["manifest.json", "bars.parquet"])
def test_generation_file_symlinks_are_rejected(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    filename: str,
) -> None:
    root = tmp_path / "eod"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    original = generation_directory(root, dataset, GENERATION_ONE) / filename
    external = tmp_path / f"external-{filename}"
    external.write_bytes(original.read_bytes())
    original.unlink()
    create_symlink_or_skip(external, original, target_is_directory=False)
    with pytest.raises(EODUnsafePathError, match="symbolic link|escapes"):
        repository.load_generation(dataset, GENERATION_ONE)


@pytest.mark.parametrize(
    "unsafe_kind",
    ["current", "generation", "manifest", "parquet"],
)
def test_symlink_detection_fails_closed_without_os_symlink_privileges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
    bars: list[EODBar],
    unsafe_kind: str,
) -> None:
    secret = "apiKey=unit-test-secret"
    root = tmp_path / secret
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    unsafe_paths = {
        "current": current_path(root, dataset),
        "generation": generation_directory(root, dataset, GENERATION_ONE),
        "manifest": manifest_path(root, dataset, GENERATION_ONE),
        "parquet": parquet_path(root, dataset, GENERATION_ONE),
    }
    simulate_symlink(monkeypatch, unsafe_paths[unsafe_kind])

    with pytest.raises(EODUnsafePathError, match="symbolic link") as exc_info:
        if unsafe_kind == "current":
            repository.load_current(dataset)
        else:
            repository.load_generation(dataset, GENERATION_ONE)

    message = str(exc_info.value)
    assert str(root.resolve()) not in message
    assert str(tmp_path) not in message
    assert secret not in message


def test_generation_path_escape_fails_closed_without_real_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    dataset: EODDatasetKey,
) -> None:
    root = tmp_path / "apiKey=unit-test-secret"
    repository = LocalEODFileRepository(root)
    unsafe_path = generation_directory(root, dataset, GENERATION_ONE)
    path_type = type(unsafe_path)
    original_resolve = path_type.resolve

    def resolve(candidate: Path, strict: bool = False) -> Path:
        if candidate == unsafe_path:
            return tmp_path / "escaped-generation"
        return original_resolve(candidate, strict=strict)

    monkeypatch.setattr(path_type, "resolve", resolve)
    with pytest.raises(EODUnsafePathError, match="escapes") as exc_info:
        repository.load_generation(dataset, GENERATION_ONE)

    message = str(exc_info.value)
    assert str(root) not in message
    assert str(tmp_path) not in message
    assert "unit-test-secret" not in message


def test_publish_does_not_modify_input_bars(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    repository = LocalEODFileRepository(tmp_path / "eod")
    supplied = list(reversed(bars))
    snapshot = list(supplied)
    repository.publish(
        dataset,
        supplied,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    assert supplied == snapshot


def test_market_data_public_exports_are_stable_and_do_not_expose_internals() -> None:
    exports = market_data.__all__
    assert len(exports) == len(set(exports))
    assert {
        "EODGenerationManifest",
        "EODCurrentPointer",
        "EODStoredGeneration",
        "EODFileRepository",
        "LocalEODFileRepository",
        "calculate_eod_content_sha256",
        "calculate_file_sha256",
    }.issubset(exports)
    assert all(not name.startswith("_") for name in exports)
    assert {
        "Provider",
        "Coordinator",
        "Watermark",
        "_create_staging_directory",
        "_replace_current_pointer",
    }.isdisjoint(exports)


def test_repository_source_does_not_read_system_time_or_generate_business_id() -> None:
    from autowealth.market_data import repositories

    source = inspect.getsource(repositories)
    assert ".now(" not in source
    assert ".utcnow(" not in source
    assert ".today(" not in source
    assert "uuid.uuid4" not in source


def test_repository_import_does_not_open_network_connections() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = """
import socket
import sys

import autowealth

def fail_network(*args, **kwargs):
    raise AssertionError("repository import attempted network access")

socket.create_connection = fail_network
socket.socket.connect = fail_network
before = set(sys.modules)
import autowealth.market_data.repositories
new_roots = {name.split(".", 1)[0] for name in set(sys.modules) - before}
assert {"akshare", "requests", "yfinance"}.isdisjoint(new_roots)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_exception_messages_do_not_expose_root_or_credentials(
    tmp_path: Path,
    dataset: EODDatasetKey,
    bars: list[EODBar],
) -> None:
    root = tmp_path / "private-token-root"
    repository = LocalEODFileRepository(root)
    repository.publish(
        dataset,
        bars,
        generation_id=GENERATION_ONE,
        created_at=CREATED_ONE,
    )
    current_path(root, dataset).write_text(
        '{"apiKey":"sensitive-token-value"}',
        encoding="utf-8",
    )
    with pytest.raises(EODIntegrityError) as captured:
        repository.load_current(dataset)
    message = str(captured.value)
    assert str(root.resolve()) not in message
    assert "sensitive-token-value" not in message
    assert "apiKey" not in message
