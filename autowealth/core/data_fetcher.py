"""
数据获取模块 - 负责从各种数据源获取金融数据
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from autowealth.config.settings import get_settings

logger = logging.getLogger(__name__)


class DataFetcher:
    """金融数据获取器"""

    def __init__(self):
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.data_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_stock_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """
        获取股票数据

        Args:
            symbol: 股票代码 (如: AAPL, 600519.SS)
            period: 时间周期 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 时间间隔 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            use_cache: 是否使用缓存

        Returns:
            DataFrame包含OHLCV数据
        """
        cache_file = self.cache_dir / f"{symbol}_{period}_{interval}.csv"

        # 检查缓存
        if use_cache and cache_file.exists():
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - cache_time < timedelta(hours=1):
                logger.info(f"使用缓存数据: {symbol}")
                return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        try:
            logger.info(f"获取股票数据: {symbol}")
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)

            if data.empty:
                raise ValueError(f"无法获取 {symbol} 的数据")

            # 保存缓存
            if use_cache:
                data.to_csv(cache_file)

            return data

        except Exception as e:
            logger.error(f"获取 {symbol} 数据失败: {e}")
            raise

    def get_multiple_stocks(
        self,
        symbols: List[str],
        period: str = "1y",
        interval: str = "1d",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量获取多只股票数据

        Args:
            symbols: 股票代码列表
            period: 时间周期
            interval: 时间间隔

        Returns:
            字典，key为股票代码，value为DataFrame
        """
        results = {}
        for symbol in symbols:
            try:
                data = self.get_stock_data(symbol, period, interval)
                results[symbol] = data
            except Exception as e:
                logger.warning(f"跳过 {symbol}: {e}")
                continue

        return results

    def get_market_indices(self, region: str = "global") -> Dict[str, pd.DataFrame]:
        """
        获取主要市场指数数据

        Args:
            region: 地区 (global, us, cn, eu)

        Returns:
            指数数据字典
        """
        indices_map = {
            "global": ["^GSPC", "^DJI", "^IXIC", "^FTSE", "^N225", "000001.SS", "^HSI"],
            "us": ["^GSPC", "^DJI", "^IXIC", "^RUT"],
            "cn": ["000001.SS", "399001.SZ", "000300.SS", "000688.SH"],
            "eu": ["^FTSE", "^GDAXI", "^FCHI", "^STOXX50E"],
        }

        symbols = indices_map.get(region, indices_map["global"])
        return self.get_multiple_stocks(symbols, period="6mo")

    def get_stock_info(self, symbol: str) -> Dict:
        """
        获取股票基本信息

        Args:
            symbol: 股票代码

        Returns:
            股票信息字典
        """
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "name": info.get("longName", "N/A"),
                "sector": info.get("sector", "N/A"),
                "industry": info.get("industry", "N/A"),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "pb_ratio": info.get("priceToBook", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),
                "average_volume": info.get("averageVolume", 0),
                "website": info.get("website", "N/A"),
                "description": info.get("longBusinessSummary", "N/A"),
            }

        except Exception as e:
            logger.error(f"获取 {symbol} 信息失败: {e}")
            return {"symbol": symbol, "error": str(e)}

    def clear_cache(self):
        """清除所有缓存数据"""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("缓存已清除")
