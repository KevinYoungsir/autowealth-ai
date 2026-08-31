"""Pure contracts for AutoWealth China A-share EOD market data."""

from importlib import import_module
from types import MappingProxyType

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
_OPERATION_EXPORTS = frozenset(
    {
        "EOD_OPERATION_JOB_SCHEMA_VERSION",
        "EOD_OPERATION_SCHEMA_VERSION",
        "EODFullRefreshOperationPayload",
        "EODIncrementalBatchOperationPayload",
        "EODIncrementalSingleOperationPayload",
        "EODMaintenanceOperationPayload",
        "EODOperationExecutionContext",
        "EODOperationFailurePolicy",
        "EODOperationFailureSummary",
        "EODOperationJob",
        "EODOperationJobStatus",
        "EODOperationRequest",
        "EODOperationResultSummary",
        "EODOperationSubmission",
        "EODOperationSubmissionStatus",
        "EODOperationType",
        "generate_eod_operation_job_id",
        "validate_eod_operation_job_id",
        "validate_operation_fingerprint",
        "validate_worker_id",
    }
)
_OPERATION_CONTROL_EXPORTS = frozenset(
    {
        "EODCheckpointStage",
        "EODLeaseControlState",
        "EODOperationControlError",
        "EODOperationWorkerConfig",
        "eod_calendar_identity",
        "eod_generation_id",
    }
)
_OPERATION_CATALOG_EXPORTS = frozenset(
    {
        "EODOperationCatalog",
        "EODOperationCatalogEntry",
        "EODOperationCatalogError",
        "EODOperationCatalogErrorCode",
        "build_eod_operation_catalog",
    }
)
_OPERATION_WORKER_EXPORTS = frozenset(
    {"EODOperationWorker", "EODOperationWorkerResult", "EODOperationWorkerStatus"}
)

_OPERATION_JOB_REPOSITORY_EXPORTS = frozenset(
    {
        "EOD_OPERATION_BUSY_TIMEOUT_MILLISECONDS",
        "EOD_OPERATION_DATABASE_NAME",
        "EOD_OPERATION_PERSISTENCE_SCHEMA_VERSION",
        "EODOperationJobRepository",
        "EODOperationJobRepositoryError",
        "EODOperationJobRepositoryErrorCode",
        "EODOperationRepositoryHealth",
        "EODOperationRepositoryHealthStatus",
        "LocalEODOperationJobRepository",
        "MAX_EOD_JOB_ALIASES",
        "MAX_EOD_JOB_LIST_LIMIT",
    }
)

_LAZY_EXPORT_MODULES = MappingProxyType(
    {
        **{name: ".repositories" for name in _REPOSITORY_EXPORTS},
        **{name: ".operations" for name in _OPERATION_EXPORTS},
        **{name: ".job_repository" for name in _OPERATION_JOB_REPOSITORY_EXPORTS},
        **{name: ".operation_control" for name in _OPERATION_CONTROL_EXPORTS},
        **{name: ".operation_catalog" for name in _OPERATION_CATALOG_EXPORTS},
        **{name: ".operation_worker" for name in _OPERATION_WORKER_EXPORTS},
        **{
            name: ".local_calendar"
            for name in (
                "EOD_CALENDAR_SCHEMA_VERSION",
                "LocalTradingCalendarError",
                "LocalTradingCalendarErrorCode",
                "LocalTradingCalendarIdentity",
                "VersionedLocalTradingCalendar",
            )
        },
        **{
            name: ".batch"
            for name in (
                "EODBatchCoordinator",
                "EODBatchDatasetFailure",
                "EODBatchDatasetRequest",
                "EODBatchDatasetResult",
                "EODBatchDatasetStatus",
                "EODBatchFailurePolicy",
                "EODBatchFailureSource",
                "EODBatchRequest",
                "EODBatchResult",
                "EODBatchStatus",
                "EODBatchValidationError",
                "EODBatchValidationErrorCode",
                "EODDatasetLockManager",
                "InProcessEODDatasetLockManager",
                "MAX_EOD_BATCH_DATASETS",
                "eod_dataset_lock_key",
            )
        },
        **{
            name: ".maintenance"
            for name in (
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
            )
        },
        **{
            name: ".composition"
            for name in (
                "EODCompositionError",
                "EODCompositionErrorCode",
                "EODProductionConfig",
                "EODRuntimeStack",
                "EOD_PRODUCTION_CONFIG_SCHEMA_VERSION",
                "build_eod_batch_coordinator",
                "build_eod_full_refresh_executor",
                "build_eod_repository_maintenance_executor",
                "build_eod_runtime",
                "load_eod_production_config",
            )
        },
        **{
            name: ".coordinator"
            for name in (
                "EODIncrementalCoordinator",
                "EODIncrementalCoordinatorError",
                "EODIncrementalCoordinatorErrorCode",
                "EODIncrementalUpdateResult",
                "EODIncrementalUpdateStatus",
            )
        },
        **{
            name: ".full_refresh"
            for name in (
                "EODFullRefreshErrorCode",
                "EODFullRefreshExecutor",
                "EODFullRefreshExecutorError",
                "EODFullRefreshRequest",
                "EODFullRefreshResult",
                "EODFullRefreshStatus",
            )
        },
        "AKShareEODEquityProvider": ".akshare_adapters",
        "AKShareEODIndexDailyProvider": ".akshare_adapters",
        "AKShareEODIndexProvider": ".akshare_adapters",
        "akshare_equity_symbol": ".akshare_adapters",
        "akshare_index_daily_symbol": ".akshare_adapters",
        "akshare_index_symbol": ".akshare_adapters",
        "convert_eod_dataframe_to_bars": ".dataframe_conversion",
        "EODProviderAttempt": ".provider_chain",
        "EODProviderChain": ".provider_chain",
        "EODProviderChainError": ".provider_chain",
        "EODProviderChainResult": ".provider_chain",
        "EODProviderInvocation": ".provider_chain",
        **{
            name: ".provider_resilience"
            for name in (
                "EODMonotonicClock",
                "EODProviderRateLimitPolicy",
                "EODProviderRateLimiter",
                "EODProviderRetryPolicy",
                "EODRetrySleeper",
                "MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER",
                "MAX_EOD_PROVIDER_DELAY_SECONDS",
                "MinimumIntervalEODProviderRateLimiter",
                "NoOpEODProviderRateLimiter",
                "SystemEODMonotonicClock",
                "SystemEODRetrySleeper",
            )
        },
    }
)


def __getattr__(name: str) -> object:
    """Load optional public exports only when a caller explicitly requests one."""

    module_name = _LAZY_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    target_module = import_module(module_name, __name__)
    value = getattr(target_module, name)
    globals()[name] = value
    return value


__all__ = [
    "EOD_MANIFEST_SCHEMA_VERSION",
    "EOD_CALENDAR_SCHEMA_VERSION",
    "EOD_PARQUET_COLUMNS",
    "EOD_PARQUET_FILE",
    "EOD_PARQUET_SCHEMA",
    "EOD_POINTER_SCHEMA_VERSION",
    "EOD_SCHEMA_VERSION",
    "MARKET_TIMEZONE",
    "AKShareEODEquityProvider",
    "AKShareEODIndexDailyProvider",
    "AKShareEODIndexProvider",
    "AdjustmentType",
    "AssetType",
    "BarFrequency",
    "EODBatchCoordinator",
    "EODBatchDatasetFailure",
    "EODBatchDatasetRequest",
    "EODBatchDatasetResult",
    "EODBatchDatasetStatus",
    "EODBatchFailurePolicy",
    "EODBatchFailureSource",
    "EODBatchRequest",
    "EODBatchResult",
    "EODBatchStatus",
    "EODBatchValidationError",
    "EODBatchValidationErrorCode",
    "EODBar",
    "EODCurrentPointer",
    "EODCompositionError",
    "EODCompositionErrorCode",
    "EODDatasetKey",
    "EODDateRange",
    "EODDatasetLockManager",
    "EODFileRepository",
    "EODGenerationExistsError",
    "EODGenerationManifest",
    "EODFullRefreshErrorCode",
    "EODFullRefreshExecutor",
    "EODFullRefreshExecutorError",
    "EODFullRefreshRequest",
    "EODFullRefreshResult",
    "EODFullRefreshStatus",
    "EODIntegrityError",
    "EODIncrementalCoordinator",
    "EODIncrementalCoordinatorError",
    "EODIncrementalCoordinatorErrorCode",
    "EODIncrementalUpdateResult",
    "EODIncrementalUpdateStatus",
    "EODNoCurrentGenerationError",
    "EODProvider",
    "EODProviderAttempt",
    "EODProviderCapability",
    "EODProviderChain",
    "EODProviderChainError",
    "EODProviderChainResult",
    "EODProviderInvocation",
    "EODProviderRateLimitPolicy",
    "EODProviderRateLimiter",
    "EODProviderRetryPolicy",
    "EODProviderError",
    "EODProviderErrorCode",
    "EODProviderRequest",
    "EODProviderResult",
    "EODProviderResultStatus",
    "EODProductionConfig",
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
    "EODRepositoryError",
    "EODRequestPlan",
    "EODRequestPlanningError",
    "EODRequestPlanningErrorCode",
    "EODRequestPlanStatus",
    "EODRevisionPolicy",
    "EODRevisionStrategy",
    "EODRuntimeStack",
    "EODRetrySleeper",
    "EODStoredGeneration",
    "EODStructuredWarning",
    "EODUpdateRequest",
    "EODUpdateResult",
    "EODUpdateStatus",
    "EODValidationReport",
    "EODWarningSeverity",
    "EOD_PRODUCTION_CONFIG_SCHEMA_VERSION",
    "EODUnsafePathError",
    "LocalEODFileRepository",
    "LocalTradingCalendarError",
    "LocalTradingCalendarErrorCode",
    "LocalTradingCalendarIdentity",
    "Market",
    "MAX_EOD_BATCH_DATASETS",
    "MAX_EOD_GENERATION_LINEAGE_DEPTH",
    "MAX_EOD_REPOSITORY_MAINTENANCE_ARTIFACTS",
    "MAX_EOD_PROVIDER_ATTEMPTS_PER_PROVIDER",
    "MAX_EOD_PROVIDER_DELAY_SECONDS",
    "MinimumIntervalEODProviderRateLimiter",
    "NoOpEODProviderRateLimiter",
    "TradingCalendar",
    "TradingCalendarContractError",
    "Venue",
    "VersionedLocalTradingCalendar",
    "EODMonotonicClock",
    "InProcessEODDatasetLockManager",
    "build_eod_batch_coordinator",
    "build_eod_full_refresh_executor",
    "build_eod_repository_maintenance_executor",
    "build_eod_runtime",
    "calculate_bytes_sha256",
    "calculate_eod_content_sha256",
    "calculate_file_sha256",
    "convert_eod_dataframe_to_bars",
    "default_eod_revision_policy",
    "eod_bar_identity",
    "eod_dataset_lock_key",
    "normalize_canonical_symbol",
    "normalize_eod_bars",
    "load_eod_production_config",
    "akshare_equity_symbol",
    "akshare_index_daily_symbol",
    "akshare_index_symbol",
    "plan_eod_request_window",
    "validate_eod_batch",
    "validate_eod_provider_request",
    "validate_eod_provider_result",
    "validate_trading_days",
    "SystemEODMonotonicClock",
    "SystemEODRetrySleeper",
]
__all__.extend(
    sorted(
        _OPERATION_EXPORTS
        | _OPERATION_JOB_REPOSITORY_EXPORTS
        | _OPERATION_CONTROL_EXPORTS
        | _OPERATION_CATALOG_EXPORTS
        | _OPERATION_WORKER_EXPORTS
    )
)
