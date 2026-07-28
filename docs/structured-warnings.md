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
去重逻辑生成；`warning_count` 仍只按该数组计算。新 run 会在完成原有完整字符串
去重后，逐项替换其中的绝对路径、凭据、header 和 traceback 危险片段。该替换不增加、
删除或重新排序 warning，普通非敏感 warning 保持逐字不变。Structured metadata 是
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

`evidence` 只允许 exact `dict`、exact `list`、exact `tuple` 和 JSON scalar；
tuple 会确定性转换为 JSON list。`UserDict`、`defaultdict`、Mapping/list 子类、
generator、set、NaN、infinity、`Path`、datetime、exception、traceback、bytes、
DataFrame、Series 和其他自定义实例会被拒绝且不会被展开。绝对路径、`file://`、
明显凭据字段和 secret-like 内容也会被拒绝。敏感键先将 camelCase、PascalCase、
kebab-case 和 dotted.name 规范化后判断；
`apiToken`、`accessToken`、`clientSecret`、`openaiApiKey` 等会被拒绝，而
`token_count`、`authorization_status`、`cookie_policy` 等状态或计数字段仍可使用。

固定容量限制为：

```text
最大嵌套容器深度                 3
单个 mapping 最大键数           32
单个 list/tuple 最大项目数      32
单个字符串最大字符数            512
完整 evidence UTF-8 JSON        16 KiB
```

mapping key 按字典序验证和输出，list/tuple 保持原顺序。任一边界超限都会拒绝整个
evidence，不会静默截断；只有异常 `safe_summary` 使用明确的长度上限。

exception 证据只保留 `exception_type`、稳定 `reason_code` 和最长 256 字符的
`safe_summary`。当前确定性格式为 `<ExceptionType> [details redacted]`，
不保留 traceback、本地绝对路径、Authorization、Token、Cookie、API Key、Secret 或
密码。benchmark evidence 只引用 canonical symbol、reason code、provider、请求窗口和
`benchmark_diagnostics.json` pointer，不复制完整 diagnostics。

Windows drive、UNC 和 POSIX 根路径即使被括号、引号或标点包裹也会被拒绝；
`https://`、`http://`、artifact 相对文件名和合法 JSON pointer 不会被当作本地路径。
`artifact_refs` 的文件部分只能使用已登记的相对 artifact 文件名；pointer 部分单独
按 RFC 6901 校验，保留合法 `~0`、`~1`，拒绝绝对路径、`..`、URL、`file://`、
凭据、无效转义以及在 pointer 中编码隐藏的 Windows、UNC 或 POSIX 路径。
`docs.json` 是明确登记的安全引用名，因此 `docs.json#/a~1b/~0value` 合法；该登记
不代表允许任意 `.json` 文件。

文本脱敏不会信任输入中伪造的内部占位符；合法占位符与额外敏感后缀拼接时会重新
脱敏。占位符只有位于值末尾、后接空白，或后接以空白/值末尾终止的句末标点、
分号或逗号时才构成完整安全值；`.abc123`、`)abc123`、`!abc123`、`_abc123`、
`-abc123` 和 `/abc123` 等紧邻后缀会连同 credential value 重新安全化。单独的
既有占位符、句末标点和正常说明文字保持幂等。

Authorization 与 Proxy-Authorization 使用 header-aware 解析：保留 Bearer、
Basic、Digest 或自定义 scheme，只替换 credential 主体；Digest 参数作为一个整体
替换。Cookie 连续处理 `name=value` 段并保留 cookie name，第一个不符合 pair 的段
及其后文本作为说明保留。Set-Cookie 至少替换首个 pair，Domain、Path、Expires、
Max-Age、SameSite、HttpOnly 和 Secure 等后续属性继续经过通用路径与凭据检查。
该解析是单次确定性处理，不反复运行贪婪正则。

cache reference 在字符规范化之前检查原始 basename，也检查有限次 URL 解码和
规范化后的安全名；任一阶段命中凭据形态都只返回稳定的
`redacted-cache-reference` 与可信扩展名。

公开 artifact 的通用递归处理只展开 exact `dict`、exact `list` 和 JSON scalar，
默认限制为 8 层、每个容器 64 项、4096 个节点、单字符串 4096 字符、累计字符串
65536 字符和 256 KiB JSON。特定的 metrics、warning summary 与确定性报告只使用
显式的更高有界预算，不存在无界递归。预算耗尽时不会返回原始对象。

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
- evidence 超过上述任一容量边界时同样返回 `invalid`，API 继续返回 HTTP 200。
- 整个 `warnings.json` 缺失：继续按必需 artifact 错误处理。
- 系统不运行时回填旧 warning，也不通过字符串推断旧 run 的 code。
- 历史文件不会重写；公开 API 和报告只在内存中替换旧 raw warning 的危险片段，
  并保持数量、顺序、legacy 分类和原 `run_status`。
- legacy 分类通过每次磁盘读取时新建的私有 `str` 标记保持；该标记不进入 JSON、
  artifact 或 API schema。调用方对公开结果执行 JSON round-trip 后会丢失标记，
  因此第三方再次运行 legacy 文本分类器不保证得到脱敏前的同一类别。

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
- Raw warning 仍可能包含第三方 provider 的非敏感措辞；公开边界只能识别明确的
  路径、凭据赋值、Bearer、header 和 traceback 形态，不能保证识别任意自然语言中
  隐含或无标签的所有秘密。
- Cookie header 以分号分段；连续的 `name=value` 视为 cookie pair，第一个不符合
  该形式的段开始视为普通说明文字。若第三方把说明伪装成 `name=value`，该段会按
  cookie value 保守脱敏。
- Benchmark diagnostics 的 cache reference 仅保存经双重凭据检查的安全 basename。
  新 artifact 的公开 `attempts` 固定保留执行顺序中的前 32 项，并使用
  `attempts_total`、`attempts_truncated`、`omitted_count` 记录完整计数；旧字段只在
  RunStore 内存中兼容读取，不迁移历史文件。完整 runtime attempts 只在单次流水线
  内存中用于逐条 warning enrichment，每条 structured evidence 只保存自身对应的
  单个安全 attempt 摘要。
- 本阶段不增加 Macro Validator、历史估值 provider、交易能力或全系统 warning
  统一改造。
