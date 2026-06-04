"""
AutoWealth AI - 机器学习预测模块测试

使用 pytest 对 MLPredictor 的所有方法进行全面测试，
包括特征工程、训练、预测、持久化和异常处理。
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock yfinance 以避免安装依赖
sys.modules["yfinance"] = MagicMock()

import numpy as np
import pandas as pd
import pytest

from autowealth.ml.predictor import MLPredictor


# ============================================================
# 测试数据工厂
# ============================================================

def make_stock_data(rows=200, seed=42, trend="normal"):
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

    prices = base_price + drift + rng.randn(rows) * 2

    df = pd.DataFrame({
        "Open": prices + rng.randn(rows) * 0.5,
        "High": prices + np.abs(rng.randn(rows)) * 1.5,
        "Low": prices - np.abs(rng.randn(rows)) * 1.5,
        "Close": prices,
        "Volume": rng.randint(1000000, 10000000, rows),
    }, index=dates)

    return df


# ============================================================
# 测试：初始化
# ============================================================

class TestMLPredictorInit:

    def test_init_default_model_type(self):
        """测试默认模型类型为 random_forest"""
        predictor = MLPredictor()
        assert predictor.model_type == "random_forest"

    def test_init_random_forest(self):
        """测试显式指定 random_forest 模型类型"""
        predictor = MLPredictor(model_type="random_forest")
        assert predictor.model_type == "random_forest"

    def test_init_lstm(self):
        """测试指定 lstm 模型类型"""
        predictor = MLPredictor(model_type="lstm")
        assert predictor.model_type == "lstm"

    def test_init_invalid_model_type(self):
        """测试不支持的模型类型应抛出 ValueError"""
        with pytest.raises(ValueError, match="不支持的模型类型"):
            MLPredictor(model_type="invalid")

    def test_init_state(self):
        """测试初始化后状态正确"""
        predictor = MLPredictor()
        assert predictor.model is None
        assert predictor.scaler is None
        assert predictor.feature_names == []
        assert predictor._is_trained is False


# ============================================================
# 测试：特征工程
# ============================================================

class TestPrepareFeatures:

    def test_prepare_features_returns_dataframe(self):
        """测试 prepare_features 返回 DataFrame"""
        data = make_stock_data(rows=100)
        predictor = MLPredictor()
        features = predictor.prepare_features(data)
        assert isinstance(features, pd.DataFrame)

    def test_prepare_features_has_expected_columns(self):
        """测试特征包含预期的列"""
        data = make_stock_data(rows=100)
        predictor = MLPredictor()
        features = predictor.prepare_features(data)
        expected_cols = ["MA_5", "MA_10", "MA_20", "MA_60", "RSI_14", "MACD", "BB_Position"]
        for col in expected_cols:
            assert col in features.columns, f"缺少特征列: {col}"

    def test_prepare_features_feature_names_set(self):
        """测试特征名列表被正确设置"""
        data = make_stock_data(rows=100)
        predictor = MLPredictor()
        predictor.prepare_features(data)
        assert len(predictor.feature_names) > 0

    def test_prepare_features_with_none_data(self):
        """测试传入 None 数据返回空 DataFrame"""
        predictor = MLPredictor()
        features = predictor.prepare_features(None)
        assert isinstance(features, pd.DataFrame)
        assert len(features) == 0

    def test_prepare_features_with_empty_data(self):
        """测试传入空 DataFrame 返回空 DataFrame"""
        predictor = MLPredictor()
        features = predictor.prepare_features(pd.DataFrame())
        assert isinstance(features, pd.DataFrame)
        assert len(features) == 0

    def test_prepare_features_with_insufficient_data(self):
        """测试数据行数不足时返回空 DataFrame"""
        predictor = MLPredictor()
        data = pd.DataFrame({"Close": [100.0]})
        features = predictor.prepare_features(data)
        assert isinstance(features, pd.DataFrame)
        assert len(features) == 0

    def test_prepare_features_missing_close_column(self):
        """测试缺少 Close 列时返回空 DataFrame"""
        predictor = MLPredictor()
        data = pd.DataFrame({"Open": [100.0], "High": [101.0]})
        features = predictor.prepare_features(data)
        assert isinstance(features, pd.DataFrame)
        assert len(features) == 0

    def test_prepare_features_volume_columns(self):
        """测试包含 Volume 列时成交量特征被正确计算"""
        data = make_stock_data(rows=100)
        predictor = MLPredictor()
        features = predictor.prepare_features(data)
        assert "Volume_Change" in features.columns
        assert "Volume_Ratio" in features.columns

    def test_prepare_features_without_volume(self):
        """测试缺少 Volume 列时使用默认值"""
        data = make_stock_data(rows=100)
        data = data.drop(columns=["Volume"])
        predictor = MLPredictor()
        features = predictor.prepare_features(data)
        assert "Volume_Change" in features.columns

    def test_prepare_features_bollinger_position_range(self):
        """测试布林带位置值在合理范围内"""
        data = make_stock_data(rows=100)
        predictor = MLPredictor()
        features = predictor.prepare_features(data)
        bb_pos = features["BB_Position"].dropna()
        # BB_Position 应在 0-1 之间（大部分情况）
        assert (bb_pos >= -0.5).all() and (bb_pos <= 1.5).all()


# ============================================================
# 测试：随机森林训练和预测
# ============================================================

class TestRandomForestTrainPredict:

    def test_train_returns_metrics(self):
        """测试训练返回包含 MSE, MAE, R2 的字典"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data)
        assert "MSE" in metrics
        assert "MAE" in metrics
        assert "R2" in metrics

    def test_train_sets_trained_flag(self):
        """测试训练后 _is_trained 标志被设置"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        assert predictor._is_trained is True

    def test_train_with_default_test_ratio(self):
        """测试使用默认 test_ratio 训练"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data)
        assert metrics["MSE"] >= 0

    def test_train_with_custom_test_ratio(self):
        """测试使用自定义 test_ratio 训练"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data, test_ratio=0.3)
        assert "MSE" in metrics

    def test_predict_returns_list(self):
        """测试预测返回列表"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        predictions = predictor.predict(data, steps=5)
        assert isinstance(predictions, list)
        assert len(predictions) == 5

    def test_predict_values_are_numeric(self):
        """测试预测值为数值类型"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        predictions = predictor.predict(data, steps=5)
        for pred in predictions:
            assert isinstance(pred, (int, float))

    def test_predict_custom_steps(self):
        """测试自定义预测步数"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        predictions = predictor.predict(data, steps=10)
        assert len(predictions) == 10

    def test_predict_before_train(self):
        """测试未训练时预测返回默认值"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictions = predictor.predict(data, steps=3)
        assert predictions == [0.0, 0.0, 0.0]

    def test_get_feature_importance(self):
        """测试获取随机森林特征重要性"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        importance = predictor.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0
        # 所有重要性值应为非负
        for v in importance.values():
            assert v >= 0

    def test_get_feature_importance_before_train(self):
        """测试未训练时获取特征重要性返回空字典"""
        predictor = MLPredictor(model_type="random_forest")
        importance = predictor.get_feature_importance()
        assert importance == {}


# ============================================================
# 测试：LSTM/MLP 训练和预测
# ============================================================

class TestLSTMTrainPredict:

    def test_lstm_train_returns_metrics(self):
        """测试 LSTM(MLP) 训练返回指标"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="lstm")
        metrics = predictor.train(data)
        assert "MSE" in metrics
        assert "MAE" in metrics
        assert "R2" in metrics

    def test_lstm_train_sets_trained_flag(self):
        """测试 LSTM(MLP) 训练后标志被设置"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="lstm")
        predictor.train(data)
        assert predictor._is_trained is True

    def test_lstm_predict_returns_list(self):
        """测试 LSTM(MLP) 预测返回列表"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="lstm")
        predictor.train(data)
        predictions = predictor.predict(data, steps=5)
        assert isinstance(predictions, list)
        assert len(predictions) == 5

    def test_lstm_get_feature_importance_empty(self):
        """测试 LSTM(MLP) 不支持特征重要性"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="lstm")
        predictor.train(data)
        importance = predictor.get_feature_importance()
        assert importance == {}


# ============================================================
# 测试：模型指标
# ============================================================

class TestModelMetrics:

    def test_get_metrics_after_train(self):
        """测试训练后获取指标"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        metrics = predictor.get_model_metrics()
        assert "MSE" in metrics
        assert "MAE" in metrics
        assert "R2" in metrics

    def test_get_metrics_before_train(self):
        """测试未训练时获取指标返回默认值"""
        predictor = MLPredictor()
        metrics = predictor.get_model_metrics()
        assert "MSE" in metrics
        assert "MAE" in metrics
        assert "R2" in metrics
        assert np.isnan(metrics["MSE"])

    def test_metrics_mse_non_negative(self):
        """测试 MSE 非负"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data)
        assert metrics["MSE"] >= 0

    def test_metrics_mae_non_negative(self):
        """测试 MAE 非负"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data)
        assert metrics["MAE"] >= 0


# ============================================================
# 测试：模型持久化
# ============================================================

class TestModelPersistence:

    def test_save_and_load_model(self):
        """测试模型保存和加载"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        original_metrics = predictor.get_model_metrics()

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name

        try:
            predictor.save_model(path)
            assert os.path.exists(path)

            new_predictor = MLPredictor()
            result = new_predictor.load_model(path)
            assert result is True
            assert new_predictor._is_trained is True
            assert new_predictor.model_type == "random_forest"

            loaded_metrics = new_predictor.get_model_metrics()
            assert loaded_metrics["MSE"] == original_metrics["MSE"]
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_save_model_success(self):
        """测试模型保存返回 True"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name

        try:
            result = predictor.save_model(path)
            assert result is True
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_load_nonexistent_model(self):
        """测试加载不存在的模型文件返回 False"""
        predictor = MLPredictor()
        result = predictor.load_model("/nonexistent/path/model.pkl")
        assert result is False

    def test_save_and_load_lstm_model(self):
        """测试 LSTM(MLP) 模型保存和加载"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="lstm")
        predictor.train(data)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name

        try:
            predictor.save_model(path)
            new_predictor = MLPredictor()
            result = new_predictor.load_model(path)
            assert result is True
            assert new_predictor.model_type == "lstm"
            assert new_predictor._is_trained is True
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_load_model_predict_works(self):
        """测试加载模型后可以正常预测"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name

        try:
            predictor.save_model(path)
            new_predictor = MLPredictor()
            new_predictor.load_model(path)
            predictions = new_predictor.predict(data, steps=3)
            assert len(predictions) == 3
            assert all(isinstance(p, (int, float)) for p in predictions)
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ============================================================
# 测试：数据不足时的处理
# ============================================================

class TestInsufficientData:

    def test_train_with_none_data(self):
        """测试 None 数据训练返回默认指标"""
        predictor = MLPredictor()
        metrics = predictor.train(None)
        assert np.isnan(metrics["MSE"])
        assert predictor._is_trained is False

    def test_train_with_empty_dataframe(self):
        """测试空 DataFrame 训练返回默认指标"""
        predictor = MLPredictor()
        metrics = predictor.train(pd.DataFrame())
        assert np.isnan(metrics["MSE"])
        assert predictor._is_trained is False

    def test_train_with_insufficient_rows(self):
        """测试行数不足时训练返回默认指标"""
        data = make_stock_data(rows=10)
        predictor = MLPredictor()
        metrics = predictor.train(data)
        assert np.isnan(metrics["MSE"])
        assert predictor._is_trained is False

    def test_predict_with_none_data(self):
        """测试 None 数据预测返回默认值"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        predictions = predictor.predict(None, steps=3)
        assert predictions == [0.0, 0.0, 0.0]

    def test_predict_with_empty_data(self):
        """测试空数据预测返回默认值"""
        data = make_stock_data(rows=200)
        predictor = MLPredictor(model_type="random_forest")
        predictor.train(data)
        predictions = predictor.predict(pd.DataFrame(), steps=3)
        assert predictions == [0.0, 0.0, 0.0]

    def test_train_with_only_close_column(self):
        """测试仅有 Close 列时仍能训练"""
        data = make_stock_data(rows=200)
        data = data[["Close"]]
        predictor = MLPredictor(model_type="random_forest")
        metrics = predictor.train(data)
        # 应该能训练成功（Volume相关特征使用默认值）
        assert predictor._is_trained is True
