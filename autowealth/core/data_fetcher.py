"""
鏁版嵁鑾峰彇妯″潡 - 璐熻矗浠庡悇绉嶆暟鎹簮鑾峰彇閲戣瀺鏁版嵁
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
    """閲戣瀺鏁版嵁鑾峰彇鍣?""

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
        鑾峰彇鑲＄エ鏁版嵁

        Args:
            symbol: 鑲＄エ浠ｇ爜 (濡? AAPL, 600519.SS)
            period: 鏃堕棿鍛ㄦ湡 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
            interval: 鏃堕棿闂撮殧 (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
            use_cache: 鏄惁浣跨敤缂撳瓨

        Returns:
            DataFrame鍖呭惈OHLCV鏁版嵁
        """
        cache_file = self.cache_dir / f"{symbol}_{period}_{interval}.csv"

        # 妫€鏌ョ紦瀛?        if use_cache and cache_file.exists():
            cache_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - cache_time < timedelta(hours=1):
                logger.info(f"浣跨敤缂撳瓨鏁版嵁: {symbol}")
                return pd.read_csv(cache_file, index_col=0, parse_dates=True)

        try:
            logger.info(f"鑾峰彇鑲＄エ鏁版嵁: {symbol}")
            ticker = yf.Ticker(symbol)
            data = ticker.history(period=period, interval=interval)

            if data.empty:
                raise ValueError(f"鏃犳硶鑾峰彇 {symbol} 鐨勬暟鎹?)

            # 淇濆瓨缂撳瓨
            if use_cache:
                data.to_csv(cache_file)

            return data

        except Exception as e:
            logger.error(f"鑾峰彇 {symbol} 鏁版嵁澶辫触: {e}")
            raise

    def get_multiple_stocks(
        self,
        symbols: List[str],
        period: str = "1y",
        interval: str = "1d",
    ) -> Dict[str, pd.DataFrame]:
        """
        鎵归噺鑾峰彇澶氬彧鑲＄エ鏁版嵁

        Args:
            symbols: 鑲＄エ浠ｇ爜鍒楄〃
            period: 鏃堕棿鍛ㄦ湡
            interval: 鏃堕棿闂撮殧

        Returns:
            瀛楀吀锛宬ey涓鸿偂绁ㄤ唬鐮侊紝value涓篋ataFrame
        """
        results = {}
        for symbol in symbols:
            try:
                data = self.get_stock_data(symbol, period, interval)
                results[symbol] = data
            except Exception as e:
                logger.warning(f"璺宠繃 {symbol}: {e}")
                continue

        return results

    def get_market_indices(self, region: str = "global") -> Dict[str, pd.DataFrame]:
        """
        鑾峰彇涓昏甯傚満鎸囨暟鏁版嵁

        Args:
            region: 鍦板尯 (global, us, cn, eu)

        Returns:
            鎸囨暟鏁版嵁瀛楀吀
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
        鑾峰彇鑲＄エ鍩烘湰淇℃伅

        Args:
            symbol: 鑲＄エ浠ｇ爜

        Returns:
            鑲＄エ淇℃伅瀛楀吀
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
            logger.error(f"鑾峰彇 {symbol} 淇℃伅澶辫触: {e}")
            return {"symbol": symbol, "error": str(e)}

    def clear_cache(self):
        """娓呴櫎鎵€鏈夌紦瀛樻暟鎹?""
        import shutil

        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("缂撳瓨宸叉竻闄?)
