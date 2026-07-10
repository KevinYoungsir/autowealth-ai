"""
Offline research experiment orchestration.
"""

from autowealth.research.mock_data import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_macro_regime,
    mock_portfolio_constraints,
    mock_price_data,
)
from autowealth.research.pipeline import run_research_pipeline
from autowealth.research.report import summarize_research_result
from autowealth.research.real_pipeline import (
    RealDataAccessError,
    RealResearchConfig,
    RealResearchError,
    RealResearchResult,
    load_real_research_config,
    run_real_data_research,
)
from autowealth.research.schema import (
    ResearchExperimentConfig,
    ResearchPipelineResult,
    ResearchSummary,
)

__all__ = [
    "ResearchExperimentConfig",
    "ResearchPipelineResult",
    "ResearchSummary",
    "RealDataAccessError",
    "RealResearchConfig",
    "RealResearchError",
    "RealResearchResult",
    "load_real_research_config",
    "mock_candidate_symbols",
    "mock_factor_scores",
    "mock_industries",
    "mock_macro_regime",
    "mock_portfolio_constraints",
    "mock_price_data",
    "run_research_pipeline",
    "run_real_data_research",
    "summarize_research_result",
]

