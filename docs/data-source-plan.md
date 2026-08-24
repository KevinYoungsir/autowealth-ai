# A 股数据源规划

## 1. 目标

本项目数据源规划目标是为 A 股长期投资组合研究提供可复现、可扩展、可审计的数据管线。第一阶段仅定义数据源和缓存方案，不接入真实 API Key，不实现 DeepSeek，不开发前端看板。

优先级：

1. AKShare
2. 东方财富公开数据
3. 本地 parquet 缓存
4. 后续扩展 Tushare、BaoStock、JQData、Wind、Choice

## 2. A 股行情数据源

### 优先数据源

- AKShare：用于获取 A 股日线行情、复权因子、股票列表、指数行情、行业板块等公开数据。
- 东方财富：用于补充行情、资金流、板块、财务摘要和公告入口等数据。
- 本地 parquet 缓存：作为研究系统的主要读取层，避免每次回测重复请求外部数据。

### 行情字段

建议基础字段：

- 股票代码、交易日期、开盘价、最高价、最低价、收盘价、前收盘价。
- 成交量、成交额、换手率、涨跌幅、涨跌额。
- 复权因子、前复权价、后复权价、不复权价。
- 是否停牌、是否涨停、是否跌停、是否 ST、上市状态。

### 扩展数据源

- Tushare：可用于更稳定的历史行情、复权因子、基础信息和部分财务数据。
- BaoStock：可作为免费历史行情和财务数据补充。
- JQData：可用于更完整的研究级数据接口。
- Wind、Choice：可作为商业数据源扩展，适合高质量财务、宏观和公告数据。

## 3. 指数数据源

指数数据用于基准比较、市场状态识别、行业轮动和风险暴露分析。

建议覆盖：

- 宽基指数：上证指数、深证成指、沪深 300、中证 500、中证 800、中证 1000、中证全指、创业板指、科创 50、北证 50。
- 风格指数：价值、成长、红利、低波、质量等。
- 行业指数：申万、中信、中证行业指数。
- 主题指数：消费、医药、科技、金融、周期、资源、先进制造等。

数据源优先级：

- AKShare 指数行情和指数成分。
- 东方财富指数与板块数据。
- 后续扩展中证指数官网、Tushare、JQData、Wind、Choice。

关键要求：

- 指数成分必须支持历史成分版本，避免使用当前成分回填历史。
- 指数行情需记录复权或全收益口径。
- 基准选择必须在回测报告中明确披露。

## 4. 财务数据源

财务数据用于质量、价值、成长、盈利稳定性和现金流因子。

建议覆盖：

- 利润表：营业收入、营业成本、净利润、扣非净利润、毛利率、净利率。
- 资产负债表：总资产、净资产、负债率、货币资金、存货、应收账款。
- 现金流量表：经营现金流、投资现金流、自由现金流估算。
- 财务指标：ROE、ROA、ROIC、EPS、每股净资产、股息率。
- 估值指标：PE、PB、PS、PCF、EV/EBITDA、估值分位。

数据源优先级：

- AKShare 财务接口。
- 东方财富财务数据。
- 后续扩展 Tushare、JQData、Wind、Choice。

关键要求：

- 必须记录报告期、公告披露日、数据更新日。
- 回测中财务数据只能在披露日之后使用。
- 修订数据应保留版本或至少记录更新日期，避免数据回填造成泄露。

## 5. 宏观数据源

宏观数据用于经济周期识别、市场风险偏好判断和组合风险解释。

建议覆盖：

- 国内宏观：GDP、PMI、CPI、PPI、社融、M2、利率、汇率、工业增加值、固定资产投资、进出口。
- 金融市场：国债收益率、信用利差、货币市场利率、人民币汇率、北向资金。
- 海外宏观：美国利率、美元指数、美债收益率、主要经济体 PMI、全球风险资产表现。

数据源优先级：

- AKShare 宏观接口。
- 国家统计局、中国人民银行、外汇交易中心等公开来源。
- 东方财富宏观与资金数据。
- 后续扩展 Wind、Choice、CEIC 等商业数据源。

关键要求：

- 宏观指标必须记录发布日期，不能按统计期直接使用。
- 周期判断需要保留规则版本和阈值。
- 宏观信号只用于风险解释、仓位约束和情景分析，不直接决定买卖。

## 6. 新闻、公告与国际政治事件数据源

### 新闻与公告

建议覆盖：

- 上交所、深交所、北交所公告。
- 巨潮资讯公告。
- 东方财富公告、研报摘要和资讯。
- 公司定期报告、临时公告、业绩预告、业绩快报。

用途：

- 财报披露日期校验。
- 重大事件标签。
- 风险事件复核。
- 研究摘要生成。

### 国际政治事件

建议覆盖：

- 地缘冲突、贸易摩擦、制裁清单、关税政策。
- 海外央行政策、汇率冲击、能源与大宗商品事件。
- 影响 A 股行业链的国际监管或供应链事件。

数据源可从公开新闻、官方公告、国际组织、主流财经媒体和后续商业数据源扩展。

关键要求：

- 新闻和国际事件数据主要用于风险标签、研究摘要和压力测试。
- 不得把未经验证的新闻直接转换为买卖决策。
- 事件影响应以行业、主题或组合暴露方式表达。

## 7. 本地缓存方案

本地缓存优先采用 parquet 格式，按数据类型、频率和日期分区。

建议目录结构：

```text
data/
  raw/
    akshare/
    eastmoney/
  normalized/
    prices/
    indices/
    financials/
    macro/
    events/
  features/
  backtests/
  metadata/
```

建议 parquet 分区：

- 行情：`data/normalized/prices/source=akshare/freq=1d/year=YYYY/`
- 指数：`data/normalized/indices/source=akshare/index_code=000300/`
- 财务：`data/normalized/financials/source=eastmoney/report_type=quarterly/`
- 宏观：`data/normalized/macro/source=akshare/category=pmi/`
- 事件：`data/normalized/events/source=eastmoney/event_type=announcement/`

缓存元数据应记录：

- 数据源、接口名称、拉取时间、覆盖区间。
- 字段清单、字段类型、复权方式、单位口径。
- 数据版本、校验摘要、缺失率、异常值数量。
- 是否允许用于回测、是否存在披露日约束。

## 8. 数据质量校验

每批数据入库前应执行校验：

- 主键唯一性：股票代码和交易日期不得重复。
- 日期连续性：识别缺失交易日和异常交易日。
- 价格一致性：最高价不低于最低价，收盘价位于合理区间。
- 成交额一致性：成交量、成交额和价格关系不能明显异常。
- 复权一致性：复权因子不能出现无法解释的跳变。
- 财务披露一致性：公告日不得晚于使用日逻辑错误。
- 状态一致性：停牌、涨跌停、ST、退市状态与交易行为一致。

DeepSeek 后续可用于提示异常样本和生成复核摘要，但不能替代确定性数据校验规则。

## 9. 扩展路线

阶段一：

- 完成项目规划、开发规范、回测规则和数据源规划。
- 不接 API Key，不实现业务逻辑。

阶段二：

- 建立本地 parquet 数据目录和元数据规范。
- 接入 AKShare 与东方财富的只读数据采集。
- 增加数据质量校验和样本缓存。

阶段三：

- 实现 A 股回测引擎的偏差规避规则。
- 实现组合构建、因子评分和风险指标。
- 加入 DeepSeek 辅助摘要与风险复核，但不让其决定买卖。

阶段四：

- 构建 outlook.xin 可视化研究看板。
- 展示组合净值、风险暴露、回测指标、研究摘要和风险复核。

## 10. 第二阶段实际实现

第二阶段已新增独立的 A 股研究数据层，位置为 `autowealth/data/`。本阶段只实现只读数据获取、字段标准化、本地 parquet 缓存和基础数据质量检查，不实现策略、回测、DeepSeek 接入或前端看板。

新增模块：

- `autowealth/data/ashare_provider.py`：`AShareDataProvider`，基于 AKShare 的 `stock_zh_a_hist` 获取 A 股历史日线数据。
- `autowealth/data/index_provider.py`：定义统一 `IndexDataProvider` 协议、canonical
  指数代码和 AKShare 端点 adapter；`AShareIndexProvider` 继续兼容原有调用。
- `autowealth/data/schema.py`：统一行情字段，保证下游始终获得固定 DataFrame 列。
- `autowealth/data/cache.py`：`ParquetCache`，默认缓存目录为 `data/cache/`。
- `autowealth/data/quality.py`：`DataQualityReport` 和基础行情质量检查。

本阶段明确保留以下边界：

- 不修改 `autowealth/core/data_fetcher.py` 的既有行为。
- 不保存真实 API Key，不接入任何交易接口。
- 不使用 DeepSeek 或其他大模型决定买卖、仓位或调仓。
- 不实现策略、回测或可视化看板。

## 11. 数据层使用示例

安装依赖后，可通过以下方式获取 15 年以上 A 股日线数据：

```python
from autowealth.data import AShareDataProvider, ParquetCache, check_price_quality

provider = AShareDataProvider()
df = provider.get_daily(
    symbol="600519",
    start_date="2009-01-01",
    end_date="2024-12-31",
    adjust="qfq",
)

report = check_price_quality(df)
cache = ParquetCache()
cache.write(df, symbol="600519", start_date="2009-01-01", end_date="2024-12-31", adjust="qfq")
```

获取指数数据：

```python
from autowealth.data import AShareIndexProvider

index_provider = AShareIndexProvider()
index_df = index_provider.get_daily(
    index="沪深300",
    start_date="2010-01-01",
    end_date="2024-12-31",
)
```

统一行情字段：

```text
date, open, high, low, close, volume, amount, amplitude, pct_change, change, turnover
```

缓存文件命名包含 `symbol`、`start_date`、`end_date` 和 `adjust`，例如：

```text
data/cache/600519_20090101_20241231_qfq.parquet
```

`data/cache/` 和 `*.parquet` 已加入 `.gitignore`，缓存数据不得提交到 Git。

## 12. 第十二阶段真实数据实现

真实研究流水线新增以下数据边界：

- `fundamental_schema.py` 统一保存 `report_date` 与 `available_date`，两者含义不得混用。
- `fundamental_provider.py` 集中处理基本面网络调用；模块 import 不访问网络。
- 历史公告日期必须来自数据源的显式公告或披露日期字段。缺失时记录 warning，不以报告期或当前日期代替。
- 历史 PE、PB、股息率无法可靠取得时保留缺失值，不把当前估值静默回填到历史。
- `universe.py` 把固定配置股票池明确标记为非 point-in-time，并预留历史指数成分 provider 接口。
- 股票、基本面和基准缓存写入 `data/real_cache/`，并保存来源、区间、拉取时间、口径、行数和摘要 metadata。
- 完整运行结果写入 `data/research_runs/<run_id>/`，两个目录均不提交到 Git。

P0 数据窗口加固后，价格 provider 与缓存键使用
`research_start_date - history_lookback.price_calendar_days` 至
`research_end_date`；基本面 provider 使用
`research_start_date - history_lookback.fundamental_years` 至
`research_end_date`。缓存 metadata 同时记录 fetch 与 research 两组边界。
同键价格缓存只有确实覆盖 fetch window 时才能复用，覆盖不足会重试 provider
或明确失败，且不会覆盖已有缓存文件。

决策时点的数据选择必须满足 `available_date <= signal_date`，其中 signal date
严格早于 execution date；基本面还必须满足 `report_date <= signal_date`。
详细配置、运行命令和数据限制见 `docs/real-data-research.md`。

## 13. 行情缺口稳定性规则

基础行情质量检查按缺失工作日衡量连续性，不再直接使用日历天间隔。
春节、国庆等正常长假通常不会超过当前 8 个缺失工作日阈值。超过阈值
时只提示复核数据源覆盖，并明确该区间仍可能包含特殊市场休市。后续接入
可靠的 A 股历史交易日历后，应使用交易所交易日替代通用工作日判断。

## 14. v0.16.0 基准指数容错

基准统一使用 `000300`、`000905`、`000852`、`000001`、`399001`、`399006`
六位 canonical code。名称中的空格会被忽略，例如“沪深300”和“沪深 300”
都解析为 `000300`；端点所需的 `sh000300`、`399001.SZ` 等形式仅由 adapter
转换，真实研究流水线不处理端点专用代码。

默认 provider chain 顺序固定为：

1. `AShareIndexProvider` / `index_zh_a_hist`（primary）。
2. `AKShareIndexDailyProvider` / `stock_zh_index_daily`（fallback）。

`IndexDataProvider` 协议统一使用 `symbol` 参数；两个生产 adapter 同时保留原
`index=` 关键字作为兼容别名，因此既有位置参数与旧关键字调用均不受影响，新代码
应使用 `symbol=`。端点专用 symbol 只在 adapter 内解析。

AKShare 仅在显式 `get_daily` 时导入和访问。端点不存在、网络异常、空响应或
质量校验失败时会保留本次 attempt，再尝试下一 provider；fallback 成功不会
抹去 primary 失败证据。全部失败时基准明确为 `unavailable`，不会插值、伪造，
也不会使用个股价格替代指数。

统一质量门槛要求 `date` 和正数 `close` 可解析、日期位于请求区间、无重复日，
`close` 还必须是有限值，并至少覆盖请求区间估算工作日的 80%。除整体覆盖率外，
首尾边界分别检查缺失工作日：绝对上限为 5 个，同时不得耗尽整体门槛允许的全部
缺失行预算。该规则可拒绝总行数达标但开头或结尾大段截断的数据。工作日估算不是
正式 A 股交易日历结论，春节、国庆等休市日可能包含在估算分母中。清洗前后行数、
首末日期、首尾缺口、重复数、实际门槛和覆盖率均进入技术诊断。

基准缓存继续 cache-first。只有 sidecar 的 canonical symbol、实际 fetch 区间、
SHA256、行数、首末日期和 source 与 parquet 一致，且数据通过同一质量门槛时
才复用。不可读、摘要不匹配或覆盖不足的旧缓存会被保留并记录失败 attempt，
不会被静默接受或覆盖；provider 成功后仅在同键不存在时写入新缓存。

`ProviderAttempt` 保留原有机器字段，并增量记录 `requested_symbol`、ISO 格式的
`requested_start_date` / `requested_end_date`、`minimum_coverage_ratio`、`rows`
兼容别名和脱敏 `exception`。symbol resolver 失败使用 `provider_exception`，并以
`failure_stage: symbol_resolution` 标识后继续 fallback。

缓存 attempt 使用稳定 reason code：`cache_hit`、`cache_unreadable`、
`cache_sha_mismatch`、`cache_insufficient_coverage` 和
`cache_metadata_mismatch`。新缓存把数据写入不可变 generation parquet，全部临时
内容完成后，最后原子替换 canonical `.meta.json` sidecar 作为 commit marker；
marker 出现前的 generation 不会被 Loader 识别为成功缓存。旧版 canonical parquet
加 sidecar 格式继续只读兼容，已有无效缓存仍不会被自动覆盖。

## 15. 宏观校验与历史估值契约

当前宏观宽表新增纯函数 adapter 和 shadow validator。它使用现有评分指标 catalog，
区分记录 schema 有效性与相对 signal date 的 PIT 可用性，并要求显式
`available_date`。校验只把有界聚合 diagnostics 写入新 run manifest，不过滤原
DataFrame，不改变宏观评分、warning 或运行状态。该阶段尚未接入新的 macro
provider，也未实现单位、频率和正式交易日历验证。

历史估值新增 `pe_ttm`、`pb`、`ps_ttm`、`dividend_yield`、`market_cap` 的
schema 与 provider protocol。记录只接受六位 canonical symbol；endpoint 专用代码
只能由 provider adapter 转换。请求上下文显式包含 symbol、指标、起止日和
`as_of_date`，晚于 as-of date 发布的记录不属于 PIT 可用数据。availability 使用
严格 status/reason 矩阵，diagnostics 使用固定且有深度、键数、列表、字符串和
16 KiB 总大小上限的 schema。

当前没有生产 valuation provider、cache、provider chain 或 factor integration。
契约只能验证日期字段存在、格式和顺序，不能证明供应商历史日期真实，也不能识别
所有当前 snapshot 配伪造日期形成的历史序列。未来 provider 必须提供来源、版本、
PIT 证据和真实历史序列 acceptance tests；本阶段不声称已经解决真实历史估值数据
可得性。详细字段与 reason codes 见 `docs/macro-valuation-contract.md`。

## 16. v0.17.0 EOD Provider Contract 与请求窗口规划

新的领域级 EOD Provider contract 位于 `autowealth/market_data/`，以
`EODDatasetKey` 作为包含市场、交易所、资产类型、canonical symbol、频率和复权
口径的完整数据集身份。Provider request、result 和 capability 均为不可变、可确定性
序列化的纯模型；一个 capability 只表示一个精确支持组合，空响应不会被视为成功。
Provider 结果必须经过统一 EOD batch 校验，才能交给后续 coordinator 判断。

Provider 和请求窗口 planner 在 import 与执行纯规划时不访问网络、文件、环境变量
或系统时钟。测试使用完全离线的 fake Provider 和 fake TradingCalendar。现有
`autowealth/data/` Provider、Pandas schema、fallback chain 和 `ParquetCache` 保持
兼容，本 PR 尚未把它们接入新 contract。

不复权数据默认使用 `append_only` 规划。前复权和后复权历史可能因后续公司行动被
供应商重新计算，因此 `qfq`、`hfq` 默认返回 `full_refresh_required`；该状态只表示
局部增量安全性无法得到证明，不代表系统每天自动重新抓取 15 年历史。只有 Provider
具有可验证的有界修订保证时，调用者才可显式选择 `overlap_window`。

Provider 不生成 repository `data_version`、generation ID 或 manifest checksum，也不
调用 repository publish。完整数据的 `data_version` 继续由 repository 基于规范化内容
checksum 生成。当前 PR 不包含真实 AKShare 或东方财富 adapter、真实 fallback、
retry、coordinator、generation 合并、worker、scheduler、API 或部署接线。

## 17. v0.17.0 AKShare EOD Adapter

`autowealth/market_data/` 新增面向领域级 EOD contract 的 AKShare 股票和指数
Adapter。股票 Adapter 使用 `stock_zh_a_hist`，指数 Adapter 在本阶段只使用
`index_zh_a_hist`；后续 PR5 增加的 `stock_zh_index_daily` fallback 保持为独立
Adapter，不隐藏在 primary Adapter 内。
Adapter 只接受包含市场、交易所、资产类型、canonical symbol、频率和复权口径的
`EODDatasetKey`，不会接受名称、裸代码或 endpoint 专用代码。

两个 Adapter 都支持注入 endpoint callable，以便使用固定 DataFrame 和 fake
TradingCalendar 完成完全离线的单元测试。未注入 endpoint 时，AKShare 只在首次
`fetch` 中延迟导入；模块导入和 Adapter 构造均不访问网络。返回的 DataFrame 会被
严格转换为不可变 `EODBar` tuple，再交给既有 Provider Result Validator。空响应保留
为 `empty` 而非成功；非空但缺少预期交易日的响应保留为 `partial_success` 和对应
覆盖不足 warning。

不复权股票和指数 capability 使用 `append_only`。`qfq`、`hfq` 股票 capability
使用 `full_refresh_required`，因为公司行动可能使历史复权值发生修订。Adapter 不
调用 repository publish，不生成 generation 或 `data_version`，也未接入旧真实研究
流水线。现有 `autowealth/data/` Provider、缓存和 fallback chain 保持兼容，尚未迁移。

本阶段对 `volume` 和 `amount` 只按确定性 Decimal 规则保留源数值，不进行乘除、
缩放或单位猜测。`stock_zh_a_hist` 与 `index_zh_a_hist` 的单位语义尚未通过固定
AKShare 版本 fixture 或显式 integration 验证，因此当前 Adapter 不声称已完成跨
endpoint 单位统一。retry、fallback、Provider attempts、coordinator、worker、API、
部署和真实网络 integration 均不属于本阶段。

## 18. v0.17.0 EOD Provider Chain 与指数 fallback

领域级 `EODProviderChain` 是独立 orchestrator，不实现 `EODProvider` Protocol，也不
伪装成单一数据源。它按声明顺序检查 Provider capability。默认仍对每个 Provider 最多
调用一次；显式配置后，仅 `temporary_provider_failure` 可在同一 Provider 内进行有界
重试，耗尽后才进入下一 fallback。完整 `success` 立即停止；`partial_success` 会保留为候选并继续 fallback；
`empty` 会保留 `empty_response` 证据并继续；明确不支持请求的 Provider 不调用
endpoint。没有完整结果时，Chain 按 row count、起止边界和 Provider 顺序确定性选择
最佳 partial。partial 只表示仍有研究价值的已验证数据，不表示 coordinator 可以发布。

每次尝试使用不可变 `EODProviderAttempt` 记录稳定 Provider/endpoint 身份、结果或错误
状态、行数、有效区间、warning code 和是否被选中。attempt 不复制 bars，不记录系统
时间、UUID、原始 payload、异常 repr、traceback、绝对路径或凭据。所有 Provider 都未
返回完整或 partial 数据时，Chain 使用有限优先级聚合 unsupported、malformed、
permanent、temporary 和 unavailable，不采用最后一次错误作为隐式结论。每个 attempt
继续代表 provider chain position；增量 invocation 诊断记录调用序号、重试序号、退避、
限流等待和最终状态，不把 retry 伪装成新的 fallback position。

重试 policy 的 `max_attempts` 包含首次调用且限制为 1 至 5；退避确定性、无 jitter，并由
可注入 sleeper 执行。单 runtime 的进程内最小间隔 limiter 使用 monotonic clock，按
`(provider_name, endpoint_name)` 共享；每次首次、重试和 fallback 调用都先 acquire。
默认 `max_attempts=1`、间隔为 0，不改变旧调用次数或引入等待。AKShare adapter 本身不
包含隐藏 retry，只将明确的 timeout/connection 临时失败映射为既有 retryable error code。

指数 fallback 是独立 `AKShareEODIndexDailyProvider`，只支持冻结的六个 canonical
指数、日频和不复权口径。`stock_zh_index_daily` 只接收带 `sh`/`sz` 前缀的 symbol，
返回的完整历史 DataFrame 会在副本上严格解析全部日期，再按请求闭区间本地过滤。
无法解析的日期使整个 payload 失败；合法区间外行可以过滤，区间内 OHLCV、重复日期
和 schema 继续由现有 converter 与 Provider Result Validator 关闭式校验。primary
`index_zh_a_hist` Adapter 内没有隐藏 fallback。

本 PR 不访问 repository，不读取或写入 `current.json`，不生成 generation、
`generation_id` 或 `data_version`，也不接入旧研究流水线。request planner、历史数据
合并/upsert、完整批次验证、partial 发布判定、原子 generation 发布、noop/幂等和发布
失败恢复均留给后续 coordinator PR6。

## 19. v0.17.0 Incremental EOD Coordinator

`EODIncrementalCoordinator` 编排单个数据集的一次同步更新。每次调用只读取一次 current
generation，由纯 Planner 决定请求窗口，并在需要抓取时最多调用一次既有 Provider Chain。
Chain 内部可按显式 policy 对单个 Provider 执行有限次调用，但 Coordinator 不再外包一层
retry，最大调用量仍受 Provider 数量乘单 Provider `max_attempts` 的固定上界约束。
Chain 的完整 `success` 才能进入合并和发布；`partial_success` 会关闭式失败并保留 attempts，
不会发布，也不会用 current 中的旧值补齐缺失交易日。

初次导入直接使用完整 Provider bars。`append_only` 增量保留既有历史，并拒绝任何新旧日期
重叠，即使两条 bar 内容相同也不会静默去重。`overlap_refresh` 会完整删除请求区间内的旧
bars，再按 whole-bar replacement 插入 Provider 返回值；不逐字段合并，新的 `amount=None`
也会替换旧值。候选 generation 先对完整历史执行结构校验，再对 effective range 切片执行
coverage 校验。重复记录和缺失交易日都会阻止发布，即使底层 Validator 将部分情况表示为
warning。完整校验通过后才计算逻辑内容摘要；内容与 current 完全相同时返回防御性 no-op，
不创建 generation 或更新 pointer。

Coordinator 不读取系统时钟、不生成 UUID。只有确实需要发布时，调用方才必须提供合法的
`generation_id` 和 timezone-aware `created_at`，后者统一为 UTC。既有 Repository 继续负责
staging、Parquet/manifest 校验、generation rename 和 `current.json` 原子激活；Coordinator
不直接写这些文件，也不会在 publish 失败后重试、删除 inactive orphan 或再次发布。pointer
激活失败时，上一版 current 仍由 Repository 保持有效。

单数据集 coordinator 自身仍以 single-writer 为前提，不内置锁、compare-and-swap、
多进程或分布式一致性。上层 `EODBatchCoordinator` 可在执行前注入 dataset lock，并提供
单进程实现；绕过该上层或在多个进程/实例中使用进程内锁仍可能在 `load_current` 与
`publish` 之间造成 lost update。`full_refresh_required` 只返回明确状态，不自动下载或
重建完整历史。旧研究 pipeline、worker、scheduler、API、CLI 和 orphan 清理仍留给
后续独立 PR。

## 20. Production Trading Calendar 与 Composition Root

生产 EOD stack 使用部署方显式提供的版本化本地 JSON 日历，不自动联网下载，也不会
用工作日规则猜测中国交易所历史交易日。日历声明 schema、identity、version、
`Asia/Shanghai` 时区和覆盖区间，并逐日显式记录 `trade_date` 与 `is_trading_day`。
文件缺失、不可读、日期非法、重复、乱序、覆盖不连续或查询越界都会关闭式失败。

`autowealth.market_data.composition` 从严格 YAML 配置构造单数据集 runtime，依次装配
TradingCalendar、`EODDatasetKey`、`LocalEODFileRepository`、AKShare primary/fallback、
`EODProviderChain` 和 `EODIncrementalCoordinator`。composition 只负责验证和构造，
不会调用 fetch、update 或 publish；AKShare 仍只在显式 fetch 时延迟导入。

配置样例为 `configs/eod_production.example.yaml`。生产 `repository_root` 必须位于持久
volume 或 durable filesystem，不能依赖容器临时磁盘。完整约束见
`docs/market-data-production-composition.md`。

## 21. EOD Batch Coordination 与并发契约

`EODBatchCoordinator` 接收显式 dataset request 列表，并按完整 `EODDatasetKey.identity`
确定性排序。重复 dataset identity 在任何读取、抓取或发布前关闭式拒绝；所有执行保持
同步串行，每个 dataset 继续复用既有 `EODIncrementalCoordinator`，不会形成第二套合并、
校验或 publication 逻辑。

默认 `stop_on_failure` 在首个普通失败后将后续 dataset 标为 `skipped`；调用方也可显式
选择 `continue_on_failure`。批次结果分别记录 success、failed、skipped 和
`full_refresh_required` 数量。后者不会被计为普通成功，也不会触发完整历史重建。
batch 不是跨 dataset 原子事务；每个 repository publication 仍是 dataset-local transaction，
后续失败不会回滚此前已经成功发布的独立 generation。

四类 dataset outcome 互斥，满足 `requested = success + failed + skipped + full_refresh`；
`attempted = requested - skipped`。全部 dataset 都要求 full refresh 时，batch 使用独立
`full_refresh_required` 全局状态；与普通成功混合时为 `partial_success`。dry-run 的全局状态
保持 `dry_run`，但每个 dataset 的 `full_refresh_required` outcome 和计数仍会保留。

`dry_run=true` 会读取 current generation、运行交易日历与请求窗口规划，并返回
initial/incremental/overlap/full-refresh 计划；它在 Provider fetch 前返回，不获取写锁，
不生成 generation，不写 pointer，也不调用 repository publication。
dry-run 是观察性计划，不保证之后真实执行时 repository state 仍与规划时一致。

真实运行以完整 canonical dataset identity 的稳定 SHA-256 摘要构造 lock key。锁覆盖
current 读取、规划、Provider chain、合并、校验和原子发布全流程，异常路径通过
`finally` 释放。内置 `InProcessEODDatasetLockManager` 只解决单进程并发，不能作为多进程、
多容器或多主机生产锁；多实例部署必须注入满足同一非阻塞 acquire/release 协议的共享锁。

Provider retry/backoff 和 rate limiting 只位于统一调用边界：只有临时失败可重试，退避
确定且有界，限流只在单个 runtime/ProviderChain 内生效。batch 继续串行，真实执行时 dataset 写锁在
Provider 重试和等待期间保持持有；dry-run 不调用 Provider、limiter 或 sleeper。本阶段仍
没有分布式限流、随机 jitter、worker、scheduler、API、CLI、orphan cleanup 或自动每日
ingestion。旧 research pipeline、旧 cache 和历史 artifacts
均未迁移或修改。

production config 因新增严格的 `retry_policy`、`rate_limit_policy` section 升级为 schema
version 2。旧 schema version 1 五字段配置继续加载，并固定映射为 `max_attempts=1`、最小
间隔 0；v1 不接受 v2 字段，避免旧 parser 与新配置对同一版本产生不同解释。

## 22. Explicit EOD Full Refresh Execution

`EODFullRefreshExecutor` 是独立的显式执行边界。普通 incremental update 和既有 batch
继续把 `full_refresh_required` 当作 planner outcome，不会自动抓取或重建完整历史。调用方
必须显式提交 `EODFullRefreshRequest`，执行器随后在 dataset 写锁内重新读取 current、调用
同一 planner，并且只在 planner 仍返回 `full_refresh_required` 时继续。

Provider request 精确使用 planner 的完整 `effective_range`。replacement candidate 只由
本次 ProviderChain 返回的 bars 构成，不与 current bars 合并，因此 qfq/hfq 历史修订不会
遗留旧 generation 的价格。只有完整 `success` 可进入严格 coverage validation；partial、
缺失交易日、区间外日期、重复、OHLC/数值异常或 identity 不一致均关闭式失败，不发布也
不改变 current pointer。执行器直接复用 ProviderChain 的有界 retry、backoff、rate limit、
fallback 和 attempts，不增加外层 retry。

候选内容 checksum 与 current 相同时返回 `unchanged_content`，不创建重复 generation。
内容变化时复用现有 repository format，创建新的 immutable generation，并让
`previous_generation_id` 指向锁内读取到的 current；旧 generation 不修改、不删除，指针
继续原子激活。dry-run 只读取 current 和规划，返回 intended full range 与待替换 generation，
不抓取、不获取写锁、不等待、不创建 generation 或写 pointer。

production composition 可通过 `build_eod_full_refresh_executor` 显式构造该边界，但不会执行。
调用方必须把与 incremental writer 共用的 lock manager 注入 executor；内置进程锁仍不能
协调多进程或多实例。本阶段不增加 batch full-refresh mode、配置默认开关、自动 maintenance
调度、完整 generation pruning、worker、scheduler、API、CLI 或自动每日 ingestion。

## 23. Explicit EOD Repository Maintenance

`EODRepositoryMaintenanceExecutor` 是独立、显式调用的 repository 检查与有限清理边界。
构造 executor 不读取或创建 repository，也不获取锁。dry-run 不获取写锁、不删除文件，
只返回有界、确定性、可 JSON 序列化的 artifact 分类和 warning。

自动删除范围严格限定为两类：

- generation ID 合法且名称精确匹配
  `.<generation_id>.<16-lowercase-hex>.staging` 的 stale staging 目录；
- 名称精确匹配 `.current.<16-lowercase-hex>.tmp` 的普通临时文件。

真实执行使用 canonical dataset identity 对应的同一写锁。executor 在锁内首次检查，
逐项重新验证待删除 artifact，只删除上述精确临时残留，然后在释放锁前再次检查
repository。删除失败会保留已删除项、剩余项和稳定错误码；不会把部分清理伪装成成功。
dry-run 结果不保留锁或 reservation，真实执行必须基于当时状态重新判断。

完整 generation 会读取并验证 manifest/parquet，并从 current 沿
`previous_generation_id` 进行有界、可检测循环的 lineage 遍历。active、可达历史、
不可达或可用于回滚的完整 generation 均只报告，不删除。不存在 current 但存在完整
generation、谱系断裂、循环、超限、畸形 generation、未知 generation 内容或符号链接时，
清理关闭式阻止。未知 root artifact 保留并报告。

maintenance 不修改 `current.json`、manifest、parquet、data version 或 EOD 配置，也不
提供 retention policy、generation pruning 或自动 orphan 回收。内置进程锁不能协调多进程、
容器或主机；多实例部署必须注入与 writer 共用的共享锁实现。本阶段没有 startup hook、
background cleanup、worker、scheduler、API 或 CLI 接线。
