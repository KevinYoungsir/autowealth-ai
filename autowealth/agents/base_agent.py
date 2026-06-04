"""
鍩虹鏅鸿兘浣撶被 - 鎵€鏈夋姇璧勬櫤鑳戒綋鐨勫熀绫?"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentSignal(BaseModel):
    """鏅鸿兘浣撲俊鍙?""
    agent_name: str
    signal_type: str  # buy, sell, hold, watch
    confidence: float  # 0-100
    reasoning: str
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon: str = "medium"  # short, medium, long
    metadata: Dict[str, Any] = {}


class BaseAgent(ABC):
    """鍩虹鏅鸿兘浣?""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"autowealth.agents.{name}")

    @abstractmethod
    def analyze(self, symbol: str, data: Dict[str, Any]) -> AgentSignal:
        """
        鍒嗘瀽骞剁敓鎴愪氦鏄撲俊鍙?
        Args:
            symbol: 鑲＄エ浠ｇ爜
            data: 鍖呭惈鎵€鏈夌浉鍏虫暟鎹殑瀛楀吀

        Returns:
            AgentSignal瀵硅薄
        """
        pass

    def validate_data(self, data: Dict[str, Any], required_keys: List[str]) -> bool:
        """楠岃瘉鏁版嵁鏄惁鍖呭惈蹇呴渶鐨勯敭"""
        for key in required_keys:
            if key not in data or data[key] is None:
                self.logger.warning(f"缂哄皯蹇呰鏁版嵁: {key}")
                return False
        return True

    def calculate_confidence(self, factors: List[float], weights: Optional[List[float]] = None) -> float:
        """璁＄畻鍔犳潈缃俊搴?""
        if not factors:
            return 50.0

        if weights is None:
            weights = [1.0] * len(factors)

        if len(factors) != len(weights):
            raise ValueError("鍥犵礌鍜屾潈閲嶆暟閲忎笉鍖归厤")

        weighted_sum = sum(f * w for f, w in zip(factors, weights))
        total_weight = sum(weights)

        confidence = weighted_sum / total_weight if total_weight > 0 else 50.0
        return max(0.0, min(100.0, confidence))
