import { zhCNMessages } from "./zh-CN";
import type { MessageShape } from "../types";

export const enUSMessages = {
  ...zhCNMessages,
  metadata: {
    title: "AutoWealth A-share Research Dashboard",
    description: "Read-only dashboard for long-horizon A-share portfolio research"
  },
  brand: {
    subtitle: "A-share research cockpit",
    environment: "outlook.xin research prototype",
    context: "Research display · Non-trading system"
  },
  navigation: {
    dashboard: "Dashboard",
    backtest: "Backtest",
    portfolio: "Portfolio",
    factors: "Factors",
    macro: "Macro",
    researchNotes: "Research Notes",
    systemStatus: "System Status"
  },
  common: {
    ...zhCNMessages.common,
    refresh: "Refresh",
    syncing: "Syncing",
    apiOnline: "API online",
    apiPending: "API pending",
    apiUnknown: "Unknown",
    dataSource: "Data source",
    technicalValue: "Technical value",
    selectRun: "Select research run",
    unavailable: "Unavailable",
    noRecords: "No records",
    pendingData: "Waiting for data",
    items: (count: number) => `${count} items`,
    flags: (count: number) => `${count} risk flags`,
    warnings: (count: number) => `${count} warnings`,
    records: (count: number) => `${count} records`,
    candidates: (count: number) => `${count} candidate scores`,
    symbols: (count: number) => `${count} research symbols`,
    dateRange: (start: string, end: string) => `${start} to ${end}`,
    researchBoundary: "This dashboard is for research and education only. Historical metrics do not determine future performance and are not investment advice or trading instructions."
  },
  metrics: {
    annualized_return: "Annualized return",
    total_return: "Total return",
    max_drawdown: "Maximum drawdown",
    volatility: "Volatility",
    sharpe_ratio: "Sharpe ratio",
    calmar_ratio: "Calmar ratio",
    turnover: "Turnover",
    warning_count: "Warning count",
    price_coverage_ratio: "Price coverage",
    factor_coverage_ratio: "Factor coverage",
    rebalance_count: "Rebalance count",
    cash_weight: "Cash weight",
    trade_value: "Trade value",
    total_cost: "Total cost"
  },
  report: {
    ...zhCNMessages.report,
    metadata: {
      dataSource: "Data source",
      runId: "Run ID",
      runStatus: "Run status",
      generatedMode: "Generated mode"
    },
    sections: {
      executiveSummary: "Executive Summary",
      performanceReview: "Performance Review",
      riskFlags: "Risk Flags",
      factorReview: "Factor Review",
      benchmarkReview: "Benchmark Review",
      macroReview: "Macro Review",
      dataQualityReview: "Data Quality Review",
      counterarguments: "Counterarguments",
      researchBoundaries: "Research Boundaries"
    },
    warningOverview: "Warning overview",
    warningSamples: "Display samples",
    viewRawDetails: "View original technical details",
    rawDetails: "Original technical details",
    sourceMessage: "Source message",
    evidenceNeeded: "Evidence needed",
    noRiskFlags: "No structured risk flags.",
    noWarnings: "No persisted warnings.",
    persistedItems: (count: number) => `${count} persisted items`,
    macroObservationCount: "Macro observation count"
  }
} as const satisfies MessageShape<typeof zhCNMessages>;
