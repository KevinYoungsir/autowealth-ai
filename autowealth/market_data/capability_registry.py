"""Static, provider-neutral EOD capability declarations.

The registry is deliberately separate from provider construction and readiness.  It
contains only immutable metadata that can be inspected without credentials, files,
SDK imports, or network access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from autowealth.security import contains_absolute_path, contains_sensitive_value

from .providers import EODProviderCapability, EODRevisionStrategy, _json_text
from .schemas import AdjustmentType, AssetType, BarFrequency, EODDatasetKey, Market, Venue

EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION = 1
AKSHARE_EQUITY_PROVIDER = "akshare_eod_equity"
AKSHARE_INDEX_PROVIDER = "akshare_eod_index"
AKSHARE_INDEX_DAILY_PROVIDER = "akshare_eod_index_daily"
TUSHARE_EQUITY_PROVIDER = "tushare_eod_equity"
TUSHARE_TOKEN_ENVIRONMENT_VARIABLE = "TUSHARE_TOKEN"
AKSHARE_INDEX_SYMBOLS = (
    "000001.SH",
    "000300.SH",
    "000905.SH",
    "000852.SH",
    "399001.SZ",
    "399006.SZ",
)
_PROVIDERS = (
    AKSHARE_EQUITY_PROVIDER,
    AKSHARE_INDEX_PROVIDER,
    AKSHARE_INDEX_DAILY_PROVIDER,
    TUSHARE_EQUITY_PROVIDER,
)

_IDENTITY_PATTERN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-"
_UNIT_VERIFICATION_STATES = frozenset({"verified", "unverified"})


class EODCapabilityRegistryError(ValueError):
    """Raised when a static capability declaration or lookup is unsafe."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EODCapabilityRegistryError("duplicate JSON field")
        result[key] = value
    return result


def _safe_identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 255
        or any(char not in _IDENTITY_PATTERN for char in value)
        or contains_absolute_path(value)
        or contains_sensitive_value(value)
    ):
        raise EODCapabilityRegistryError(f"{field_name} must be a safe stable identifier")
    return value


def _enum_values(value: object, enum_type: type, field_name: str) -> Tuple[object, ...]:
    if type(value) not in (list, tuple) or not value:
        raise EODCapabilityRegistryError(f"{field_name} must be a non-empty list or tuple")
    values = []
    for item in value:
        try:
            normalized = item if isinstance(item, enum_type) else enum_type(item)
        except (TypeError, ValueError) as exc:
            raise EODCapabilityRegistryError(f"{field_name} contains an unsupported value") from exc
        values.append(normalized)
    if len(set(values)) != len(values):
        raise EODCapabilityRegistryError(f"{field_name} contains duplicates")
    return tuple(sorted(values, key=lambda item: item.value))


@dataclass(frozen=True)
class EODProviderCapabilityDeclaration:
    """Complete static capability metadata for one provider identity."""

    provider_name: str
    provider_version: str
    capabilities: Tuple[EODProviderCapability, ...]
    asset_types: Tuple[AssetType, ...]
    frequencies: Tuple[BarFrequency, ...]
    adjustment_types: Tuple[AdjustmentType, ...]
    markets: Tuple[Market, ...]
    venues: Tuple[Venue, ...]
    volume_unit: str
    amount_unit: str
    unit_verification: str
    observation_source_required: bool
    credential_required: bool
    credential_environment_variable: Optional[str] = None

    def __post_init__(self) -> None:
        name = _safe_identifier(self.provider_name, "provider_name")
        version = _safe_identifier(self.provider_version, "provider_version")
        if name not in _PROVIDERS or version != "1":
            raise EODCapabilityRegistryError("unknown provider identity or version")
        if type(self.capabilities) not in (list, tuple) or not self.capabilities:
            raise EODCapabilityRegistryError("capabilities must be a non-empty tuple")
        capabilities = tuple(self.capabilities)
        if any(type(item) is not EODProviderCapability for item in capabilities):
            raise EODCapabilityRegistryError("capabilities must contain exact contract values")
        if len(set(capabilities)) != len(capabilities):
            raise EODCapabilityRegistryError("capabilities contain duplicates")
        keys = tuple(
            (c.market, c.venue, c.asset_type, c.frequency, c.adjustment_type) for c in capabilities
        )
        if len(set(keys)) != len(keys):
            raise EODCapabilityRegistryError("capabilities contain ambiguous matches")
        fields = (
            ("asset_types", self.asset_types, AssetType),
            ("frequencies", self.frequencies, BarFrequency),
            ("adjustment_types", self.adjustment_types, AdjustmentType),
            ("markets", self.markets, Market),
            ("venues", self.venues, Venue),
        )
        normalized = {
            field: _enum_values(value, enum_type, field) for field, value, enum_type in fields
        }
        for scope, attribute in (
            ("asset_types", "asset_type"),
            ("frequencies", "frequency"),
            ("adjustment_types", "adjustment_type"),
            ("markets", "market"),
            ("venues", "venue"),
        ):
            if set(normalized[scope]) != {getattr(c, attribute) for c in capabilities}:
                raise EODCapabilityRegistryError("scope must exactly match capabilities")
        for field in ("volume_unit", "amount_unit"):
            _safe_identifier(getattr(self, field), field)
        if (
            type(self.unit_verification) is not str
            or self.unit_verification not in _UNIT_VERIFICATION_STATES
        ):
            raise EODCapabilityRegistryError("unit_verification is unsupported")
        if (self.volume_unit, self.amount_unit) not in (
            ("shares", "CNY_yuan"),
            ("source_value", "source_value"),
        ) or (self.volume_unit == "source_value" and self.unit_verification == "verified"):
            raise EODCapabilityRegistryError("unit contract is unsupported")
        if type(self.observation_source_required) is not bool:
            raise EODCapabilityRegistryError("observation_source_required must be bool")
        if type(self.credential_required) is not bool:
            raise EODCapabilityRegistryError("credential_required must be bool")
        env = self.credential_environment_variable
        if self.credential_required:
            if env is None:
                raise EODCapabilityRegistryError("credential environment variable is required")
            env = _safe_identifier(env, "credential_environment_variable")
            if env != TUSHARE_TOKEN_ENVIRONMENT_VARIABLE:
                raise EODCapabilityRegistryError("credential environment name is unsupported")
        elif env is not None:
            raise EODCapabilityRegistryError("credential environment variable requires credentials")
        object.__setattr__(self, "provider_name", name)
        object.__setattr__(self, "provider_version", version)
        object.__setattr__(
            self,
            "capabilities",
            tuple(
                sorted(
                    capabilities,
                    key=lambda item: (
                        item.market.value,
                        item.venue.value,
                        item.asset_type.value,
                        item.frequency.value,
                        (AdjustmentType.NONE, AdjustmentType.QFQ, AdjustmentType.HFQ).index(
                            item.adjustment_type
                        ),
                    ),
                )
            ),
        )
        for field, value in normalized.items():
            object.__setattr__(self, field, value)
        object.__setattr__(self, "credential_environment_variable", env)

    def supports(self, dataset: object) -> bool:
        if type(dataset) is not EODDatasetKey:
            raise TypeError("dataset must be an exact EODDatasetKey")
        return any(capability.matches(dataset) for capability in self.capabilities) and (
            self.asset_types != (AssetType.INDEX,)
            or dataset.canonical_symbol in AKSHARE_INDEX_SYMBOLS
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "request_grain": "single_dataset_closed_range",
            "supported_symbols": (
                list(sorted(AKSHARE_INDEX_SYMBOLS))
                if self.asset_types == (AssetType.INDEX,)
                else None
            ),
            "capabilities": [item.to_dict() for item in self.capabilities],
            "asset_types": [item.value for item in self.asset_types],
            "frequencies": [item.value for item in self.frequencies],
            "adjustment_types": [item.value for item in self.adjustment_types],
            "markets": [item.value for item in self.markets],
            "venues": [item.value for item in self.venues],
            "units": {
                "volume": self.volume_unit,
                "amount": self.amount_unit,
                "verification": self.unit_verification,
            },
            "observation_source_required": self.observation_source_required,
            "credential": {
                "required": self.credential_required,
                "environment_variable": self.credential_environment_variable,
            },
        }

    @property
    def identity(self) -> str:
        payload = self.to_json()
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return _json_text(self.to_dict())

    @property
    def unit_contract(self) -> dict[str, str]:
        return {
            "volume": self.volume_unit,
            "amount": self.amount_unit,
            "verification": self.unit_verification,
        }

    @classmethod
    def from_dict(cls, payload: object) -> "EODProviderCapabilityDeclaration":
        if type(payload) is not dict:
            raise EODCapabilityRegistryError("capability declaration must be an object")
        required = {
            "provider_name",
            "provider_version",
            "capabilities",
            "asset_types",
            "frequencies",
            "adjustment_types",
            "markets",
            "venues",
            "units",
            "observation_source_required",
            "credential",
            "request_grain",
            "supported_symbols",
        }
        if (
            set(payload) != required
            or type(payload["units"]) is not dict
            or type(payload["credential"]) is not dict
        ):
            raise EODCapabilityRegistryError("capability declaration schema is invalid")
        unit = payload["units"]
        if payload["request_grain"] != "single_dataset_closed_range":
            raise EODCapabilityRegistryError("unsupported request grain")
        expected_symbols = (
            list(sorted(AKSHARE_INDEX_SYMBOLS)) if payload["asset_types"] == ["index"] else None
        )
        if payload["supported_symbols"] != expected_symbols:
            raise EODCapabilityRegistryError("unsupported symbol scope")
        credential = payload["credential"]
        if set(unit) != {"volume", "amount", "verification"} or set(credential) != {
            "required",
            "environment_variable",
        }:
            raise EODCapabilityRegistryError("capability declaration metadata is invalid")
        if type(payload["capabilities"]) is not list:
            raise EODCapabilityRegistryError("capabilities must be a list")
        capabilities = []
        try:
            for item in payload["capabilities"]:
                if type(item) is not dict:
                    raise EODCapabilityRegistryError("capability entry must be an object")
                if set(item) != {
                    "market",
                    "venue",
                    "asset_type",
                    "frequency",
                    "adjustment_type",
                    "revision_strategy",
                    "maximum_overlap_trading_days",
                }:
                    raise EODCapabilityRegistryError("invalid capability fields")
                capabilities.append(
                    EODProviderCapability(
                        market=Market(item["market"]),
                        venue=Venue(item["venue"]),
                        asset_type=AssetType(item["asset_type"]),
                        frequency=BarFrequency(item["frequency"]),
                        adjustment_type=AdjustmentType(item["adjustment_type"]),
                        revision_strategy=EODRevisionStrategy(item["revision_strategy"]),
                        maximum_overlap_trading_days=item["maximum_overlap_trading_days"],
                    )
                )
            return cls(
                payload["provider_name"],
                payload["provider_version"],
                tuple(capabilities),
                payload["asset_types"],
                payload["frequencies"],
                payload["adjustment_types"],
                payload["markets"],
                payload["venues"],
                unit["volume"],
                unit["amount"],
                unit["verification"],
                payload["observation_source_required"],
                credential["required"],
                credential["environment_variable"],
            )
        except EODCapabilityRegistryError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EODCapabilityRegistryError("capability declaration values are invalid") from exc


# A concise alias makes the declaration discoverable without introducing a second model.
EODCapabilityDeclaration = EODProviderCapabilityDeclaration


@dataclass(frozen=True, init=False)
class EODCapabilityRegistry:
    """Immutable stable-order registry of known provider declarations."""

    _declarations: Tuple[EODProviderCapabilityDeclaration, ...]
    _by_name: Mapping[str, EODProviderCapabilityDeclaration] = field(repr=False, compare=False)
    _identity: str

    def __init__(self, declarations: Tuple[EODProviderCapabilityDeclaration, ...]) -> None:
        if type(declarations) not in (list, tuple) or not declarations:
            raise EODCapabilityRegistryError("declarations must be a non-empty tuple")
        values = tuple(declarations)
        if any(type(item) is not EODProviderCapabilityDeclaration for item in values):
            raise EODCapabilityRegistryError("declarations must contain exact declaration values")
        names = tuple(item.provider_name for item in values)
        if len(set(names)) != len(names):
            raise EODCapabilityRegistryError("duplicate provider identity")
        ordered = tuple(
            sorted(values, key=lambda item: (item.provider_name, item.provider_version))
        )
        object.__setattr__(self, "_declarations", ordered)
        object.__setattr__(
            self, "_by_name", MappingProxyType({item.provider_name: item for item in ordered})
        )
        object.__setattr__(self, "_identity", self._calculate_identity())

    @property
    def declarations(self) -> Tuple[EODProviderCapabilityDeclaration, ...]:
        return self._declarations

    @property
    def identity(self) -> str:
        return self._identity

    def lookup(self, provider_name: str) -> EODProviderCapabilityDeclaration:
        if type(provider_name) is not str:
            raise EODCapabilityRegistryError("unknown provider")
        try:
            return self._by_name[provider_name]
        except (KeyError, TypeError) as exc:
            raise EODCapabilityRegistryError("unknown provider") from exc

    def get(self, provider_name: str) -> Optional[EODProviderCapabilityDeclaration]:
        if type(provider_name) is not str:
            raise TypeError("provider_name must be a string")
        return self.lookup(provider_name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION,
            "providers": [item.to_dict() for item in self._declarations],
        }

    def to_json(self) -> str:
        return _json_text(self.to_dict())

    @classmethod
    def from_dict(cls, payload: object) -> "EODCapabilityRegistry":
        if type(payload) is not dict or set(payload) != {"schema_version", "providers"}:
            raise EODCapabilityRegistryError("registry schema is invalid")
        if (
            type(payload["schema_version"]) is not int
            or payload["schema_version"] != EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION
        ):
            raise EODCapabilityRegistryError("registry schema version is unsupported")
        if type(payload["providers"]) is not list:
            raise EODCapabilityRegistryError("registry providers must be a list")
        try:
            declarations = tuple(
                EODProviderCapabilityDeclaration.from_dict(item) for item in payload["providers"]
            )
        except EODCapabilityRegistryError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise EODCapabilityRegistryError("registry provider declaration is invalid") from exc
        return cls(declarations)

    @classmethod
    def from_json(cls, payload: object) -> "EODCapabilityRegistry":
        if type(payload) is not str:
            raise TypeError("payload must be a string")
        try:
            decoded = json.loads(payload, object_pairs_hook=_unique_object)
        except (TypeError, ValueError) as exc:
            raise EODCapabilityRegistryError("registry JSON is invalid") from exc
        return cls.from_dict(decoded)

    def _calculate_identity(self) -> str:
        return "sha256:" + hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


def _capabilities(*items: EODProviderCapability) -> Tuple[EODProviderCapability, ...]:
    return tuple(items)


def build_default_eod_capability_registry() -> EODCapabilityRegistry:
    """Construct the four currently supported declarations without side effects."""

    equity = (AssetType.EQUITY,)
    index = (AssetType.INDEX,)
    daily = (BarFrequency.DAILY,)
    both_venues = (Venue.SSE, Venue.SZSE)
    cn = (Market.CN,)
    none = (AdjustmentType.NONE,)
    ak_equity_caps = _capabilities(
        *[
            EODProviderCapability(
                market,
                venue,
                AssetType.EQUITY,
                BarFrequency.DAILY,
                adjustment,
                strategy,
            )
            for venue in both_venues
            for adjustment, strategy in (
                (AdjustmentType.NONE, EODRevisionStrategy.APPEND_ONLY),
                (AdjustmentType.QFQ, EODRevisionStrategy.FULL_REFRESH_REQUIRED),
                (AdjustmentType.HFQ, EODRevisionStrategy.FULL_REFRESH_REQUIRED),
            )
            for market in cn
        ]
    )
    index_caps = _capabilities(
        *[
            EODProviderCapability(
                market,
                venue,
                AssetType.INDEX,
                BarFrequency.DAILY,
                AdjustmentType.NONE,
                EODRevisionStrategy.APPEND_ONLY,
            )
            for market in cn
            for venue in both_venues
        ]
    )
    declarations = (
        EODProviderCapabilityDeclaration(
            AKSHARE_EQUITY_PROVIDER,
            "1",
            ak_equity_caps,
            equity,
            daily,
            (AdjustmentType.NONE, AdjustmentType.QFQ, AdjustmentType.HFQ),
            cn,
            both_venues,
            "shares",
            "CNY_yuan",
            "unverified",
            False,
            False,
        ),
        EODProviderCapabilityDeclaration(
            AKSHARE_INDEX_PROVIDER,
            "1",
            index_caps,
            index,
            daily,
            none,
            cn,
            both_venues,
            "source_value",
            "source_value",
            "unverified",
            False,
            False,
        ),
        EODProviderCapabilityDeclaration(
            AKSHARE_INDEX_DAILY_PROVIDER,
            "1",
            index_caps,
            index,
            daily,
            none,
            cn,
            both_venues,
            "source_value",
            "source_value",
            "unverified",
            False,
            False,
        ),
        EODProviderCapabilityDeclaration(
            TUSHARE_EQUITY_PROVIDER,
            "1",
            _capabilities(
                *[
                    EODProviderCapability(
                        market,
                        venue,
                        AssetType.EQUITY,
                        BarFrequency.DAILY,
                        AdjustmentType.NONE,
                        EODRevisionStrategy.APPEND_ONLY,
                    )
                    for market in cn
                    for venue in both_venues
                ]
            ),
            equity,
            daily,
            none,
            cn,
            both_venues,
            "shares",
            "CNY_yuan",
            "verified",
            True,
            True,
            TUSHARE_TOKEN_ENVIRONMENT_VARIABLE,
        ),
    )
    return EODCapabilityRegistry(declarations)


DEFAULT_EOD_CAPABILITY_REGISTRY = build_default_eod_capability_registry()


def get_eod_capability(provider_name: str) -> EODProviderCapabilityDeclaration:
    return DEFAULT_EOD_CAPABILITY_REGISTRY.lookup(provider_name)


__all__ = [
    "DEFAULT_EOD_CAPABILITY_REGISTRY",
    "EOD_CAPABILITY_REGISTRY_SCHEMA_VERSION",
    "EODCapabilityDeclaration",
    "EODCapabilityRegistry",
    "EODCapabilityRegistryError",
    "EODProviderCapabilityDeclaration",
    "build_default_eod_capability_registry",
    "get_eod_capability",
]
