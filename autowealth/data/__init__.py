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
from autowealth.data.index_provider import (
    AKShareIndexDailyProvider,
    AShareIndexProvider,
    IndexDataProvider,
    canonical_index_symbol,
)
from autowealth.data.index_provider_chain import (
    BenchmarkLoadResult,
    IndexProviderChain,
    ProviderAttempt,
    load_benchmark_with_cache,
)
from autowealth.data.index_quality import BenchmarkQualityResult, validate_benchmark_data
from autowealth.data.quality import DataQualityReport, check_price_quality
from autowealth.data.schema import MARKET_DATA_COLUMNS, normalize_market_data
from autowealth.data.universe import (
    FixedStockUniverse,
    HistoricalUniverseProvider,
    UniverseSnapshot,
)

__all__ = [
    "AKShareIndexDailyProvider",
    "AShareDataProvider",
    "AShareFundamentalProvider",
    "AShareIndexProvider",
    "BenchmarkLoadResult",
    "BenchmarkQualityResult",
    "DataQualityReport",
    "FUNDAMENTAL_COLUMNS",
    "FixedStockUniverse",
    "FundamentalDataProvider",
    "FundamentalProviderResult",
    "FundamentalRecord",
    "HistoricalUniverseProvider",
    "IndexDataProvider",
    "IndexProviderChain",
    "MARKET_DATA_COLUMNS",
    "ParquetCache",
    "ProviderAttempt",
    "UniverseSnapshot",
    "check_price_quality",
    "canonical_index_symbol",
    "eligible_fundamentals_asof",
    "latest_fundamental_asof",
    "load_benchmark_with_cache",
    "normalize_fundamental_data",
    "normalize_market_data",
    "validate_benchmark_data",
]
