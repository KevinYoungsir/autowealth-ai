"""Strict, side-effect-free configuration for the EOD operator CLI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import importlib
import re
from typing import Tuple

Path = importlib.import_module("pathlib").Path

import yaml

from autowealth.security import contains_absolute_path, contains_sensitive_value

EOD_OPERATOR_CONFIG_SCHEMA_VERSION = 1
MAX_EOD_OPERATOR_CONFIG_BYTES = 1024 * 1024
MAX_EOD_OPERATOR_DATASETS = 256

_CONFIG_FIELDS = frozenset({"config_schema_version", "operations_root", "datasets"})
_DATASET_FIELDS = frozenset({"production_config", "storage_identity", "enabled"})
_STORAGE_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}$")
_URI_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")
_ENVIRONMENT_PATTERN = re.compile(r"\$(?:\{[^}]*\}|[A-Za-z_])|%[^%]+%")


class EODOperatorConfigErrorCode(str, Enum):
    CONFIG_MISSING = "config_missing"
    CONFIG_UNREADABLE = "config_unreadable"
    INVALID_YAML = "invalid_yaml"
    INVALID_CONFIG = "invalid_config"


_ERROR_MESSAGES = {
    EODOperatorConfigErrorCode.CONFIG_MISSING: "The EOD operator configuration is missing.",
    EODOperatorConfigErrorCode.CONFIG_UNREADABLE: "The EOD operator configuration is unreadable.",
    EODOperatorConfigErrorCode.INVALID_YAML: "The EOD operator configuration is not valid YAML.",
    EODOperatorConfigErrorCode.INVALID_CONFIG: "The EOD operator configuration is invalid.",
}


class EODOperatorConfigError(ValueError):
    def __init__(self, code: EODOperatorConfigErrorCode) -> None:
        if type(code) is not EODOperatorConfigErrorCode:
            raise TypeError("code must be an exact EODOperatorConfigErrorCode")
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class EODOperatorDatasetConfig:
    production_config: Path
    storage_identity: str
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.production_config, Path) or not self.production_config.is_absolute():
            raise ValueError("production_config must be an explicit absolute Path")
        _validate_storage_identity(self.storage_identity)
        if type(self.enabled) is not bool:
            raise ValueError("enabled must be an exact bool")


@dataclass(frozen=True)
class EODOperatorConfig:
    config_schema_version: int
    operations_root: Path
    datasets: Tuple[EODOperatorDatasetConfig, ...]

    def __post_init__(self) -> None:
        if (
            type(self.config_schema_version) is not int
            or self.config_schema_version != EOD_OPERATOR_CONFIG_SCHEMA_VERSION
        ):
            raise ValueError("config_schema_version is unsupported")
        if not isinstance(self.operations_root, Path) or not self.operations_root.is_absolute():
            raise ValueError("operations_root must be an explicit absolute Path")
        if type(self.datasets) not in (list, tuple):
            raise TypeError("datasets must be an exact list or tuple")
        datasets = tuple(self.datasets)
        if not 1 <= len(datasets) <= MAX_EOD_OPERATOR_DATASETS:
            raise ValueError("datasets must contain between 1 and 256 entries")
        if any(type(item) is not EODOperatorDatasetConfig for item in datasets):
            raise TypeError("datasets must contain exact EODOperatorDatasetConfig values")
        storage_identities = tuple(item.storage_identity for item in datasets)
        if len(set(storage_identities)) != len(storage_identities):
            raise ValueError("datasets must not contain duplicate storage identities")
        object.__setattr__(self, "datasets", datasets)


def load_eod_operator_config(path: Path) -> EODOperatorConfig:
    """Read only the requested manifest and resolve its explicit local paths."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    try:
        if not path.is_file():
            raise EODOperatorConfigError(EODOperatorConfigErrorCode.CONFIG_MISSING)
        raw_text = path.read_text(encoding="utf-8")
    except EODOperatorConfigError:
        raise
    except UnicodeError:
        raise EODOperatorConfigError(EODOperatorConfigErrorCode.INVALID_YAML) from None
    except OSError:
        raise EODOperatorConfigError(EODOperatorConfigErrorCode.CONFIG_UNREADABLE) from None
    if len(raw_text.encode("utf-8")) > MAX_EOD_OPERATOR_CONFIG_BYTES:
        raise EODOperatorConfigError(EODOperatorConfigErrorCode.INVALID_CONFIG)
    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        raise EODOperatorConfigError(EODOperatorConfigErrorCode.INVALID_YAML) from None
    try:
        if type(payload) is not dict or frozenset(payload) != _CONFIG_FIELDS:
            raise ValueError("operator config fields are invalid")
        version = payload["config_schema_version"]
        if type(version) is not int or version != EOD_OPERATOR_CONFIG_SCHEMA_VERSION:
            raise ValueError("operator config version is invalid")
        dataset_payloads = payload["datasets"]
        if type(dataset_payloads) is not list or not 1 <= len(dataset_payloads) <= 256:
            raise ValueError("operator datasets are invalid")
        root = path.resolve(strict=False).parent
        datasets = tuple(_dataset_config(item, root) for item in dataset_payloads)
        return EODOperatorConfig(
            config_schema_version=version,
            operations_root=_local_path(payload["operations_root"], root),
            datasets=datasets,
        )
    except (KeyError, TypeError, ValueError):
        raise EODOperatorConfigError(EODOperatorConfigErrorCode.INVALID_CONFIG) from None


def _dataset_config(value: object, root: Path) -> EODOperatorDatasetConfig:
    if type(value) is not dict or frozenset(value) != _DATASET_FIELDS:
        raise ValueError("operator dataset fields are invalid")
    if type(value["enabled"]) is not bool:
        raise ValueError("enabled must be an exact bool")
    return EODOperatorDatasetConfig(
        production_config=_local_path(value["production_config"], root),
        storage_identity=_validate_storage_identity(value["storage_identity"]),
        enabled=value["enabled"],
    )


def _local_path(value: object, root: Path) -> Path:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise ValueError("path must be bounded local text")
    text = value.strip()
    is_uri = _URI_PATTERN.match(text) is not None and _WINDOWS_ABSOLUTE_PATTERN.match(text) is None
    if is_uri or _ENVIRONMENT_PATTERN.search(text) is not None:
        raise ValueError("path must not contain a URI or environment substitution")
    candidate = Path(text)
    return (
        candidate.resolve(strict=False) if candidate.is_absolute() else (root / candidate).resolve()
    )


def _validate_storage_identity(value: object) -> str:
    if (
        type(value) is not str
        or _STORAGE_IDENTITY_PATTERN.fullmatch(value) is None
        or contains_absolute_path(value)
        or contains_sensitive_value(value)
    ):
        raise ValueError("storage_identity must be a safe path-independent identifier")
    return value


__all__ = [
    "EOD_OPERATOR_CONFIG_SCHEMA_VERSION",
    "EODOperatorConfig",
    "EODOperatorConfigError",
    "EODOperatorConfigErrorCode",
    "EODOperatorDatasetConfig",
    "load_eod_operator_config",
]
