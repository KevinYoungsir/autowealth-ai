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

配置是一次实验的固定输入。流水线不会搜索参数、比较参数组合或自动寻找最高历史收益方案。

## 股票池

基线使用显式固定股票池。固定股票池易包含幸存者偏差，因为它不是按历史时点重建的指数成分、上市状态、ST 状态和退市状态。

不要用当前仍上市股票列表冒充历史股票池。`HistoricalUniverseProvider` 已预留历史成分接口；在可靠历史成分数据接入前，run manifest 和 warnings 会保留固定股票池限制。

## Point-in-time 要求

基本面记录同时保存：

- `report_date`：财务报告对应的报告期。
- `available_date`：该记录当时真正公开并可被研究者获得的日期。

调仓日只能选择同时满足以下条件的记录：

```text
report_date <= rebalance_date
available_date <= rebalance_date
```

缺少 `available_date` 的记录不会被静默当作已公开数据。晚于调仓日的公告记录会被排除并写入 warning。若公开数据源不能提供可靠历史公告日期，provider 会标记 point-in-time 未验证，不会用当前值回填历史。

宏观 CSV 同样要求 `date` 和 `available_date`。`autowealth.macro.asof.select_macro_asof` 只选择调仓日已经发布的最新记录，禁止读取调仓日之后的数据。`configs/macro_data_template.csv` 只提供字段和说明，不包含伪造宏观观察值。

价格因子只接收 `date <= rebalance_date` 的历史切片。流水线不使用向后填充把未来价格、财报或宏观值补到过去。

## 数据源与缓存

默认行情和指数 provider 基于 AKShare，基本面 provider 优先兼容 AKShare 可用的历史财务指标接口。网络访问只发生在用户调用 `run_real_data_research` 时；import 模块和默认单元测试不会访问网络。

缓存默认写入 `data/real_cache/`：

- `prices/`：股票日线 parquet 与 metadata sidecar。
- `fundamentals/`：基本面 parquet 与 point-in-time metadata。
- `benchmarks/`：指数日线 parquet 与 metadata sidecar。

metadata 记录数据类型、标的、来源、覆盖区间、拉取时间、复权方式、行数和文件摘要。`data/real_cache/` 不提交到 Git。

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

`run_manifest.json` 记录运行时间、Git commit、数据源、数据区间、配置摘要、point-in-time 限制和幸存者偏差风险。复核实验时应先阅读 manifest 与 warnings，再读取指标和曲线。

可使用 pandas 读取 parquet：

```python
from pathlib import Path

import pandas as pd

run_dir = Path("data/research_runs/<run_id>")
equity_curve = pd.read_parquet(run_dir / "equity_curve.parquet")
factor_snapshots = pd.read_parquet(run_dir / "factor_snapshots.parquet")
```

## 当前限制

- 固定股票池不是历史成分股，存在幸存者偏差。
- 历史 ST、退市、涨跌停、精确停牌执行和成交容量尚未完整建模。
- 暂无可靠历史行业分类时，行业约束按 unknown 保守处理。
- 不复权价格不含现金分红和完整公司行动收益；前复权/后复权可能包含后续调整因子，需按数据源单独审查。
- 基准曲线不扣除组合交易成本，仅用于对照。
- 公开基本面源若缺少可靠公告日期，不能声称为严格 point-in-time 数据。

## 提供给看板

后续可由研究 API 读取已审核的 `data/research_runs/<run_id>/`，把指标、权益曲线、持仓快照、因子快照、基准和 warnings 转换为适合 `dashboard.outlook.xin` 的只读展示数据。看板不得绕过 manifest 和 warnings，也不得把研究目标权重转换为真实交易指令。
