"""
AutoWealth AI - 分析器模块测试

使用 pytest 对 TechnicalAnalyzer 和 FundamentalAnalyzer 的所有方法进行全面测试，
包括正常情况、边界情况和异常情况。
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 添加项目根目录到路径，确保可以导入 autowealth
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock yfinance 以避免安装依赖
sys.modules['yfinance'] = MagicMock()

import numpy as np
import pandas as pd
import pytest

from autowealth.core.analyzer import FundamentalAnalyzer, TechnicalAnalyzer


# ============================================================
# 测试数据工厂
# ============================================================

def make_stock_data(rows=120, seed=42, trend="normal"):
    """
    创建模拟股票 OHLCV 数据。

    Args:
        rows: 数据行数
        seed: 随机种子
        trend: 趋势类型 (normal / uptrend / downtrend / flat)

    Returns:
        包含 Open, High, Low, Close, Volume 列的 DataFrame
    """
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    base_price = 100.0

    if trend == "uptrend":
        drift = np.linspace(0, 50, rows)
    elif trend == "downtrend":
        drift = np.linspace(0, -50, rows)
    elif trend == "flat":
        drift = np.zeros(rows)
    else:
        drift = np.cumsum(rng.randn(rows) * 0.5)

    close = base_price + drift + rng.randn(rows) * 2
    close = np.maximum(close, 1.0)  # 确保价格为正

    # 生成 OHLC
    high = close + rng.uniform(0.5, 3.0, rows)
    low = close - rng.uniform(0.5, 3.0, rows)
    low = np.maximum(low, 0.5)
    open_ = low + rng.uniform(0, 1, rows) * (high - low)
    volume = rng.randint(1000000, 10000000, rows).astype(float)

    df = pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)

    return df


def make_all_up_data(rows=120, seed=99):
    """创建全涨数据（Close 每天都上涨），用于测试 RSI 除零情况。"""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    close = np.linspace(50, 150, rows)  # 持续上涨
    high = close + rng.uniform(0.1, 1.0, rows)
    low = close - rng.uniform(0.1, 0.5, rows)
    low = np.maximum(low, close - 1)
    open_ = low + rng.uniform(0, 0.5, rows) * (high - low)
    volume = rng.randint(1000000, 5000000, rows).astype(float)

    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


def make_all_down_data(rows=120, seed=88):
    """创建全跌数据（Close 每天都下跌），用于测试 RSI 极端值。"""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    close = np.linspace(150, 50, rows)  # 持续下跌
    high = close + rng.uniform(0.1, 1.0, rows)
    low = close - rng.uniform(0.1, 0.5, rows)
    low = np.maximum(low, 1.0)
    open_ = low + rng.uniform(0, 0.5, rows) * (high - low)
    volume = rng.randint(1000000, 5000000, rows).astype(float)

    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": volume,
    }, index=dates)


def make_suspended_data(rows=120, seed=77):
    """
    创建停牌数据（High == Low == Close），用于测试 KDJ 除零情况。
    停牌时价格不变，价格区间为零。
    """
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")
    price = 100.0
    volume = 0.0  # 停牌无成交

    return pd.DataFrame({
        "Open": [price] * rows,
        "High": [price] * rows,
        "Low": [price] * rows,
        "Close": [price] * rows,
        "Volume": [volume] * rows,
    }, index=dates)


# ============================================================
# TechnicalAnalyzer 测试
# ============================================================

class TestCalculateMA:
    """测试 TechnicalAnalyzer.calculate_ma 方法"""

    def test_ma_columns_exist(self):
        """验证 calculate_ma 生成正确的 MA 列名"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ma(data)
        for period in [5, 10, 20, 60]:
            assert f"MA{period}" in result.columns

    def test_ma_values_correct(self):
        """验证 MA5 计算值是否等于最近5日收盘价的均值"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ma(data)
        # 第6行（index=5）开始有 MA5 值
        expected_ma5 = data["Close"].iloc[:5].mean()
        actual_ma5 = result["MA5"].iloc[4]  # 第5行（0-based index=4）
        assert abs(actual_ma5 - expected_ma5) < 1e-10

    def test_ma_custom_periods(self):
        """验证自定义周期的 MA 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ma(data, periods=[3, 7])
        assert "MA3" in result.columns
        assert "MA7" in result.columns
        assert "MA5" not in result.columns

    def test_ma_nan_in_initial_rows(self):
        """验证 MA 在前 N-1 行应为 NaN"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ma(data, periods=[10])
        # 前9行应该没有 MA10 值（NaN）
        assert result["MA10"].iloc[:9].isna().all()
        # 第10行应有值
        assert not pd.isna(result["MA10"].iloc[9])

    def test_ma_does_not_modify_original(self):
        """验证 calculate_ma 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_ma(data)
        assert set(data.columns) == original_cols


class TestCalculateEMA:
    """测试 TechnicalAnalyzer.calculate_ema 方法"""

    def test_ema_columns_exist(self):
        """验证 calculate_ema 生成正确的 EMA 列名"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ema(data)
        assert "EMA12" in result.columns
        assert "EMA26" in result.columns

    def test_ema_first_value_equals_close(self):
        """验证 EMA 第一个值应等于收盘价（adjust=False 时）"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ema(data, periods=[12])
        assert abs(result["EMA12"].iloc[0] - data["Close"].iloc[0]) < 1e-10

    def test_ema_custom_periods(self):
        """验证自定义周期的 EMA 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ema(data, periods=[5, 50])
        assert "EMA5" in result.columns
        assert "EMA50" in result.columns

    def test_ema_no_nan(self):
        """验证 EMA 不应产生 NaN（ewm 从第一行开始就有值）"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_ema(data)
        assert result["EMA12"].notna().all()
        assert result["EMA26"].notna().all()


class TestCalculateMACD:
    """测试 TechnicalAnalyzer.calculate_macd 方法"""

    def test_macd_columns_exist(self):
        """验证 calculate_macd 生成 MACD、MACD_Signal、MACD_Histogram 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_macd(data)
        assert "MACD" in result.columns
        assert "MACD_Signal" in result.columns
        assert "MACD_Histogram" in result.columns

    def test_macd_histogram_equals_diff(self):
        """验证 MACD_Histogram = MACD - MACD_Signal"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_macd(data)
        expected = result["MACD"] - result["MACD_Signal"]
        np.testing.assert_allclose(result["MACD_Histogram"].values, expected.values)

    def test_macd_custom_params(self):
        """验证自定义参数的 MACD 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_macd(data, fast=5, slow=10, signal=3)
        assert "MACD" in result.columns
        assert "MACD_Signal" in result.columns


class TestCalculateRSI:
    """测试 TechnicalAnalyzer.calculate_rsi 方法"""

    def test_rsi_column_exists(self):
        """验证 calculate_rsi 生成 RSI 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_rsi(data)
        assert "RSI" in result.columns

    def test_rsi_range(self):
        """验证 RSI 值在 0-100 之间"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_rsi(data)
        valid_rsi = result["RSI"].dropna()
        assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()

    def test_rsi_all_up_data(self):
        """
        测试全涨数据下 RSI 不应崩溃（除零保护）。
        当所有 delta > 0 时，loss 为 0，代码使用 replace(0, 1e-10) 保护。
        """
        data = make_all_up_data(120)
        result = TechnicalAnalyzer.calculate_rsi(data)
        valid_rsi = result["RSI"].dropna()
        # 全涨时 RSI 应接近 100
        assert len(valid_rsi) > 0
        assert valid_rsi.iloc[-1] > 90  # 持续上涨 RSI 应很高
        assert not valid_rsi.isna().any()  # 不应有 NaN

    def test_rsi_all_down_data(self):
        """
        测试全跌数据下 RSI 不应崩溃。
        当所有 delta < 0 时，gain 为 0，代码使用 replace(0, 1e-10) 保护。
        """
        data = make_all_down_data(120)
        result = TechnicalAnalyzer.calculate_rsi(data)
        valid_rsi = result["RSI"].dropna()
        assert len(valid_rsi) > 0
        assert valid_rsi.iloc[-1] < 10  # 持续下跌 RSI 应很低
        assert not valid_rsi.isna().any()

    def test_rsi_custom_period(self):
        """验证自定义周期的 RSI 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_rsi(data, period=7)
        assert "RSI" in result.columns
        # 前7行应为 NaN
        assert result["RSI"].iloc[:6].isna().all()


class TestCalculateBollingerBands:
    """测试 TechnicalAnalyzer.calculate_bollinger_bands 方法"""

    def test_bollinger_columns_exist(self):
        """验证 calculate_bollinger_bands 生成正确的列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_bollinger_bands(data)
        for col in ["BB_Middle", "BB_Upper", "BB_Lower", "BB_Width", "BB_Position"]:
            assert col in result.columns

    def test_bollinger_upper_greater_than_lower(self):
        """验证布林带上轨应大于下轨"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_bollinger_bands(data)
        valid = result.dropna(subset=["BB_Upper", "BB_Lower"])
        assert (valid["BB_Upper"] >= valid["BB_Lower"]).all()

    def test_bollinger_middle_equals_ma(self):
        """验证布林带中轨等于20日简单移动平均"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_bollinger_bands(data)
        expected_middle = data["Close"].rolling(window=20).mean()
        np.testing.assert_allclose(
            result["BB_Middle"].values,
            expected_middle.values,
            equal_nan=True,
        )

    def test_bollinger_width_equals_range(self):
        """验证 BB_Width = BB_Upper - BB_Lower"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_bollinger_bands(data)
        expected_width = result["BB_Upper"] - result["BB_Lower"]
        np.testing.assert_allclose(
            result["BB_Width"].values,
            expected_width.values,
            equal_nan=True,
        )

    def test_bollinger_custom_params(self):
        """验证自定义参数的布林带计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_bollinger_bands(data, period=10, std_dev=1.5)
        assert "BB_Middle" in result.columns
        # 前9行应为 NaN
        assert result["BB_Middle"].iloc[:9].isna().all()


class TestCalculateKDJ:
    """测试 TechnicalAnalyzer.calculate_kdj 方法"""

    def test_kdj_columns_exist(self):
        """验证 calculate_kdj 生成 K, D, J 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_kdj(data)
        for col in ["K", "D", "J"]:
            assert col in result.columns

    def test_kdj_j_equals_formula(self):
        """验证 J = 3*K - 2*D"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_kdj(data)
        expected_j = 3 * result["K"] - 2 * result["D"]
        np.testing.assert_allclose(result["J"].values, expected_j.values, equal_nan=True)

    def test_kdj_suspended_data(self):
        """
        测试停牌数据（High == Low）下 KDJ 不应崩溃。
        停牌时 price_range 为 0，代码使用 replace(0, 1e-10) 保护。
        注意：rolling窗口前n行为NaN是正常行为，只检查窗口期之后的数据。
        """
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.calculate_kdj(data)
        # 不应有 inf
        assert not np.isinf(result["K"].values).any(), "K 值不应包含 inf"
        assert not np.isinf(result["D"].values).any(), "D 值不应包含 inf"
        assert not np.isinf(result["J"].values).any(), "J 值不应包含 inf"
        # 窗口期之后不应有 NaN
        assert not result["K"].iloc[10:].isna().any(), "K 值窗口期后不应包含 NaN"
        assert not result["D"].iloc[10:].isna().any(), "D 值窗口期后不应包含 NaN"

    def test_kdj_custom_params(self):
        """验证自定义参数的 KDJ 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_kdj(data, n=14, m1=5, m2=5)
        assert "K" in result.columns
        assert "D" in result.columns
        assert "J" in result.columns


class TestCalculateVolumeIndicators:
    """测试 TechnicalAnalyzer.calculate_volume_indicators 方法"""

    def test_volume_columns_exist(self):
        """验证 calculate_volume_indicators 生成正确的列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_volume_indicators(data)
        for col in ["Volume_MA5", "Volume_MA20", "Volume_Ratio"]:
            assert col in result.columns

    def test_volume_ma_correct(self):
        """验证 Volume_MA5 等于最近5日成交量的均值"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_volume_indicators(data)
        expected = data["Volume"].iloc[:5].mean()
        actual = result["Volume_MA5"].iloc[4]
        assert abs(actual - expected) < 1e-10

    def test_volume_ratio_calculation(self):
        """验证 Volume_Ratio = Volume / Volume_MA20"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_volume_indicators(data)
        valid = result.dropna(subset=["Volume_Ratio"])
        expected_ratio = valid["Volume"] / valid["Volume_MA20"]
        np.testing.assert_allclose(valid["Volume_Ratio"].values, expected_ratio.values)


class TestFullAnalysis:
    """测试 TechnicalAnalyzer.full_analysis 方法"""

    def test_full_analysis_contains_all_indicators(self):
        """验证 full_analysis 包含所有技术指标列"""
        data = make_stock_data(120)
        result = TechnicalAnalyzer.full_analysis(data)

        expected_cols = [
            "MA5", "MA10", "MA20", "MA60",
            "EMA12", "EMA26",
            "MACD", "MACD_Signal", "MACD_Histogram",
            "RSI",
            "BB_Middle", "BB_Upper", "BB_Lower", "BB_Width", "BB_Position",
            "K", "D", "J",
            "Volume_MA5", "Volume_MA20", "Volume_Ratio",
        ]
        for col in expected_cols:
            assert col in result.columns, f"缺少列: {col}"

    def test_full_analysis_preserves_original_columns(self):
        """验证 full_analysis 保留原始 OHLCV 列"""
        data = make_stock_data(120)
        result = TechnicalAnalyzer.full_analysis(data)
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            assert col in result.columns

    def test_full_analysis_row_count_unchanged(self):
        """验证 full_analysis 不改变数据行数"""
        data = make_stock_data(120)
        result = TechnicalAnalyzer.full_analysis(data)
        assert len(result) == len(data)

    def test_full_analysis_does_not_modify_original(self):
        """验证 full_analysis 不修改原始 DataFrame"""
        data = make_stock_data(120)
        original_cols = list(data.columns)
        TechnicalAnalyzer.full_analysis(data)
        assert list(data.columns) == original_cols


class TestTechnicalAnalyzerEdgeCases:
    """TechnicalAnalyzer 边界情况测试"""

    def test_empty_dataframe(self):
        """测试空 DataFrame 不应导致崩溃"""
        data = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        result = TechnicalAnalyzer.calculate_ma(data)
        assert len(result) == 0
        assert "MA5" in result.columns

    def test_single_row_data(self):
        """测试只有一行数据的情况"""
        data = pd.DataFrame({
            "Open": [100], "High": [101], "Low": [99], "Close": [100], "Volume": [1000000]
        })
        result = TechnicalAnalyzer.calculate_ma(data)
        assert len(result) == 1
        assert pd.isna(result["MA5"].iloc[0])  # 单行不足以计算 MA5

    def test_very_few_rows(self):
        """测试数据行数很少（少于窗口期）的情况"""
        data = make_stock_data(5)
        result = TechnicalAnalyzer.full_analysis(data)
        assert len(result) == 5
        # MA60 应全部为 NaN
        assert result["MA60"].isna().all()

    def test_suspended_data_full_analysis(self):
        """测试停牌数据在完整分析中不崩溃"""
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.full_analysis(data)
        assert len(result) == 120
        # 不应有 inf
        numeric_cols = result.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            assert not np.isinf(result[col].values).any(), f"{col} 包含 inf 值"

    def test_all_up_data_full_analysis(self):
        """测试全涨数据在完整分析中不崩溃"""
        data = make_all_up_data(120)
        result = TechnicalAnalyzer.full_analysis(data)
        assert len(result) == 120
        # RSI 不应有 NaN（除零保护）
        assert not result["RSI"].iloc[14:].isna().any()

    def test_all_down_data_full_analysis(self):
        """测试全跌数据在完整分析中不崩溃"""
        data = make_all_down_data(120)
        result = TechnicalAnalyzer.full_analysis(data)
        assert len(result) == 120
        # RSI 不应有 NaN（除零保护）
        assert not result["RSI"].iloc[14:].isna().any()


# ============================================================
# FundamentalAnalyzer 测试
# ============================================================

class TestAnalyzeValuation:
    """测试 FundamentalAnalyzer.analyze_valuation 方法"""

    def test_valuation_keys(self):
        """验证 analyze_valuation 返回所有必需的键"""
        stock_info = {
            "pe_ratio": 15.0,
            "pb_ratio": 2.0,
            "dividend_yield": 0.03,
        }
        result = FundamentalAnalyzer.analyze_valuation(stock_info)
        expected_keys = [
            "pe_ratio", "pb_ratio", "dividend_yield",
            "pe_score", "pb_score", "dividend_score", "valuation_score",
        ]
        for key in expected_keys:
            assert key in result

    def test_valuation_score_range(self):
        """验证估值评分在 0-100 之间"""
        stock_info = {"pe_ratio": 15.0, "pb_ratio": 2.0, "dividend_yield": 0.03}
        result = FundamentalAnalyzer.analyze_valuation(stock_info)
        assert 0 <= result["valuation_score"] <= 100

    def test_valuation_low_pe_high_score(self):
        """验证低 PE 比率产生较高的 PE 评分"""
        low_pe = FundamentalAnalyzer.analyze_valuation({"pe_ratio": 5, "pb_ratio": 1, "dividend_yield": 0})
        high_pe = FundamentalAnalyzer.analyze_valuation({"pe_ratio": 50, "pb_ratio": 1, "dividend_yield": 0})
        assert low_pe["pe_score"] > high_pe["pe_score"]

    def test_valuation_high_dividend_high_score(self):
        """验证高股息率产生较高的股息评分"""
        low_div = FundamentalAnalyzer.analyze_valuation({"pe_ratio": 0, "pb_ratio": 0, "dividend_yield": 0.005})
        high_div = FundamentalAnalyzer.analyze_valuation({"pe_ratio": 0, "pb_ratio": 0, "dividend_yield": 0.05})
        assert high_div["dividend_score"] > low_div["dividend_score"]

    def test_valuation_missing_fields(self):
        """验证缺失字段时使用默认值 50"""
        stock_info = {}  # 所有字段缺失
        result = FundamentalAnalyzer.analyze_valuation(stock_info)
        assert result["pe_ratio"] == 0
        assert result["pb_ratio"] == 0
        assert result["pe_score"] == 50
        assert result["pb_score"] == 50

    def test_valuation_none_dividend(self):
        """验证 dividend_yield 为 None 时不出错"""
        stock_info = {"pe_ratio": 10, "pb_ratio": 1.5, "dividend_yield": None}
        result = FundamentalAnalyzer.analyze_valuation(stock_info)
        assert result["dividend_yield"] == 0
        assert result["dividend_score"] == 0


class TestAnalyzeGrowth:
    """测试 FundamentalAnalyzer.analyze_growth 方法"""

    def test_growth_keys(self):
        """验证 analyze_growth 返回所有必需的键"""
        data = make_stock_data(120, trend="uptrend")
        result = FundamentalAnalyzer.analyze_growth(data)
        expected_keys = ["return_1m", "return_3m", "trend", "growth_score"]
        for key in expected_keys:
            assert key in result

    def test_growth_uptrend(self):
        """验证上涨趋势数据返回 uptrend 或 strong_uptrend"""
        data = make_stock_data(120, trend="uptrend")
        result = FundamentalAnalyzer.analyze_growth(data)
        assert result["trend"] in ("uptrend", "strong_uptrend")

    def test_growth_downtrend(self):
        """验证下跌趋势数据返回 downtrend 或 strong_downtrend"""
        data = make_stock_data(120, trend="downtrend")
        result = FundamentalAnalyzer.analyze_growth(data)
        assert result["trend"] in ("downtrend", "strong_downtrend")

    def test_growth_score_range(self):
        """验证成长性评分在 0-100 之间"""
        data = make_stock_data(120)
        result = FundamentalAnalyzer.analyze_growth(data)
        assert 0 <= result["growth_score"] <= 100

    def test_growth_insufficient_data(self):
        """验证数据不足（少于60行）时返回 unknown 和默认评分"""
        data = make_stock_data(30)
        result = FundamentalAnalyzer.analyze_growth(data)
        assert result["trend"] == "unknown"
        assert result["growth_score"] == 50

    def test_growth_positive_returns(self):
        """验证上涨趋势的月度收益率为正"""
        data = make_stock_data(120, trend="uptrend")
        result = FundamentalAnalyzer.analyze_growth(data)
        assert result["return_1m"] > 0

    def test_growth_negative_returns(self):
        """验证下跌趋势的月度收益率为负"""
        data = make_stock_data(120, trend="downtrend")
        result = FundamentalAnalyzer.analyze_growth(data)
        assert result["return_1m"] < 0


class TestFullFundamentalAnalysis:
    """测试 FundamentalAnalyzer.full_fundamental_analysis 方法"""

    def test_full_fundamental_keys(self):
        """验证 full_fundamental_analysis 返回所有必需的键"""
        data = make_stock_data(120)
        stock_info = {"pe_ratio": 15, "pb_ratio": 2, "dividend_yield": 0.03}
        result = FundamentalAnalyzer.full_fundamental_analysis(stock_info, data)
        expected_keys = ["valuation", "growth", "overall_score"]
        for key in expected_keys:
            assert key in result

    def test_full_fundamental_overall_score_range(self):
        """验证综合评分在 0-100 之间"""
        data = make_stock_data(120)
        stock_info = {"pe_ratio": 15, "pb_ratio": 2, "dividend_yield": 0.03}
        result = FundamentalAnalyzer.full_fundamental_analysis(stock_info, data)
        assert 0 <= result["overall_score"] <= 100

    def test_full_fundamental_overall_score_calculation(self):
        """验证综合评分 = (valuation_score + growth_score) / 2"""
        data = make_stock_data(120)
        stock_info = {"pe_ratio": 15, "pb_ratio": 2, "dividend_yield": 0.03}
        result = FundamentalAnalyzer.full_fundamental_analysis(stock_info, data)
        expected = (result["valuation"]["valuation_score"] + result["growth"]["growth_score"]) / 2
        assert abs(result["overall_score"] - expected) < 1e-10

    def test_full_fundamental_insufficient_data(self):
        """验证数据不足时仍能正常返回"""
        data = make_stock_data(30)
        stock_info = {"pe_ratio": 15, "pb_ratio": 2, "dividend_yield": 0.03}
        result = FundamentalAnalyzer.full_fundamental_analysis(stock_info, data)
        assert result["growth"]["trend"] == "unknown"
        assert result["overall_score"] is not None


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
