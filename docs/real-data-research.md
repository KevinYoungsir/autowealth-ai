# 真实 A 股数据研究流水线

## 模块定位

`autowealth.research.real_pipeline` 把配置、真实行情缓存、基本面时点选择、宏观时点选择、多因子评分、组合构建、组合回测、基准比较和研究结果落盘连接为一次可复现实验。

该模块只用于研究和教育，不包含真实交易能力，不调用真实 DeepSeek，不执行参数寻优。历史回测结果受数据质量、模型假设和样本偏差影响，不代表未来表现，也不构成投资建议。

## 准备配置

基线配置位于 `configs/a_share_15y_baseline.yaml`，至少包含：

- `start_date`、`end_date`
- `candidate_symbols`
- `rebalance_frequency`：当前真实流水线支持 `yearly` 和 `five_year`
- `initial_capital`、`commission`、`stamp_tax`、`slippage`
- `factor_weights`
- `portfolio_constraints`
- `benchmark_symbols`
- `macro_csv_path`
- `cache_directory`
- `output_directory`
- `price_adjust`：`none`、`qfq` 或 `hfq`
- `history_lookback`：研究开始日前的只读数据回看窗口；旧配置缺失时使用
  `price_calendar_days: 450` 和 `fundamental_years: 5`

配置是一次实验的固定输入。流水线不会搜索参数、比较参数组合或自动寻找最高历史收益方案。

`history_lookback` 的两个值必须是非负整数。它们只控制数据抓取范围，
实际因子交易日样本数由代码中的统一规则决定，不能通过 YAML 调整。

## 四层窗口与执行时序

- **Research window**：配置的 `start_date` 至 `end_date`，定义正式研究区间。
- **Fetch window**：价格从研究开始日前 450 个日历日抓取，基本面从研究
  开始日前 5 年抓取，结束日均不超过研究结束日。
- **Signal window**：每个 execution date 使用严格早于该日的最近一个组合
  对齐真实交易日；价格、财报和宏观输入均以该 signal date 截止。
- **Metrics window**：权益曲线、交易、持仓和全部绩效指标只覆盖 research
  window，warm-up 数据不产生正式研究收益。

当前日线能力只可靠支持收盘价：信号使用 signal date close，交易使用
execution date close。旧持仓先承受截至 execution close 的价格变化，再按该
收盘价调仓；新权重从 execution close 之后的首个收益区间生效。同一收盘价
不会同时用于生成信号并让新仓位取得该日收益。

## 股票池

基线使用显式固定股票池。固定股票池易包含幸存者偏差，因为它不是按历史时点重建的指数成分、上市状态、ST 状态和退市状态。

不要用当前仍上市股票列表冒充历史股票池。`HistoricalUniverseProvider` 已预留历史成分接口；在可靠历史成分数据接入前，run manifest 和 warnings 会保留固定股票池限制。

## Point-in-time 要求

基本面记录同时保存：

- `report_date`：财务报告对应的报告期。
- `available_date`：该记录当时真正公开并可被研究者获得的日期。

每个 signal date 只能选择同时满足以下条件的记录：

```text
report_date <= signal_date
available_date <= signal_date
```

缺少 `available_date` 的记录不会被静默当作已公开数据。晚于 signal date 的公告记录会被排除并写入 warning。研究开始日前已经公开且仍是最新记录的财报可用于首期信号。若公开数据源不能提供可靠历史公告日期，provider 会标记 point-in-time 未验证，不会用报告期或当前值回填历史。

`available_date < report_date` 的异常记录保留审计痕迹但会失效其
`available_date`，因此不能进入 as-of 选择。完全重复的报告按
`fetched_at`、稳定来源顺序保留最后一条，并生成 warning。

宏观 CSV 同样要求 `date` 和 `available_date`。
`autowealth.macro.asof.select_macro_asof` 只选择 signal date 已经发布的最新记录，
禁止读取 signal date 之后的数据。`configs/macro_data_template.csv` 只提供字段
和说明，不包含伪造宏观观察值。

价格因子只接收 `date <= signal_date` 的历史切片。signal date 来自所有已
加载组合标的都有真实 bar 的共同日期，不用自然日减一天，也不把单只证券
独有日期当作组合决策时点。流水线不使用向后填充把未来价格、财报或宏观
值补到过去。

## 数据源与缓存

默认行情和指数 provider 基于 AKShare，基本面 provider 优先兼容 AKShare 可用的历史财务指标接口。指数按 `index_zh_a_hist` primary、`stock_zh_index_daily` fallback 的顺序尝试，并只接受通过统一质量校验的首个结果。网络访问只发生在用户调用 `run_real_data_research` 时；import 模块和默认单元测试不会访问网络。

缓存默认写入 `data/real_cache/`：

- `prices/`：股票日线 parquet 与 metadata sidecar。
- `fundamentals/`：基本面 parquet 与 point-in-time metadata。
- `benchmarks/`：指数日线 parquet 与 metadata sidecar。

价格缓存键使用实际 fetch start/end；覆盖不足的同键缓存不会被静默接受，
流水线会重试 provider 或明确失败，也不会覆盖已有缓存文件。metadata 同时
记录 `fetch_start_date`、`fetch_end_date`、`research_start_date` 和
`research_end_date`。基本面缓存同样按 fundamental fetch window 区分。
`data/real_cache/` 不提交到 Git。

公开数据源可能出现接口变更、公告日期缺失、历史估值缺失、复权口径差异和临时网络失败。流水线会保留 warning，不会伪造研究结果。

## 运行短区间 Smoke Test

integration smoke 仅覆盖两只股票和短日期区间，默认 skip。PowerShell 下显式启用：

```powershell
$env:AUTOWEALTH_RUN_REAL_DATA_SMOKE="1"
python -m pytest tests/integration/test_real_data_smoke.py -m integration -q --basetemp D:\pytest-tmp-autowealth -p no:cacheprovider
```

该命令会访问公开数据源。网络不可用或必要行情无法获得时，测试会明确 skip 并显示原因。

## 运行 15 年研究

先检查股票池、成本假设、复权方式、宏观 CSV 和输出路径，再主动执行：

```powershell
python examples/run_real_15y_research.py --config configs/a_share_15y_baseline.yaml
```

完整任务可能受公开接口限速、历史数据覆盖和本地存储影响。本阶段验收不运行完整 15 年网络任务。

## 研究结果目录

每次运行生成唯一 `run_id`，默认目录为 `data/research_runs/<run_id>/`：

- `config.json`
- `run_manifest.json`
- `metrics.json`
- `benchmark_metrics.json`
- `equity_curve.parquet`
- `benchmark_curve.parquet`
- `holdings.parquet`
- `trades.parquet`
- `factor_snapshots.parquet`
- `warnings.json`
- `benchmark_diagnostics.json`（仅新运行）

`run_manifest.json` 以增量字段记录 `artifact_schema_version`、
`research_window`、`metrics_window`、`fetch_windows`、`factor_lookbacks`、
`signal_execution_policy` 和 `price_alignment`，同时保留原有数据区间、配置
摘要、point-in-time 限制和幸存者偏差风险。旧 run 缺少这些字段仍可读取。
新运行的 manifest 在 `artifact_files` 中登记基准诊断文件，并在
`artifact_summary.benchmark_diagnostics` 记录基准总数、成功数和不可用数。
`factor_snapshots.parquet` 新增 `signal_date` 与 `execution_date`，并继续保留
`rebalance_date` 作为 execution date 的兼容字段。

可使用 pandas 读取 parquet：

```python
from pathlib import Path

import pandas as pd

run_dir = Path("data/research_runs/<run_id>")
equity_curve = pd.read_parquet(run_dir / "equity_curve.parquet")
factor_snapshots = pd.read_parquet(run_dir / "factor_snapshots.parquet")
```

## 运行状态与覆盖摘要

`run_manifest.json` 包含 `run_status`、`run_status_reasons` 和
`coverage_summary`。状态规则如下：

- `success`：候选行情、基准、宏观、持仓数量和关键因子覆盖均达到要求。
- `partial_success`：任一候选行情失败、任一基准不可用、宏观数据为空而使用中性乘数、任一调仓低于 `min_holdings`，或任一正权重配置因子的全运行总体覆盖率低于 0.8。
- `failed`：没有可用候选行情或没有可执行调仓。必要行情完全不可用时，流水线可能在 artifacts 生成前明确抛错，不会伪造失败结果。

`coverage_summary` 记录请求与成功行情标的、失败行情标的、行情覆盖率、
成功基本面标的、基准状态、宏观观察数、调仓数、各期持仓数、各期因子
覆盖率、全运行总体因子覆盖率和最终 warning 数量。

基准失败时，`benchmark_metrics.json` 保留结构化原因，不生成收益数据：

```json
{
  "000300": {
    "status": "unavailable",
    "symbol": "000300",
    "reason": "provider error",
    "reason_code": "provider_exception",
    "diagnostics_available": true,
    "metrics": {}
  }
}
```

成功基准继续使用原有指标对象。`benchmark_diagnostics.json` 保存每个 canonical
symbol 的 selected provider/endpoint、缓存状态、清洗前后行数、首末日期、
工作日估算覆盖率、实际 minimum coverage ratio 和全部 `ProviderAttempt`。
每次 attempt 增量保存原始请求 symbol、ISO 请求起止日期、供应商 symbol、首末
数据日期、行数、门槛、reason code 和脱敏异常。异常原因限制长度并脱敏 URL、
代理凭证、token 和敏感 header。旧 run 没有该文件时 RunStore、API 和真实报告
返回空诊断，原有 metrics、curve 和 warnings 读取方式不变。

默认 minimum coverage ratio 为 80%。质量检查同时限制请求窗口首尾缺失工作日：
每端绝对上限为 5 个，且上限还受整体覆盖门槛剩余缺失预算约束。新缓存采用不可变
generation parquet，canonical `.meta.json` 最后原子发布并作为 commit marker；
Loader 只有在 marker、SHA、metadata 和 generation 全部一致时才返回 cache hit。
旧版 canonical parquet 与 sidecar 继续兼容读取。缓存失败 reason code 区分
`cache_hit`、`cache_unreadable`、`cache_sha_mismatch`、
`cache_insufficient_coverage` 和 `cache_metadata_mismatch`。

Artifact 先写入同一输出目录下的隐藏 staging 目录，文件齐全后再发布为最终
`run_id` 目录；任一文件写入失败会清理 staging，不留下可被读取的半成品 run。

## 收益与缺失数据规则

年度收益的首个有效年度按“首个有效净值到该年年末”计算，后续年度按
相邻年末净值计算。只有一个净值点的年度会被排除，并列入 metrics 的
`excluded_partial_years`；`annual_return_method` 记录当前口径。

行情连续性使用缺失工作日而非日历日检查。超过 8 个缺失工作日才产生
提示，且提示明确说明可能包含特殊市场休市；在接入正式交易日历前，
该检查不能用于断言数据必然缺失。

每个调仓日的因子快照记录各因子的可用状态及原始输入可用/缺失数量。
某因子所有有效原始输入都缺失时，该因子不进入复合分数，其配置权重在
剩余可用因子间重新归一化，并形成 warning。若所有配置因子都不可用，
该候选在该调仓日被拒绝评分。

因子子项最低样本要求固定在 `autowealth.factors.readiness`：

| 子项 | 最低有效样本 |
| --- | ---: |
| 6 个月动量（剔除最近 1 个月） | 148 个收盘价 |
| 12 个月动量（剔除最近 1 个月） | 274 个收盘价 |
| 年化波动率 | 253 个收盘价 / 252 个收益率 |
| 最大回撤 | 253 个收盘价，使用同一固定窗口 |
| RSI | 15 个收盘价 |
| 布林带位置 | 20 个收盘价 |
| 短期收益 | 21 个收盘价 |
| 成交量比率 | 60 个有效成交量记录 |

样本不足时原始输入为 unavailable，warning 会记录实际数与最低要求。多输入
因子仍可使用其余有效子项；coverage 使用与复合评分相同的可用性规则。

Structured warnings 是 best-effort 增量 metadata，原始 `warnings` 始终是兼容
权威来源。enrichment 完整时，新运行在同一 `warnings.json` 中保存 schema version 1
的 `structured_warnings`，两者同序、同数且 message 逐字一致。任一最终 raw warning
缺少显式 metadata 时，运行不会猜测 code、改变 `run_status` 或阻止 artifacts 发布，
而是退化为仅含 `warnings` 的 raw-only artifact；RunStore 将其解释为 `absent`。
Artifact writer 对调用方明确传入的 structured 数据仍执行严格验证。已知生产路径的
漏登记由离线测试发现。code 由价格、基本面、宏观、股票池、因子、组合或基准的
明确阶段设置，不根据英文文本推断。详见
[`structured-warnings.md`](structured-warnings.md)。

价格矩阵前向填充最多 5 个组合交易日，并在 manifest 记录是否发生、填充
数量和仍未解决的缺失数。execution date 必须是所有已加载标的都有真实 bar
的共同日期；有限前向填充只用于持仓估值对齐，不会把缺失真实 bar 的证券
当作正常成交。

## 当前限制

- 固定股票池不是历史成分股，存在幸存者偏差。
- 历史 ST、退市、涨跌停、精确停牌执行和成交容量尚未完整建模。
- 暂无可靠历史行业分类时，行业约束按 unknown 保守处理。
- 不复权价格不含现金分红和完整公司行动收益；前复权/后复权可能包含后续调整因子，需按数据源单独审查。
- 基准曲线不扣除组合交易成本，仅用于对照。
- 基准覆盖率当前以工作日估算，尚未接入正式 A 股历史交易日历；80% 门槛不会
  为适配单个端点或测试而降低。首尾最多 5 个估算工作日的容忍仍可能受到春节、
  国庆等特殊休市影响，诊断不能替代正式交易日历。
- 两个公开 AKShare 指数端点都可能因版本、代理、接口或网络状态而不可用；
  provider chain 只提高可诊断性和容错，不保证获得基准。
- 公开基本面源若缺少可靠公告日期，不能声称为严格 point-in-time 数据。

## 提供给看板

后续可由研究 API 读取已审核的 `data/research_runs/<run_id>/`，把指标、权益曲线、持仓快照、因子快照、基准和 warnings 转换为适合 `dashboard.outlook.xin` 的只读展示数据。看板不得绕过 manifest 和 warnings，也不得把研究目标权重转换为真实交易指令。
