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
- `autowealth/data/index_provider.py`：`AShareIndexProvider`，基于 AKShare 的 `index_zh_a_hist` 获取主要 A 股指数日线数据。
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

调仓日的数据选择必须满足 `available_date <= rebalance_date`。详细配置、运行命令和数据限制见 `docs/real-data-research.md`。

## 13. 行情缺口稳定性规则

基础行情质量检查按缺失工作日衡量连续性，不再直接使用日历天间隔。
春节、国庆等正常长假通常不会超过当前 8 个缺失工作日阈值。超过阈值
时只提示复核数据源覆盖，并明确该区间仍可能包含特殊市场休市。后续接入
可靠的 A 股历史交易日历后，应使用交易所交易日替代通用工作日判断。
