"""Pure catalog values and explicit read-only production runtime composition."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from autowealth.security import contains_absolute_path, contains_sensitive_value

from .composition import EODProductionConfig, EODRuntimeStack, ProviderFactory, build_eod_runtime
from .operation_control import eod_calendar_identity
from .operations import EODOperationExecutionContext
from .schemas import EODDatasetKey

EOD_OPERATION_CATALOG_SCHEMA_VERSION = 1
EOD_RUNTIME_CONTRACT_VERSION = 1
MAX_EOD_OPERATION_CATALOG_ENTRIES = 256
_STORAGE_IDENTITY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,255}$")


class EODOperationCatalogErrorCode(str, Enum):
    CATALOG_EMPTY = "catalog_empty"
    CATALOG_TOO_LARGE = "catalog_too_large"
    DUPLICATE_DATASET = "duplicate_dataset"
    DUPLICATE_STORAGE_IDENTITY = "duplicate_storage_identity"
    MIXED_CALENDAR_IDENTITY = "mixed_calendar_identity"
    NO_ENABLED_DATASET = "no_enabled_dataset"
    DATASET_NOT_IN_CATALOG = "dataset_not_in_catalog"
    DATASET_DISABLED = "dataset_disabled"


class EODOperationCatalogError(ValueError):
    def __init__(self, code: EODOperationCatalogErrorCode) -> None:
        if type(code) is not EODOperationCatalogErrorCode:
            raise TypeError("code must be an exact catalog error code")
        self.code = code
        super().__init__(f"The EOD operation catalog is unavailable ({code.value}).")


@dataclass(frozen=True)
class EODOperationCatalogEntry:
    dataset: EODDatasetKey
    enabled: bool
    storage_identity: str
    runtime: EODRuntimeStack

    def __post_init__(self) -> None:
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.enabled) is not bool:
            raise TypeError("enabled must be an exact bool")
        _storage_identity(self.storage_identity)
        if type(self.runtime) is not EODRuntimeStack or self.runtime.dataset != self.dataset:
            raise TypeError("runtime must be an exact matching EODRuntimeStack")

    @property
    def calendar_identity(self) -> str:
        return eod_calendar_identity(self.runtime.calendar.identity)

    @property
    def provider_identities(self) -> Tuple[Tuple[str, str], ...]:
        return tuple(
            (provider.provider_name, provider.provider_version)
            for provider in self.runtime.providers
        )

    def fingerprint_dict(self) -> dict[str, object]:
        config = self.runtime.config
        return {
            "dataset": self.dataset.to_dict(),
            "storage_identity": self.storage_identity,
            "enabled": self.enabled,
            "production_config_schema_version": config.config_schema_version,
            "providers": [
                {"provider_name": name, "provider_version": version}
                for name, version in self.provider_identities
            ],
            "retry_policy": {
                "max_attempts": config.retry_policy.max_attempts,
                "initial_backoff_seconds": config.retry_policy.initial_backoff_seconds,
                "backoff_multiplier": config.retry_policy.backoff_multiplier,
                "max_backoff_seconds": config.retry_policy.max_backoff_seconds,
            },
            "rate_limit_policy": {
                "minimum_interval_seconds": config.rate_limit_policy.minimum_interval_seconds
            },
        }


class EODOperationCatalog:
    """Canonical in-memory catalog; construction performs no I/O or execution."""

    def __init__(self, entries: Tuple[EODOperationCatalogEntry, ...]) -> None:
        if type(entries) not in (list, tuple):
            raise TypeError("entries must be an exact list or exact tuple")
        normalized = tuple(entries)
        if not normalized:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.CATALOG_EMPTY)
        if len(normalized) > MAX_EOD_OPERATION_CATALOG_ENTRIES:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.CATALOG_TOO_LARGE)
        if any(type(entry) is not EODOperationCatalogEntry for entry in normalized):
            raise TypeError("entries must contain exact EODOperationCatalogEntry values")
        datasets = tuple(entry.dataset for entry in normalized)
        storage = tuple(entry.storage_identity for entry in normalized)
        if len(set(datasets)) != len(datasets):
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.DUPLICATE_DATASET)
        if len(set(storage)) != len(storage):
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.DUPLICATE_STORAGE_IDENTITY)
        ordered = tuple(sorted(normalized, key=lambda entry: entry.dataset.identity))
        enabled_calendars = tuple(
            entry.runtime.calendar.identity.to_dict() for entry in ordered if entry.enabled
        )
        if enabled_calendars and any(
            value != enabled_calendars[0] for value in enabled_calendars[1:]
        ):
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.MIXED_CALENDAR_IDENTITY)
        self._entries = ordered
        self._by_dataset = MappingProxyType({entry.dataset: entry for entry in ordered})
        self._calendar_payload = enabled_calendars[0] if enabled_calendars else None
        self._calendar_identity = next(
            (entry.calendar_identity for entry in ordered if entry.enabled), None
        )
        self._fingerprint = _fingerprint(self.fingerprint_dict())

    @property
    def entries(self) -> Tuple[EODOperationCatalogEntry, ...]:
        return self._entries

    @property
    def calendar_identity(self) -> Optional[str]:
        return self._calendar_identity

    @property
    def execution_config_fingerprint(self) -> str:
        return self._fingerprint

    @property
    def execution_context(self) -> EODOperationExecutionContext:
        if self._calendar_identity is None:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.NO_ENABLED_DATASET)
        return EODOperationExecutionContext(
            calendar_identity=self._calendar_identity,
            execution_config_fingerprint=self._fingerprint,
        )

    def get(self, dataset: EODDatasetKey) -> Optional[EODOperationCatalogEntry]:
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        return self._by_dataset.get(dataset)

    def require_enabled(self, dataset: EODDatasetKey) -> EODOperationCatalogEntry:
        entry = self.get(dataset)
        if entry is None:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.DATASET_NOT_IN_CATALOG)
        if not entry.enabled:
            raise EODOperationCatalogError(EODOperationCatalogErrorCode.DATASET_DISABLED)
        return entry

    def fingerprint_dict(self) -> dict[str, object]:
        return {
            "catalog_schema_version": EOD_OPERATION_CATALOG_SCHEMA_VERSION,
            "runtime_contract_version": EOD_RUNTIME_CONTRACT_VERSION,
            "calendar_identity": self._calendar_payload,
            "datasets": [entry.fingerprint_dict() for entry in self._entries],
        }


def build_eod_operation_catalog(
    configs: Tuple[EODProductionConfig, ...],
    *,
    storage_identities: Mapping[EODDatasetKey, str],
    enabled: Optional[Mapping[EODDatasetKey, bool]] = None,
    provider_factories: Optional[Mapping[str, ProviderFactory]] = None,
) -> EODOperationCatalog:
    """Read local calendar artifacts and construct runtimes without executing Providers."""

    if type(configs) not in (list, tuple) or not configs:
        raise TypeError("configs must be a non-empty exact list or exact tuple")
    normalized = tuple(configs)
    if any(type(config) is not EODProductionConfig for config in normalized):
        raise TypeError("configs must contain exact EODProductionConfig values")
    if type(storage_identities) is not dict:
        raise TypeError("storage_identities must be an exact dict")
    expected = {config.dataset for config in normalized}
    if set(storage_identities) != expected:
        raise ValueError("storage_identities must exactly cover configured datasets")
    if enabled is None:
        enabled_values = {dataset: True for dataset in expected}
    elif type(enabled) is dict and set(enabled) == expected:
        enabled_values = dict(enabled)
    else:
        raise ValueError("enabled must exactly cover configured datasets")
    if any(type(value) is not bool for value in enabled_values.values()):
        raise TypeError("enabled values must be exact bool values")

    entries = tuple(
        EODOperationCatalogEntry(
            dataset=config.dataset,
            enabled=enabled_values[config.dataset],
            storage_identity=storage_identities[config.dataset],
            runtime=build_eod_runtime(config, provider_factories=provider_factories),
        )
        for config in normalized
    )
    return EODOperationCatalog(entries)


def _storage_identity(value: object) -> str:
    if (
        type(value) is not str
        or _STORAGE_IDENTITY_PATTERN.fullmatch(value) is None
        or contains_absolute_path(value)
        or contains_sensitive_value(value)
    ):
        raise ValueError("storage_identity must be a safe path-independent identifier")
    return value


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"


__all__ = [
    "EOD_OPERATION_CATALOG_SCHEMA_VERSION",
    "EOD_RUNTIME_CONTRACT_VERSION",
    "MAX_EOD_OPERATION_CATALOG_ENTRIES",
    "EODOperationCatalog",
    "EODOperationCatalogEntry",
    "EODOperationCatalogError",
    "EODOperationCatalogErrorCode",
    "build_eod_operation_catalog",
]
