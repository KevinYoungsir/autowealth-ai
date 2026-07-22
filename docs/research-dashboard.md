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
研究总览 / 回测分析 / 组合持仓 / 因子分析 / 宏观环境 / 研究报告 / 系统状态
```

`ResearchRunStore` 仅在收到 API 请求后读取配置根目录。模块 import 不扫描磁盘，
任何看板请求也不会触发真实网络数据获取。原始 JSON 和 parquet 文件保持不变。

## 页面字段来源

| 页面 | 主要字段 | Artifact 或 API 来源 |
| --- | --- | --- |
| 研究总览 | run 状态、区间、覆盖率、绩效 | `run_manifest.json`、`metrics.json`、`/equity-curve` |
| 回测分析 | 年度/月度收益、回撤、换手率 | `metrics.json`、`benchmark_metrics.json` |
| 组合持仓 | 最近调仓持仓、现金、持仓数量 | `holdings.parquet`、manifest 配置摘要 |
| 因子分析 | 因子覆盖、缺失数、实际复合权重 | manifest 覆盖摘要、`factor_snapshots.parquet` |
| 宏观环境 | 宏观观察数、中性回退状态 | manifest `coverage_summary` |
| 研究报告 | 确定性复核、风险、反方观点和研究边界 | 所选运行的 `/research/runs/{run_id}/report`；无真实运行时才使用 mock |
| 警告摘要 | legacy 分类、结构化状态、severity/scope 计数与样例 | `warnings.json` 的只读聚合结果 |
| 系统状态 | API、目录、latest run 和数据来源 | `/research/health`、`/research/runs`、latest 摘要 |

权益、持仓和因子接口均设有返回上限。权益曲线降采样会保留首尾点。通用
warning 接口默认返回分类计数和少量样例；真实研究报告则包含全部持久化
warning。研究报告首屏按类别显示数量和最多 3 条中文样本，原始技术文本只在
“查看原始技术详情”折叠区中完整保留。

## 真实数据与演示数据

页面顶部始终显示数据来源：

- `real_artifacts`：来自所选 `run_id` 的已落盘研究结果。
- `mock_demo`：运行目录为空或真实运行不可用时加载的离线演示结果。
- `api_unavailable`：研究 API 无法访问，页面不把占位内容标记为真实结果。

运行选择器只列出真实 artifacts。Research Notes 跟随同一个 `selectedRunId`：
存在真实运行时使用确定性 artifact 报告，不调用 demo 或 mock report；只有
运行列表为空并明确进入 `mock_demo` 时才展示演示研究报告。

看板主要界面固定使用简体中文，并显式请求真实报告 `locale=zh-CN`。机器字段
继续以等宽字体保留原值，例如“部分完成”旁保留 `partial_success`。演示报告由
前端确定性 presenter 中文化，不改变 mock agent 的结构或研究规则。

System Status 只复用 health 和运行摘要，不调用 DeepSeek。它只显示 API 地址的
协议类别和公开主机摘要，不展示服务器磁盘路径或环境变量原值。

## 运行状态

- `success`（完成）：配置要求的数据链路已完成，但仍应结合数据源限制解读。
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

报告中的 `warning_presentations` 是派生展示结构。`source_message`、原始顺序和
总数不变；`display_message` 只提供中文类别说明，无法可靠翻译的 provider 错误
仍通过折叠区展示原文。任何本地化都不会降低风险等级。

新 run 还提供与 raw warning 同序的结构化 code、severity、scope、source 和安全
evidence。看板应把 `structured_status=absent` 解释为旧 run，把 `invalid` 解释为
结构化元数据不可用；两者都不得隐藏 raw warning、`partial_success` 或 benchmark
`unavailable`。结构化 scope 不替代上述 legacy 分类，warning severity 也不替代
报告 risk severity。

## 已知限制

- 当前 artifacts 可能来自固定股票池，无法消除幸存者偏差。
- 免费公开数据源未必提供严格 point-in-time 的全部历史估值和公告字段。
- 停牌、涨跌停、退市和成交可行性的历史状态仍受数据源覆盖限制。
- 基准不可用时只返回结构化原因和空曲线，不推断或伪造基准表现。
- 看板不重新计算底层结果；发现 artifact 损坏或缺失时由 API 返回明确错误。
- 真实 Research Notes 是确定性 artifact 复核，不调用 DeepSeek；无真实运行时的
  演示报告仍固定使用本地 mock mode，不读取真实 API Key。
- 生产构建缺少 `NEXT_PUBLIC_API_BASE_URL` 时显示 `api_unavailable`，不会回退 localhost。
- 中文字体全部使用系统回退栈，不下载 Google Fonts、`next/font` 远程资源或
  字体文件，适合中国大陆网络环境。
