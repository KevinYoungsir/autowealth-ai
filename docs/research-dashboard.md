# 真实研究看板

## 目标与边界

研究看板只读展示 `data/research_runs/<run_id>/` 中已经落盘的研究 artifacts。
它不会启动回测、修改研究结果、调用真实 DeepSeek、连接券商、生成交易指令或
搜索最优参数。页面中的收益和风险指标仅用于研究与教育，历史结果不代表未来
表现，也不构成投资建议。

## 数据流

```text
research artifacts (read-only)
        |
        v
ResearchRunStore
        |
        v
FastAPI /research/runs/*
        |
        v
Next.js /api/research/runs/* proxy
        |
        v
Dashboard / Backtest / Portfolio / Factors / Macro / System Status
```

`ResearchRunStore` 仅在收到 API 请求后读取配置根目录。模块 import 不扫描磁盘，
任何看板请求也不会触发真实网络数据获取。原始 JSON 和 parquet 文件保持不变。

## 页面字段来源

| 页面 | 主要字段 | Artifact 或 API 来源 |
| --- | --- | --- |
| Dashboard | run 状态、区间、覆盖率、绩效 | `run_manifest.json`、`metrics.json`、`/equity-curve` |
| Backtest | 年度/月度收益、回撤、换手率 | `metrics.json`、`benchmark_metrics.json` |
| Portfolio | 最近调仓持仓、现金、持仓数量 | `holdings.parquet`、manifest 配置摘要 |
| Factors | 因子覆盖、缺失数、实际复合权重 | manifest 覆盖摘要、`factor_snapshots.parquet` |
| Macro | 宏观观察数、中性乘数状态 | manifest `coverage_summary` |
| Research Notes | mock 风险复核与反方观点 | `/research/deepseek/mock-report`，固定 mock 模式 |
| Warning 摘要 | 分类计数与少量样例 | 原始 `warnings.json` 的只读聚合结果 |
| System Status | API、目录、latest run 和数据来源 | `/research/health`、`/research/runs`、latest 摘要 |

权益、持仓和因子接口均设有返回上限。权益曲线降采样会保留首尾点，warning
默认只显示分类计数和少量样例，不会一次渲染完整原始列表。

## 真实数据与演示数据

页面顶部始终显示数据来源：

- `real_artifacts`：来自所选 `run_id` 的已落盘研究结果。
- `mock_demo`：运行目录为空或真实运行不可用时加载的离线演示结果。
- `api_unavailable`：研究 API 无法访问，页面不把占位内容标记为真实结果。

运行选择器只列出真实 artifacts。Research Notes 当前仍是 `mock review`，即使
同页上下文来自真实量化运行，也不得把该复核描述为真实模型结论。

System Status 只复用 health 和运行摘要，不调用 DeepSeek。它只显示 API 地址的
协议类别和公开主机摘要，不展示服务器磁盘路径或环境变量原值。

## 运行状态

- `success`（完整运行）：配置要求的数据链路已完成，但仍应结合数据源限制解读。
- `partial_success`（部分完成）：至少存在价格、基本面、宏观、基准、持仓数量或
  因子覆盖方面的限制；看板显示主要 warning 和覆盖率。
- `failed`（运行失败）：不展示可能造成误解的绩效结论，只显示状态和失败限制。

`partial_success` 不等于结果无效，也不等于完整可比。使用者应先检查覆盖率、
warning 分类和基准状态，再决定该运行是否足以支持具体研究问题。

## 覆盖率解释

- 价格覆盖率：成功取得价格数据的候选股票数除以请求股票数。
- 因子覆盖率：每个因子实际可用记录数除以该调仓期应评估记录数。
- 基本面覆盖率：manifest 中成功获得合规基本面记录的股票范围。
- 宏观观察数：调仓时点可按 as-of 规则使用的宏观记录数量；为零时看板明确显示
  使用中性乘数。

覆盖率只描述数据完整程度，不证明信号质量或投资有效性。缺失因子不得在看板中
伪装为正常零分；实际复合权重以 artifacts 中记录的重新归一化结果为准。

## Warning 分类

API 在不修改 `warnings.json` 的前提下聚合以下类别：

- `price_provider`：行情 provider 调用失败或标的缺失。
- `price_quality`：重复日期、异常价格、交易日缺口等质量问题。
- `fundamental_data`：基本面缺失、历史字段不可用或 provider 限制。
- `point_in_time`：公告可用日、未来数据拒绝和时点一致性限制。
- `macro_data`：宏观记录缺失或中性乘数降级。
- `universe_bias`：固定股票池与幸存者偏差风险。
- `portfolio_constraints`：最小持仓数、权重或行业约束未满足。
- `factor_coverage`：因子输入不足或复合权重降级。
- `benchmark`：基准行情或指标不可用。
- `system`：无法归入以上类别的运行级问题。

## 已知限制

- 当前 artifacts 可能来自固定股票池，无法消除幸存者偏差。
- 免费公开数据源未必提供严格 point-in-time 的全部历史估值和公告字段。
- 停牌、涨跌停、退市和成交可行性的历史状态仍受数据源覆盖限制。
- 基准不可用时只返回结构化原因和空曲线，不推断或伪造基准表现。
- 看板不重新计算底层结果；发现 artifact 损坏或缺失时由 API 返回明确错误。
- DeepSeek 区域当前只展示本地 mock review，不读取真实 API Key。
- 生产构建缺少 `NEXT_PUBLIC_API_BASE_URL` 时显示 `api_unavailable`，不会回退 localhost。
