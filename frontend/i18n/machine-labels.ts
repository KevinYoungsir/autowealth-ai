import type { AppLocale } from "./types";

export type MachineLabelGroup =
  | "dataSource"
  | "runStatus"
  | "availability"
  | "generatedMode"
  | "serviceStatus"
  | "reportStatus"
  | "severity"
  | "warningCategory"
  | "factor"
  | "macroRegime";

const zhCNLabels: Record<MachineLabelGroup, Record<string, string>> = {
  dataSource: {
    real_artifacts: "真实研究数据",
    mock_demo: "演示数据",
    api_unavailable: "API 暂不可用"
  },
  runStatus: {
    partial_success: "部分完成",
    success: "完成",
    failed: "失败",
    demo: "演示运行",
    unavailable: "暂不可用"
  },
  availability: {
    available: "可用",
    unavailable: "暂不可用",
    partial: "部分可用"
  },
  generatedMode: {
    deterministic: "确定性生成",
    mock: "演示生成",
    unavailable: "暂不可用"
  },
  serviceStatus: {
    running: "运行正常",
    ok: "正常",
    degraded: "服务降级",
    unavailable: "暂不可用",
    unknown: "状态未知"
  },
  reportStatus: {
    available: "可用",
    unavailable: "暂不可用",
    partial: "部分可用",
    neutral_fallback: "中性回退（缺少数据）",
    insufficient_coverage: "覆盖不足",
    warnings_present: "存在警告",
    no_persisted_warnings: "无已落盘警告",
    research_only: "仅限研究",
    partial_success: "部分完成",
    success: "完成",
    failed: "失败"
  },
  severity: {
    info: "信息",
    low: "低风险",
    medium: "中风险",
    high: "高风险",
    critical: "严重风险"
  },
  warningCategory: {
    fundamental_data: "基本面数据",
    point_in_time: "时点一致性",
    macro_data: "宏观数据",
    universe_bias: "股票池偏差",
    portfolio_constraints: "组合约束",
    factor_coverage: "因子覆盖",
    benchmark: "基准数据",
    price_provider: "行情数据源",
    price_quality: "行情质量",
    system: "系统",
    drawdown: "历史回撤",
    concentration: "集中度",
    cash_weight: "现金权重",
    pipeline_warnings: "流水线警告",
    general_review: "综合复核",
    run_status: "运行状态",
    data_quality: "数据质量",
    consistency: "一致性",
    price_data: "行情数据",
    factor_data: "因子数据"
  },
  factor: {
    value: "价值因子",
    quality: "质量因子",
    momentum: "动量因子",
    low_vol: "低波因子",
    overbought_oversold: "超买超卖因子",
    composite: "综合因子"
  },
  macroRegime: {
    expansion: "扩张",
    slowdown: "放缓",
    recession: "衰退",
    recovery: "复苏",
    stagflation: "滞胀",
    uncertain: "不确定",
    not_provided: "未提供"
  }
};

const enUSLabels: typeof zhCNLabels = Object.fromEntries(
  Object.entries(zhCNLabels).map(([group, values]) => [
    group,
    Object.fromEntries(Object.keys(values).map((value) => [value, value]))
  ])
) as typeof zhCNLabels;

export function machineLabel(
  group: MachineLabelGroup,
  value: string,
  locale: AppLocale = "zh-CN"
): string {
  const catalog = locale === "zh-CN" ? zhCNLabels : enUSLabels;
  return catalog[group][value] ?? value;
}

const zhCNRunReasons: Record<string, string> = {
  "required price or rebalance coverage is empty": "必要的行情或调仓覆盖为空。",
  "one or more candidate price series are unavailable": "至少一只候选股票的行情序列不可用。",
  "one or more benchmarks are unavailable": "至少一个基准不可用。",
  "benchmark unavailable": "基准数据不可用。",
  "macro data is empty and the neutral multiplier is used": "由于缺少可用宏观数据，本次研究使用中性回退值。",
  "one or more rebalances are below min_holdings": "至少一个调仓日的持仓数低于 min_holdings。",
  "one or more configured factors have insufficient coverage": "至少一个配置因子的覆盖率不足。"
};

export function runReasonLabel(value: string, locale: AppLocale = "zh-CN"): string {
  if (locale === "en-US") return value;
  return zhCNRunReasons[value] ?? "该运行存在需要复核的技术限制。";
}

export { zhCNLabels, enUSLabels };
