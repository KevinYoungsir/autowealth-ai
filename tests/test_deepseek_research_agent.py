import copy
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

from autowealth.agents.deepseek_research_agent import DeepSeekResearchAgent
from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_macro_regime,
    mock_portfolio_constraints,
    mock_price_data,
    run_research_pipeline,
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
        experiment_name="mock_deepseek_research_agent",
        rebalance_frequency="yearly",
    )


def assert_no_forbidden_phrases(payload):
    text = json.dumps(payload, ensure_ascii=False, default=str)
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in text


def test_summary_output_fields_are_complete():
    agent = DeepSeekResearchAgent(mock_mode=True)
    summary = agent.summarize_research_result(make_result())

    assert set(summary) >= {"title", "summary", "key_points", "limitations", "evidence", "warnings"}
    assert isinstance(summary["key_points"], list)
    assert isinstance(summary["evidence"], dict)
    assert_no_forbidden_phrases(summary)


def test_risk_flag_output_fields_are_complete():
    agent = DeepSeekResearchAgent(mock_mode=True)
    risk_review = agent.analyze_risk_flags(make_result())

    assert set(risk_review) >= {"risk_flags", "warnings", "metadata"}
    assert risk_review["risk_flags"]
    first_flag = risk_review["risk_flags"][0]
    assert set(first_flag) >= {"category", "severity", "description", "evidence", "review_focus"}
    assert_no_forbidden_phrases(risk_review)


def test_counter_argument_output_fields_are_complete():
    agent = DeepSeekResearchAgent(mock_mode=True)
    counter_review = agent.generate_counter_arguments(make_result())

    assert set(counter_review) >= {"counter_arguments", "metadata"}
    assert counter_review["counter_arguments"]
    first_argument = counter_review["counter_arguments"][0]
    assert set(first_argument) >= {
        "topic",
        "argument",
        "evidence_needed",
        "affected_assumptions",
        "research_value",
    }
    assert_no_forbidden_phrases(counter_review)


def test_validation_output_fields_are_complete():
    agent = DeepSeekResearchAgent(mock_mode=True)
    validation = agent.validate_research_consistency(make_result())

    assert set(validation) >= {
        "is_consistent",
        "checks",
        "issues",
        "warnings",
        "target_weights_unchanged",
    }
    assert validation["target_weights_unchanged"] is True
    assert "target_weight_sum_lte_one" in validation["checks"]
    assert_no_forbidden_phrases(validation)


def test_mock_mode_does_not_access_network():
    agent = DeepSeekResearchAgent(mock_mode=True)
    with patch("requests.post", side_effect=AssertionError("network call is not allowed")) as post:
        result = make_result()
        assert agent.summarize_research_result(result)
        assert agent.analyze_risk_flags(result)
        assert agent.generate_counter_arguments(result)
        assert agent.validate_research_consistency(result)

    post.assert_not_called()


def test_target_weights_are_not_modified():
    agent = DeepSeekResearchAgent(mock_mode=True)
    result = make_result()
    original_weights = copy.deepcopy(result.target_weights)

    agent.summarize_research_result(result)
    agent.analyze_risk_flags(result)
    agent.generate_counter_arguments(result)
    validation = agent.validate_research_consistency(result)

    assert result.target_weights == original_weights
    assert validation["target_weights_unchanged"] is True


def test_full_report_is_structured_json():
    agent = DeepSeekResearchAgent(mock_mode=True)
    report = agent.build_research_report(make_result())

    assert set(report) >= {
        "research_note",
        "risk_flags",
        "counter_arguments",
        "validation_result",
        "metadata",
        "warnings",
    }
    json.dumps(report, ensure_ascii=False, default=str)
    assert_no_forbidden_phrases(report)
