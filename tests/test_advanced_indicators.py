"""
AutoWealth AI - 高级技术指标测试

使用 pytest 对 TechnicalAnalyzer 新增的6个高级技术指标进行全面测试，
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

from autowealth.core.analyzer import TechnicalAnalyzer


# ============================================================
# 测试数据工厂（与 test_analyzer.py 保持一致）
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


def make_suspended_data(rows=120, seed=77):
    """
    创建停牌数据（High == Low == Close），用于测试除零保护。
    """
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")
    price = 100.0
    volume = 0.0

    return pd.DataFrame({
        "Open": [price] * rows,
        "High": [price] * rows,
        "Low": [price] * rows,
        "Close": [price] * rows,
        "Volume": [volume] * rows,
    }, index=dates)


def make_all_up_data(rows=120, seed=99):
    """创建全涨数据（Close 每天都上涨）。"""
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    close = np.linspace(50, 150, rows)
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


# ============================================================
# OBV 测试
# ============================================================

class TestCalculateOBV:
    """测试 TechnicalAnalyzer.calculate_obv 方法"""

    def test_obv_column_exists(self):
        """验证 calculate_obv 生成 OBV 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_obv(data)
        assert "OBV" in result.columns

    def test_obv_first_value_equals_volume(self):
        """验证 OBV 第一个值等于第一日成交量"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_obv(data)
        assert abs(result["OBV"].iloc[0] - data["Volume"].iloc[0]) < 1e-10

    def test_obv_increases_when_price_rises(self):
        """验证价格上涨时 OBV 应增加"""
        data = make_all_up_data(120)
        result = TechnicalAnalyzer.calculate_obv(data)
        # 全涨数据中，OBV 应持续增加
        obv_diff = result["OBV"].diff().dropna()
        # 排除第一行，其余应 >= 0（因为 diff > 0 时加 volume）
        assert (obv_diff.iloc[1:] >= 0).all()

    def test_obv_flat_data(self):
        """验证停牌数据（价格不变）时 OBV 保持不变"""
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.calculate_obv(data)
        # 价格不变，OBV 应始终等于第一日成交量
        assert (result["OBV"] == data["Volume"].iloc[0]).all()

    def test_obv_does_not_modify_original(self):
        """验证 calculate_obv 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_obv(data)
        assert set(data.columns) == original_cols


# ============================================================
# ATR 测试
# ============================================================

class TestCalculateATR:
    """测试 TechnicalAnalyzer.calculate_atr 方法"""

    def test_atr_columns_exist(self):
        """验证 calculate_atr 生成 TR 和 ATR 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_atr(data)
        assert "TR" in result.columns
        assert "ATR14" in result.columns

    def test_atr_positive(self):
        """验证 ATR 值始终为正"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_atr(data)
        valid_atr = result["ATR14"].dropna()
        assert (valid_atr > 0).all()

    def test_atr_custom_period(self):
        """验证自定义周期的 ATR 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_atr(data, period=10)
        assert "ATR10" in result.columns
        assert result["ATR10"].iloc[:9].isna().all()

    def test_atr_nan_in_initial_rows(self):
        """验证 ATR 在前 period-1 行应为 NaN"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_atr(data, period=14)
        assert result["ATR14"].iloc[:13].isna().all()
        assert not pd.isna(result["ATR14"].iloc[13])

    def test_atr_does_not_modify_original(self):
        """验证 calculate_atr 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_atr(data)
        assert set(data.columns) == original_cols


# ============================================================
# DMI 测试
# ============================================================

class TestCalculateDMI:
    """测试 TechnicalAnalyzer.calculate_dmi 方法"""

    def test_dmi_columns_exist(self):
        """验证 calculate_dmi 生成 +DI, -DI, ADX 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_dmi(data)
        assert "+DI" in result.columns
        assert "-DI" in result.columns
        assert "ADX" in result.columns

    def test_dmi_di_range(self):
        """验证 +DI 和 -DI 值在 0-100 之间"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_dmi(data)
        valid_plus = result["+DI"].dropna()
        valid_minus = result["-DI"].dropna()
        assert (valid_plus >= 0).all() and (valid_plus <= 100).all()
        assert (valid_minus >= 0).all() and (valid_minus <= 100).all()

    def test_dmi_adx_range(self):
        """验证 ADX 值在 0-100 之间"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_dmi(data)
        valid_adx = result["ADX"].dropna()
        assert (valid_adx >= 0).all() and (valid_adx <= 100).all()

    def test_dmi_suspended_data(self):
        """验证停牌数据（High == Low）下 DMI 不应崩溃"""
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.calculate_dmi(data)
        # 不应有 inf
        assert not np.isinf(result["+DI"].values).any()
        assert not np.isinf(result["-DI"].values).any()
        assert not np.isinf(result["ADX"].values).any()

    def test_dmi_custom_period(self):
        """验证自定义周期的 DMI 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_dmi(data, period=10)
        assert "+DI" in result.columns
        assert "-DI" in result.columns
        assert "ADX" in result.columns


# ============================================================
# CCI 测试
# ============================================================

class TestCalculateCCI:
    """测试 TechnicalAnalyzer.calculate_cci 方法"""

    def test_cci_column_exists(self):
        """验证 calculate_cci 生成 CCI 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_cci(data)
        assert "CCI20" in result.columns

    def test_cci_custom_period(self):
        """验证自定义周期的 CCI 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_cci(data, period=10)
        assert "CCI10" in result.columns

    def test_cci_nan_in_initial_rows(self):
        """验证 CCI 在前 period-1 行应为 NaN"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_cci(data, period=20)
        assert result["CCI20"].iloc[:19].isna().all()
        assert not pd.isna(result["CCI20"].iloc[19])

    def test_cci_suspended_data(self):
        """验证停牌数据（High == Low == Close）下 CCI 不应崩溃"""
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.calculate_cci(data)
        # 不应有 inf
        assert not np.isinf(result["CCI20"].values).any()
        # 停牌时典型价格不变，CCI 应为 0（或接近 0）
        valid_cci = result["CCI20"].dropna()
        assert (np.abs(valid_cci) < 1e-6).all()

    def test_cci_does_not_modify_original(self):
        """验证 calculate_cci 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_cci(data)
        assert set(data.columns) == original_cols


# ============================================================
# WR 测试
# ============================================================

class TestCalculateWR:
    """测试 TechnicalAnalyzer.calculate_wr 方法"""

    def test_wr_column_exists(self):
        """验证 calculate_wr 生成 WR 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_wr(data)
        assert "WR14" in result.columns

    def test_wr_range(self):
        """验证 WR 值在 -100 到 0 之间"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_wr(data)
        valid_wr = result["WR14"].dropna()
        assert (valid_wr >= -100).all() and (valid_wr <= 0).all()

    def test_wr_custom_period(self):
        """验证自定义周期的 WR 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_wr(data, period=10)
        assert "WR10" in result.columns
        assert result["WR10"].iloc[:9].isna().all()

    def test_wr_suspended_data(self):
        """验证停牌数据（High == Low）下 WR 不应崩溃"""
        data = make_suspended_data(120)
        result = TechnicalAnalyzer.calculate_wr(data)
        # 不应有 inf
        assert not np.isinf(result["WR14"].values).any()
        # 当 High == Low == Close 时，WR 应为 0
        valid_wr = result["WR14"].dropna()
        assert (np.abs(valid_wr) < 1e-6).all()

    def test_wr_does_not_modify_original(self):
        """验证 calculate_wr 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_wr(data)
        assert set(data.columns) == original_cols


# ============================================================
# PSY 测试
# ============================================================

class TestCalculatePSY:
    """测试 TechnicalAnalyzer.calculate_psy 方法"""

    def test_psy_column_exists(self):
        """验证 calculate_psy 生成 PSY 列"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_psy(data)
        assert "PSY12" in result.columns

    def test_psy_range(self):
        """验证 PSY 值在 0-100 之间"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_psy(data)
        valid_psy = result["PSY12"].dropna()
        assert (valid_psy >= 0).all() and (valid_psy <= 100).all()

    def test_psy_custom_period(self):
        """验证自定义周期的 PSY 计算"""
        data = make_stock_data(100)
        result = TechnicalAnalyzer.calculate_psy(data, period=10)
        assert "PSY10" in result.columns
        # PSY 使用 diff > 0 的 rolling sum，前 1 行 diff 为 NaN
        # 因此 PSY10 从第 11 行（index=10）开始有值
        assert result["PSY10"].iloc[:9].isna().all()
        assert not pd.isna(result["PSY10"].iloc[9])

    def test_psy_all_up_data(self):
        """验证全涨数据下 PSY 应为 100"""
        data = make_all_up_data(120)
        result = TechnicalAnalyzer.calculate_psy(data)
        valid_psy = result["PSY12"].dropna()
        # 全涨数据中 diff > 0 的比例应很高
        assert valid_psy.iloc[-1] == 100

    def test_psy_does_not_modify_original(self):
        """验证 calculate_psy 不修改原始 DataFrame"""
        data = make_stock_data(100)
        original_cols = set(data.columns)
        TechnicalAnalyzer.calculate_psy(data)
        assert set(data.columns) == original_cols


# ============================================================
# full_analysis 新增列测试
# ============================================================

class TestFullAnalysisAdvancedIndicators:
    """测试 full_analysis 包含所有新增高级指标列"""

    def test_full_analysis_contains_advanced_indicators(self):
        """验证 full_analysis 包含所有新增技术指标列"""
        data = make_stock_data(120)
        result = TechnicalAnalyzer.full_analysis(data)

        expected_cols = [
            "OBV",
            "TR", "ATR14",
            "+DI", "-DI", "ADX",
            "CCI20",
            "WR14",
            "PSY12",
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


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
