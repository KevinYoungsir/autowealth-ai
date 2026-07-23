# 宏观影子校验与历史估值契约

## 范围

v0.16.0 PR 4 增加两项相互独立的基础契约：

- 对现有宏观宽表做非阻断、只观察的 shadow validation。
- 为未来历史估值数据源定义 point-in-time schema 和 provider protocol。

本阶段不增加宏观或估值数据源，不修改宏观评分、组合、因子、回测、
`run_status` 或 warning，也不接入交易。所有输出仅用于研究审计，不构成投资建议。

## Shadow-only 原则

宏观 validator 在 provider 或 CSV 加载完成后、现有 as-of 和 scoring 流程前运行。
它接收原 DataFrame 的深拷贝所展开的记录，但不会替换、过滤或改写传给
`select_macro_asof()` 的原 DataFrame。

开关 `macro_validation_enabled` 默认是 `True`。关闭时不生成 manifest 增量字段；
开启、关闭或 validator 自身异常时，以下业务输出必须保持一致：

- raw warnings、structured warnings 和 `warning_count`
- `run_status` 与 `run_status_reasons`
- 宏观 score、regime 和 multiplier
- 目标权重、持仓、交易、因子快照
- metrics、equity curve 和 benchmark curve

validator 异常被转换为有界的 `invalid` diagnostics。异常文本、traceback、本地路径、
Token、Cookie、请求头和密钥不会写入 manifest，研究运行继续使用原逻辑。

## MacroObservation

必需字段：

| 字段 | 规则 |
| --- | --- |
| `indicator` | 只能使用当前评分实际读取的稳定指标代码 |
| `observation_date` | 严格 ISO `YYYY-MM-DD`，无时区 |
| `available_date` | 严格 ISO `YYYY-MM-DD`，必需且不早于观察日 |
| `value` | 可转为有限 `float`，拒绝 NaN 和正负 Infinity |
| `source` | 非空安全机器标识，不接受路径或凭据文本 |

可选字段 `revision` 为稳定字符串或整数；`unit` 和 `frequency` 仅保存和透传，
本阶段不建立单位或频率注册表。

指标 catalog 与当前宏观评分保持一致：

```text
pmi
cpi_yoy
ppi_yoy
m2_yoy
social_financing_yoy
ten_year_yield
usd_cny
policy_score
external_risk_score
```

宽表 adapter 只展开上述指标，排除 `date`、`observation_date`、
`available_date`、`source`、`revision`、`unit` 和 `frequency` 等技术列。
空指标值不生成候选记录；缺失 `available_date` 会原样留给 validator 拒绝，
不会回填为 `observation_date`。adapter 不修改输入 DataFrame。

## Record Validity 与 PIT Eligibility

记录有效性是全局 schema 判断。第一版 reason codes 为：

```text
success
empty_input
invalid_schema
missing_indicator
missing_observation_date
missing_available_date
invalid_observation_date
invalid_available_date
available_before_observation
non_finite_value
duplicate_observation
duplicate_version
unsorted_dates
```

PIT eligibility 是记录相对于某个 `signal_date` 的可用性：

```text
observation_date <= signal_date
and available_date <= signal_date
```

PIT 聚合 reason codes 为 `future_observation`、`future_available_date` 和
`no_pit_eligible_record`。这些代码不会把记录全局判为 invalid，也不会改变现有
as-of 选择行为。

完全相同的 indicator、日期、revision、value 和 source 记录为
`duplicate_version`，确定性保留一条。同一 indicator 与 observation date 有多条
记录但 revision 缺失、重复或内容冲突时记录为 `duplicate_observation`。唯一 revision
的多个版本保持有效，validator 只统计版本数，不为 scoring 选择版本。

未排序输入增加 `unsorted_dates`，validator 只在内部副本上排序 diagnostics。

## Diagnostics

新 run 的 `run_manifest.json` 可选增加：

```json
{
  "macro_validation_diagnostics": {
    "schema_version": 1,
    "validation_mode": "shadow",
    "status": "valid",
    "reason_codes": ["success"],
    "raw_row_count": 18,
    "valid_row_count": 18,
    "rejected_row_count": 0,
    "coverage_ratio": 1.0,
    "rejected_counts": {},
    "source": "local_csv",
    "indicators": {},
    "pit_summary": {
      "signal_date_count": 2,
      "fully_available_count": 1,
      "partially_available_count": 0,
      "unavailable_count": 1,
      "reason_counts": {
        "no_pit_eligible_record": 1
      }
    }
  }
}
```

`raw_row_count` 表示宽表展开后的宏观候选记录数；`coverage_ratio` 仅表示
`valid_row_count / raw_row_count`，不是交易日或时间窗口覆盖率。`indicators` 只含
每个指标的计数和首末日期。PIT 只保存聚合计数，不保存逐 signal date 矩阵。

diagnostics 状态 `valid`、`partial`、`invalid`、`empty` 仅属于校验结果，不是研究
运行状态。字段不升级全局 artifact schema，不增加 artifact 文件，不改变必需文件。

真实报告只在 `macro_review.evidence.macro_validation_diagnostics` 展示压缩证据。
旧 run 缺失字段时显示 `absent`，损坏时显示 `invalid`；两种情况都不改变 HTTP、
宏观复核状态或风险等级。run detail 通过现有 manifest 原样只读暴露该增量字段。

## Historical Valuation Contract

`ValuationMetric` 第一版 catalog：

```text
pe_ttm
pb
ps_ttm
dividend_yield
market_cap
```

`ValuationRecord.symbol` 只接受正则 `^\d{6}$` 对应的 canonical 六位代码，且不做
trim、前后缀删除、大小写转换或供应商格式猜测。`SH600519`、`600519.SH`、
`sh.600519` 等 endpoint 专用代码均会被拒绝。canonical code 到 provider code 的
转换只能由 `HistoricalValuationProvider.provider_symbol()` 完成。

记录还必须包含 `metric`、`observation_date`、`available_date`、有限 `value`、
安全 `source` 和非空 `unit`；`revision` 可选。`available_date` 必须存在且不得早于
观察日。聚合入口同时要求 `requested_symbol`、`requested_metrics`、请求起止日和
`as_of_date`，并执行以下检查：

- record symbol 必须等于 requested symbol；
- metric 必须属于 requested metrics；
- `start_date <= observation_date <= end_date`；
- `start_date <= end_date`；
- `available_date > as_of_date` 的记录不会进入 PIT 可用 records，也不会计入
  available metric，并记录 `future_available_date`。

这些规则要求 provider 提交显式历史日期，但无法证明供应商日期真实，也无法识别
所有“把当前 snapshot 复制到多个历史日期”的伪历史序列。未来真实 provider 必须
补充来源、数据版本和 point-in-time 证据，并通过真实历史序列 acceptance tests；
本阶段没有生产 provider，因此不声称已经解决真实历史估值可得性或回填识别。

Provider protocol：

```python
class HistoricalValuationProvider(Protocol):
    def provider_symbol(self, canonical_symbol: str) -> str: ...
    def supports_metric(self, metric: ValuationMetric) -> bool: ...
    def fetch_historical_valuation(
        self,
        symbol: str,
        metric: ValuationMetric,
        start_date: date,
        end_date: date,
        as_of_date: date,
    ) -> ValuationProviderResult: ...
    def source_metadata(self) -> Mapping[str, JsonValue]: ...
```

本阶段只有 fake provider 离线测试，没有生产实现、provider chain 或网络客户端。

## Valuation Availability

状态与主 reason 使用严格白名单：

| status | 允许的主 reason |
| --- | --- |
| `available` | `success` |
| `partial` | `unsupported_metric`、`provider_exception`、`empty_response`、`future_available_date`、`insufficient_coverage`、`historical_valuation_unavailable` |
| `unavailable` | `provider_not_configured`、`unsupported_metric`、`provider_exception`、`empty_response`、`future_available_date`、`insufficient_coverage`、`historical_valuation_unavailable` |
| `invalid` | `invalid_schema`、`missing_available_date`、`non_finite_value` |

若 `available_date < observation_date`，`ValuationRecord` 会直接拒绝；当前没有为此
扩展新的 reason code，provider 响应聚合时可将相应输入归为 `invalid_schema`。

状态不变量如下：

- `available`：available metrics 非空且等于全部 requested metrics，missing 为空，
  records 非空。
- `partial`：available 与 missing 均非空、无交集，二者并集等于 requested metrics，
  且至少有一条 PIT 可用 record。
- `unavailable`：available 为空、missing 等于 requested、records 为空。
- `invalid`：available 为空、missing 等于 requested、records 为空，reason 只能表示
  输入或响应结构无效。

三个 metric 集合都会去重并按稳定 metric catalog 排序；records 中每个 metric 必须
属于 available metrics，且每个 available metric 至少有一条 record。直接构造和
`available`、`partial`、`unavailable`、`invalid` factories 共用同一套校验。

完整 reason catalog 为：

```text
success
provider_not_configured
unsupported_metric
provider_exception
empty_response
invalid_schema
missing_available_date
future_available_date
non_finite_value
insufficient_coverage
historical_valuation_unavailable
```

## Valuation Diagnostics

`ValuationDiagnostics` 是固定 schema，不接受任意顶层字段：

```text
schema_version
provider
requested_symbol
provider_symbol
requested_metrics
requested_start_date
requested_end_date
as_of_date
status
available_metrics
missing_metrics
row_count
accepted_row_count
rejected_row_count
coverage_ratio
reason_codes
reason_counts
source_metadata
exception_type       # 仅异常，可选
safe_summary         # 仅异常，可选
```

`row_count = accepted_row_count + rejected_row_count`。reason、metric 和 mapping key
按稳定顺序输出；不保存动态时间、随机 ID、完整 provider response、records、rows、
payload、headers 或 traceback。异常只保留异常类名、稳定 reason 和不复制原始异常
文本的 safe summary。

`source_metadata` 仍允许少量 provider 证据，但采用以下硬上限并在超限时拒绝：

- 最大嵌套深度：3；
- 单个 mapping 最大键数：32；
- 单个 list 最大长度：32；
- 单个字符串最大长度：512 字符；
- 完整 diagnostics UTF-8 JSON 最大 16 KiB。

凭据键在 camelCase、PascalCase、kebab-case、dotted.name 和 snake_case 统一后检查；
`apiKey`、`accessToken`、`clientSecret`、Authorization、Cookie 和密码类字段会被拒绝，
`token_count`、`authorization_status`、`cookie_policy` 等非凭据状态字段仍允许。字符串
中的 Bearer、凭据赋值和嵌入式 Windows、UNC、POSIX 绝对路径同样会被拒绝；HTTP(S)
URL、相对文档路径和 artifact JSON pointer 可以保留。

## 已知限制

- Macro validator 目前只生成 shadow diagnostics，不阻断无效记录进入原 scoring。
- 现有宏观 scoring 与 as-of 行为保持不变。
- 尚未实现宏观单位和频率验证，也未补充正式交易日历。
- Historical Valuation 只有 schema 和 protocol，未接真实供应商。
- Historical Valuation 未接入 real pipeline、value factor、cache、provider chain 或 API。
- 当前契约不能证明 provider 的历史日期、revision 或来源真实性，也不能检测所有
  当前 snapshot 伪装成历史序列的情况。
- 本阶段不声称已解决历史估值数据可得性、真实 point-in-time 证明和 revision 选择。
