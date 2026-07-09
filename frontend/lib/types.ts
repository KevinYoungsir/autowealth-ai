export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  mock_mode: boolean;
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
