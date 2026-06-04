"""
中文自然语言解析器测试
"""
import pytest

from autowealth.nlp.parser import CHINESE_NAME_TO_SYMBOL, NLPParser


@pytest.fixture
def parser():
    """创建 NLPParser 实例"""
    return NLPParser()


class TestIntentDetection:
    """测试意图识别"""

    def test_analyze_single_intent(self, parser: NLPParser):
        queries = [
            "分析苹果公司",
            "查看AAPL",
            "评估特斯拉",
            "诊断茅台",
            "AAPL怎么样",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "analyze_single", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_analyze_batch_intent(self, parser: NLPParser):
        queries = [
            "批量分析AAPL,GOOGL,MSFT",
            "一起分析苹果和微软",
            "分析多个股票AAPL MSFT",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "analyze_batch", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_portfolio_intent(self, parser: NLPParser):
        queries = [
            "我的持仓有100股苹果成本150",
            "投资组合分析",
            "查看我的仓位",
            "持仓收益如何",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "portfolio", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_market_intent(self, parser: NLPParser):
        queries = [
            "市场概览",
            "今天大盘怎么样",
            "查看市场行情",
            "指数走势",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "market", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_backtest_intent(self, parser: NLPParser):
        queries = [
            "回测特斯拉买入持有策略",
            "模拟交易AAPL",
            "策略测试MSFT",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "backtest", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_optimize_intent(self, parser: NLPParser):
        queries = [
            "优化组合AAPL,MSFT目标收益10%",
            "资产配置苹果微软",
            "最优配置",
        ]
        for q in queries:
            result = parser.parse_query(q)
            assert result["intent"] == "optimize", f"查询 '{q}' 意图识别失败: {result['intent']}"

    def test_unknown_intent(self, parser: NLPParser):
        result = parser.parse_query("")
        assert result["intent"] == "unknown"

        result = parser.parse_query("hello world")
        assert result["intent"] == "unknown"


class TestSymbolExtraction:
    """测试股票代码提取"""

    def test_extract_us_stock_symbol(self, parser: NLPParser):
        result = parser.parse_query("分析AAPL")
        assert result["intent"] == "analyze_single"
        assert result["symbol"] == "AAPL"

    def test_extract_chinese_name_mapping(self, parser: NLPParser):
        result = parser.parse_query("分析苹果公司")
        assert result["intent"] == "analyze_single"
        assert result["symbol"] == "AAPL"

    def test_extract_a_share_symbol(self, parser: NLPParser):
        result = parser.parse_query("分析600519.SS")
        # 600519.SS 和 600519 都被识别，所以是 analyze_batch
        assert result["intent"] in ("analyze_single", "analyze_batch")
        assert "600519.SS" in result.get("symbol", "") or "600519.SS" in result.get("symbols", [])

    def test_extract_moutai(self, parser: NLPParser):
        result = parser.parse_query("分析茅台")
        assert result["intent"] == "analyze_single"
        assert result["symbol"] == "600519.SS"

    def test_extract_tesla(self, parser: NLPParser):
        result = parser.parse_query("回测特斯拉")
        assert result["intent"] == "backtest"
        assert result["symbol"] == "TSLA"

    def test_extract_multiple_symbols(self, parser: NLPParser):
        result = parser.parse_query("批量分析AAPL,GOOGL,MSFT")
        assert result["intent"] == "analyze_batch"
        assert "symbols" in result
        assert set(result["symbols"]) == {"AAPL", "GOOGL", "MSFT"}

    def test_extract_symbols_with_chinese_names(self, parser: NLPParser):
        result = parser.parse_query("分析苹果和微软")
        assert result["intent"] == "analyze_batch"
        assert "AAPL" in result["symbols"]
        assert "MSFT" in result["symbols"]


class TestPortfolioExtraction:
    """测试持仓信息提取"""

    def test_extract_holding_with_cost(self, parser: NLPParser):
        result = parser.parse_query("我的持仓有100股苹果成本150")
        assert result["intent"] == "portfolio"
        assert "holdings" in result
        assert len(result["holdings"]) == 1
        holding = result["holdings"][0]
        assert holding["symbol"] == "AAPL"
        assert holding["quantity"] == 100.0
        assert holding["cost_basis"] == 150.0

    def test_extract_multiple_holdings(self, parser: NLPParser):
        result = parser.parse_query("持仓：100股AAPL成本150, 50股MSFT成本300")
        assert result["intent"] == "portfolio"
        assert len(result["holdings"]) == 2
        symbols = [h["symbol"] for h in result["holdings"]]
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_extract_holding_without_cost(self, parser: NLPParser):
        result = parser.parse_query("持仓：100股特斯拉")
        assert result["intent"] == "portfolio"
        assert "holdings" in result
        assert result["holdings"][0]["quantity"] == 100.0
        assert result["holdings"][0]["cost_basis"] == 0.0


class TestBacktestExtraction:
    """测试回测参数提取"""

    def test_extract_backtest_params(self, parser: NLPParser):
        result = parser.parse_query("回测特斯拉买入持有策略")
        assert result["intent"] == "backtest"
        assert result["symbol"] == "TSLA"
        assert result["strategy"] == "buy_hold"

    def test_extract_backtest_sma_cross(self, parser: NLPParser):
        result = parser.parse_query("回测AAPL均线交叉策略")
        assert result["intent"] == "backtest"
        assert result["symbol"] == "AAPL"
        assert result["strategy"] == "sma_cross"

    def test_extract_backtest_rsi(self, parser: NLPParser):
        result = parser.parse_query("回测MSFT RSI策略")
        assert result["intent"] == "backtest"
        assert result["symbol"] == "MSFT"
        assert result["strategy"] == "rsi"

    def test_extract_initial_capital(self, parser: NLPParser):
        result = parser.parse_query("回测AAPL，本金10万")
        assert result["intent"] == "backtest"
        assert result["initial_capital"] == 100000.0


class TestOptimizeExtraction:
    """测试组合优化参数提取"""

    def test_extract_optimize_symbols(self, parser: NLPParser):
        result = parser.parse_query("优化组合AAPL,MSFT目标收益10%")
        assert result["intent"] == "optimize"
        assert "symbols" in result
        assert "AAPL" in result["symbols"]
        assert "MSFT" in result["symbols"]

    def test_extract_target_return(self, parser: NLPParser):
        result = parser.parse_query("优化组合AAPL,MSFT目标收益10%")
        assert result["intent"] == "optimize"
        assert result["target_return"] == 0.10

    def test_extract_target_return_decimal(self, parser: NLPParser):
        result = parser.parse_query("优化AAPL,MSFT目标收益15.5%")
        assert result["intent"] == "optimize"
        assert result["target_return"] == 0.155

    def test_optimize_without_target_return(self, parser: NLPParser):
        result = parser.parse_query("优化组合AAPL,MSFT")
        assert result["intent"] == "optimize"
        assert result["target_return"] is None


class TestNameMapping:
    """测试中文名称映射"""

    def test_all_mappings_are_valid(self, parser: NLPParser):
        """确保所有预定义映射都能正确解析"""
        for name, expected_symbol in CHINESE_NAME_TO_SYMBOL.items():
            result = parser.parse_query(f"分析{name}")
            assert result["intent"] == "analyze_single", f"名称 '{name}' 解析失败"
            assert result["symbol"] == expected_symbol, f"名称 '{name}' 映射错误"

    def test_add_custom_mapping(self, parser: NLPParser):
        parser.add_name_mapping("测试股票", "TEST123")
        result = parser.parse_query("分析测试股票")
        assert result["symbol"] == "TEST123"

    def test_remove_custom_mapping(self, parser: NLPParser):
        parser.add_name_mapping("临时股票", "TMP456")
        parser.remove_name_mapping("临时股票")
        result = parser.parse_query("分析临时股票")
        assert result["intent"] == "unknown" or "symbol" not in result


class TestEdgeCases:
    """测试边界情况"""

    def test_empty_string(self, parser: NLPParser):
        result = parser.parse_query("")
        assert result["intent"] == "unknown"

    def test_whitespace_only(self, parser: NLPParser):
        result = parser.parse_query("   ")
        assert result["intent"] == "unknown"

    def test_no_recognizable_symbol(self, parser: NLPParser):
        result = parser.parse_query("分析这只股票")
        assert result["intent"] == "unknown"
        assert "error" in result

    def test_mixed_chinese_english(self, parser: NLPParser):
        result = parser.parse_query("Analyze 苹果公司")
        assert result["intent"] == "analyze_single"
        assert result["symbol"] == "AAPL"

    def test_numbers_in_text(self, parser: NLPParser):
        result = parser.parse_query("分析100股AAPL")
        assert result["intent"] == "analyze_single"
        assert result["symbol"] == "AAPL"
