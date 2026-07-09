"""
Run one offline research pipeline experiment with mock data.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autowealth.agents.deepseek_research_agent import DeepSeekResearchAgent
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


def main():
    result = run_research_pipeline(
        candidate_symbols=mock_candidate_symbols(),
        factor_scores=mock_factor_scores(),
        macro_regime=mock_macro_regime(),
        portfolio_constraints=mock_portfolio_constraints(),
        price_data=mock_price_data(),
        industries=mock_industries(),
        start_date="2020-01-01",
        end_date="2024-12-31",
        experiment_name="mock_a_share_research_pipeline",
    )
    summary = summarize_research_result(result)

    print("Target weights:")
    print(result.target_weights)
    print("\nBacktest metrics:")
    print(result.backtest_metrics)
    print("\nResearch summary:")
    print(
        {
            "experiment_name": summary.experiment_name,
            "selected_symbols": summary.selected_symbols,
            "cash_weight": summary.backtest_metrics["cash_weight"],
            "macro_summary": summary.macro_summary,
            "warnings": summary.warnings,
        }
    )

    agent = DeepSeekResearchAgent(mock_mode=True)
    research_note = agent.summarize_research_result(result)
    risk_review = agent.analyze_risk_flags(result)
    print("\nMock DeepSeek research note:")
    print(json.dumps(research_note, ensure_ascii=False, indent=2))
    print("\nMock DeepSeek risk review:")
    print(json.dumps(risk_review, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
