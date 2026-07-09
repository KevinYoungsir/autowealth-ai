# Research API

## 用途

Research API 是 A 股研究系统的聚合接口层，用于给后续 outloo.xin 可视化看板提供结构化数据。它连接 mock 或外部传入的研究数据、研究流水线、研究摘要和 mock DeepSeek 复核报告。

本阶段接口只用于研究展示，不接入真实交易，不做参数寻优，不承诺收益，不输出真实交易指令。DeepSeek 路径固定使用 `mock_mode=True`。

## 本地启动

```bash
uvicorn autowealth.api.research_server:app --reload --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/research/health
```

## 接口列表

### GET `/research/health`

返回服务状态、模块版本和 mock 状态。

响应示例：

```json
{
  "status": "ok",
  "service": "autowealth-research-api",
  "version": "0.1.0",
  "mock_mode": true
}
```

### GET `/research/demo`

使用 `autowealth/research/mock_data.py` 运行一次完整离线研究实验，返回 `result` 和 `summary`。该接口不访问真实网络，不调用真实 DeepSeek API。

响应字段包括：

- `result.target_weights`
- `result.backtest_metrics`
- `result.equity_curve`
- `summary.factor_summary`
- `summary.macro_summary`
- `summary.backtest_metrics`

### POST `/research/run`

接收候选股票、预计算因子分数、宏观乘数、价格数据和组合约束参数，调用 `run_research_pipeline`，返回可供看板展示的研究流水线结果。

请求示例：

```json
{
  "experiment_name": "dashboard_research_case",
  "start_date": "2020-01-01",
  "end_date": "2024-12-31",
  "candidate_symbols": ["600519", "000001"],
  "factor_scores": {
    "600519": {"score": 90, "factor_scores": {"composite": 90}},
    "000001": {"score": 75, "factor_scores": {"composite": 75}}
  },
  "macro_multiplier": 1.0,
  "industries": {"600519": "consumer", "000001": "financial"},
  "constraints": {
    "max_position_weight": 0.2,
    "min_position_weight": 0.01,
    "max_industry_weight": 0.4,
    "max_holdings": 10,
    "min_holdings": 1,
    "cash_weight_min": 0.0,
    "cash_weight_max": 0.4,
    "min_score": 60
  },
  "price_data": {
    "600519": [
      {"date": "2020-01-02", "close": 100.0},
      {"date": "2020-01-03", "close": 101.0}
    ],
    "000001": [
      {"date": "2020-01-02", "close": 10.0},
      {"date": "2020-01-03", "close": 10.1}
    ]
  }
}
```

### POST `/research/summarize`

接收 `/research/run` 或 `/research/demo` 返回的 `result` 字段，调用 `summarize_research_result`，返回结构化摘要。

### POST `/research/deepseek/mock-report`

接收研究流水线结果，使用 `DeepSeekResearchAgent(mock_mode=True)` 生成结构化研究报告。该接口显式传入空 API 配置，不读取真实 DeepSeek Key，不访问真实网络。

响应包括：

- `research_note`
- `risk_flags`
- `counter_arguments`
- `validation_result`
- `metadata`
- `warnings`

## mock 模式

本阶段所有内置接口都可以在无网络环境中运行。`/research/demo` 使用本地 mock 股票、mock 因子、mock 宏观状态和 mock 价格数据。`/research/deepseek/mock-report` 使用本地确定性规则生成结构化报告。

## 边界

- API 输出仅用于研究和教育展示。
- `target_weights` 是研究目标权重，不是实盘交易指令。
- 历史回测指标不代表未来表现。
- DeepSeek 只做研究摘要、风险复核、反方观点和一致性检查。
- 后续接入 outloo.xin 看板时，应继续保留上述研究边界。
