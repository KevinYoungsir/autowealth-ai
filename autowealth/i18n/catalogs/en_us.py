"""English (United States) deterministic report catalog."""

MESSAGES = {
    "persisted_unknown": "Technical note (source preserved): {source}",
    "research_boundary": (
        "This report is for research and education only. It is not investment "
        "advice, a trading instruction, or a return promise; historical results "
        "do not determine future performance."
    ),
    "benchmark_reason_missing": "No benchmark reason was persisted.",
    "benchmark_unavailable_summary": (
        "The persisted benchmark is unavailable; no benchmark return is "
        "inferred or fabricated."
    ),
    "benchmark_available_summary": (
        "Persisted benchmark metrics are available for deterministic review."
    ),
    "benchmark_partial_summary": (
        "Only part of the requested benchmark set is available."
    ),
    "benchmark_relative_limitation": (
        "Relative performance cannot be assessed while the benchmark is unavailable."
    ),
    "performance_available_summary": (
        "Performance values are reproduced from metrics.json and are not "
        "re-estimated by the report endpoint."
    ),
    "performance_unavailable_summary": (
        "No persisted core performance metric is available."
    ),
    "performance_observation": "{label} ({name})={value:.6f}",
    "metric_annualized_return": "Annualized return",
    "metric_total_return": "Total return",
    "metric_max_drawdown": "Maximum drawdown",
    "metric_volatility": "Volatility",
    "metric_sharpe_ratio": "Sharpe ratio",
    "metric_calmar_ratio": "Calmar ratio",
    "metric_turnover": "Turnover",
    "performance_limitation": (
        "Metrics reflect the persisted backtest period, assumptions and data coverage only."
    ),
    "macro_available_summary": (
        "Persisted macro observations were available to the research run."
    ),
    "macro_neutral_summary": (
        "No persisted macro observation was available; the run disclosed a neutral fallback."
    ),
    "macro_missing_limitation": (
        "Macro-cycle interpretation is limited because no as-of observation was persisted."
    ),
    "risk_run_title": "Research run is not complete",
    "risk_run_description": (
        "The persisted run_status is {run_status} and must remain visible."
    ),
    "risk_run_review": (
        "Resolve or explicitly accept every persisted run-status reason before comparison."
    ),
    "risk_benchmark_title": "Benchmark comparison is incomplete",
    "risk_benchmark_description": (
        "The persisted benchmark status is {benchmark_status}."
    ),
    "risk_benchmark_review": (
        "Restore a compatible benchmark artifact before drawing relative-performance conclusions."
    ),
    "risk_warnings_title": "Persisted warnings require review",
    "risk_warnings_description": "The run contains {warning_count} persisted warnings.",
    "risk_warnings_review": (
        "Review warning categories and original warning text; do not infer missing observations."
    ),
    "risk_warning_mismatch_title": "Warning counts differ",
    "risk_warning_mismatch_description": (
        "The manifest warning count differs from warnings.json."
    ),
    "risk_warning_mismatch_review": (
        "Reconcile artifact generation before treating the run as internally consistent."
    ),
    "risk_price_title": "Candidate price coverage is incomplete",
    "risk_price_description": "Persisted price coverage is {price_coverage:.2%}.",
    "risk_price_review": (
        "Assess how excluded symbols alter universe representativeness and portfolio concentration."
    ),
    "risk_macro_title": "Macro input used a neutral fallback",
    "risk_macro_description": "No macro observation was persisted for the run.",
    "risk_macro_review": (
        "Treat macro-regime interpretation as unavailable, not neutral evidence."
    ),
    "risk_holdings_title": "One or more rebalances are below min_holdings",
    "risk_holdings_description": (
        "Persisted holding counts do not satisfy the configured minimum."
    ),
    "risk_holdings_review": (
        "Review concentration and the data exclusions that reduced eligible holdings."
    ),
    "risk_factor_title": "Configured factor coverage is insufficient",
    "risk_factor_description": (
        "At least one persisted factor coverage ratio is below the run threshold."
    ),
    "risk_factor_review": (
        "Use saved availability and effective weights; never replace missing factors with fabricated values."
    ),
    "factor_empty_summary": (
        "The persisted factor snapshot artifact contains no records."
    ),
    "factor_insufficient_summary": (
        "Persisted factor snapshots contain one or more coverage ratios below "
        "the configured threshold. Missing values are not converted into "
        "fabricated scores by this report."
    ),
    "factor_available_summary": (
        "Persisted factor snapshots and coverage are available for review."
    ),
    "factor_limitation": (
        "Factor comparability depends on point-in-time input coverage and saved effective weights."
    ),
    "data_quality_warnings_summary": (
        "The run contains {warning_count} persisted warnings; all original warning "
        "strings are included in this response."
    ),
    "data_quality_empty_summary": (
        "warnings.json contains no persisted warning strings."
    ),
    "executive_summary": (
        "Run {run_id} is preserved as {run_status}. The report is a deterministic "
        "review of persisted artifacts and does not replace the underlying research evidence."
    ),
    "observation_run_status": "Run status: {run_status}",
    "observation_benchmark_status": "Benchmark status: {benchmark_status}",
    "observation_warning_count": "Warning count: {warning_count}",
    "counter_universe_topic": "Universe representativeness",
    "counter_universe_argument": (
        "A fixed or incompletely covered universe can make the historical portfolio "
        "look more robust than a point-in-time investable universe."
    ),
    "counter_universe_evidence_1": "historical constituent membership",
    "counter_universe_evidence_2": "delisting and ST history",
    "counter_universe_evidence_3": "failed-symbol attribution",
    "counter_universe_assumption_1": "survivorship bias",
    "counter_universe_assumption_2": "investable universe",
    "counter_universe_value": (
        "Tests whether results depend on today's surviving securities."
    ),
    "counter_factor_topic": "Data availability and factor degradation",
    "counter_factor_argument": (
        "Factor scores based on reduced inputs may not be comparable across symbols "
        "or rebalance dates even when weights are re-normalized."
    ),
    "counter_factor_evidence_1": "factor coverage by rebalance",
    "counter_factor_evidence_2": "effective composite weights",
    "counter_factor_evidence_3": "point-in-time fundamental availability",
    "counter_factor_assumption_1": "factor comparability",
    "counter_factor_assumption_2": "missing-data handling",
    "counter_factor_value": "Separates model behavior from changing data coverage.",
    "counter_execution_topic": "Execution realism",
    "counter_execution_argument": (
        "Persisted trades do not prove that all historical orders were executable "
        "under exact suspension, price-limit and liquidity conditions."
    ),
    "counter_execution_evidence_1": "historical suspension state",
    "counter_execution_evidence_2": "price-limit state",
    "counter_execution_evidence_3": "capacity and volume constraints",
    "counter_execution_assumption_1": "fill availability",
    "counter_execution_assumption_2": "transaction-cost realism",
    "counter_execution_value": (
        "Challenges whether backtest fills could have occurred as modeled."
    ),
    "counter_benchmark_topic": "Missing benchmark context",
    "counter_benchmark_argument": (
        "Absolute performance cannot establish relative value when the requested benchmark is unavailable."
    ),
    "counter_benchmark_evidence_1": "compatible benchmark curve",
    "counter_benchmark_evidence_2": "benchmark metrics",
    "counter_benchmark_assumption_1": "relative performance",
    "counter_benchmark_assumption_2": "market regime comparison",
    "counter_benchmark_value": (
        "Prevents absolute returns from being interpreted without market context."
    ),
    "counter_macro_topic": "Macro regime not observed",
    "counter_macro_argument": (
        "A neutral fallback is an absence-of-data treatment, not evidence that the macro environment was neutral."
    ),
    "counter_macro_evidence_1": "as-of macro observations",
    "counter_macro_evidence_2": "publication dates",
    "counter_macro_assumption_1": "macro multiplier",
    "counter_macro_assumption_2": "regime interpretation",
    "counter_macro_value": (
        "Avoids assigning economic meaning to a fallback value."
    ),
}

PERSISTED_MESSAGES: dict[str, str] = {}

WARNING_CATEGORY_LABELS = {
    "fundamental_data": "Fundamental data",
    "point_in_time": "Point-in-time consistency",
    "macro_data": "Macro data",
    "universe_bias": "Universe bias",
    "portfolio_constraints": "Portfolio constraints",
    "factor_coverage": "Factor coverage",
    "benchmark": "Benchmark data",
    "price_provider": "Price provider",
    "price_quality": "Price quality",
    "system": "System",
}

WARNING_CATEGORY_MESSAGES = {
    category: "Review the original technical warning."
    for category in WARNING_CATEGORY_LABELS
}
