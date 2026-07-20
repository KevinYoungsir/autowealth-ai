import type { DeepSeekReport, ResearchResult } from "@/lib/types";
import { ui } from "./index";

function percent(value: unknown): string {
  const number = typeof value === "number" ? value : Number(value);
  return Number.isFinite(number)
    ? new Intl.NumberFormat("zh-CN", {
        style: "percent",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(number)
    : "--";
}

export function localizeMockReport(
  report: DeepSeekReport,
  result: ResearchResult
): DeepSeekReport {
  const selectedCount = result.selected_symbols.length;
  const cashWeight = Math.max(
    0,
    1 - Object.values(result.target_weights).reduce((sum, weight) => sum + weight, 0)
  );

  return {
    ...report,
    research_note: {
      ...report.research_note,
      title: ui.mock.summaryTitle,
      summary: ui.mock.summary(
        result.experiment_name,
        selectedCount,
        percent(cashWeight)
      ),
      key_points: [
        ui.mock.researchWindow(result.start_date, result.end_date),
        ui.mock.selectedCount(selectedCount),
        ui.mock.annualizedReturn(percent(result.backtest_metrics.annualized_return)),
        ui.mock.maxDrawdown(percent(result.backtest_metrics.max_drawdown)),
        ui.mock.macroRegime(String(result.macro_summary.regime ?? "not_provided"))
      ],
      limitations: [...ui.mock.limitations]
    },
    risk_flags: report.risk_flags.map((flag) => ({
      ...flag,
      description:
        ui.mock.riskDescriptions[
          flag.category as keyof typeof ui.mock.riskDescriptions
        ] ?? ui.mock.genericRiskDescription,
      review_focus:
        ui.mock.riskFocus[
          flag.category as keyof typeof ui.mock.riskFocus
        ] ?? ui.mock.genericRiskFocus
    })),
    counter_arguments: report.counter_arguments.map((item) => {
      const localized =
        ui.mock.counterarguments[
          item.topic as keyof typeof ui.mock.counterarguments
        ];
      if (!localized) return item;
      return {
        ...item,
        topic: localized.topic,
        argument: localized.argument,
        evidence_needed: [...localized.evidence],
        research_value: localized.value
      };
    })
  };
}
