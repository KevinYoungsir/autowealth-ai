"""Pure contracts for AutoWealth China A-share EOD market data."""

from .calendar import (
    MARKET_TIMEZONE,
    TradingCalendar,
    TradingCalendarContractError,
    validate_trading_days,
)
from .normalization import normalize_canonical_symbol, normalize_eod_bars
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

__all__ = [
    "EOD_SCHEMA_VERSION",
    "MARKET_TIMEZONE",
    "AdjustmentType",
    "AssetType",
    "BarFrequency",
    "EODBar",
    "EODDatasetKey",
    "EODDateRange",
    "EODStructuredWarning",
    "EODUpdateRequest",
    "EODUpdateResult",
    "EODUpdateStatus",
    "EODValidationReport",
    "EODWarningSeverity",
    "Market",
    "TradingCalendar",
    "TradingCalendarContractError",
    "Venue",
    "eod_bar_identity",
    "normalize_canonical_symbol",
    "normalize_eod_bars",
    "validate_eod_batch",
    "validate_trading_days",
]
