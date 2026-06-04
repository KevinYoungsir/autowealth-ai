"""
AutoWealth AI - 实时预警系统测试

使用 pytest 对 AlertMonitor 和 AlertNotifier 的所有方法进行全面测试，
包括规则管理、预警触发、通知发送和异常处理。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock yfinance 以避免安装依赖
sys.modules["yfinance"] = MagicMock()

import numpy as np
import pandas as pd
import pytest

from autowealth.alerts.monitor import Alert, AlertMonitor, AlertRule
from autowealth.alerts.notifier import AlertNotifier, NotificationRecord


# ============================================================
# 测试数据工厂
# ============================================================

def make_market_data(rows=30, last_close=155.0, last_volume=5000000, seed=42):
    """
    创建模拟市场数据。

    Args:
        rows: 数据行数
        last_close: 最后一天的收盘价
        last_volume: 最后一天的成交量
        seed: 随机种子

    Returns:
        包含 Open, High, Low, Close, Volume 列的 DataFrame
    """
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start="2024-01-01", periods=rows, freq="B")

    # 生成从100到last_close的价格序列
    prices = np.linspace(100, last_close, rows) + rng.randn(rows) * 0.5

    # 生成正常成交量，最后一天使用指定成交量
    volumes = rng.randint(1000000, 3000000, rows).astype(float)
    volumes[-1] = last_volume

    df = pd.DataFrame({
        "Open": prices + rng.randn(rows) * 0.3,
        "High": prices + np.abs(rng.randn(rows)),
        "Low": prices - np.abs(rng.randn(rows)),
        "Close": prices,
        "Volume": volumes,
    }, index=dates)

    return df


def make_macd_data(golden_cross=False, death_cross=False):
    """
    创建包含MACD指标的数据，用于测试指标交叉预警。

    Args:
        golden_cross: 是否包含金叉信号
        death_cross: 是否包含死叉信号

    Returns:
        包含 MACD, MACD_Signal 列的 DataFrame
    """
    dates = pd.date_range(start="2024-01-01", periods=5, freq="B")

    if golden_cross:
        # MACD从下方穿越Signal: iloc[-2] MACD <= Signal, iloc[-1] MACD > Signal
        macd = [0.1, 0.2, -0.1, -0.2, 0.3]
        signal = [0.3, 0.2, 0.1, 0.0, -0.1]
    elif death_cross:
        # MACD从上方穿越Signal: iloc[-2] MACD >= Signal, iloc[-1] MACD < Signal
        macd = [0.1, 0.2, 0.1, 0.2, -0.3]
        signal = [-0.1, -0.1, 0.0, 0.0, -0.1]
    else:
        # 无交叉
        macd = [0.1, 0.2, 0.3, 0.4, 0.5]
        signal = [0.0, 0.1, 0.2, 0.3, 0.4]

    df = pd.DataFrame({
        "Close": [100, 101, 102, 103, 104],
        "Volume": [1000000] * 5,
        "MACD": macd,
        "MACD_Signal": signal,
    }, index=dates)

    return df


# ============================================================
# 测试：AlertRule 数据类
# ============================================================

class TestAlertRule:

    def test_alert_rule_creation(self):
        """测试创建 AlertRule"""
        rule = AlertRule(symbol="AAPL", rule_type="price_above", params={"threshold": 150})
        assert rule.symbol == "AAPL"
        assert rule.rule_type == "price_above"
        assert rule.params == {"threshold": 150}
        assert rule.active is True
        assert rule.id  # 应有自动生成的ID

    def test_alert_rule_default_active(self):
        """测试默认 active 为 True"""
        rule = AlertRule()
        assert rule.active is True

    def test_alert_rule_unique_id(self):
        """测试每条规则的ID唯一"""
        rule1 = AlertRule()
        rule2 = AlertRule()
        assert rule1.id != rule2.id


# ============================================================
# 测试：Alert 数据类
# ============================================================

class TestAlert:

    def test_alert_creation(self):
        """测试创建 Alert"""
        alert = Alert(
            rule_id="rule-1",
            symbol="AAPL",
            message="价格突破150",
            severity="warning",
        )
        assert alert.rule_id == "rule-1"
        assert alert.symbol == "AAPL"
        assert alert.message == "价格突破150"
        assert alert.severity == "warning"
        assert alert.id  # 应有自动生成的ID

    def test_alert_data_snapshot(self):
        """测试 Alert 数据快照"""
        alert = Alert(data_snapshot={"price": 155.0})
        assert alert.data_snapshot == {"price": 155.0}


# ============================================================
# 测试：规则添加/移除
# ============================================================

class TestRuleManagement:

    def test_add_price_above_rule(self):
        """测试添加价格高于规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        assert rule_id
        rules = monitor.get_active_rules()
        assert len(rules) == 1
        assert rules[0].rule_type == "price_above"

    def test_add_price_below_rule(self):
        """测试添加价格低于规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "price_below", {"threshold": 90})
        assert rule_id
        rules = monitor.get_active_rules()
        assert len(rules) == 1

    def test_add_pct_change_rule(self):
        """测试添加涨跌幅规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "pct_change", {"threshold": 5.0})
        assert rule_id
        assert len(monitor.get_active_rules()) == 1

    def test_add_volume_spike_rule(self):
        """测试添加成交量异常规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "volume_spike", {"multiplier": 2.0})
        assert rule_id
        assert len(monitor.get_active_rules()) == 1

    def test_add_indicator_cross_rule(self):
        """测试添加指标交叉规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule(
            "AAPL", "indicator_cross",
            {"indicator": "MACD", "cross_type": "golden"}
        )
        assert rule_id
        assert len(monitor.get_active_rules()) == 1

    def test_add_invalid_rule_type_raises(self):
        """测试添加不支持的规则类型应抛出 ValueError"""
        monitor = AlertMonitor()
        with pytest.raises(ValueError, match="不支持的规则类型"):
            monitor.add_rule("AAPL", "invalid_type", {})

    def test_remove_rule(self):
        """测试移除规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        result = monitor.remove_rule(rule_id)
        assert result is True
        assert len(monitor.get_active_rules()) == 0

    def test_remove_nonexistent_rule(self):
        """测试移除不存在的规则返回 False"""
        monitor = AlertMonitor()
        result = monitor.remove_rule("nonexistent-id")
        assert result is False

    def test_add_multiple_rules(self):
        """测试添加多条规则"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        monitor.add_rule("AAPL", "price_below", {"threshold": 90})
        monitor.add_rule("GOOG", "pct_change", {"threshold": 5.0})
        assert len(monitor.get_active_rules()) == 3

    def test_get_active_rules_excludes_inactive(self):
        """测试获取活跃规则排除非活跃规则"""
        monitor = AlertMonitor()
        rule_id = monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        monitor._rules[rule_id].active = False
        assert len(monitor.get_active_rules()) == 0


# ============================================================
# 测试：价格预警触发
# ============================================================

class TestPriceAlerts:

    def test_price_above_triggered(self):
        """测试价格高于阈值时触发预警"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150, "message": "价格突破150"})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert alerts[0].symbol == "AAPL"
        assert "150" in alerts[0].message

    def test_price_above_not_triggered(self):
        """测试价格未超过阈值时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 200})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0

    def test_price_below_triggered(self):
        """测试价格低于阈值时触发预警"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_below", {"threshold": 90, "message": "价格跌破90"})
        data = make_market_data(last_close=85.0)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert alerts[0].symbol == "AAPL"

    def test_price_below_not_triggered(self):
        """测试价格未低于阈值时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_below", {"threshold": 90})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0

    def test_price_alert_severity(self):
        """测试价格预警的严重程度"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert alerts[0].severity == "warning"

    def test_price_alert_data_snapshot(self):
        """测试价格预警包含数据快照"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert "price" in alerts[0].data_snapshot
        assert "threshold" in alerts[0].data_snapshot


# ============================================================
# 测试：涨跌幅预警触发
# ============================================================

class TestPctChangeAlerts:

    def test_pct_change_up_triggered(self):
        """测试涨幅超过阈值时触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "pct_change", {"threshold": 5.0, "direction": "up"})
        # 构造涨幅超过5%的数据
        data = make_market_data(rows=30, last_close=200.0)
        # 确保最后两天涨幅超过5%
        data.loc[data.index[-2], "Close"] = 150.0
        data.loc[data.index[-1], "Close"] = 160.0  # 6.67%涨幅
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1

    def test_pct_change_down_triggered(self):
        """测试跌幅超过阈值时触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "pct_change", {"threshold": 5.0, "direction": "down"})
        data = make_market_data(rows=30, last_close=80.0)
        data.loc[data.index[-2], "Close"] = 150.0
        data.loc[data.index[-1], "Close"] = 140.0  # 6.67%跌幅
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1

    def test_pct_change_any_triggered(self):
        """测试任意方向涨跌幅超过阈值时触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "pct_change", {"threshold": 3.0, "direction": "any"})
        data = make_market_data(rows=30, last_close=80.0)
        data.loc[data.index[-2], "Close"] = 150.0
        data.loc[data.index[-1], "Close"] = 140.0
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1

    def test_pct_change_not_triggered(self):
        """测试涨跌幅未超过阈值时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "pct_change", {"threshold": 10.0, "direction": "up"})
        data = make_market_data(rows=30, last_close=155.0)
        data.loc[data.index[-2], "Close"] = 150.0
        data.loc[data.index[-1], "Close"] = 152.0  # 1.33%涨幅
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0

    def test_pct_change_critical_severity(self):
        """测试大幅涨跌幅预警严重程度为 critical"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "pct_change", {"threshold": 5.0, "direction": "any"})
        data = make_market_data(rows=30, last_close=80.0)
        data.loc[data.index[-2], "Close"] = 150.0
        data.loc[data.index[-1], "Close"] = 130.0  # 13.3%跌幅
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert alerts[0].severity == "critical"


# ============================================================
# 测试：成交量异常预警
# ============================================================

class TestVolumeSpikeAlerts:

    def test_volume_spike_triggered(self):
        """测试成交量异常放大时触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "volume_spike", {"multiplier": 2.0})
        data = make_market_data(rows=30, last_volume=10000000)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert "volume_ratio" in alerts[0].data_snapshot

    def test_volume_spike_not_triggered(self):
        """测试成交量正常时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "volume_spike", {"multiplier": 5.0})
        data = make_market_data(rows=30, last_volume=2000000)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0

    def test_volume_spike_insufficient_data(self):
        """测试数据不足时成交量预警不触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "volume_spike", {"multiplier": 2.0})
        data = make_market_data(rows=5, last_volume=10000000)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0


# ============================================================
# 测试：指标交叉预警
# ============================================================

class TestIndicatorCrossAlerts:

    def test_macd_golden_cross_triggered(self):
        """测试MACD金叉触发"""
        monitor = AlertMonitor()
        monitor.add_rule(
            "AAPL", "indicator_cross",
            {"indicator": "MACD", "cross_type": "golden", "message": "MACD金叉"}
        )
        data = make_macd_data(golden_cross=True)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert "MACD" in alerts[0].message

    def test_macd_death_cross_triggered(self):
        """测试MACD死叉触发"""
        monitor = AlertMonitor()
        monitor.add_rule(
            "AAPL", "indicator_cross",
            {"indicator": "MACD", "cross_type": "death", "message": "MACD死叉"}
        )
        data = make_macd_data(death_cross=True)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 1
        assert alerts[0].severity == "warning"

    def test_macd_no_cross_not_triggered(self):
        """测试无交叉时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule(
            "AAPL", "indicator_cross",
            {"indicator": "MACD", "cross_type": "golden"}
        )
        data = make_macd_data(golden_cross=False, death_cross=False)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0

    def test_indicator_cross_missing_columns(self):
        """测试缺少MACD列时不触发"""
        monitor = AlertMonitor()
        monitor.add_rule(
            "AAPL", "indicator_cross",
            {"indicator": "MACD", "cross_type": "golden"}
        )
        data = make_market_data(rows=30)
        alerts = monitor.check_alerts(data)
        assert len(alerts) == 0


# ============================================================
# 测试：check_alerts 边界情况
# ============================================================

class TestCheckAlertsEdgeCases:

    def test_check_alerts_with_none(self):
        """测试传入 None 返回空列表"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        alerts = monitor.check_alerts(None)
        assert alerts == []

    def test_check_alerts_with_empty_dataframe(self):
        """测试传入空 DataFrame 返回空列表"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        alerts = monitor.check_alerts(pd.DataFrame())
        assert alerts == []

    def test_check_alerts_no_rules(self):
        """测试无规则时返回空列表"""
        monitor = AlertMonitor()
        data = make_market_data(rows=30, last_close=155.0)
        alerts = monitor.check_alerts(data)
        assert alerts == []

    def test_check_alerts_multiple_rules_trigger(self):
        """测试多条规则同时触发"""
        monitor = AlertMonitor()
        monitor.add_rule("AAPL", "price_above", {"threshold": 150})
        monitor.add_rule("AAPL", "price_below", {"threshold": 200})
        data = make_market_data(last_close=155.0)
        alerts = monitor.check_alerts(data)
        # 价格155 > 150 (price_above触发) 且 155 < 200 (price_below触发)
        assert len(alerts) == 2


# ============================================================
# 测试：通知发送
# ============================================================

class TestAlertNotifier:

    def test_init_default_channels(self):
        """测试默认通知渠道为 console"""
        notifier = AlertNotifier()
        assert "console" in notifier.channels

    def test_init_custom_channels(self):
        """测试自定义通知渠道"""
        notifier = AlertNotifier(channels=["console", "webhook"])
        assert "console" in notifier.channels
        assert "webhook" in notifier.channels

    def test_send_console_notification(self, capsys):
        """测试控制台通知发送"""
        notifier = AlertNotifier(channels=["console"])
        alert = Alert(
            symbol="AAPL",
            message="价格突破150",
            severity="warning",
        )
        results = notifier.send(alert)
        assert results["console"] is True
        captured = capsys.readouterr()
        assert "ALERT" in captured.out
        assert "AAPL" in captured.out

    def test_send_email_not_supported(self):
        """测试邮件通知返回即将支持"""
        notifier = AlertNotifier(channels=["email"])
        alert = Alert(symbol="AAPL", message="测试")
        results = notifier.send(alert)
        assert results["email"] is False

    def test_add_webhook(self):
        """测试添加webhook"""
        notifier = AlertNotifier()
        result = notifier.add_webhook(
            "https://oapi.dingtalk.com/robot/send?access_token=test",
            "dingtalk"
        )
        assert result is True

    def test_add_webhook_invalid_url(self):
        """测试添加无效URL的webhook"""
        notifier = AlertNotifier()
        result = notifier.add_webhook("invalid-url", "test")
        assert result is False

    def test_add_webhook_empty_params(self):
        """测试添加空参数的webhook"""
        notifier = AlertNotifier()
        assert notifier.add_webhook("", "test") is False
        assert notifier.add_webhook("https://example.com", "") is False

    def test_remove_webhook(self):
        """测试移除webhook"""
        notifier = AlertNotifier()
        notifier.add_webhook("https://example.com/webhook", "test")
        result = notifier.remove_webhook("test")
        assert result is True

    def test_remove_nonexistent_webhook(self):
        """测试移除不存在的webhook"""
        notifier = AlertNotifier()
        result = notifier.remove_webhook("nonexistent")
        assert result is False

    def test_webhook_send_with_mock(self):
        """测试webhook发送（使用mock）"""
        notifier = AlertNotifier(channels=["webhook"])
        notifier.add_webhook("https://oapi.dingtalk.com/robot/send?token=test", "dingtalk")

        alert = Alert(symbol="AAPL", message="价格突破150", severity="warning")

        with patch("autowealth.alerts.notifier.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            results = notifier.send(alert)
            assert results["webhook"] is True
            mock_post.assert_called_once()

    def test_webhook_send_failure(self):
        """测试webhook发送失败"""
        notifier = AlertNotifier(channels=["webhook"])
        notifier.add_webhook("https://example.com/webhook", "test")

        alert = Alert(symbol="AAPL", message="测试")

        with patch("autowealth.alerts.notifier.requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection error")

            results = notifier.send(alert)
            assert results["webhook"] is False

    def test_webhook_no_webhooks_configured(self):
        """测试未配置webhook时发送返回False"""
        notifier = AlertNotifier(channels=["webhook"])
        alert = Alert(symbol="AAPL", message="测试")
        results = notifier.send(alert)
        assert results["webhook"] is False

    def test_notification_history(self):
        """测试通知历史记录"""
        notifier = AlertNotifier(channels=["console"])
        alert = Alert(symbol="AAPL", message="测试")
        notifier.send(alert)
        history = notifier.get_notification_history()
        assert len(history) == 1
        assert history[0].channel == "console"
        assert history[0].alert_id == alert.id

    def test_clear_history(self):
        """测试清空通知历史"""
        notifier = AlertNotifier(channels=["console"])
        alert = Alert(symbol="AAPL", message="测试")
        notifier.send(alert)
        assert len(notifier.get_notification_history()) == 1
        notifier.clear_history()
        assert len(notifier.get_notification_history()) == 0

    def test_multi_channel_send(self):
        """测试多渠道同时发送"""
        notifier = AlertNotifier(channels=["console", "email"])
        alert = Alert(symbol="AAPL", message="测试")
        results = notifier.send(alert)
        assert len(results) == 2
        assert "console" in results
        assert "email" in results

    def test_send_records_on_failure(self):
        """测试发送失败时记录错误"""
        notifier = AlertNotifier(channels=["email"])
        alert = Alert(symbol="AAPL", message="测试")
        notifier.send(alert)
        history = notifier.get_notification_history()
        assert len(history) == 1
        assert history[0].success is False
        assert history[0].error != ""

    def test_dingtalk_webhook_payload_format(self):
        """测试钉钉webhook payload格式"""
        notifier = AlertNotifier(channels=["webhook"])
        notifier.add_webhook("https://oapi.dingtalk.com/robot/send?token=xxx", "dingtalk")

        alert = Alert(symbol="AAPL", message="测试消息", severity="warning")

        with patch("autowealth.alerts.notifier.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            notifier.send(alert)
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
            assert payload["msgtype"] == "text"
            assert "text" in payload

    def test_slack_webhook_payload_format(self):
        """测试Slack webhook payload格式"""
        notifier = AlertNotifier(channels=["webhook"])
        notifier.add_webhook("https://hooks.slack.com/services/xxx", "slack")

        alert = Alert(symbol="AAPL", message="测试消息", severity="warning")

        with patch("autowealth.alerts.notifier.requests.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            notifier.send(alert)
            call_args = mock_post.call_args
            payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
            assert "text" in payload
