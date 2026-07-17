export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  mock_mode: boolean;
  research_runs_available: boolean;
  latest_run_available: boolean;
};

export type EquityPoint = {
  date: string;
  equity: number;
};

export type ResearchResult = {
  experiment_name: string;
  start_date: string;
  end_date: string;
  candidate_symbols: string[];
  selected_symbols: string[];
  rejected_symbols: Record<string, string>;
  factor_summary: Record<string, any>;
  macro_summary: Record<string, any>;
  target_weights: Record<string, number>;
  backtest_metrics: Record<string, number | string | null>;
  equity_curve: EquityPoint[];
  warnings: string[];
  explanation: string;
};

export type ResearchSummary = ResearchResult;

export type DemoResponse = {
  mock_mode: boolean;
  result: ResearchResult;
  summary: ResearchSummary;
  explanation: string;
};

export type RiskFlag = {
  category: string;
  severity: string;
  description: string;
  evidence: Record<string, any>;
  review_focus: string;
};

export type CounterArgument = {
  topic: string;
  argument: string;
  evidence_needed: string[];
  affected_assumptions: string[];
  research_value: string;
};

export type DeepSeekReport = {
  research_note: {
    title: string;
    summary: string;
    key_points: string[];
    limitations: string[];
    evidence: Record<string, any>;
    warnings: string[];
  };
  risk_flags: RiskFlag[];
  counter_arguments: CounterArgument[];
  validation_result: Record<string, any>;
  metadata: Record<string, any>;
  warnings: string[];
};

export type ArtifactReportSection = {
  status: string;
  summary: string;
  evidence: Record<string, any>;
  observations: string[];
  limitations: string[];
};

export type ArtifactRiskFlag = RiskFlag & {
  code: string;
  title: string;
};

export type RealResearchReport = {
  run_id: string;
  data_source: "real_artifacts";
  generated_mode: "deterministic";
  run_status: RunStatus;
  benchmark_status: string;
  warning_count: number;
  executive_summary: ArtifactReportSection;
  performance_review: ArtifactReportSection;
  risk_flags: ArtifactRiskFlag[];
  factor_review: ArtifactReportSection;
  benchmark_review: ArtifactReportSection;
  macro_review: ArtifactReportSection;
  data_quality_review: ArtifactReportSection;
  counterarguments: CounterArgument[];
  research_boundaries: ArtifactReportSection;
};

export type ResearchReport = DeepSeekReport | RealResearchReport;

export type ResearchDataSource =
  | "real_artifacts"
  | "mock_demo"
  | "api_unavailable";

export type RunStatus = "success" | "partial_success" | "failed";

export type FactorCoverage = {
  available_count: number;
  missing_count: number;
  coverage_ratio: number;
};

export type ResearchRunSummary = {
  run_id: string;
  run_time: string;
  experiment_name: string;
  run_status: RunStatus;
  start_date: string;
  end_date: string;
  annualized_return: number | null;
  total_return: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  benchmark_status: string;
  warning_count: number;
  price_coverage_ratio: number | null;
  factor_coverage_overall: Record<string, FactorCoverage>;
};

export type ResearchRunListResponse = {
  data_source: "real_artifacts";
  count: number;
  runs: ResearchRunSummary[];
};

export type WarningSummary = {
  total: number;
  categories: Record<string, number>;
  samples: Record<string, string[]>;
  raw_warnings: string[];
  raw_returned: number;
  raw_truncated: boolean;
};

export type ResearchRunDetail = {
  data_source: "real_artifacts";
  summary: ResearchRunSummary;
  manifest: Record<string, any>;
  metrics: Record<string, any>;
  benchmark_metrics: Record<string, any>;
  warning_summary: WarningSummary;
};

export type ResearchEquityCurveResponse = {
  data_source: "real_artifacts";
  run_id: string;
  total_points: number;
  returned_points: number;
  downsample: number;
  points: EquityPoint[];
};

export type HoldingRecord = {
  rebalance_date: string;
  symbol: string;
  weight: number;
  shares: number | null;
  cash_weight: number | null;
  cash: number | null;
  equity: number | null;
};

export type ResearchHoldingsResponse = {
  data_source: "real_artifacts";
  run_id: string;
  records: HoldingRecord[];
  returned: number;
  min_holdings: number | null;
  holdings_count_by_rebalance: Record<string, number>;
};

export type ResearchFactorsResponse = {
  data_source: "real_artifacts";
  run_id: string;
  records: Array<Record<string, any>>;
  returned: number;
  coverage_by_rebalance: Record<string, Record<string, FactorCoverage>>;
  coverage_overall: Record<string, FactorCoverage>;
};

export type ResearchWarningsResponse = {
  data_source: "real_artifacts";
  run_id: string;
  summary: WarningSummary;
};

export type ResearchBenchmarkCurveResponse = {
  data_source: "real_artifacts";
  run_id: string;
  status: string;
  reasons: Record<string, string>;
  total_points: number;
  returned_points: number;
  downsample: number;
  points: Array<Record<string, number | string | null>>;
};
