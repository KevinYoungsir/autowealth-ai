"""
工具函数模块
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional


def setup_logging(level: str = "INFO") -> logging.Logger:
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("autowealth")


def format_number(value: float, decimals: int = 2) -> str:
    """格式化数字"""
    if abs(value) >= 1e12:
        return f"{value / 1e12:.{decimals}f}T"
    elif abs(value) >= 1e9:
        return f"{value / 1e9:.{decimals}f}B"
    elif abs(value) >= 1e6:
        return f"{value / 1e6:.{decimals}f}M"
    elif abs(value) >= 1e3:
        return f"{value / 1e3:.{decimals}f}K"
    return f"{value:.{decimals}f}"


def format_price(price: float, currency: str = "$") -> str:
    """格式化价格"""
    return f"{currency}{price:,.2f}"


def format_pct(value: float) -> str:
    """格式化百分比"""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """安全除法"""
    if denominator == 0:
        return default
    return numerator / denominator


def validate_symbol(symbol: str) -> bool:
    """验证股票代码格式"""
    symbol = symbol.strip().upper()
    if not symbol or len(symbol) > 20:
        return False
    return True


def timestamp_now() -> str:
    """获取当前时间戳字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
