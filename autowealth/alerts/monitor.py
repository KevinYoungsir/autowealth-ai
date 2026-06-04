"""
实时预警监控模块 - 提供灵活的价格和指标预警规则管理

支持价格突破、涨跌幅、成交量异常、指标交叉等多种预警类型。
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class AlertRule:
    """预警规则数据类

    Attributes:
        id: 规则唯一标识
        symbol: 标的代码
        rule_type: 规则类型 (price_above, price_below, pct_change, volume_spike, indicator_cross)
        params: 规则参数字典
        created_at: 创建时间
        active: 是否活跃
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    rule_type: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    active: bool = True


@dataclass
class Alert:
    """预警通知数据类

    Attributes:
        id: 预警唯一标识
        rule_id: 触发的规则ID
        symbol: 标的代码
        message: 预警消息
        severity: 严重程度 (info, warning, critical)
        triggered_at: 触发时间
        data_snapshot: 触发时的数据快照
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str = ""
    symbol: str = ""
    message: str = ""
    severity: str = "info"
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    data_snapshot: Dict[str, Any] = field(default_factory=dict)


class AlertMonitor:
    """预警监控器

    管理预警规则，检查数据是否触发预警条件。

    支持的规则类型:
        - price_above: 价格高于阈值
        - price_below: 价格低于阈值
        - pct_change: 涨跌幅超过阈值
        - volume_spike: 成交量异常放大
        - indicator_cross: 指标交叉（如MACD金叉/死叉）
    """

    SUPPORTED_RULE_TYPES = {
        "price_above",
        "price_below",
        "pct_change",
        "volume_spike",
        "indicator_cross",
    }

    def __init__(self):
        """初始化预警监控器"""
        self._rules: Dict[str, AlertRule] = {}

    def add_rule(self, symbol: str, rule_type: str, params: Dict[str, Any]) -> str:
        """添加预警规则

        Args:
            symbol: 标的代码
            rule_type: 规则类型
            params: 规则参数
                - price_above/price_below: {"threshold": 150, "message": "价格突破150"}
                - pct_change: {"threshold": 5.0, "direction": "up", "message": "涨幅超过5%"}
                - volume_spike: {"multiplier": 2.0, "message": "成交量异常放大"}
                - indicator_cross: {"indicator": "MACD", "cross_type": "golden", "message": "MACD金叉"}

        Returns:
            规则ID

        Raises:
            ValueError: 规则类型不支持时
        """
        try:
            if rule_type not in self.SUPPORTED_RULE_TYPES:
                raise ValueError(
                    f"不支持的规则类型: {rule_type}，"
                    f"支持: {', '.join(self.SUPPORTED_RULE_TYPES)}"
                )

            rule = AlertRule(
                symbol=symbol,
                rule_type=rule_type,
                params=params,
            )
            self._rules[rule.id] = rule

            logger.info(
                f"添加预警规则: {rule.id} | {symbol} | {rule_type} | {params}"
            )
            return rule.id

        except Exception as e:
            logger.error(f"添加预警规则失败: {e}")
            raise

    def remove_rule(self, rule_id: str) -> bool:
        """移除预警规则

        Args:
            rule_id: 规则ID

        Returns:
            是否成功移除
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            logger.info(f"移除预警规则: {rule_id}")
            return True
        logger.warning(f"规则不存在: {rule_id}")
        return False

    def check_alerts(self, data: pd.DataFrame) -> List[Alert]:
        """检查数据是否触发预警

        Args:
            data: 包含市场数据的 DataFrame（至少包含 Close 列）

        Returns:
            触发的预警列表
        """
        try:
            if data is None or len(data) < 2:
                return []

            alerts = []

            for rule_id, rule in self._rules.items():
                if not rule.active:
                    continue

                triggered_alerts = self._check_single_rule(rule, data)
                alerts.extend(triggered_alerts)

            return alerts

        except Exception as e:
            logger.error(f"检查预警失败: {e}")
            return []

    def _check_single_rule(self, rule: AlertRule, data: pd.DataFrame) -> List[Alert]:
        """检查单条规则是否触发"""
        alerts = []

        try:
            if rule.rule_type == "price_above":
                alert = self._check_price_above(rule, data)
            elif rule.rule_type == "price_below":
                alert = self._check_price_below(rule, data)
            elif rule.rule_type == "pct_change":
                alert = self._check_pct_change(rule, data)
            elif rule.rule_type == "volume_spike":
                alert = self._check_volume_spike(rule, data)
            elif rule.rule_type == "indicator_cross":
                alert = self._check_indicator_cross(rule, data)
            else:
                return alerts

            if alert is not None:
                alerts.append(alert)

        except Exception as e:
            logger.error(f"检查规则 {rule.id} 失败: {e}")

        return alerts

    def _check_price_above(self, rule: AlertRule, data: pd.DataFrame) -> Optional[Alert]:
        """检查价格是否高于阈值"""
        if "Close" not in data.columns:
            return None

        threshold = rule.params.get("threshold", float("inf"))
        current_price = data["Close"].iloc[-1]

        if current_price > threshold:
            return Alert(
                rule_id=rule.id,
                symbol=rule.symbol,
                message=rule.params.get(
                    "message",
                    f"{rule.symbol} 价格突破 {threshold}，当前 {current_price:.2f}"
                ),
                severity="warning",
                data_snapshot={"price": current_price, "threshold": threshold},
            )
        return None

    def _check_price_below(self, rule: AlertRule, data: pd.DataFrame) -> Optional[Alert]:
        """检查价格是否低于阈值"""
        if "Close" not in data.columns:
            return None

        threshold = rule.params.get("threshold", 0)
        current_price = data["Close"].iloc[-1]

        if current_price < threshold:
            return Alert(
                rule_id=rule.id,
                symbol=rule.symbol,
                message=rule.params.get(
                    "message",
                    f"{rule.symbol} 价格跌破 {threshold}，当前 {current_price:.2f}"
                ),
                severity="warning",
                data_snapshot={"price": current_price, "threshold": threshold},
            )
        return None

    def _check_pct_change(self, rule: AlertRule, data: pd.DataFrame) -> Optional[Alert]:
        """检查涨跌幅是否超过阈值"""
        if "Close" not in data.columns or len(data) < 2:
            return None

        threshold = rule.params.get("threshold", 5.0)
        direction = rule.params.get("direction", "any")  # up, down, any
        current_price = data["Close"].iloc[-1]
        prev_price = data["Close"].iloc[-2]

        pct_change = (current_price - prev_price) / prev_price * 100

        triggered = False
        if direction == "up" and pct_change > threshold:
            triggered = True
        elif direction == "down" and pct_change < -threshold:
            triggered = True
        elif direction == "any" and abs(pct_change) > threshold:
            triggered = True

        if triggered:
            direction_str = "上涨" if pct_change > 0 else "下跌"
            return Alert(
                rule_id=rule.id,
                symbol=rule.symbol,
                message=rule.params.get(
                    "message",
                    f"{rule.symbol} {direction_str} {abs(pct_change):.2f}%，超过阈值 {threshold}%"
                ),
                severity="warning" if abs(pct_change) < 10 else "critical",
                data_snapshot={
                    "price": current_price,
                    "prev_price": prev_price,
                    "pct_change": pct_change,
                },
            )
        return None

    def _check_volume_spike(self, rule: AlertRule, data: pd.DataFrame) -> Optional[Alert]:
        """检查成交量是否异常放大"""
        if "Volume" not in data.columns or len(data) < 20:
            return None

        multiplier = rule.params.get("multiplier", 2.0)
        current_volume = data["Volume"].iloc[-1]
        avg_volume = data["Volume"].iloc[-20:-1].mean()

        if avg_volume == 0:
            return None

        volume_ratio = current_volume / avg_volume

        if volume_ratio > multiplier:
            return Alert(
                rule_id=rule.id,
                symbol=rule.symbol,
                message=rule.params.get(
                    "message",
                    f"{rule.symbol} 成交量异常放大 {volume_ratio:.1f} 倍"
                ),
                severity="info",
                data_snapshot={
                    "volume": current_volume,
                    "avg_volume": avg_volume,
                    "volume_ratio": volume_ratio,
                },
            )
        return None

    def _check_indicator_cross(self, rule: AlertRule, data: pd.DataFrame) -> Optional[Alert]:
        """检查指标交叉"""
        indicator = rule.params.get("indicator", "MACD")
        cross_type = rule.params.get("cross_type", "golden")  # golden or death

        if indicator == "MACD":
            # 需要MACD和MACD_Signal列
            if "MACD" not in data.columns or "MACD_Signal" not in data.columns:
                return None

            if len(data) < 2:
                return None

            current_macd = data["MACD"].iloc[-1]
            current_signal = data["MACD_Signal"].iloc[-1]
            prev_macd = data["MACD"].iloc[-2]
            prev_signal = data["MACD_Signal"].iloc[-2]

            # 金叉：MACD从下方穿越Signal
            if cross_type == "golden":
                if prev_macd <= prev_signal and current_macd > current_signal:
                    return Alert(
                        rule_id=rule.id,
                        symbol=rule.symbol,
                        message=rule.params.get("message", f"{rule.symbol} MACD金叉"),
                        severity="info",
                        data_snapshot={
                            "macd": current_macd,
                            "signal": current_signal,
                        },
                    )
            # 死叉：MACD从上方穿越Signal
            elif cross_type == "death":
                if prev_macd >= prev_signal and current_macd < current_signal:
                    return Alert(
                        rule_id=rule.id,
                        symbol=rule.symbol,
                        message=rule.params.get("message", f"{rule.symbol} MACD死叉"),
                        severity="warning",
                        data_snapshot={
                            "macd": current_macd,
                            "signal": current_signal,
                        },
                    )

        return None

    def get_active_rules(self) -> List[AlertRule]:
        """获取所有活跃规则

        Returns:
            活跃规则列表
        """
        return [rule for rule in self._rules.values() if rule.active]

    def get_all_rules(self) -> Dict[str, AlertRule]:
        """获取所有规则（包括非活跃的）

        Returns:
            规则字典
        """
        return self._rules.copy()
