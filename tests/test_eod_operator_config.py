from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from autowealth.market_data.operator_config import (
    EOD_OPERATOR_CONFIG_SCHEMA_VERSION,
    EODOperatorConfig,
    EODOperatorConfigError,
    EODOperatorConfigErrorCode,
    EODOperatorDatasetConfig,
    load_eod_operator_config,
)


def payload() -> dict[str, object]:
    return {
        "config_schema_version": EOD_OPERATOR_CONFIG_SCHEMA_VERSION,
        "operations_root": "operations",
        "datasets": [
            {
                "production_config": "configs/equity.yaml",
                "storage_identity": "cn-sse-equity-600000-none",
                "enabled": True,
            }
        ],
    }


def write_manifest(root: Path, value: object) -> Path:
    path = root / "operator.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def assert_invalid(path: Path, code: EODOperatorConfigErrorCode) -> None:
    with pytest.raises(EODOperatorConfigError) as captured:
        load_eod_operator_config(path)
    assert captured.value.code is code
    assert str(path.resolve()) not in captured.value.message


def test_valid_schema_resolves_relative_paths_from_manifest_directory(tmp_path: Path) -> None:
    root = tmp_path / "manifest"
    parsed = load_eod_operator_config(write_manifest(root, payload()))

    assert parsed.config_schema_version == 1
    assert parsed.operations_root == (root / "operations").resolve()
    assert parsed.datasets == (
        EODOperatorDatasetConfig(
            production_config=(root / "configs/equity.yaml").resolve(),
            storage_identity="cn-sse-equity-600000-none",
            enabled=True,
        ),
    )
    assert not parsed.operations_root.exists()
    assert not parsed.datasets[0].production_config.exists()


def test_absolute_paths_are_supported_without_creating_them(tmp_path: Path) -> None:
    value = payload()
    operations = (tmp_path / "absolute-operations").resolve()
    production = (tmp_path / "absolute-production.yaml").resolve()
    value["operations_root"] = str(operations)
    value["datasets"][0]["production_config"] = str(production)

    parsed = load_eod_operator_config(write_manifest(tmp_path, value))

    assert parsed.operations_root == operations
    assert parsed.datasets[0].production_config == production
    assert not operations.exists()
    assert not production.exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value.pop("operations_root"),
        lambda value: value.update({"config_schema_version": 2}),
        lambda value: value.update({"config_schema_version": True}),
        lambda value: value["datasets"][0].update({"enabled": 1}),
        lambda value: value["datasets"][0].update({"unknown": "value"}),
        lambda value: value.update({"datasets": []}),
        lambda value: value.update({"datasets": "not-a-list"}),
    ],
)
def test_schema_is_exact_and_strict(tmp_path: Path, mutate) -> None:
    value = payload()
    mutate(value)
    assert_invalid(
        write_manifest(tmp_path, value),
        EODOperatorConfigErrorCode.INVALID_CONFIG,
    )


def test_dataset_count_is_bounded(tmp_path: Path) -> None:
    value = payload()
    value["datasets"] = [
        {
            "production_config": f"configs/{index}.yaml",
            "storage_identity": f"dataset-{index}",
            "enabled": True,
        }
        for index in range(257)
    ]
    assert_invalid(
        write_manifest(tmp_path, value),
        EODOperatorConfigErrorCode.INVALID_CONFIG,
    )


@pytest.mark.parametrize(
    "field,text",
    [
        ("operations_root", "https://example.test/operations"),
        ("operations_root", "file://private/operations"),
        ("operations_root", "file:C:/private/operations"),
        ("operations_root", "https:relative-operations"),
        ("operations_root", "${OPERATIONS_ROOT}/jobs"),
        ("operations_root", "%OPERATIONS_ROOT%/jobs"),
        ("production_config", "https://example.test/eod.yaml"),
        ("production_config", "$HOME/eod.yaml"),
    ],
)
def test_uri_and_environment_substitution_are_rejected(
    tmp_path: Path,
    field: str,
    text: str,
) -> None:
    value = payload()
    if field == "operations_root":
        value[field] = text
    else:
        value["datasets"][0][field] = text
    assert_invalid(
        write_manifest(tmp_path, value),
        EODOperatorConfigErrorCode.INVALID_CONFIG,
    )


@pytest.mark.parametrize(
    "identity",
    ["../private", "C:/private", "apiKey=secret", "", "contains space"],
)
def test_unsafe_storage_identity_is_rejected(tmp_path: Path, identity: str) -> None:
    value = payload()
    value["datasets"][0]["storage_identity"] = identity
    assert_invalid(
        write_manifest(tmp_path, value),
        EODOperatorConfigErrorCode.INVALID_CONFIG,
    )


def test_duplicate_storage_identity_is_rejected(tmp_path: Path) -> None:
    value = payload()
    value["datasets"].append(dict(value["datasets"][0]))
    assert_invalid(
        write_manifest(tmp_path, value),
        EODOperatorConfigErrorCode.INVALID_CONFIG,
    )


def test_missing_and_invalid_yaml_errors_are_safe(tmp_path: Path) -> None:
    missing = tmp_path / "apiKey=secret.yaml"
    assert_invalid(missing, EODOperatorConfigErrorCode.CONFIG_MISSING)

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("[", encoding="utf-8")
    assert_invalid(invalid, EODOperatorConfigErrorCode.INVALID_YAML)


def test_contract_construction_has_no_filesystem_mutation(tmp_path: Path) -> None:
    operations = (tmp_path / "operations").resolve()
    production = (tmp_path / "production.yaml").resolve()
    before = tuple(tmp_path.rglob("*"))

    config = EODOperatorConfig(
        config_schema_version=1,
        operations_root=operations,
        datasets=(
            EODOperatorDatasetConfig(
                production_config=production,
                storage_identity="fixture-dataset",
                enabled=True,
            ),
        ),
    )

    assert config.operations_root == operations
    assert tuple(tmp_path.rglob("*")) == before
