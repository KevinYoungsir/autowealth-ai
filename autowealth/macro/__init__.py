"""
宏观经济周期与外部风险研究评分模块。
"""

from autowealth.macro.asof import (
    MacroAsOfResult,
    load_macro_asof_csv,
    select_macro_asof,
)
from autowealth.macro.data_loader import load_macro_csv, latest_macro_indicators
from autowealth.macro.position import equity_position_multiplier
from autowealth.macro.regime import classify_macro_regime
from autowealth.macro.schema import MacroIndicator, MacroRegime, MacroRiskScore
from autowealth.macro.scoring import macro_dimension_scores, score_macro_environment

__all__ = [
    "MacroIndicator",
    "MacroAsOfResult",
    "MacroRegime",
    "MacroRiskScore",
    "classify_macro_regime",
    "equity_position_multiplier",
    "latest_macro_indicators",
    "load_macro_asof_csv",
    "load_macro_csv",
    "macro_dimension_scores",
    "score_macro_environment",
    "select_macro_asof",
]

