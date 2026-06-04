"""
机器学习预测模块 - 提供基于ML的价格预测能力

支持随机森林和MLP两种模型，提供特征工程、训练、预测和模型持久化功能。
"""

import logging
import pickle
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class MLPredictor:
    """机器学习价格预测器

    支持随机森林和MLP两种模型类型，用于基于技术指标特征的价格预测。

    Args:
        model_type: 模型类型，支持 "random_forest" 和 "lstm"（实际使用MLP替代）
    """

    def __init__(self, model_type: str = "random_forest"):
        if model_type not in ("random_forest", "lstm"):
            raise ValueError(f"不支持的模型类型: {model_type}，请使用 'random_forest' 或 'lstm'")
        self.model_type = model_type
        self.model = None
        self.scaler = None
        self.feature_names: List[str] = []
        self._metrics: Dict[str, float] = {}
        self._is_trained = False
        self._X_test = None
        self._y_test = None

    def prepare_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """从OHLCV数据构造技术指标特征

        构造的特征包括：MA(5/10/20/60)、RSI(14)、MACD、布林带位置、
        波动率、成交量变化率等。

        Args:
            data: 包含 Open, High, Low, Close, Volume 列的 DataFrame

        Returns:
            包含所有特征列的 DataFrame（前若干行因滚动窗口可能含NaN）
        """
        try:
            if data is None or len(data) < 2:
                logger.warning("数据不足，无法构造特征")
                return pd.DataFrame()

            df = data.copy()

            # 确保必要的列存在
            required_cols = ["Close"]
            for col in required_cols:
                if col not in df.columns:
                    logger.warning(f"缺少必要列: {col}")
                    return pd.DataFrame()

            # 移动平均线
            for period in [5, 10, 20, 60]:
                df[f"MA_{period}"] = df["Close"].rolling(window=period).mean()

            # RSI (14)
            delta = df["Close"].diff()
            gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
            rs = gain / loss.replace(0, 1e-10)
            df["RSI_14"] = 100 - (100 / (1 + rs))

            # MACD
            ema_fast = df["Close"].ewm(span=12, adjust=False).mean()
            ema_slow = df["Close"].ewm(span=26, adjust=False).mean()
            df["MACD"] = ema_fast - ema_slow
            df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
            df["MACD_Histogram"] = df["MACD"] - df["MACD_Signal"]

            # 布林带位置
            bb_middle = df["Close"].rolling(window=20).mean()
            bb_std = df["Close"].rolling(window=20).std()
            bb_upper = bb_middle + bb_std * 2
            bb_lower = bb_middle - bb_std * 2
            bb_range = (bb_upper - bb_lower).replace(0, 1e-10)
            df["BB_Position"] = (df["Close"] - bb_lower) / bb_range

            # 波动率 (20日收益率标准差)
            df["Volatility_20"] = df["Close"].pct_change().rolling(window=20).std()

            # 成交量变化率
            if "Volume" in df.columns:
                df["Volume_Change"] = df["Volume"].pct_change()
                df["Volume_MA_5"] = df["Volume"].rolling(window=5).mean()
                df["Volume_Ratio"] = df["Volume"] / df["Volume_MA_5"].replace(0, 1e-10)
            else:
                df["Volume_Change"] = 0.0
                df["Volume_MA_5"] = 0.0
                df["Volume_Ratio"] = 1.0

            # 价格动量
            for period in [5, 10, 20]:
                df[f"Momentum_{period}"] = df["Close"].pct_change(period)

            # 收益率
            df["Return_1"] = df["Close"].pct_change(1)

            # 价格位置 (相对于20日高低)
            if "High" in df.columns and "Low" in df.columns:
                high_20 = df["High"].rolling(window=20).max()
                low_20 = df["Low"].rolling(window=20).min()
                price_range = (high_20 - low_20).replace(0, 1e-10)
                df["Price_Position_20"] = (df["Close"] - low_20) / price_range
            else:
                df["Price_Position_20"] = 0.5

            # 收集特征列名
            feature_candidates = [
                "MA_5", "MA_10", "MA_20", "MA_60",
                "RSI_14",
                "MACD", "MACD_Signal", "MACD_Histogram",
                "BB_Position",
                "Volatility_20",
                "Volume_Change", "Volume_MA_5", "Volume_Ratio",
                "Momentum_5", "Momentum_10", "Momentum_20",
                "Return_1",
                "Price_Position_20",
            ]
            self.feature_names = [c for c in feature_candidates if c in df.columns]

            return df

        except Exception as e:
            logger.error(f"特征构造失败: {e}")
            return pd.DataFrame()

    def train(
        self,
        data: pd.DataFrame,
        target_col: str = "Close",
        test_ratio: float = 0.2,
    ) -> Dict[str, float]:
        """训练模型

        Args:
            data: 包含OHLCV数据的DataFrame
            target_col: 目标列名（默认为 "Close"）
            test_ratio: 测试集比例（默认为 0.2）

        Returns:
            包含 MSE, MAE, R2 等指标的字典
        """
        try:
            if data is None or len(data) < 30:
                logger.warning("数据不足（至少需要30条），无法训练模型")
                self._metrics = {
                    "MSE": float("nan"),
                    "MAE": float("nan"),
                    "R2": float("nan"),
                }
                return self._metrics

            # 构造特征
            df = self.prepare_features(data)
            if df.empty or len(self.feature_names) == 0:
                logger.warning("特征构造失败，无法训练")
                self._metrics = {
                    "MSE": float("nan"),
                    "MAE": float("nan"),
                    "R2": float("nan"),
                }
                return self._metrics

            # 去除NaN行
            df = df.dropna(subset=self.feature_names + [target_col])
            if len(df) < 20:
                logger.warning("有效数据不足（去除NaN后），无法训练模型")
                self._metrics = {
                    "MSE": float("nan"),
                    "MAE": float("nan"),
                    "R2": float("nan"),
                }
                return self._metrics

            # 构造目标：下一期收益率
            df = df.copy()
            df["Target"] = df[target_col].shift(-1)
            df = df.dropna(subset=["Target"])

            X = df[self.feature_names].values
            y = df["Target"].values

            # 标准化
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # 划分训练/测试集
            split_idx = int(len(X_scaled) * (1 - test_ratio))
            X_train, X_test = X_scaled[:split_idx], X_scaled[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            self._X_test = X_test
            self._y_test = y_test

            # 创建并训练模型
            if self.model_type == "random_forest":
                self.model = RandomForestRegressor(
                    n_estimators=100,
                    max_depth=10,
                    random_state=42,
                    n_jobs=-1,
                )
            elif self.model_type == "lstm":
                self.model = MLPRegressor(
                    hidden_layer_sizes=(64, 32),
                    activation="relu",
                    solver="adam",
                    max_iter=500,
                    random_state=42,
                    early_stopping=True,
                    validation_fraction=0.1,
                )

            self.model.fit(X_train, y_train)
            self._is_trained = True

            # 计算指标
            y_pred = self.model.predict(X_test)
            self._metrics = {
                "MSE": float(mean_squared_error(y_test, y_pred)),
                "MAE": float(mean_absolute_error(y_test, y_pred)),
                "R2": float(r2_score(y_test, y_pred)),
            }

            logger.info(
                f"模型训练完成 ({self.model_type}): "
                f"MSE={self._metrics['MSE']:.4f}, "
                f"MAE={self._metrics['MAE']:.4f}, "
                f"R2={self._metrics['R2']:.4f}"
            )

            return self._metrics

        except Exception as e:
            logger.error(f"模型训练失败: {e}")
            self._metrics = {
                "MSE": float("nan"),
                "MAE": float("nan"),
                "R2": float("nan"),
            }
            return self._metrics

    def predict(self, data: pd.DataFrame, steps: int = 5) -> List[float]:
        """预测未来N步价格

        使用最后一条数据的特征进行递推预测。

        Args:
            data: 包含OHLCV数据的DataFrame
            steps: 预测步数（默认为5）

        Returns:
            预测价格列表
        """
        try:
            if not self._is_trained or self.model is None:
                logger.warning("模型尚未训练，无法预测")
                return [0.0] * steps

            if data is None or len(data) < 2:
                logger.warning("数据不足，无法预测")
                return [0.0] * steps

            df = self.prepare_features(data)
            if df.empty or len(self.feature_names) == 0:
                logger.warning("特征构造失败，无法预测")
                return [0.0] * steps

            df = df.dropna(subset=self.feature_names)
            if df.empty:
                logger.warning("有效特征数据为空，无法预测")
                return [0.0] * steps

            predictions = []
            last_features = df[self.feature_names].iloc[-1:].values

            # 获取最后已知价格
            last_price = data["Close"].iloc[-1] if "Close" in data.columns else 0.0

            for _ in range(steps):
                scaled = self.scaler.transform(last_features)
                pred = self.model.predict(scaled)[0]
                predictions.append(float(pred))

                # 更新特征用于下一步预测（简单递推：用预测值更新Close相关特征）
                # 这里使用简化方式：直接使用上一步的特征
                pass

            return predictions

        except Exception as e:
            logger.error(f"预测失败: {e}")
            return [0.0] * steps

    def get_feature_importance(self) -> Dict[str, float]:
        """返回特征重要性（仅random_forest模型）

        Returns:
            特征名到重要性分数的字典；非随机森林模型返回空字典
        """
        try:
            if self.model_type != "random_forest":
                logger.info("特征重要性仅支持 random_forest 模型")
                return {}

            if not self._is_trained or self.model is None:
                logger.warning("模型尚未训练")
                return {}

            importances = self.model.feature_importances_
            return dict(zip(self.feature_names, importances.tolist()))

        except Exception as e:
            logger.error(f"获取特征重要性失败: {e}")
            return {}

    def get_model_metrics(self) -> Dict[str, float]:
        """返回模型评估指标

        Returns:
            包含 MSE, MAE, R2 的字典
        """
        if not self._metrics:
            return {
                "MSE": float("nan"),
                "MAE": float("nan"),
                "R2": float("nan"),
            }
        return self._metrics.copy()

    def save_model(self, path: str) -> bool:
        """保存模型到文件

        Args:
            path: 保存路径

        Returns:
            是否保存成功
        """
        try:
            model_data = {
                "model_type": self.model_type,
                "model": self.model,
                "scaler": self.scaler,
                "feature_names": self.feature_names,
                "metrics": self._metrics,
                "is_trained": self._is_trained,
            }
            with open(path, "wb") as f:
                pickle.dump(model_data, f)
            logger.info(f"模型已保存到: {path}")
            return True

        except Exception as e:
            logger.error(f"模型保存失败: {e}")
            return False

    def load_model(self, path: str) -> bool:
        """从文件加载模型

        Args:
            path: 模型文件路径

        Returns:
            是否加载成功
        """
        try:
            with open(path, "rb") as f:
                model_data = pickle.load(f)

            self.model_type = model_data["model_type"]
            self.model = model_data["model"]
            self.scaler = model_data["scaler"]
            self.feature_names = model_data["feature_names"]
            self._metrics = model_data.get("metrics", {})
            self._is_trained = model_data.get("is_trained", False)

            logger.info(f"模型已从 {path} 加载")
            return True

        except FileNotFoundError:
            logger.error(f"模型文件不存在: {path}")
            return False
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            return False
