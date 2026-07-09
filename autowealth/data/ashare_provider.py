"""
A 股日线行情数据提供者。
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from autowealth.data.schema import akshare_adjust, normalize_date, normalize_market_data


class AShareDataProvider:
    """
    Fetch A 股 historical daily bars from AKShare.

    The provider uses explicit ``start_date`` and ``end_date`` parameters, so it
    can request 15+ years of history and does not rely on fixed 1y/5y/10y modes.
    """

    def __init__(self, akshare_module: Optional[object] = None):
        if akshare_module is not None:
            self.ak = akshare_module
            return

        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError("AShareDataProvider requires akshare: pip install akshare") from exc

        self.ak = ak

    def get_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """
        Fetch daily historical data for an A 股 stock.

        Args:
            symbol: Stock code, e.g. ``600519``, ``600519.SH`` or ``000001.SZ``.
            start_date: ``YYYYMMDD`` or ``YYYY-MM-DD``.
            end_date: ``YYYYMMDD`` or ``YYYY-MM-DD``.
            adjust: ``qfq``, ``hfq`` or ``none``.
        """
        clean_symbol = self._clean_symbol(symbol)
        start = normalize_date(start_date)
        end = normalize_date(end_date)

        raw = self.ak.stock_zh_a_hist(
            symbol=clean_symbol,
            period="daily",
            start_date=start,
            end_date=end,
            adjust=akshare_adjust(adjust),
        )
        return normalize_market_data(raw)

    @staticmethod
    def _clean_symbol(symbol: str) -> str:
        clean = str(symbol).strip().upper()
        for suffix in (".SH", ".SS", ".SZ", ".BJ"):
            clean = clean.replace(suffix, "")
        return clean

