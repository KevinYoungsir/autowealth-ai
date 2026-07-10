"""
A 股研究数据层。

该包只提供只读数据获取、字段标准化、本地缓存和质量检查能力。
"""

from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.cache import ParquetCache
from autowealth.data.fundamental_provider import (
    AShareFundamentalProvider,
    FundamentalDataProvider,
    FundamentalProviderResult,
)
from autowealth.data.fundamental_schema import (
    FUNDAMENTAL_COLUMNS,
    FundamentalRecord,
    eligible_fundamentals_asof,
    latest_fundamental_asof,
    normalize_fundamental_data,
)
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.quality import DataQualityReport, check_price_quality
from autowealth.data.schema import MARKET_DATA_COLUMNS, normalize_market_data
from autowealth.data.universe import (
    FixedStockUniverse,
    HistoricalUniverseProvider,
    UniverseSnapshot,
)

__all__ = [
    "AShareDataProvider",
    "AShareFundamentalProvider",
    "AShareIndexProvider",
    "DataQualityReport",
    "FUNDAMENTAL_COLUMNS",
    "FixedStockUniverse",
    "FundamentalDataProvider",
    "FundamentalProviderResult",
    "FundamentalRecord",
    "HistoricalUniverseProvider",
    "MARKET_DATA_COLUMNS",
    "ParquetCache",
    "UniverseSnapshot",
    "check_price_quality",
    "eligible_fundamentals_asof",
    "latest_fundamental_asof",
    "normalize_fundamental_data",
    "normalize_market_data",
]
