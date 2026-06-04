"""
基础智能体类 - 所有投资智能体的基类
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentSignal(BaseModel):
    """智能体信号"""
    agent_name: str
    signal_type: str  # buy, sell, hold, watch
    confidence: float  # 0-100
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str = "medium"  # short, medium, long
    metadata: Dict[str, Any] = {}


class BaseAgent(ABC):
    """基础智能体"""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"autowealth.agents.{name}")

    @abstractmethod
    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        分析并生成交易信号

        Args:
            symbol: 股票代码
            data: 包含所有相关数据的字典

        Returns:
            AgentSignal对象
        """
        pass

    def validate_data(self, data: Dict[str, Any], required_keys: List[str]) -> bool:
        """验证数据是否包含必需的键"""
        for key in required_keys:
            if key not in data or data[key] is None:
                self.logger.warning(f"缺少必要数据: {key}")
                return False
        return True

    def calculate_confidence(self, factors: List[float], weights: Optional[List[float]] = None) -> float:
        """计算加权置信度"""
        if not factors:
            return 50.0

        if weights is None:
            weights = [1.0] * len(factors)

        if len(factors) != len(weights):
            raise ValueError("因素和权重数量不匹配")

        weighted_sum = sum(f * w for f, w in zip(factors, weights))
        total_weight = sum(weights)

        confidence = weighted_sum / total_weight if total_weight > 0 else 50.0
        return max(0.0, min(100.0, confidence))
