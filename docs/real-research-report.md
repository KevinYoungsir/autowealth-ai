# 真实研究复核报告

## 模块定位

AutoWealth v0.15.0 为已落盘真实研究运行提供确定性、只读的结构化复核报告。
报告用于把运行状态、绩效、风险、因子、基准、宏观和数据质量限制汇总到
Research Notes 页面。它不会重新执行回测，也不会把缺失数据补成推断值。

所有输出仅用于研究和教育，不构成投资建议或交易指令。历史回测结果不代表
未来表现，也不构成任何收益承诺。

## 只读接口

```http
GET /research/runs/{run_id}/report
GET /research/runs/{run_id}/report?locale=zh-CN
GET /research/runs/{run_id}/report?locale=en-US
```

未传 `locale` 时默认 `en-US`，保持既有 API 客户端兼容；生产看板显式传入
`zh-CN`。响应顶层增加 `locale`，并返回对应的 `Content-Language` 响应头。
不支持的 locale 返回 HTTP 422。

接口仅读取以下 artifacts：

- `run_manifest.json`
- `metrics.json`
- `benchmark_metrics.json`
- `warnings.json`
- `holdings.parquet`
- `factor_snapshots.parquet`
- `trades.parquet`
- `benchmark_diagnostics.json`（新 run 可选）

请求不会修改 artifacts、访问行情 provider、调用真实 DeepSeek、执行交易或运行
参数寻优。报告不包含当前时间等运行外变量，因此相同 artifacts 会生成相同结构。
新 run 的基准复核把完整 provider attempts 放在 `provider_diagnostics` 技术证据
中；用户摘要仍使用 `benchmark_metrics.json` 的简洁原因。旧 run 缺少该可选
artifact 时返回空诊断，不影响报告生成或原七类 artifact 的兼容读取。

## 响应契约

顶层字段包括：

- `run_id`
- `locale: zh-CN | en-US`
- `data_source: real_artifacts`
- `generated_mode: deterministic`
- `run_status`
- `benchmark_status`
- `warning_count`
- `executive_summary`
- `performance_review`
- `risk_flags`
- `factor_review`
- `benchmark_review`
- `macro_review`
- `data_quality_review`
- `counterarguments`
- `research_boundaries`

每个复核章节包含 `status`、`summary`、`evidence`、`observations` 和
`limitations`。报告直接保留 manifest 的 `partial_success`，直接保留
`benchmark_metrics.json` 的 `unavailable` 状态和原因，并在数据质量章节返回
`warnings.json` 中的全部 warning 字符串，不生成基准收益或缺失因子值。中文响应
另含 `warning_presentations`，用于提供类别标签和中文展示说明；其中
`source_message` 与原始 warning 逐字一致。

生产运行的顶层状态示例：

```json
{
  "run_id": "20260710T064844Z_c5b63b7161",
  "locale": "zh-CN",
  "data_source": "real_artifacts",
  "generated_mode": "deterministic",
  "run_status": "partial_success",
  "benchmark_status": "unavailable",
  "warning_count": 193
}
```

该示例只展示已知状态字段，不代表运行完整、基准可比或结果可外推。

## 确定性复核规则

- 绩效复核只复述 `metrics.json` 已有指标，不重新估算或调整结果。
- 风险标记由已落盘状态和覆盖摘要触发，包括部分完成、基准不可用、warning、
  行情覆盖不足、宏观中性回退、持仓数不足和因子覆盖不足。
- 因子复核读取快照和 manifest 覆盖率；缺失因子不会被视为正常零分。
- 基准不可用时保留原始结构化原因，不生成相对表现。
- 宏观观察数为零时标记 `neutral_fallback`；中性回退表示没有数据，不表示经济
  环境实际中性。
- 数据质量复核对 warning 分类，同时保留完整原始 warning 列表。
- `zh-CN` 和 `en-US` 只改变展示文本；指标、机器状态、风险 code/category/severity、
  原始 provider 原因和 warning 完全一致。
- 反方观点是基于已落盘限制的固定研究问题，不是模型生成的交易观点。

## 前端切换

Research Notes 使用当前全局选中的 `run_id`：

1. `dataSource === "real_artifacts"` 且存在 `selectedRunId` 时，只请求真实报告
   接口，不请求 `/research/demo` 或 `/research/deepseek/mock-report`。
2. 真实来源缺少 `selectedRunId` 时返回明确错误，不静默回退 mock。
3. 只有运行列表为空、数据源明确为 `mock_demo` 时，才加载 demo 与 mock report。
4. `partial_success` 使用黄色限制提示，页面同时显示中文状态、原始机器值、来源、
   `run_id`、生成模式和报告 locale。
5. 前端真实报告请求显式使用 `locale=zh-CN`；本地化请求失败时不静默回退 mock。

## 错误语义

- 非法 `run_id`：HTTP 400，`code=invalid_run_id`。
- 运行不存在：HTTP 404，`code=research_run_not_found`。
- 必需 artifact 缺失：HTTP 404，`code=research_artifact_not_found`。
- artifact 无法解析：HTTP 422，`code=invalid_research_artifact`。
- 不支持的 `locale`：HTTP 422，FastAPI 结构化参数错误。

错误响应不返回服务器磁盘路径、环境变量、密钥或 Python 堆栈。

## 已知边界

- 报告质量受原始运行的 point-in-time、幸存者偏差、停复牌、涨跌停、退市、
  行业分类和公开数据源覆盖限制影响。
- 报告不读取 `equity_curve.parquet` 或 `benchmark_curve.parquet`，曲线仍由既有
  专用只读接口提供。
- 本阶段不调用真实 DeepSeek。后续若增加模型辅助摘要，必须与确定性证据分层，
  且不得覆盖或弱化原始运行状态和 warnings。
