"""
鏁版嵁鍒嗘瀽妯″潡 - 璐熻矗鎶€鏈寚鏍囪绠楀拰鍩烘湰闈㈠垎鏋?"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """鎶€鏈垎鏋愬櫒"""

    @staticmethod
    def calculate_ma(data: pd.DataFrame, periods: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
        """璁＄畻绉诲姩骞冲潎绾?""
        df = data.copy()
        for period in periods:
            df[f"MA{period}"] = df["Close"].rolling(window=period).mean()
        return df

    @staticmethod
    def calculate_ema(data: pd.DataFrame, periods: List[int] = [12, 26]) -> pd.DataFrame:
        """璁＄畻鎸囨暟绉诲姩骞冲潎绾?""
        df = data.copy()
        for period in periods:
            df[f"EMA{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
        return df

    @staticmethod
    def calculate_macd(
        data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """璁＄畻MACD鎸囨爣"""
        df = data.copy()
        ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()

        df["MACD"] = ema_fast - ema_slow
        df["MACD_Signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]
        return df

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """璁＄畻RSI鎸囨爣"""
        df = data.copy()
        delta = df["Close"].diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        df["RSI"] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def calculate_bollinger_bands(
        data: pd.DataFrame, period: int = 20, std_dev: float = 2.0
    ) -> pd.DataFrame:
        """璁＄畻甯冩灄甯?""
        df = data.copy()
        df["BB_Middle"] = df["Close"].rolling(window=period).mean()
        bb_std = df["Close"].rolling(window=period).std()
        df["BB_Upper"] = df["BB_Middle"] + (bb_std * std_dev)
        df["BB_Lower"] = df["BB_Middle"] - (bb_std * std_dev)
        df["BB_Width"] = df["BB_Upper"] - df["BB_Lower"]
        df["BB_Position"] = (df["Close"] - df["BB_Lower"]) / (df["BB_Upper"] - df["BB_Lower"])
        return df

    @staticmethod
    def calculate_kdj(data: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
        """璁＄畻KDJ鎸囨爣"""
        df = data.copy()
        low_list = df["Low"].rolling(window=n, min_periods=n).min()
        high_list = df["High"].rolling(window=n, min_periods=n).max()
        rsv = (df["Close"] - low_list) / (high_list - low_list) * 100

        df["K"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        df["D"] = df["K"].ewm(com=m2 - 1, adjust=False).mean()
        df["J"] = 3 * df["K"] - 2 * df["D"]
        return df

    @staticmethod
    def calculate_volume_indicators(data: pd.DataFrame) -> pd.DataFrame:
        """璁＄畻鎴愪氦閲忔寚鏍?""
        df = data.copy()
        df["Volume_MA5"] = df["Volume"].rolling(window=5).mean()
        df["Volume_MA20"] = df["Volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_MA20"]
        return df

    @classmethod
    def full_analysis(cls, data: pd.DataFrame) -> pd.DataFrame:
        """鎵ц瀹屾暣鐨勬妧鏈垎鏋?""
        df = data.copy()
        df = cls.calculate_ma(df)
        df = cls.calculate_ema(df)
        df = cls.calculate_macd(df)
        df = cls.calculate_rsi(df)
        df = cls.calculate_bollinger_bands(df)
        df = cls.calculate_kdj(df)
        df = cls.calculate_volume_indicators(df)
        return df


class FundamentalAnalyzer:
    """鍩烘湰闈㈠垎鏋愬櫒"""

    @staticmethod
    def analyze_valuation(stock_info: Dict) -> Dict[str, float]:
        """鍒嗘瀽浼板€兼按骞?""
        pe = stock_info.get("pe_ratio", 0)
        pb = stock_info.get("pb_ratio", 0)
        dividend_yield = stock_info.get("dividend_yield", 0) or 0

        # 绠€鍗曠殑浼板€艰瘎鍒?(0-100)
        pe_score = max(0, min(100, 100 - pe * 2)) if pe > 0 else 50
        pb_score = max(0, min(100, 100 - pb * 15)) if pb > 0 else 50
        dividend_score = min(100, dividend_yield * 1000)

        return {
            "pe_ratio": pe,
            "pb_ratio": pb,
            "dividend_yield": dividend_yield,
            "pe_score": pe_score,
            "pb_score": pb_score,
            "dividend_score": dividend_score,
            "valuation_score": (pe_score + pb_score + dividend_score) / 3,
        }

    @staticmethod
    def analyze_growth(historical_data: pd.DataFrame) -> Dict[str, float]:
        """鍒嗘瀽鎴愰暱鎬?""
        if len(historical_data) < 60:
            return {"growth_score": 50, "trend": "unknown"}

        # 璁＄畻浠锋牸瓒嬪娍
        recent_price = historical_data["Close"].iloc[-1]
        price_1m_ago = historical_data["Close"].iloc[-20] if len(historical_data) >= 20 else historical_data["Close"].iloc[0]
        price_3m_ago = historical_data["Close"].iloc[-60] if len(historical_data) >= 60 else historical_data["Close"].iloc[0]

        return_1m = (recent_price - price_1m_ago) / price_1m_ago * 100
        return_3m = (recent_price - price_3m_ago) / price_3m_ago * 100

        # 瓒嬪娍鍒ゆ柇
        if return_1m > 5 and return_3m > 10:
            trend = "strong_uptrend"
        elif return_1m > 0:
            trend = "uptrend"
        elif return_1m < -5 and return_3m < -10:
            trend = "strong_downtrend"
        elif return_1m < 0:
            trend = "downtrend"
        else:
            trend = "sideways"

        # 鎴愰暱鎬ц瘎鍒?        growth_score = max(0, min(100, 50 + return_3m * 2))

        return {
            "return_1m": return_1m,
            "return_3m": return_3m,
            "trend": trend,
            "growth_score": growth_score,
        }

    @classmethod
    def full_fundamental_analysis(
        cls, stock_info: Dict, historical_data: pd.DataFrame
    ) -> Dict:
        """鎵ц瀹屾暣鐨勫熀鏈潰鍒嗘瀽"""
        valuation = cls.analyze_valuation(stock_info)
        growth = cls.analyze_growth(historical_data)

        return {
            "valuation": valuation,
            "growth": growth,
            "overall_score": (valuation["valuation_score"] + growth["growth_score"]) / 2,
        }
