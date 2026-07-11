# Research API

## 用途

Research API 是 A 股研究系统的聚合接口层，用于给后续 outlook.xin 可视化看板提供结构化数据。它连接 mock 或外部传入的研究数据、研究流水线、研究摘要和 mock DeepSeek 复核报告。

本阶段接口只用于研究展示，不接入真实交易，不做参数寻优，不承诺收益，不输出真实交易指令。DeepSeek 路径固定使用 `mock_mode=True`。

## 本地启动

```bash
uvicorn autowealth.api.research_server:app --reload --port 8001
```

健康检查：

```bash
curl http://127.0.0.1:8001/research/health
```

## CORS 配置

研究 API 的 CORS 只配置在独立的 `autowealth.api.research_server` 应用上，不改变 `autowealth.api.server` 的既有行为。默认允许：

- `http://127.0.0.1:3000`
- `http://localhost:3000`
- `https://dashboard.outlook.xin`

可以使用逗号分隔的环境变量覆盖默认值：

```env
RESEARCH_API_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,https://dashboard.outlook.xin
```

生产部署建议由 `https://dashboard.outlook.xin` 提供看板，由 `https://api.outlook.xin` 提供研究 API，并保持精确来源白名单，避免使用通配来源。

`RESEARCH_API_CORS_ORIGINS` 不接受 `*`。生产环境同时设置可信 Host：

```env
RESEARCH_API_TRUSTED_HOSTS=api.outlook.xin
```

本地默认允许 `localhost`、`127.0.0.1`，应用还会安全追加 Railway 健康检查
使用的 `healthcheck.railway.app`。Host 值不允许协议、路径或通配符。未知 Host
返回 400；允许来源的 OPTIONS 预检保持正常。

## 接口列表

### GET `/research/health`

返回服务状态、模块版本、mock 状态和运行目录布尔可用性，不返回目录路径或变量值。

响应示例：

```json
{
  "status": "ok",
  "service": "autowealth-research-api",
  "version": "0.1.0",
  "mock_mode": true,
  "research_runs_available": true,
  "latest_run_available": false
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

## 真实研究运行目录

真实运行接口通过只读 `ResearchRunStore` 读取 artifacts。默认目录为项目根
目录下的 `data/research_runs`，可使用环境变量覆盖：

```env
RESEARCH_RUNS_DIRECTORY=data/research_runs
```

Railway Volume 生产配置使用绝对路径：

```env
RESEARCH_RUNS_DIRECTORY=/data/research_runs
```

缺失目录会在首次读取时安全尝试创建。空目录下 `/research/runs` 返回空列表，
`/research/runs/latest` 返回结构化 404，不会创建 mock artifacts。

API 不接受磁盘路径参数。`run_id` 只能包含字母、数字、下划线和连字符，
并且解析后的目录必须仍位于配置根目录内。模块 import 不扫描目录，API
请求也不会触发网络或修改 artifacts。

## 真实运行接口

- `GET /research/runs?limit=20`：按运行时间倒序返回摘要，不读取大体积 parquet。
- `GET /research/runs/latest`：返回最新运行摘要、manifest、metrics、基准和 warning 摘要。
- `GET /research/runs/{run_id}`：返回指定运行详情。
- `GET /research/runs/{run_id}/equity-curve?downsample=500`：返回有上限且保留首尾点的权益曲线。
- `GET /research/runs/{run_id}/benchmark-curve?downsample=500`：返回基准曲线或结构化 unavailable 原因。
- `GET /research/runs/{run_id}/holdings?limit=200&rebalance_date=YYYY-MM-DD`：返回逐标的持仓快照。
- `GET /research/runs/{run_id}/trades?limit=500`：返回有限数量交易记录。
- `GET /research/runs/{run_id}/factors?limit=500`：返回因子快照与调仓期/总体覆盖率。
- `GET /research/runs/{run_id}/warnings?sample_limit=3&raw_limit=20`：返回分类计数、少量样例和有限原始 warning。

真实运行响应统一包含 `data_source: "real_artifacts"`。`run_status` 显示为
`success`、`partial_success` 或 `failed`；看板分别解释为完整运行、部分完成
和运行失败。失败运行不应展示误导性的绩效结论。

## Warning 聚合

原始 `warnings.json` 保持不变。API 读取后按以下类别聚合：

```text
price_provider, price_quality, fundamental_data, point_in_time,
macro_data, universe_bias, portfolio_constraints, factor_coverage,
benchmark, system
```

每类只返回配置数量的样例，避免前端默认渲染全部 warning。

## 基准不可用

基准失败时 API 返回 `status: "unavailable"`、各标的 `reason` 和空 points，
不会创建或推断基准曲线。成功基准继续返回已落盘的真实曲线。

## 前端 Fallback

看板先调用 `/research/runs`。存在运行时只使用所选真实 artifacts；目录为空
时回退 `/research/demo` 并显示“演示数据”。API 整体不可用时显示
`api_unavailable`，不会把 mock 标记成真实。DeepSeek 页面继续使用 mock
review，并与真实量化运行分开标识。

## 边界

- API 输出仅用于研究和教育展示。
- `target_weights` 是研究目标权重，不是实盘交易指令。
- 历史回测指标不代表未来表现。
- DeepSeek 只做研究摘要、风险复核、反方观点和一致性检查。
- 后续接入 outlook.xin 看板时，应继续保留上述研究边界。
- 未处理的服务端异常统一脱敏，不返回 Python 堆栈、绝对路径、环境变量或密钥。
