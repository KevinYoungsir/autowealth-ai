"""
A 股研究数据层。

该包只提供只读数据获取、字段标准化、本地缓存和质量检查能力。
"""

from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.cache import ParquetCache
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.quality import DataQualityReport, check_price_quality
from autowealth.data.schema import MARKET_DATA_COLUMNS, normalize_market_data

__all__ = [
    "AShareDataProvider",
    "AShareIndexProvider",
    "DataQualityReport",
    "MARKET_DATA_COLUMNS",
    "ParquetCache",
    "check_price_quality",
    "normalize_market_data",
]

