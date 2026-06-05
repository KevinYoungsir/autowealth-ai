"""
Twelve Data 数据源 - 提供真实美股/全球股票数据
免费版: 每天800次API调用, 无需信用卡
注册: https://twelvedata.com/pricing (免费获取API Key)
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class TwelveDataSource:
    """Twelve Data API 数据源"""

    BASE_URL = "https://api.twelvedata.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or "demo"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AutoWealth-AI/1.0",
            "Accept": "application/json",
        })

    def get_stock_data(
        self,
        symbol: str,
        period: str = "1y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        获取股票历史数据

        Args:
            symbol: 股票代码 (如 AAPL, MSFT, TSLA)
            period: 时间周期 (1mo, 3mo, 6mo, 1y, 2y, 5y, 10y)
            interval: 时间间隔 (1min, 5min, 15min, 30min, 1h, 1day, 1week, 1month)

        Returns:
            DataFrame包含OHLCV数据
        """
        # 将period转换为outputsize
        period_map = {
            "1mo": 22,
            "3mo": 66,
            "6mo": 132,
            "1y": 252,
            "2y": 504,
            "5y": 1260,
            "10y": 2520,
        }
        outputsize = period_map.get(period, 252)

        # 将interval转换为Twelve Data格式
        interval_map = {
            "1d": "1day",
            "1wk": "1week",
            "1mo": "1month",
        }
        td_interval = interval_map.get(interval, "1day")

        params = {
            "symbol": symbol,
            "interval": td_interval,
            "apikey": self.api_key,
            "outputsize": outputsize,
            "format": "JSON",
        }

        logger.info(f"从Twelve Data获取数据: {symbol}, period={period}")

        try:
            response = self.session.get(
                f"{self.BASE_URL}/time_series",
                params=params,
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            # 检查错误
            if data.get("status") == "error":
                error_msg = data.get("message", "Unknown error")
                if "demo" in error_msg.lower():
                    raise ValueError(
                        f"Twelve Data demo key限制: {error_msg}\n"
                        f"请访问 https://twelvedata.com/pricing 注册免费API Key"
                    )
                raise ValueError(f"Twelve Data API错误: {error_msg}")

            values = data.get("values", [])
            if not values:
                raise ValueError(f"Twelve Data返回空数据: {symbol}")

            # 转换为DataFrame
            records = []
            for v in values:
                records.append({
                    "Date": v["datetime"],
                    "Open": float(v["open"]),
                    "High": float(v["high"]),
                    "Low": float(v["low"]),
                    "Close": float(v["close"]),
                    "Volume": int(v["volume"]),
                })

            df = pd.DataFrame(records)
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()

            logger.info(f"Twelve Data返回 {len(df)} 行数据: {symbol}")
            return df

        except requests.exceptions.RequestException as e:
            logger.error(f"Twelve Data请求失败: {e}")
            raise

    def get_stock_info(self, symbol: str) -> Dict:
        """
        获取股票基本信息

        Args:
            symbol: 股票代码

        Returns:
            股票信息字典
        """
        params = {
            "symbol": symbol,
            "apikey": self.api_key,
        }

        try:
            response = self.session.get(
                f"{self.BASE_URL}/quote",
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "error":
                logger.warning(f"Twelve Data quote失败: {data.get('message')}")
                return {"symbol": symbol, "name": symbol}

            return {
                "symbol": symbol,
                "name": data.get("name", symbol),
                "exchange": data.get("exchange", "N/A"),
                "currency": data.get("currency", "USD"),
                "type": data.get("type", "N/A"),
                "close": float(data.get("close", 0)),
                "change": float(data.get("change", 0)),
                "percent_change": float(data.get("percent_change", 0)),
                "volume": int(data.get("volume", 0)),
                "fifty_two_week_high": float(data.get("fifty_two_week_high", 0)),
                "fifty_two_week_low": float(data.get("fifty_two_week_low", 0)),
            }

        except Exception as e:
            logger.error(f"获取Twelve Data股票信息失败: {e}")
            return {"symbol": symbol, "name": symbol}

    def is_available(self) -> bool:
        """检查API是否可用"""
        try:
            params = {
                "symbol": "AAPL",
                "interval": "1day",
                "apikey": self.api_key,
                "outputsize": 1,
            }
            response = self.session.get(
                f"{self.BASE_URL}/time_series",
                params=params,
                timeout=10,
            )
            data = response.json()
            return data.get("status") != "error" or "demo" not in data.get("message", "").lower()
        except Exception:
            return False
