import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_macro_regime,
    mock_portfolio_constraints,
    mock_price_data,
    run_research_pipeline,
    summarize_research_result,
)


FORBIDDEN_PHRASES = ["建议买入", "建议卖出", "推荐买入", "推荐卖出", "保证收益"]


def make_result():
    return run_research_pipeline(
        candidate_symbols=mock_candidate_symbols(),
        factor_scores=mock_factor_scores(),
        macro_regime=mock_macro_regime(),
        portfolio_constraints=mock_portfolio_constraints(),
        price_data=mock_price_data(),
        industries=mock_industries(),
        start_date="2020-01-01",
        end_date="2024-12-31",
        experiment_name="mock_research_pipeline",
        rebalance_frequency="yearly",
    )


def test_research_pipeline_outputs_target_weights():
    result = make_result()

    assert result.target_weights
    assert sum(result.target_weights.values()) <= 1.0


def test_research_pipeline_outputs_backtest_metrics():
    result = make_result()

    assert "annualized_return" in result.backtest_metrics
    assert "max_drawdown" in result.backtest_metrics
    assert "sharpe_ratio" in result.backtest_metrics
    assert "calmar_ratio" in result.backtest_metrics


def test_research_pipeline_equity_curve_is_not_empty():
    result = make_result()

    assert not result.equity_curve.empty


def test_rejected_symbols_are_recorded():
    result = make_result()

    assert "600000" in result.rejected_symbols
    assert "score below threshold" in result.rejected_symbols["600000"]


def test_explanation_contains_no_forbidden_trading_language():
    result = make_result()
    summary = summarize_research_result(result)

    text = " ".join([result.explanation, summary.explanation])
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text


def test_pipeline_does_not_access_real_network():
    with patch(
        "autowealth.data.ashare_provider.AShareDataProvider.__init__",
        side_effect=AssertionError("real data provider should not be initialized"),
    ):
        result = make_result()

    assert result.target_weights


def test_research_summary_contains_structured_fields():
    summary = summarize_research_result(make_result())

    assert summary.backtest_metrics["holding_count"] == len(summary.selected_symbols)
    assert "cash_weight" in summary.backtest_metrics
    assert "score_buckets" in summary.factor_summary
    assert "regime" in summary.macro_summary

