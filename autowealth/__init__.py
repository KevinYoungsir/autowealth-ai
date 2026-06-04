"""
AutoWealth AI - 鍩轰簬澶氭櫤鑳戒綋鐨勪釜浜鸿储瀵岀鐞嗕笌鎶曡祫鍐崇瓥寮曟搸

AutoWealth AI 鏄竴娆惧紑婧愮殑鏅鸿兘鎶曡祫鍒嗘瀽宸ュ叿锛岄€氳繃澶氭櫤鑳戒綋鍗忎綔绯荤粺
涓轰釜浜烘姇璧勮€呮彁渚涗笓涓氱殑鎶€鏈垎鏋愩€佸熀鏈潰鍒嗘瀽鍜屽競鍦烘儏缁垎鏋愩€?
Example:
    >>> from autowealth import AutoWealthEngine
    >>> engine = AutoWealthEngine()
    >>> result = engine.analyze("AAPL")
    >>> print(result['decision']['signal_type'])
    'buy'
"""

__version__ = "0.1.0"
__author__ = "AutoWealth Team"
__license__ = "MIT"

from autowealth.core.engine import AutoWealthEngine, batch_analyze, quick_analyze

__all__ = [
    "AutoWealthEngine",
    "quick_analyze",
    "batch_analyze",
]
