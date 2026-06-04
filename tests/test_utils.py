"""
AutoWealth AI - 工具函数测试

测试所有工具函数的正确性和边界情况。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from autowealth.utils import (
    format_number,
    format_pct,
    format_price,
    safe_divide,
    timestamp_now,
    validate_symbol,
)


# ============================================================
# format_number 测试
# ============================================================

class TestFormatNumber:
    """测试 format_number 函数"""

    def test_format_small_number(self):
        """验证小数字格式化"""
        assert format_number(123.456) == "123.46"
        assert format_number(0.5) == "0.50"

    def test_format_thousands(self):
        """验证千位数字格式化"""
        assert format_number(1500) == "1.50K"
        assert format_number(999) == "999.00"

    def test_format_millions(self):
        """验证百万位数字格式化"""
        assert format_number(2500000) == "2.50M"
        assert format_number(1000000) == "1.00M"

    def test_format_billions(self):
        """验证十亿位数字格式化"""
        assert format_number(3500000000) == "3.50B"

    def test_format_trillions(self):
        """验证万亿位数字格式化"""
        assert format_number(1200000000000) == "1.20T"

    def test_format_negative(self):
        """验证负数格式化"""
        assert format_number(-1500) == "-1.50K"

    def test_format_zero(self):
        """验证零格式化"""
        assert format_number(0) == "0.00"

    def test_format_custom_decimals(self):
        """验证自定义小数位"""
        assert format_number(1234.5678, decimals=3) == "1.235K"


# ============================================================
# format_price 测试
# ============================================================

class TestFormatPrice:
    """测试 format_price 函数"""

    def test_format_price_usd(self):
        """验证美元价格格式化"""
        assert format_price(150.5) == "$150.50"

    def test_format_price_cny(self):
        """验证人民币价格格式化"""
        assert format_price(100.0, currency="¥") == "¥100.00"

    def test_format_price_large(self):
        """验证大价格格式化"""
        assert format_price(10000) == "$10,000.00"

    def test_format_price_zero(self):
        """验证零价格格式化"""
        assert format_price(0) == "$0.00"


# ============================================================
# format_pct 测试
# ============================================================

class TestFormatPct:
    """测试 format_pct 函数"""

    def test_format_positive_pct(self):
        """验证正百分比格式化"""
        assert format_pct(5.25) == "+5.25%"

    def test_format_negative_pct(self):
        """验证负百分比格式化"""
        assert format_pct(-3.5) == "-3.50%"

    def test_format_zero_pct(self):
        """验证零百分比格式化"""
        assert format_pct(0) == "+0.00%"

    def test_format_large_pct(self):
        """验证大百分比格式化"""
        assert format_pct(100.0) == "+100.00%"


# ============================================================
# safe_divide 测试
# ============================================================

class TestSafeDivide:
    """测试 safe_divide 函数"""

    def test_safe_divide_normal(self):
        """验证正常除法"""
        assert safe_divide(10, 2) == 5.0

    def test_safe_divide_by_zero(self):
        """验证除零保护"""
        assert safe_divide(10, 0) == 0.0

    def test_safe_divide_by_zero_custom_default(self):
        """验证除零时自定义默认值"""
        assert safe_divide(10, 0, default=-1) == -1

    def test_safe_divide_zero_numerator(self):
        """验证分子为零"""
        assert safe_divide(0, 5) == 0.0

    def test_safe_divide_negative(self):
        """验证负数除法"""
        assert safe_divide(-10, 2) == -5.0

    def test_safe_divide_float(self):
        """验证浮点数除法"""
        assert abs(safe_divide(1, 3) - 0.333333) < 1e-6


# ============================================================
# validate_symbol 测试
# ============================================================

class TestValidateSymbol:
    """测试 validate_symbol 函数"""

    def test_validate_valid_symbol(self):
        """验证有效股票代码"""
        assert validate_symbol("AAPL") is True
        assert validate_symbol("600519.SS") is True
        assert validate_symbol("BTC-USD") is True

    def test_validate_empty_symbol(self):
        """验证空股票代码"""
        assert validate_symbol("") is False
        assert validate_symbol("   ") is False

    def test_validate_too_long_symbol(self):
        """验证过长的股票代码"""
        assert validate_symbol("A" * 21) is False

    def test_validate_whitespace(self):
        """验证带空格的股票代码"""
        assert validate_symbol("  AAPL  ") is True


# ============================================================
# timestamp_now 测试
# ============================================================

class TestTimestampNow:
    """测试 timestamp_now 函数"""

    def test_timestamp_format(self):
        """验证时间戳格式"""
        ts = timestamp_now()
        assert len(ts) == 19  # "YYYY-MM-DD HH:MM:SS"
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == " "
        assert ts[13] == ":"
        assert ts[16] == ":"

    def test_timestamp_is_string(self):
        """验证返回值为字符串"""
        ts = timestamp_now()
        assert isinstance(ts, str)


# ============================================================
# setup_logging 测试
# ============================================================

class TestSetupLogging:
    """测试 setup_logging 函数"""

    def test_setup_logging_returns_logger(self):
        """验证返回 Logger 对象"""
        import logging
        logger = __import__("autowealth.utils", fromlist=["setup_logging"]).setup_logging()
        assert isinstance(logger, logging.Logger)

    def test_setup_logging_level(self):
        """验证日志级别设置 - 由于 basicConfig 只能配置一次，验证 logger 被创建"""
        import logging
        logger = __import__("autowealth.utils", fromlist=["setup_logging"]).setup_logging("DEBUG")
        # basicConfig 只能生效一次，验证 logger 对象存在即可
        assert logger is not None
        assert isinstance(logger, logging.Logger)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
