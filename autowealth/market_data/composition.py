"""Explicit, side-effect-free construction of one production EOD runtime stack."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import importlib
import re
from typing import TYPE_CHECKING, Callable, Mapping, Optional, Tuple

import yaml

from .calendar import TradingCalendar
from .local_calendar import VersionedLocalTradingCalendar
from .providers import EODProvider, EODProviderCapability
from .schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODDatasetKey,
    Market,
    Venue,
)

EOD_PRODUCTION_CONFIG_SCHEMA_VERSION = 1
MAX_EOD_PRODUCTION_CONFIG_BYTES = 1024 * 1024

Path = importlib.import_module("pathlib").Path

if TYPE_CHECKING:
    from .batch import EODBatchCoordinator, EODDatasetLockManager
    from .coordinator import EODIncrementalCoordinator
    from .provider_chain import EODProviderChain
    from .repositories import EODFileRepository

AKSHARE_EQUITY_PROVIDER = "akshare_eod_equity"
AKSHARE_INDEX_PROVIDER = "akshare_eod_index"
AKSHARE_INDEX_DAILY_PROVIDER = "akshare_eod_index_daily"

_SUPPORTED_PROVIDER_NAMES = frozenset(
    {
        AKSHARE_EQUITY_PROVIDER,
        AKSHARE_INDEX_PROVIDER,
        AKSHARE_INDEX_DAILY_PROVIDER,
    }
)
_CONFIG_FIELDS = frozenset(
    {
        "config_schema_version",
        "repository_root",
        "calendar_source",
        "dataset",
        "provider_order",
    }
)
_DATASET_FIELDS = frozenset(
    {
        "market",
        "venue",
        "asset_type",
        "canonical_symbol",
        "frequency",
        "adjustment_type",
    }
)
_URI_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

ProviderFactory = Callable[[TradingCalendar], EODProvider]


class EODCompositionErrorCode(str, Enum):
    """Stable production composition failure codes."""

    CONFIG_MISSING = "config_missing"
    CONFIG_UNREADABLE = "config_unreadable"
    INVALID_YAML = "invalid_yaml"
    INVALID_CONFIG = "invalid_config"
    REPOSITORY_INVALID = "repository_invalid"
    PROVIDER_INVALID = "provider_invalid"


_ERROR_MESSAGES = {
    EODCompositionErrorCode.CONFIG_MISSING: "The production EOD configuration is missing.",
    EODCompositionErrorCode.CONFIG_UNREADABLE: ("The production EOD configuration is unreadable."),
    EODCompositionErrorCode.INVALID_YAML: ("The production EOD configuration is not valid YAML."),
    EODCompositionErrorCode.INVALID_CONFIG: ("The production EOD configuration is invalid."),
    EODCompositionErrorCode.REPOSITORY_INVALID: (
        "The production EOD repository configuration is invalid."
    ),
    EODCompositionErrorCode.PROVIDER_INVALID: (
        "The production EOD provider configuration is invalid."
    ),
}


class EODCompositionError(ValueError):
    """Safe composition error that does not echo paths, secrets or provider payloads."""

    def __init__(self, code: EODCompositionErrorCode) -> None:
        if not isinstance(code, EODCompositionErrorCode):
            raise TypeError("code must be EODCompositionErrorCode")
        self.code = code
        self.message = _ERROR_MESSAGES[code]
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message}


@dataclass(frozen=True)
class EODProductionConfig:
    """Validated configuration for one single-dataset production EOD stack."""

    config_schema_version: int
    repository_root: Path
    calendar_source: Path
    dataset: EODDatasetKey
    provider_order: Tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.config_schema_version) is not int or (
            self.config_schema_version != EOD_PRODUCTION_CONFIG_SCHEMA_VERSION
        ):
            raise ValueError("config_schema_version is unsupported")
        if not isinstance(self.repository_root, Path) or not self.repository_root.is_absolute():
            raise ValueError("repository_root must be an explicit absolute Path")
        if not isinstance(self.calendar_source, Path) or not self.calendar_source.is_absolute():
            raise ValueError("calendar_source must be an explicit absolute Path")
        if self.repository_root == self.calendar_source:
            raise ValueError("repository_root and calendar_source must differ")
        if self.calendar_source.suffix.lower() != ".json":
            raise ValueError("calendar_source must identify a JSON artifact")
        if type(self.dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        if type(self.provider_order) not in (list, tuple):
            raise TypeError("provider_order must be an exact list or tuple")
        provider_order = tuple(self.provider_order)
        if not provider_order:
            raise ValueError("provider_order cannot be empty")
        if any(
            type(name) is not str or name not in _SUPPORTED_PROVIDER_NAMES
            for name in provider_order
        ):
            raise ValueError("provider_order contains an unsupported provider")
        if len(set(provider_order)) != len(provider_order):
            raise ValueError("provider_order cannot contain duplicates")

        allowed = (
            {AKSHARE_EQUITY_PROVIDER}
            if self.dataset.asset_type is AssetType.EQUITY
            else {AKSHARE_INDEX_PROVIDER, AKSHARE_INDEX_DAILY_PROVIDER}
        )
        if any(name not in allowed for name in provider_order):
            raise ValueError("provider_order is incompatible with the dataset asset type")
        if (
            self.dataset.asset_type is AssetType.INDEX
            and self.dataset.adjustment_type is not AdjustmentType.NONE
        ):
            raise ValueError("index EOD composition only supports unadjusted prices")
        object.__setattr__(self, "provider_order", provider_order)


@dataclass(frozen=True)
class EODRuntimeStack:
    """Constructed objects for one dataset; creating this value performs no update."""

    config: EODProductionConfig
    calendar: VersionedLocalTradingCalendar
    repository: "EODFileRepository"
    providers: Tuple[EODProvider, ...]
    provider_chain: "EODProviderChain"
    coordinator: "EODIncrementalCoordinator"

    def __post_init__(self) -> None:
        if type(self.config) is not EODProductionConfig:
            raise TypeError("config must be an exact EODProductionConfig")
        if type(self.calendar) is not VersionedLocalTradingCalendar:
            raise TypeError("calendar must be VersionedLocalTradingCalendar")
        if type(self.providers) is not tuple or not self.providers:
            raise TypeError("providers must be a non-empty exact tuple")

    @property
    def dataset(self) -> EODDatasetKey:
        return self.config.dataset

    @property
    def provider_order(self) -> Tuple[str, ...]:
        return tuple(getattr(provider, "provider_name") for provider in self.providers)


def load_eod_production_config(path: Path) -> EODProductionConfig:
    """Read one strict YAML configuration without contacting providers."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib Path")
    try:
        if not path.is_file():
            raise EODCompositionError(EODCompositionErrorCode.CONFIG_MISSING)
        raw_text = path.read_text(encoding="utf-8")
    except EODCompositionError:
        raise
    except OSError as exc:
        error = EODCompositionError(EODCompositionErrorCode.CONFIG_UNREADABLE)
        raise error from exc
    except UnicodeError as exc:
        error = EODCompositionError(EODCompositionErrorCode.INVALID_YAML)
        raise error from exc
    if len(raw_text.encode("utf-8")) > MAX_EOD_PRODUCTION_CONFIG_BYTES:
        raise EODCompositionError(EODCompositionErrorCode.INVALID_CONFIG)

    try:
        payload = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        error = EODCompositionError(EODCompositionErrorCode.INVALID_YAML)
        raise error from exc
    if type(payload) is not dict or set(payload) != _CONFIG_FIELDS:
        raise EODCompositionError(EODCompositionErrorCode.INVALID_CONFIG)

    root = _project_or_config_root(path)
    try:
        dataset_payload = payload["dataset"]
        if type(dataset_payload) is not dict or set(dataset_payload) != _DATASET_FIELDS:
            raise ValueError("dataset fields are invalid")
        dataset = EODDatasetKey(
            market=Market(dataset_payload["market"]),
            venue=Venue(dataset_payload["venue"]),
            asset_type=AssetType(dataset_payload["asset_type"]),
            canonical_symbol=dataset_payload["canonical_symbol"],
            frequency=BarFrequency(dataset_payload["frequency"]),
            adjustment_type=AdjustmentType(dataset_payload["adjustment_type"]),
        )
        provider_order = payload["provider_order"]
        if type(provider_order) is not list:
            raise ValueError("provider_order must be a YAML list")
        return EODProductionConfig(
            config_schema_version=payload["config_schema_version"],
            repository_root=_resolve_local_path(payload["repository_root"], root),
            calendar_source=_resolve_local_path(payload["calendar_source"], root),
            dataset=dataset,
            provider_order=tuple(provider_order),
        )
    except (KeyError, TypeError, ValueError) as exc:
        error = EODCompositionError(EODCompositionErrorCode.INVALID_CONFIG)
        raise error from exc


def build_eod_runtime(
    config: EODProductionConfig,
    *,
    provider_factories: Optional[Mapping[str, ProviderFactory]] = None,
) -> EODRuntimeStack:
    """Validate and construct the EOD stack without fetching or publishing data."""

    if type(config) is not EODProductionConfig:
        raise TypeError("config must be an exact EODProductionConfig")
    calendar = VersionedLocalTradingCalendar.from_file(config.calendar_source)

    try:
        from .repositories import LocalEODFileRepository

        repository = LocalEODFileRepository(config.repository_root)
    except Exception as exc:
        error = EODCompositionError(EODCompositionErrorCode.REPOSITORY_INVALID)
        raise error from exc

    factories = _provider_factories(config.provider_order, provider_factories)
    providers = []
    try:
        for provider_name in config.provider_order:
            provider = factories[provider_name](calendar)
            if getattr(provider, "provider_name", None) != provider_name:
                raise ValueError("provider identity does not match configuration")
            capabilities = getattr(provider, "capabilities")
            if type(capabilities) not in (list, tuple) or any(
                type(capability) is not EODProviderCapability for capability in capabilities
            ):
                raise TypeError("provider capabilities must contain exact contract values")
            matches = tuple(
                capability for capability in capabilities if capability.matches(config.dataset)
            )
            if len(matches) != 1:
                raise ValueError("provider must expose one exact matching capability")
            providers.append(provider)

        from .provider_chain import EODProviderChain

        provider_chain = EODProviderChain(tuple(providers))
    except Exception as exc:
        error = EODCompositionError(EODCompositionErrorCode.PROVIDER_INVALID)
        raise error from exc

    from .coordinator import EODIncrementalCoordinator

    coordinator = EODIncrementalCoordinator(repository, provider_chain, calendar)
    return EODRuntimeStack(
        config=config,
        calendar=calendar,
        repository=repository,
        providers=tuple(providers),
        provider_chain=provider_chain,
        coordinator=coordinator,
    )


def build_eod_batch_coordinator(
    runtimes: Tuple[EODRuntimeStack, ...],
    *,
    lock_manager: "EODDatasetLockManager",
) -> "EODBatchCoordinator":
    """Construct a batch coordinator from explicit runtimes without executing updates."""

    if type(runtimes) not in (list, tuple):
        raise TypeError("runtimes must be an exact list or exact tuple")
    normalized = tuple(runtimes)
    if not normalized:
        raise ValueError("runtimes cannot be empty")
    if any(type(runtime) is not EODRuntimeStack for runtime in normalized):
        raise TypeError("runtimes must contain exact EODRuntimeStack values")
    datasets = tuple(runtime.dataset for runtime in normalized)
    if len(set(datasets)) != len(datasets):
        raise ValueError("runtimes cannot contain duplicate dataset identities")

    from .batch import EODBatchCoordinator

    return EODBatchCoordinator(
        {runtime.dataset: runtime.coordinator for runtime in normalized},
        lock_manager,
    )


def _provider_factories(
    provider_order: Tuple[str, ...],
    supplied: Optional[Mapping[str, ProviderFactory]],
) -> dict[str, ProviderFactory]:
    if supplied is None:
        return {name: _default_provider_factory(name) for name in provider_order}
    if type(supplied) is not dict or set(supplied) != set(provider_order):
        raise EODCompositionError(EODCompositionErrorCode.PROVIDER_INVALID)
    factories = dict(supplied)
    if any(not callable(factory) for factory in factories.values()):
        raise EODCompositionError(EODCompositionErrorCode.PROVIDER_INVALID)
    return factories


def _default_provider_factory(name: str) -> ProviderFactory:
    from .akshare_adapters import (
        AKShareEODEquityProvider,
        AKShareEODIndexDailyProvider,
        AKShareEODIndexProvider,
    )

    provider_types = {
        AKSHARE_EQUITY_PROVIDER: AKShareEODEquityProvider,
        AKSHARE_INDEX_PROVIDER: AKShareEODIndexProvider,
        AKSHARE_INDEX_DAILY_PROVIDER: AKShareEODIndexDailyProvider,
    }
    try:
        provider_type = provider_types[name]
    except KeyError as exc:  # pragma: no cover - config validation rejects unknown names.
        error = EODCompositionError(EODCompositionErrorCode.PROVIDER_INVALID)
        raise error from exc
    return provider_type


def _resolve_local_path(value: object, root: Path) -> Path:
    if type(value) is not str or not value.strip() or "\x00" in value:
        raise ValueError("path must be non-empty local text")
    if _URI_PATTERN.match(value.strip()) is not None:
        raise ValueError("path must not be a URI")
    candidate = Path(value.strip())
    return (
        candidate.resolve(strict=False) if candidate.is_absolute() else (root / candidate).resolve()
    )


def _project_or_config_root(config_path: Path) -> Path:
    resolved = config_path.resolve(strict=False)
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return resolved.parent


__all__ = [
    "AKSHARE_EQUITY_PROVIDER",
    "AKSHARE_INDEX_DAILY_PROVIDER",
    "AKSHARE_INDEX_PROVIDER",
    "EODCompositionError",
    "EODCompositionErrorCode",
    "EODProductionConfig",
    "EODRuntimeStack",
    "EOD_PRODUCTION_CONFIG_SCHEMA_VERSION",
    "build_eod_batch_coordinator",
    "build_eod_runtime",
    "load_eod_production_config",
]
