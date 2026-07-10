"""
Local parquet cache for market data.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import pandas as pd

from autowealth.data.schema import normalize_adjust, normalize_date


PathLike = Union[str, Path]


class ParquetCache:
    """
    Store and load normalized market data as parquet files.
    """

    def __init__(self, cache_dir: PathLike = "data/cache"):
        self.cache_dir = Path(cache_dir)

    def path_for(self, symbol: str, start_date: str, end_date: str, adjust: str = "none") -> Path:
        safe_symbol = self._safe_part(symbol)
        start = normalize_date(start_date)
        end = normalize_date(end_date)
        safe_adjust = normalize_adjust(adjust)
        return self.cache_dir / f"{safe_symbol}_{start}_{end}_{safe_adjust}.parquet"

    def exists(self, symbol: str, start_date: str, end_date: str, adjust: str = "none") -> bool:
        return self.path_for(symbol, start_date, end_date, adjust).exists()

    def read(self, symbol: str, start_date: str, end_date: str, adjust: str = "none") -> pd.DataFrame:
        path = self.path_for(symbol, start_date, end_date, adjust)
        return pd.read_parquet(path)

    def write(
        self,
        df: pd.DataFrame,
        symbol: str,
        start_date: str,
        end_date: str,
        adjust: str = "none",
    ) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.path_for(symbol, start_date, end_date, adjust)
        df.to_parquet(path, index=False)
        return path

    @staticmethod
    def _safe_part(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value).strip())

