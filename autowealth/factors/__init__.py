"""
A 股多因子研究评分模块。
"""

from autowealth.factors.composite import combine_factor_scores
from autowealth.factors.low_vol import low_vol_factor
from autowealth.factors.momentum import momentum_factor
from autowealth.factors.overbought_oversold import overbought_oversold_factor
from autowealth.factors.quality import quality_factor
from autowealth.factors.schema import CompositeFactorScore, FactorScore
from autowealth.factors.value import value_factor

__all__ = [
    "CompositeFactorScore",
    "FactorScore",
    "combine_factor_scores",
    "low_vol_factor",
    "momentum_factor",
    "overbought_oversold_factor",
    "quality_factor",
    "value_factor",
]

