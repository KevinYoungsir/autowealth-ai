"""
预警通知模块 - 提供多渠道预警通知发送能力

支持控制台输出、Webhook（钉钉/飞书/Slack）和邮件（预留接口）。
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

from autowealth.alerts.monitor import Alert

logger = logging.getLogger(__name__)


@dataclass
class NotificationRecord:
    """通知记录数据类"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = ""
    alert_id: str = ""
    message: str = ""
    sent_at: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: str = ""


class AlertNotifier:
    """预警通知器

    支持多通知渠道发送预警通知。

    支持的渠道:
        - console: 打印到控制台
        - webhook: 发送HTTP POST（支持钉钉/飞书/Slack webhook URL）
        - email: 预留接口（返回"即将支持"）

    Args:
        channels: 启用的通知渠道列表
    """

    def __init__(self, channels: Optional[List[str]] = None):
        """初始化预警通知器

        Args:
            channels: 启用的通知渠道列表，默认为 ["console"]
        """
        self.channels = channels if channels is not None else ["console"]
        self._webhooks: Dict[str, str] = {}  # name -> url
        self._history: List[NotificationRecord] = []

    def send(self, alert: Alert) -> Dict[str, bool]:
        """发送预警通知到所有启用的渠道

        Args:
            alert: 预警对象

        Returns:
            各渠道发送结果的字典 {channel: success}
        """
        results = {}

        for channel in self.channels:
            try:
                if channel == "console":
                    success = self._send_console(alert)
                elif channel == "webhook":
                    success = self._send_webhook(alert)
                elif channel == "email":
                    success = self._send_email(alert)
                else:
                    logger.warning(f"未知的通知渠道: {channel}")
                    success = False

                results[channel] = success

                self._history.append(NotificationRecord(
                    channel=channel,
                    alert_id=alert.id,
                    message=alert.message,
                    success=success,
                    error="" if success else f"渠道 {channel} 发送失败",
                ))

            except Exception as e:
                logger.error(f"通过 {channel} 发送通知失败: {e}")
                results[channel] = False
                self._history.append(NotificationRecord(
                    channel=channel,
                    alert_id=alert.id,
                    message=alert.message,
                    success=False,
                    error=str(e),
                ))

        return results

    def _send_console(self, alert: Alert) -> bool:
        """通过控制台发送通知"""
        try:
            timestamp = alert.triggered_at
            severity_str = f"[{alert.severity.upper()}]"
            print(f"[ALERT] {timestamp} {severity_str} {alert.symbol}: {alert.message}")
            return True
        except Exception as e:
            logger.error(f"控制台通知发送失败: {e}")
            return False

    def _send_webhook(self, alert: Alert) -> bool:
        """通过Webhook发送通知

        支持钉钉、飞书、Slack等webhook格式。
        根据URL自动判断格式。
        """
        try:
            if not self._webhooks:
                logger.warning("未配置任何webhook地址")
                return False

            all_success = True

            for name, url in self._webhooks.items():
                try:
                    payload = self._build_webhook_payload(alert, url)

                    response = requests.post(
                        url,
                        json=payload,
                        timeout=10,
                        headers={"Content-Type": "application/json"},
                    )

                    if response.status_code == 200:
                        logger.info(f"Webhook通知已发送到 {name}")
                    else:
                        logger.warning(
                            f"Webhook {name} 返回状态码: {response.status_code}"
                        )
                        all_success = False

                except requests.RequestException as e:
                    logger.error(f"Webhook {name} 发送失败: {e}")
                    all_success = False

            return all_success

        except Exception as e:
            logger.error(f"Webhook通知发送失败: {e}")
            return False

    def _build_webhook_payload(self, alert: Alert, url: str) -> Dict[str, Any]:
        """根据URL构建对应的webhook payload

        Args:
            alert: 预警对象
            url: webhook URL

        Returns:
            请求payload字典
        """
        parsed = urlparse(url)

        # 钉钉webhook
        if "dingtalk" in parsed.netloc or "oapi.dingtalk" in url:
            return {
                "msgtype": "text",
                "text": {
                    "content": (
                        f"[AutoWealth预警] {alert.symbol}\n"
                        f"级别: {alert.severity}\n"
                        f"消息: {alert.message}\n"
                        f"时间: {alert.triggered_at}"
                    )
                },
            }

        # 飞书webhook
        if "feishu" in parsed.netloc or "open.feishu" in url or "lark" in parsed.netloc:
            return {
                "msg_type": "text",
                "content": {
                    "text": (
                        f"[AutoWealth预警] {alert.symbol}\n"
                        f"级别: {alert.severity}\n"
                        f"消息: {alert.message}\n"
                        f"时间: {alert.triggered_at}"
                    )
                },
            }

        # Slack webhook
        if "slack" in parsed.netloc or "hooks.slack" in url:
            return {
                "text": (
                    f"[AutoWealth Alert] {alert.symbol} | "
                    f"Severity: {alert.severity} | "
                    f"Message: {alert.message}"
                ),
            }

        # 默认格式（通用JSON）
        return {
            "symbol": alert.symbol,
            "severity": alert.severity,
            "message": alert.message,
            "triggered_at": alert.triggered_at,
            "data_snapshot": alert.data_snapshot,
        }

    def _send_email(self, alert: Alert) -> bool:
        """邮件通知（预留接口）

        Args:
            alert: 预警对象

        Returns:
            始终返回 False（即将支持）
        """
        logger.info("邮件通知功能即将支持")
        return False

    def add_webhook(self, url: str, name: str) -> bool:
        """添加webhook地址

        Args:
            url: webhook URL
            name: webhook名称（用于标识）

        Returns:
            是否添加成功
        """
        try:
            if not url or not name:
                return False

            # 简单验证URL格式
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                logger.warning(f"无效的webhook URL: {url}")
                return False

            self._webhooks[name] = url
            logger.info(f"添加webhook: {name} -> {url}")
            return True

        except Exception as e:
            logger.error(f"添加webhook失败: {e}")
            return False

    def remove_webhook(self, name: str) -> bool:
        """移除webhook地址

        Args:
            name: webhook名称

        Returns:
            是否成功移除
        """
        if name in self._webhooks:
            del self._webhooks[name]
            return True
        return False

    def get_notification_history(self) -> List[NotificationRecord]:
        """获取通知历史

        Returns:
            通知记录列表
        """
        return self._history.copy()

    def clear_history(self) -> None:
        """清空通知历史"""
        self._history.clear()
