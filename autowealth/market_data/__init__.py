"""Pure contracts for AutoWealth China A-share EOD market data."""

from importlib import import_module

from .calendar import (
    MARKET_TIMEZONE,
    TradingCalendar,
    TradingCalendarContractError,
    validate_trading_days,
)
from .normalization import normalize_canonical_symbol, normalize_eod_bars
from .planning import (
    EODRequestPlan,
    EODRequestPlanningError,
    EODRequestPlanningErrorCode,
    EODRequestPlanStatus,
    EODRevisionPolicy,
    default_eod_revision_policy,
    plan_eod_request_window,
)
from .providers import (
    EODProvider,
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRevisionStrategy,
    validate_eod_provider_request,
    validate_eod_provider_result,
)
from .schemas import (
    EOD_SCHEMA_VERSION,
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    EODDatasetKey,
    EODDateRange,
    EODStructuredWarning,
    EODUpdateRequest,
    EODUpdateResult,
    EODUpdateStatus,
    EODWarningSeverity,
    Market,
    Venue,
)
from .validation import EODValidationReport, eod_bar_identity, validate_eod_batch
from .versioning import (
    EOD_MANIFEST_SCHEMA_VERSION,
    EOD_PARQUET_FILE,
    EOD_POINTER_SCHEMA_VERSION,
    EODCurrentPointer,
    EODGenerationManifest,
    EODStoredGeneration,
    calculate_bytes_sha256,
    calculate_eod_content_sha256,
    calculate_file_sha256,
)

_REPOSITORY_EXPORTS = frozenset(
    {
        "EOD_PARQUET_COLUMNS",
        "EOD_PARQUET_SCHEMA",
        "EODFileRepository",
        "EODGenerationExistsError",
        "EODIntegrityError",
        "EODNoCurrentGenerationError",
        "EODRepositoryError",
        "EODUnsafePathError",
        "LocalEODFileRepository",
    }
)


def __getattr__(name: str) -> object:
    """Load repository exports only when a caller explicitly requests one."""

    if name not in _REPOSITORY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    repository_module = import_module(".repositories", __name__)
    value = getattr(repository_module, name)
    globals()[name] = value
    return value


__all__ = [
    "EOD_MANIFEST_SCHEMA_VERSION",
    "EOD_PARQUET_COLUMNS",
    "EOD_PARQUET_FILE",
    "EOD_PARQUET_SCHEMA",
    "EOD_POINTER_SCHEMA_VERSION",
    "EOD_SCHEMA_VERSION",
    "MARKET_TIMEZONE",
    "AdjustmentType",
    "AssetType",
    "BarFrequency",
    "EODBar",
    "EODCurrentPointer",
    "EODDatasetKey",
    "EODDateRange",
    "EODFileRepository",
    "EODGenerationExistsError",
    "EODGenerationManifest",
    "EODIntegrityError",
    "EODNoCurrentGenerationError",
    "EODProvider",
    "EODProviderCapability",
    "EODProviderError",
    "EODProviderErrorCode",
    "EODProviderRequest",
    "EODProviderResult",
    "EODProviderResultStatus",
    "EODRepositoryError",
    "EODRequestPlan",
    "EODRequestPlanningError",
    "EODRequestPlanningErrorCode",
    "EODRequestPlanStatus",
    "EODRevisionPolicy",
    "EODRevisionStrategy",
    "EODStoredGeneration",
    "EODStructuredWarning",
    "EODUpdateRequest",
    "EODUpdateResult",
    "EODUpdateStatus",
    "EODValidationReport",
    "EODWarningSeverity",
    "EODUnsafePathError",
    "LocalEODFileRepository",
    "Market",
    "TradingCalendar",
    "TradingCalendarContractError",
    "Venue",
    "calculate_bytes_sha256",
    "calculate_eod_content_sha256",
    "calculate_file_sha256",
    "default_eod_revision_policy",
    "eod_bar_identity",
    "normalize_canonical_symbol",
    "normalize_eod_bars",
    "plan_eod_request_window",
    "validate_eod_batch",
    "validate_eod_provider_request",
    "validate_eod_provider_result",
    "validate_trading_days",
]
