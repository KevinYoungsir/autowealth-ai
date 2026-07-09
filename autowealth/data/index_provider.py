"""
A 股主要指数日线行情数据提供者。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from autowealth.data.schema import normalize_date, normalize_market_data


class AShareIndexProvider:
    """
    Fetch major A 股 index daily bars from AKShare.
    """

    INDEX_SYMBOLS = {
        "上证指数": "000001",
        "深证成指": "399001",
        "沪深300": "000300",
        "沪深 300": "000300",
        "中证500": "000905",
        "中证 500": "000905",
        "中证1000": "000852",
        "中证 1000": "000852",
        "创业板指": "399006",
        "000001": "000001",
        "399001": "399001",
        "000300": "000300",
        "000905": "000905",
        "000852": "000852",
        "399006": "399006",
    }

    def __init__(self, akshare_module: Optional[object] = None):
        if akshare_module is not None:
            self.ak = akshare_module
            return

        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError("AShareIndexProvider requires akshare: pip install akshare") from exc

        self.ak = ak

    def get_daily(self, index: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch daily historical data for a supported A 股 index.
        """
        symbol = self.resolve_symbol(index)
        raw = self.ak.index_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=normalize_date(start_date),
            end_date=normalize_date(end_date),
        )
        return normalize_market_data(raw)

    @classmethod
    def resolve_symbol(cls, index: str) -> str:
        key = str(index).strip()
        if key not in cls.INDEX_SYMBOLS:
            supported = ", ".join(sorted(cls.INDEX_SYMBOLS))
            raise ValueError(f"Unsupported A 股 index: {index}. Supported values: {supported}")
        return cls.INDEX_SYMBOLS[key]

