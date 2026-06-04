"""
数据分析模块 - 负责技术指标计算和基本面分析
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:
    """技术分析器"""

    @staticmethod
    def calculate_ma(data: pd.DataFrame, periods: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
        """计算移动平均线"""
        df = data.copy()
        for period in periods:
            df[f"MA{period}"] = df["Close"].rolling(window=period).mean()
        return df

    @staticmethod
    def calculate_ema(data: pd.DataFrame, periods: List[int] = [12, 26]) -> pd.DataFrame:
        """计算指数移动平均线"""
        df = data.copy()
        for period in periods:
            df[f"EMA{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
        return df

    @staticmethod
    def calculate_macd(
        data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9
    ) -> pd.DataFrame:
        """计算MACD指标"""
        df = data.copy()
        ema_fast = df["Close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["Close"].ewm(span=slow, adjust=False).mean()

        df["MACD"] = ema_fast - ema_slow
        df["MACD_Signal"] = df["MACD"].ewm(span=signal, adjust=False).mean()
        df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]
        return df

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算RSI指标"""
        df = data.copy()
        delta = df["Close"].diff()

        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss.replace(0, 1e-10)
        df["RSI"] = 100 - (100 / (1 + rs))
        return df

    @staticmethod
    def calculate_bollinger_bands(
        data: pd.DataFrame, period: int = 20, std_dev: float = 2.0
    ) -> pd.DataFrame:
        """计算布林带"""
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
        """计算KDJ指标"""
        df = data.copy()
        low_list = df["Low"].rolling(window=n, min_periods=n).min()
        high_list = df["High"].rolling(window=n, min_periods=n).max()
        price_range = high_list - low_list
        price_range = price_range.replace(0, 1e-10)
        rsv = (df["Close"] - low_list) / price_range * 100

        df["K"] = rsv.ewm(com=m1 - 1, adjust=False).mean()
        df["D"] = df["K"].ewm(com=m2 - 1, adjust=False).mean()
        df["J"] = 3 * df["K"] - 2 * df["D"]
        return df

    @staticmethod
    def calculate_volume_indicators(data: pd.DataFrame) -> pd.DataFrame:
        """计算成交量指标"""
        df = data.copy()
        df["Volume_MA5"] = df["Volume"].rolling(window=5).mean()
        df["Volume_MA20"] = df["Volume"].rolling(window=20).mean()
        df["Volume_Ratio"] = df["Volume"] / df["Volume_MA20"]
        return df

    @staticmethod
    def calculate_obv(data: pd.DataFrame) -> pd.DataFrame:
        """计算OBV能量潮指标"""
        df = data.copy()
        close_diff = df["Close"].diff()
        obv = pd.Series(0, index=df.index)
        obv.iloc[0] = df["Volume"].iloc[0]
        for i in range(1, len(df)):
            if close_diff.iloc[i] > 0:
                obv.iloc[i] = obv.iloc[i - 1] + df["Volume"].iloc[i]
            elif close_diff.iloc[i] < 0:
                obv.iloc[i] = obv.iloc[i - 1] - df["Volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]
        df["OBV"] = obv
        return df

    @staticmethod
    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算ATR真实波幅"""
        df = data.copy()
        high_low = df["High"] - df["Low"]
        high_close = (df["High"] - df["Close"].shift()).abs()
        low_close = (df["Low"] - df["Close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["TR"] = tr
        df[f"ATR{period}"] = tr.rolling(window=period).mean()
        return df

    @staticmethod
    def calculate_dmi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算DMI趋向指标（+DI, -DI, ADX）"""
        df = data.copy()
        high_diff = df["High"].diff()
        low_diff = -df["Low"].diff()

        plus_dm = ((high_diff > low_diff) & (high_diff > 0)) * high_diff
        minus_dm = ((low_diff > high_diff) & (low_diff > 0)) * low_diff

        tr = pd.concat([
            df["High"] - df["Low"],
            (df["High"] - df["Close"].shift()).abs(),
            (df["Low"] - df["Close"].shift()).abs(),
        ], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        atr = atr.replace(0, 1e-10)

        plus_di = 100 * plus_dm.rolling(window=period).mean() / atr
        minus_di = 100 * minus_dm.rolling(window=period).mean() / atr

        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10) * 100
        adx = dx.rolling(window=period).mean()

        df["+DI"] = plus_di
        df["-DI"] = minus_di
        df["ADX"] = adx
        return df

    @staticmethod
    def calculate_cci(data: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """计算CCI顺势指标"""
        df = data.copy()
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        ma_tp = tp.rolling(window=period).mean()
        md = tp.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
        md = md.replace(0, 1e-10)
        df[f"CCI{period}"] = (tp - ma_tp) / (0.015 * md)
        return df

    @staticmethod
    def calculate_wr(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """计算WR威廉指标"""
        df = data.copy()
        highest_high = df["High"].rolling(window=period).max()
        lowest_low = df["Low"].rolling(window=period).min()
        price_range = (highest_high - lowest_low).replace(0, 1e-10)
        df[f"WR{period}"] = (highest_high - df["Close"]) / price_range * -100
        return df

    @staticmethod
    def calculate_psy(data: pd.DataFrame, period: int = 12) -> pd.DataFrame:
        """计算PSY心理线"""
        df = data.copy()
        up_days = (df["Close"].diff() > 0).rolling(window=period).sum()
        df[f"PSY{period}"] = up_days / period * 100
        return df

    @classmethod
    def full_analysis(cls, data: pd.DataFrame) -> pd.DataFrame:
        """执行完整的技术分析"""
        df = data.copy()
        df = cls.calculate_ma(df)
        df = cls.calculate_ema(df)
        df = cls.calculate_macd(df)
        df = cls.calculate_rsi(df)
        df = cls.calculate_bollinger_bands(df)
        df = cls.calculate_kdj(df)
        df = cls.calculate_volume_indicators(df)
        df = cls.calculate_obv(df)
        df = cls.calculate_atr(df)
        df = cls.calculate_dmi(df)
        df = cls.calculate_cci(df)
        df = cls.calculate_wr(df)
        df = cls.calculate_psy(df)
        return df


class FundamentalAnalyzer:
    """基本面分析器"""

    @staticmethod
    def analyze_valuation(stock_info: Dict) -> Dict[str, float]:
        """分析估值水平"""
        pe = stock_info.get("pe_ratio", 0)
        pb = stock_info.get("pb_ratio", 0)
        dividend_yield = stock_info.get("dividend_yield", 0) or 0

        # 简单的估值评分 (0-100)
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
        """分析成长性"""
        if len(historical_data) < 60:
            return {"growth_score": 50, "trend": "unknown"}

        # 计算价格趋势
        recent_price = historical_data["Close"].iloc[-1]
        price_1m_ago = historical_data["Close"].iloc[-20] if len(historical_data) >= 20 else historical_data["Close"].iloc[0]
        price_3m_ago = historical_data["Close"].iloc[-60] if len(historical_data) >= 60 else historical_data["Close"].iloc[0]

        return_1m = (recent_price - price_1m_ago) / price_1m_ago * 100
        return_3m = (recent_price - price_3m_ago) / price_3m_ago * 100

        # 趋势判断
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

        # 成长性评分
        growth_score = max(0, min(100, 50 + return_3m * 2))

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
        """执行完整的基本面分析"""
        valuation = cls.analyze_valuation(stock_info)
        growth = cls.analyze_growth(historical_data)

        return {
            "valuation": valuation,
            "growth": growth,
            "overall_score": (valuation["valuation_score"] + growth["growth_score"]) / 2,
        }
