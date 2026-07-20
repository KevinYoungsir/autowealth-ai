"""Simplified Chinese deterministic report catalog."""

MESSAGES = {
    "persisted_unknown": "技术说明（原文保留）：{source}",
    "research_boundary": (
        "本报告仅用于研究与教育，不构成投资建议、交易指令或收益承诺；"
        "历史研究结果不代表未来表现。"
    ),
    "benchmark_reason_missing": "artifacts 未保存基准不可用原因。",
    "benchmark_unavailable_summary": (
        "基准数据暂不可用，当前无法得出相对表现结论。"
    ),
    "benchmark_available_summary": "已落盘的基准指标可用于确定性复核。",
    "benchmark_partial_summary": "所请求的基准中仅有部分数据可用。",
    "benchmark_relative_limitation": (
        "基准不可用期间，不能据此评价组合的相对表现。"
    ),
    "performance_available_summary": (
        "本节直接复现 metrics.json 中的历史表现指标，报告接口未重新估算这些数值。"
    ),
    "performance_unavailable_summary": "artifacts 中没有可用的核心历史表现指标。",
    "performance_observation": "{label}（{name}）={value:.6f}",
    "metric_annualized_return": "年化收益率",
    "metric_total_return": "累计收益率",
    "metric_max_drawdown": "最大回撤",
    "metric_volatility": "波动率",
    "metric_sharpe_ratio": "夏普比率",
    "metric_calmar_ratio": "卡玛比率",
    "metric_turnover": "换手率",
    "performance_limitation": (
        "指标仅反映已落盘回测区间、既定假设与实际数据覆盖范围。"
    ),
    "macro_available_summary": "本次研究运行使用了当时可用且已落盘的宏观观测。",
    "macro_neutral_summary": "由于缺少可用宏观数据，本次研究使用中性回退值。",
    "macro_missing_limitation": (
        "未保存可按时点使用的宏观观测，因此不能对宏观周期作有效判断。"
    ),
    "risk_run_title": "研究运行未完整完成",
    "risk_run_description": (
        "已落盘的 run_status 为 {run_status}，该状态必须持续明确展示。"
    ),
    "risk_run_review": "开展横向比较前，应逐项解决或明确接受已保存的运行状态原因。",
    "risk_benchmark_title": "基准对比不完整",
    "risk_benchmark_description": (
        "已落盘的 benchmark_status 为 {benchmark_status}。"
    ),
    "risk_benchmark_review": (
        "在得出相对表现结论前，需要补充与研究区间兼容的基准 artifacts。"
    ),
    "risk_warnings_title": "已落盘警告需要复核",
    "risk_warnings_description": "本次运行保存了 {warning_count} 条原始警告。",
    "risk_warnings_review": (
        "应按类别核对原始警告，不得对缺失观测作推断性补全。"
    ),
    "risk_warning_mismatch_title": "警告数量不一致",
    "risk_warning_mismatch_description": (
        "run_manifest.json 记录的警告数量与 warnings.json 不一致。"
    ),
    "risk_warning_mismatch_review": (
        "应先核对 artifacts 生成过程，再判断该运行是否内部一致。"
    ),
    "risk_price_title": "候选股票行情覆盖不完整",
    "risk_price_description": "已落盘的行情覆盖率为 {price_coverage:.2%}。",
    "risk_price_review": (
        "应评估被排除股票对股票池代表性和组合集中度的影响。"
    ),
    "risk_macro_title": "宏观输入使用了中性回退值",
    "risk_macro_description": "本次运行未保存可用的宏观观测。",
    "risk_macro_review": (
        "宏观状态应视为不可判断，不应把中性回退值解释为宏观环境真实中性。"
    ),
    "risk_holdings_title": "部分调仓日持仓数低于 min_holdings",
    "risk_holdings_description": "已落盘持仓数量未满足配置中的最低持仓约束。",
    "risk_holdings_review": "应复核组合集中度及导致可选标的减少的数据排除原因。",
    "risk_factor_title": "配置因子的数据覆盖不足",
    "risk_factor_description": "至少一个已落盘因子覆盖率低于本次运行阈值。",
    "risk_factor_review": (
        "应使用已保存的可用性标记和实际权重，不得用虚构值替代缺失因子。"
    ),
    "factor_empty_summary": "已落盘的 factor_snapshots.parquet 不包含记录。",
    "factor_insufficient_summary": (
        "已落盘因子快照中至少一个覆盖率低于配置阈值；"
        "本报告不会把缺失值转换为虚构评分。"
    ),
    "factor_available_summary": "已落盘的因子快照和覆盖率可用于复核。",
    "factor_limitation": (
        "因子可比性取决于调仓时点的数据覆盖及已保存的实际复合权重。"
    ),
    "data_quality_warnings_summary": (
        "本次运行包含 {warning_count} 条已落盘警告；响应继续保留全部原始警告字符串。"
    ),
    "data_quality_empty_summary": "warnings.json 中没有已落盘的警告字符串。",
    "executive_summary": (
        "研究运行 {run_id} 的状态保持为 {run_status}。本报告仅对已落盘 artifacts "
        "进行确定性复核，不能替代底层研究证据。"
    ),
    "observation_run_status": "运行状态：{run_status}",
    "observation_benchmark_status": "基准状态：{benchmark_status}",
    "observation_warning_count": "警告数量：{warning_count}",
    "counter_universe_topic": "股票池代表性",
    "counter_universe_argument": (
        "固定股票池或行情覆盖不完整，可能使历史组合看起来比当时真实可投资股票池更稳健。"
    ),
    "counter_universe_evidence_1": "历史指数成分记录",
    "counter_universe_evidence_2": "退市与 ST 状态历史",
    "counter_universe_evidence_3": "行情失败标的归因",
    "counter_universe_assumption_1": "幸存者偏差",
    "counter_universe_assumption_2": "可投资股票池",
    "counter_universe_value": "检验研究结果是否依赖当前仍存续的证券。",
    "counter_factor_topic": "数据可用性与因子降级",
    "counter_factor_argument": (
        "即使对可用因子重新归一化权重，输入减少后的因子评分在不同股票或调仓日之间仍可能不可比。"
    ),
    "counter_factor_evidence_1": "各调仓日因子覆盖率",
    "counter_factor_evidence_2": "实际复合因子权重",
    "counter_factor_evidence_3": "基本面数据的时点可用性",
    "counter_factor_assumption_1": "因子可比性",
    "counter_factor_assumption_2": "缺失数据处理",
    "counter_factor_value": "区分模型行为变化与数据覆盖变化。",
    "counter_execution_topic": "成交可实现性",
    "counter_execution_argument": (
        "已落盘交易记录不能证明全部历史订单在当时停牌、涨跌停和流动性条件下均可实际成交。"
    ),
    "counter_execution_evidence_1": "历史停复牌状态",
    "counter_execution_evidence_2": "涨跌停状态",
    "counter_execution_evidence_3": "容量与成交量约束",
    "counter_execution_assumption_1": "成交可得性",
    "counter_execution_assumption_2": "交易成本真实性",
    "counter_execution_value": "检验回测成交是否能按模型设定实现。",
    "counter_benchmark_topic": "缺少基准背景",
    "counter_benchmark_argument": (
        "当所请求基准不可用时，组合的绝对历史表现不能用于证明相对价值。"
    ),
    "counter_benchmark_evidence_1": "兼容的基准曲线",
    "counter_benchmark_evidence_2": "基准指标",
    "counter_benchmark_assumption_1": "相对表现",
    "counter_benchmark_assumption_2": "市场环境对比",
    "counter_benchmark_value": "避免脱离市场背景解读绝对收益。",
    "counter_macro_topic": "宏观状态未被观测",
    "counter_macro_argument": (
        "中性回退值只是缺少数据时的处理方式，不代表当时宏观环境处于中性状态。"
    ),
    "counter_macro_evidence_1": "按时点可用的宏观观测",
    "counter_macro_evidence_2": "数据发布日期",
    "counter_macro_assumption_1": "宏观仓位乘数",
    "counter_macro_assumption_2": "宏观状态解释",
    "counter_macro_value": "避免为回退值赋予未经数据支持的经济含义。",
}

PERSISTED_MESSAGES = {
    "required price or rebalance coverage is empty": "必要的行情或调仓覆盖为空。",
    "one or more candidate price series are unavailable": "至少一只候选股票的行情序列不可用。",
    "one or more benchmarks are unavailable": "至少一个基准不可用。",
    "benchmark unavailable": "基准数据不可用。",
    "macro data is empty and the neutral multiplier is used": (
        "由于缺少可用宏观数据，本次研究使用中性回退值。"
    ),
    "one or more rebalances are below min_holdings": "至少一个调仓日的持仓数低于 min_holdings。",
    "one or more configured factors have insufficient coverage": "至少一个配置因子的覆盖率不足。",
    "The fixed configured universe is not historical index membership and may contain survivorship bias.": (
        "固定配置股票池并非历史指数成分股，可能包含幸存者偏差。"
    ),
    "Historical ST, delisting, limit-up/limit-down and exact suspension execution rules are not fully modeled.": (
        "历史 ST、退市、涨跌停及精确停牌成交规则尚未完全建模。"
    ),
    "Industry history is unavailable, so unknown-industry exposure is handled conservatively.": (
        "历史行业分类不可用，因此系统对未知行业暴露采用保守处理。"
    ),
    "Valuation fields may be absent when the provider cannot supply historical point-in-time values.": (
        "当数据源无法提供历史时点估值时，估值字段可能缺失。"
    ),
    "Benchmark curves exclude portfolio transaction costs and are comparison references only.": (
        "基准曲线未计入组合交易成本，仅作为比较参考。"
    ),
    "At least one fundamental source lacks verified historical publication dates; affected rows are excluded or degraded.": (
        "至少一个基本面数据源缺少经核验的历史发布日期，受影响记录已排除或降级处理。"
    ),
    "No published macro observations were supplied; a neutral multiplier is disclosed and used.": (
        "由于缺少可用宏观数据，本次研究使用中性回退值。"
    ),
    "Adjusted price series may embed adjustment factors known after an earlier date and require source-specific review.": (
        "复权行情可能包含较晚时点才确定的复权因子，需要结合具体数据源复核。"
    ),
    "Unadjusted prices avoid retrospective adjustment but do not include dividends or corporate-action total returns.": (
        "不复权价格避免追溯调整，但不包含分红及公司行动带来的总回报。"
    ),
    "The configured fixed stock universe can overstate historical results because it is not reconstructed from historical constituents.": (
        "固定配置股票池未按历史成分重建，可能高估历史研究结果。"
    ),
}

WARNING_CATEGORY_LABELS = {
    "fundamental_data": "基本面数据",
    "point_in_time": "时点一致性",
    "macro_data": "宏观数据",
    "universe_bias": "股票池偏差",
    "portfolio_constraints": "组合约束",
    "factor_coverage": "因子覆盖",
    "benchmark": "基准数据",
    "price_provider": "行情数据源",
    "price_quality": "行情质量",
    "system": "系统",
}

WARNING_CATEGORY_MESSAGES = {
    "fundamental_data": "基本面数据存在缺失或来源限制，请结合原始技术信息复核。",
    "point_in_time": "数据时点一致性存在提示，请确认调仓日可用范围。",
    "macro_data": "宏观数据存在缺失或回退提示，请结合原始技术信息复核。",
    "universe_bias": "股票池代表性存在偏差风险，请结合原始技术信息复核。",
    "portfolio_constraints": "组合约束存在未满足或降级情况，请结合原始技术信息复核。",
    "factor_coverage": "因子数据覆盖存在缺失，请结合原始技术信息复核。",
    "benchmark": "基准数据存在可用性或完整性提示，请结合原始技术信息复核。",
    "price_provider": "行情数据源调用或覆盖存在异常，请结合原始技术信息复核。",
    "price_quality": "行情质量存在异常提示，其中可能包含正常市场休市，请结合原始技术信息复核。",
    "system": "系统记录了未归入其他类别的技术提示，请查看原始信息。",
}
