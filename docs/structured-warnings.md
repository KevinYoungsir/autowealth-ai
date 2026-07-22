# 结构化研究警告

## 目标与边界

Structured Research Warnings 为真实研究流水线已有的 warning 增加稳定、机器可读、
可审计的元数据。本功能只结构化既有警告，不新增数据质量规则，不改变指标、曲线、
`run_status`、`partial_success` 或 benchmark `unavailable` 判定，也不重写历史 run。

所有内容仅用于研究与教育，不构成投资建议、交易指令或收益承诺。历史研究结果不代表
未来表现。

## Raw 与 Structured 双轨

新 run 的 `warnings.json` 使用以下增量结构：

```json
{
  "warnings": ["benchmark 000300 unavailable: provider unavailable"],
  "structured_warnings_schema_version": 1,
  "structured_warnings": [
    {
      "code": "benchmark_data_unavailable",
      "severity": "error",
      "scope": "benchmark",
      "message": "benchmark 000300 unavailable: provider unavailable",
      "source": "benchmark_provider_chain",
      "evidence": {
        "canonical_symbol": "000300",
        "reason_code": "provider_exception"
      },
      "affected_symbols": ["000300"],
      "artifact_refs": ["benchmark_diagnostics.json#/benchmarks/000300"],
      "retryable": true,
      "documentation_ref": "docs/structured-warnings.md"
    }
  ]
}
```

`warnings` 是兼容权威来源，继续由原有阶段返回值、append/extend 和完整字符串
去重逻辑生成；`warning_count` 仍只按该数组计算。Structured metadata 是
best-effort 增量。仅当 enrichment 完整时，新 run 才同时写入 structured 字段并满足：

```text
len(warnings) == len(structured_warnings)
structured_warnings[i].message == warnings[i]
```

任一最终 raw warning 缺少显式 metadata 时，流水线不会猜测 code、增加 warning、
改变 `run_status` 或中止 artifacts 发布，而是把该 run 的 `warnings.json` 整体退化为：

```json
{"warnings": ["..."]}
```

此时不会写入半完整的 schema version 或 structured list，RunStore 将状态解释为
`absent`。调用方明确向 artifact writer 传入 structured list 时，writer 仍严格验证
schema、数量、message 对齐和 evidence 安全，并可拒绝无效调用。

## Schema

必需字段：

- `code`：显式注册的稳定 snake_case 机器码。
- `severity`：warning 自身严重程度。
- `scope`：产生 warning 的研究阶段。
- `message`：与同位置 raw warning 逐字一致。
- `source`：稳定的小写机器标识。

可选字段：

- `evidence`：严格 JSON-safe 的结构化证据。
- `affected_symbols`：稳定去重并保留首次出现顺序的 canonical symbol。
- `artifact_refs`：artifact 文件名及可选 JSON pointer，不允许绝对路径。
- `retryable`：是否适合在外部条件恢复后重新运行。
- `user_action`：研究复核动作，不是交易动作。
- `documentation_ref`：相关项目文档。

`severity` 第一版仅允许：`info`、`warning`、`error`。它与真实报告中的 risk
severity 相互独立，不参与风险 flag 升降级。

实际使用的 `scope`：

```text
price_provider, benchmark, fundamental, macro, universe, factor, portfolio
```

## Code Catalog

第一版仅注册已有生产点实际使用的业务语义：

```text
price_provider_failed
price_cache_unavailable
price_data_quality_degraded
fundamental_data_unavailable
fundamental_point_in_time_rejected
macro_data_unavailable
universe_point_in_time_unverified
factor_data_incomplete
portfolio_construction_degraded
benchmark_data_unavailable
benchmark_provider_fallback_used
benchmark_cache_rejected
```

code 在明确的流水线阶段边界设置，不从英文 message、正则或关键词动态推断。来自
factor、macro、portfolio 等模块的 warning list 只在其已知阶段上下文中映射。

## Evidence 安全规则

`evidence` 只允许 `null`、布尔值、整数、有限浮点数、字符串、列表和字符串键对象。
NaN、infinity、`Path`、datetime、exception、traceback、bytes、DataFrame、Series 和
自定义实例会被拒绝。绝对路径、`file://`、明显凭据字段和 secret-like 内容也会被
拒绝。敏感键先将 camelCase、PascalCase、kebab-case 和 dotted.name 规范化后判断；
`apiToken`、`accessToken`、`clientSecret`、`openaiApiKey` 等会被拒绝，而
`token_count`、`authorization_status`、`cookie_policy` 等状态或计数字段仍可使用。

exception 证据只保留 `exception_type`、稳定 `reason_code` 和最长 240 字符的
`safe_summary`；
不保留 traceback、本地绝对路径、Authorization、Token、Cookie、API Key、Secret 或
密码。benchmark evidence 只引用 canonical symbol、reason code、provider、请求窗口和
`benchmark_diagnostics.json` pointer，不复制完整 diagnostics。

Windows drive、UNC 和 POSIX 根路径即使被括号、引号或标点包裹也会被拒绝；
`https://`、`http://`、artifact 相对文件名和合法 JSON pointer 不会被当作本地路径。

## 确定性

- 每个流水线阶段使用本地 collector，不直接修改 run-level raw warning。
- 父层仅提交它按旧数据流实际接受的阶段 metadata；阶段失败时未被接受的中间
  metadata 会被丢弃。
- 最终 structured list 按已经去重的权威 raw 顺序投影；投影不完整则 raw-only 发布。
- 完整 raw 字符串是唯一去重键，保留第一次出现顺序。
- 相同 raw 字符串再次出现时，两条序列都忽略该次出现。
- code 相同但 raw message 不同的 warning 分别保留。
- 不排序 severity 或 scope，不写 UUID、warning ID、occurrence count 或当前时间。
- `affected_symbols` 稳定去重；JSON 语义不依赖 evidence key 顺序。

## 旧 Run 与损坏数据

- 旧 run 或 enrichment 不完整的新 run 只有 `{"warnings": [...]}`：
  `structured_status=absent`，raw 正常读取。
- schema version 或结构缺失、错误、数量不符、message 不齐或 evidence 非法：
  `structured_status=invalid`，structured 返回空数组，raw 仍正常读取。
- 整个 `warnings.json` 缺失：继续按必需 artifact 错误处理。
- 系统不运行时回填旧 warning，也不通过字符串推断旧 run 的 code。

## API Additive Fields

既有 `total`、`categories`、`samples`、`raw_warnings`、`raw_returned` 和
`raw_truncated` 保持语义不变。warning summary 增量返回：

```text
structured_available
structured_status
structured_warnings_schema_version
structured_warnings
severity_counts
scope_counts
```

legacy `categories` 和 `samples` 继续使用既有文本分类器；`severity_counts` 与
`scope_counts` 仅根据合法 structured warnings 计算。真实报告在
`data_quality_review.evidence` 中增量暴露相同结构，不改变风险评分。

## 已知限制

- 历史 run 不自动获得结构化元数据。
- Structured metadata 是 best-effort；测试负责发现已知生产路径的 metadata
  漏登记，生产任务不会因此失败。
- Raw warning 仍可能包含第三方 provider 原始措辞；结构化 evidence 执行更严格的
  路径和凭据安全规则。
- 本阶段不增加 Macro Validator、历史估值 provider、交易能力或全系统 warning
  统一改造。
