export const zhCNMessages = {
  metadata: {
    title: "AutoWealth A 股研究看板",
    description: "面向 A 股长期组合研究的只读数据看板"
  },
  brand: {
    subtitle: "A 股组合研究台",
    environment: "outlook.xin 研究原型",
    context: "研究展示 · 非交易系统"
  },
  navigation: {
    dashboard: "研究总览",
    backtest: "回测分析",
    portfolio: "组合持仓",
    factors: "因子分析",
    macro: "宏观环境",
    researchNotes: "研究报告",
    systemStatus: "系统状态"
  },
  common: {
    refresh: "刷新数据",
    syncing: "正在同步",
    apiOnline: "API 运行正常",
    apiPending: "API 等待响应",
    apiUnknown: "状态未知",
    dataSource: "数据来源",
    technicalValue: "技术值",
    selectRun: "选择研究运行",
    unavailable: "暂不可用",
    noRecords: "暂无记录",
    pendingData: "等待数据",
    items: (count: number) => `${count} 项`,
    flags: (count: number) => `${count} 条风险提示`,
    warnings: (count: number) => `${count} 条警告`,
    records: (count: number) => `${count} 条记录`,
    candidates: (count: number) => `${count} 个候选评分`,
    symbols: (count: number) => `${count} 个研究标的`,
    dateRange: (start: string, end: string) => `${start} 至 ${end}`,
    realRunLoaded: (runId: string) => `已读取真实运行 ${runId}`,
    noRealRuns: "API 正常，暂无真实研究运行",
    realRunsDegraded: "真实运行接口不可用，演示接口可用",
    researchApiUnavailable: "研究 API 不可用",
    researchBoundary: "当前看板仅展示研究实验、演示数据与结构化复核结果；历史指标不代表未来表现，不构成投资建议或交易指令。"
  },
  pages: {
    dashboard: {
      eyebrow: "研究总览",
      title: "研究总览",
      realDescription: (name: string) => `${name} 的只读研究 artifacts。`,
      mockDescription: "基于本地演示研究 API 的离线快照。"
    },
    backtest: {
      eyebrow: "回测分析",
      title: "回测分析",
      description: "展示历史样本下的研究指标、权益曲线与基准可用状态。"
    },
    portfolio: {
      eyebrow: "组合持仓",
      title: "组合持仓",
      description: "展示研究目标权重、现金仓位与候选过滤记录。"
    },
    factors: {
      eyebrow: "因子分析",
      title: "因子分析",
      description: "展示多因子综合评分、数据覆盖与候选池分布。"
    },
    macro: {
      eyebrow: "宏观环境",
      title: "宏观环境",
      description: "展示宏观状态、权益仓位系数与外部风险维度。"
    },
    researchNotes: {
      eyebrow: "研究报告",
      realTitle: "真实研究复核报告",
      mockTitle: "演示研究报告",
      unavailableTitle: "研究报告暂不可用",
      realDescription: "基于所选 run_id 已落盘 artifacts 生成的确定性、只读复核。",
      mockDescription: "暂无真实运行时，使用离线演示数据生成结构化复核。",
      unavailableDescription: "研究 API 当前不可用，页面不会把占位内容标记为真实报告。",
      loadingReal: "正在读取所选 run_id 的真实研究复核报告。",
      waitingReal: "真实研究复核报告尚未返回。",
      unavailable: "研究 API 不可用，当前没有可展示的研究报告。",
      mockDisclosure: "当前没有可用的真实运行，页面展示 mock_demo 演示复核；该内容不代表真实 artifacts 的结论。"
    },
    systemStatus: {
      eyebrow: "系统状态",
      title: "部署与数据状态",
      description: "只读检查前端、研究 API 和已落盘运行，不触发研究任务。"
    }
  },
  metrics: {
    annualized_return: "年化收益率",
    total_return: "累计收益率",
    max_drawdown: "最大回撤",
    volatility: "波动率",
    sharpe_ratio: "夏普比率",
    calmar_ratio: "卡玛比率",
    turnover: "换手率",
    warning_count: "警告数量",
    price_coverage_ratio: "行情覆盖率",
    factor_coverage_ratio: "因子覆盖率",
    rebalance_count: "调仓次数",
    cash_weight: "现金权重",
    trade_value: "交易金额",
    total_cost: "总交易成本"
  },
  tables: {
    symbol: "股票代码",
    weight: "权重",
    score: "评分",
    state: "状态",
    shares: "份额",
    rebalanceDate: "调仓日期",
    factor: "因子",
    available: "可用数量",
    missing: "缺失数量",
    coverage: "覆盖率",
    effectiveWeight: "实际权重",
    category: "类别",
    count: "数量"
  },
  panels: {
    equityCurve: "权益曲线",
    realEquityCurve: "真实 artifacts 权益曲线",
    mockEquityCurve: "演示研究权益曲线",
    targetWeights: "目标持仓权重",
    portfolioDetails: "组合明细",
    researchTarget: "研究目标",
    candidateFilters: "候选过滤记录",
    rejectedCandidate: "候选标的未通过筛选",
    originalTechnicalReason: "查看原始技术原因",
    pipelineWarning: "研究流水线提示",
    factorDistribution: "因子分布",
    compositeBuckets: "综合评分区间分布",
    mean: "平均值",
    minimum: "最小值",
    maximum: "最大值",
    scoreRanking: "评分排行",
    macroState: "宏观状态",
    macroSnapshot: "研究状态快照",
    macroDimensions: "宏观维度",
    researchScale: "0–100 研究评分尺度",
    growthDimension: "经济增长",
    inflationDimension: "通胀环境",
    liquidityDimension: "流动性",
    creditDimension: "信用周期",
    policyDimension: "政策环境",
    externalRiskDimension: "外部风险",
    regime: "宏观状态",
    multiplier: "仓位乘数",
    growth: "经济增长",
    externalRisk: "外部风险",
    monthlyAnnualReturns: "月度 / 年度收益",
    reservedReturns: "收益矩阵占位",
    pendingIntegration: "待接入",
    latestHoldings: "最近调仓持仓",
    noRebalance: "暂无调仓记录",
    minimumHoldingCount: (count: number | null) => `最低持仓数 ${count ?? "--"}`,
    meetsMinimum: "达到最低持仓数",
    belowMinimum: "低于最低持仓数",
    cashRatio: "现金比例",
    factorCoverage: "因子覆盖率",
    factorCoverageSubtitle: "全运行覆盖与最近实际复合权重",
    factorMissingNotice: "存在缺失因子输入，复合权重以 artifacts 中的实际权重为准。",
    macroDataStatus: "宏观数据状态",
    realManifest: "真实运行 manifest",
    macroObservationCount: "宏观观测数量",
    multiplierStatus: "仓位乘数状态",
    neutralFallbackUsed: "使用中性回退值",
    publishedMacroUsed: "使用已公布宏观记录",
    macroMissingExplanation: "当前运行没有真实宏观观测值，宏观调整不应被解释为有效宏观判断。",
    returnsAndBenchmark: "收益与基准",
    returnSubtitle: "年度、最近月度与基准可用状态",
    annualReturns: "年度收益",
    recentMonthlyReturns: "最近月度收益",
    benchmarkStatus: "基准状态",
    warningSummary: "警告摘要",
    warningSummarySubtitle: (count: number) => `共 ${count} 条，默认不展开全部技术内容`,
    mockResearchSummary: "演示研究摘要",
    mockModel: "演示生成",
    waitingMockReport: "等待演示研究报告",
    riskReview: "风险复核",
    counterargumentReview: "反方论证",
    evidence: "复核证据"
  },
  report: {
    metadata: {
      dataSource: "数据来源",
      runId: "运行编号",
      runStatus: "运行状态",
      generatedMode: "生成方式"
    },
    sections: {
      executiveSummary: "执行摘要",
      performanceReview: "历史表现复核",
      riskFlags: "风险提示",
      factorReview: "因子覆盖复核",
      benchmarkReview: "基准对比复核",
      macroReview: "宏观数据复核",
      dataQualityReview: "数据质量复核",
      counterarguments: "反方论证",
      researchBoundaries: "研究边界"
    },
    warningOverview: "警告概览",
    warningSamples: "中文展示样本",
    viewRawDetails: "查看原始技术详情",
    rawDetails: "原始技术详情",
    sourceMessage: "原始信息",
    evidenceNeeded: "复核证据",
    noRiskFlags: "暂无结构化风险提示。",
    noWarnings: "未保存原始警告。",
    warningFallback: "该技术警告需要结合原始信息复核。",
    persistedItems: (count: number) => `${count} 条原始记录`,
    macroObservationCount: "宏观观测数量"
  },
  mock: {
    summaryTitle: "演示研究实验摘要",
    summary: (name: string, selected: number, cash: string) => `演示实验 ${name} 共纳入 ${selected} 个研究标的，现金权重为 ${cash}。`,
    researchWindow: (start: string, end: string) => `研究区间：${start} 至 ${end}。`,
    selectedCount: (count: number) => `研究标的数量：${count}。`,
    annualizedReturn: (value: string) => `历史年化收益率指标：${value}。`,
    maxDrawdown: (value: string) => `历史最大回撤指标：${value}。`,
    macroRegime: (value: string) => `宏观状态技术值：${value}。`,
    limitations: [
      "演示模式仅使用已提供的结构化字段。",
      "历史指标不代表未来表现。",
      "本输出不包含交易执行指令。"
    ],
    genericRiskDescription: "该演示风险类别需要进一步研究复核。",
    genericRiskFocus: "请结合结构化证据和研究假设复核。",
    riskDescriptions: {
      drawdown: "需复核研究回测中的历史回撤深度。",
      concentration: "需复核目标权重中的集中度暴露。",
      cash_weight: "研究结果中的现金权重较高。",
      pipeline_warnings: "研究流水线警告需要进一步复核。",
      general_review: "演示规则未触发主要结构化风险提示。"
    },
    riskFocus: {
      drawdown: "重点检查压力区间、数据覆盖和调仓假设。",
      concentration: "重点检查单一标的和行业集中度假设。",
      cash_weight: "重点检查宏观乘数与组合约束的影响。",
      pipeline_warnings: "重点检查输入完整性和候选股票排除原因。",
      general_review: "进入下游使用前仍需继续核查研究假设。"
    },
    counterarguments: {
      factor_stability: {
        topic: "因子稳定性",
        argument: "当前因子快照在不同市场环境或报告期内可能无法保持稳定。",
        evidence: ["滚动因子排名历史", "样本外因子衰减分析", "行业中性因子诊断"],
        value: "检验研究标的是否过度依赖单一时点评分。"
      },
      macro_sensitivity: {
        topic: "宏观敏感性",
        argument: "宏观乘数可能把多维宏观信息压缩成单一仓位系数。",
        evidence: ["宏观状态转换历史", "放缓与复苏情景分析", "外部风险事件时间线"],
        value: "检验宏观解释是否过于粗略。"
      },
      backtest_assumptions: {
        topic: "回测假设",
        argument: "回测指标可能对数据质量、调仓时点、交易成本和幸存者偏差控制较为敏感。",
        evidence: ["数据质量报告", "调仓日历审计", "成本与滑点敏感性表"],
        value: "区分模型假设与历史观测结果。"
      }
    }
  },
  system: {
    frontendStatus: "前端运行状态",
    frontendLoaded: "Next.js 页面已加载",
    apiStatus: "API 运行状态",
    noHealthResponse: "未收到有效健康响应",
    researchRuns: "研究运行",
    persistedRunAvailable: "存在已落盘运行",
    noLatestRun: "没有可用的最新运行",
    apiTarget: "API 地址摘要",
    apiTargetDetail: "仅显示协议类别和公开主机，不显示变量原值",
    noRealRunsTitle: "暂无真实研究运行",
    noRealRunsDetail: "API 已启动且运行目录可访问，当前看板使用明确标记的演示数据。",
    latestRun: "最近运行状态",
    publicFieldsOnly: "仅显示公开研究摘要字段",
    latestRunId: "最新 run_id",
    latestRunStatus: "最新 run_status",
    benchmark: "基准状态",
    warningCount: "警告数量",
    lastApiCheck: "最后 API 检查",
    notCompleted: "尚未完成",
    productionApiMissing: "生产 API 未配置",
    localHttpApi: "本地 HTTP API",
    invalidApiUrl: "API 地址格式无效",
    timeUnavailable: "时间不可用"
  },
  errors: {
    apiRequestFailed: (status: number) => `研究 API 请求失败（HTTP ${status}）。`,
    reportUnavailable: "研究复核暂不可用。",
    runReadFailed: "研究运行读取失败。",
    realRunFallback: "真实研究运行不可用，当前显示演示数据。",
    apiUnavailable: "研究 API 不可用。",
    realRunRequired: "真实研究报告需要已选择的 run_id。",
    productionApiRequired: "生产部署必须配置 NEXT_PUBLIC_API_BASE_URL。",
    researchPathsOnly: "仅允许代理研究 API 路径。",
    invalidApiBaseUrl: "研究 API 基础地址格式无效。",
    productionHttpsRequired: "生产环境的研究 API 连接必须使用 HTTPS。"
  },
  aria: {
    equityCurve: "权益曲线",
    refresh: "刷新研究数据",
    status: "研究服务状态",
    originalWarnings: "原始技术警告"
  }
} as const;
