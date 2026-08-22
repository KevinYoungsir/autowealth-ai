# EOD Production Calendar and Composition

## Decision

AutoWealth 的生产 EOD runtime 使用部署方显式提供的版本化本地交易日历 artifact。
`autowealth.market_data.composition` 只负责读取配置、验证依赖并构造单数据集 runtime；
它也可以把调用方显式提供的多个 runtime 组装为 batch coordinator，但构造本身不执行
抓取、更新或发布。

## Context

中国交易所开闭市日期不能通过周一至周五规则可靠推断，也不能为了形成完整历史而在
仓库中生成未经来源验证的数据。第一版因此不内置或自动下载生产日历，而是要求部署
流程提供经过来源核验的只读 JSON 文件。

日历 schema version 1：

```json
{
  "schema_version": 1,
  "calendar_id": "cn_a_share_exchange_calendar",
  "calendar_version": "operator-supplied-version",
  "timezone": "Asia/Shanghai",
  "coverage_start": "2024-01-01",
  "coverage_end": "2024-01-03",
  "days": [
    {"trade_date": "2024-01-01", "is_trading_day": false},
    {"trade_date": "2024-01-02", "is_trading_day": true},
    {"trade_date": "2024-01-03", "is_trading_day": true}
  ]
}
```

示例只说明结构，不代表真实交易日。artifact 必须对覆盖区间内的每个自然日显式给出
`is_trading_day`，不能省略日期后依靠程序猜测。

## Validation

加载器关闭式拒绝以下输入：

- 文件缺失、不可读、非 UTF-8 或无效 JSON；
- 未知字段、缺少字段或不支持的 schema version；
- 非 ISO 日期、重复、乱序、覆盖缺口或空日历；
- 非布尔 `is_trading_day`、错误时区或无效 identity/version；
- 超出 artifact 覆盖范围的查询。

异常只暴露稳定 code 和通用 message，不包含绝对路径、凭据或原始 payload。日期表示
`Asia/Shanghai` 的交易 session date，不进行 datetime 或 UTC 日期偏移。

## Production configuration

`configs/eod_production.example.yaml` 展示 production config schema version 2。配置必须显式提供：

- `repository_root`；
- `calendar_source`；
- 完整 `EODDatasetKey`；
- 有序 `provider_order`。

配置可选提供严格的 `retry_policy` 和 `rate_limit_policy`。缺省值分别为
`max_attempts=1` 和 `minimum_interval_seconds=0`，因此旧配置不重试、不等待。启用后，
单 Provider 的 `max_attempts` 包含第一次调用且上限为 5；退避按
`min(initial_backoff * multiplier ** retry_index, max_backoff)` 计算，不使用 jitter。
schema version 1 的既有五字段配置仍可读取，并映射到上述兼容缺省值；v1 不接受新增
resilience 字段。version 2 严格允许这两个可选 section，未知字段仍关闭式拒绝。

相对路径按最近的项目根目录解析；项目根目录不可识别时按配置文件目录解析。配置不
包含 API Key，也没有用户目录或本机绝对路径默认值。生产环境可显式提供挂载路径。

## Composition flow

```text
YAML configuration
  -> VersionedLocalTradingCalendar
  -> EODDatasetKey
  -> LocalEODFileRepository
  -> AKShare primary/fallback providers
  -> bounded retry policy + local provider/endpoint rate limiter
  -> EODProviderChain
  -> EODIncrementalCoordinator
  -> optional explicit EODFullRefreshExecutor
  -> optional explicit EODRepositoryMaintenanceExecutor
```

`build_eod_runtime` 只执行 `VALIDATE + CONSTRUCT`。AKShare 仍在首次显式 `fetch` 时才
延迟导入；构造 runtime 不会访问网络、创建 generation、写 `current.json` 或调用
Coordinator `update`。

`build_eod_full_refresh_executor` 可从一个已验证 runtime 和调用方显式提供的同一 dataset
lock manager 构造独立 full-refresh execution boundary。构造过程同样不读取 current、抓取、
等待、获取锁或发布。普通 `EODIncrementalCoordinator` 和既有 batch 不会因为该构造函数
自动执行 full refresh。

`build_eod_repository_maintenance_executor` 从已验证 runtime 和调用方显式提供的同一
dataset lock manager 构造 repository maintenance boundary。构造过程不读取或创建
repository，也不会自动清理。dry-run 只观察并分类，不获取锁；真实执行在锁内重新检查，
只删除精确匹配的 stale staging 目录和 `current` 临时文件，再次检查后才释放锁。完整
generation（包括不可达和回滚候选）只报告，不删除；谱系不明确、畸形内容或符号链接会
关闭式阻止清理。

多个 runtime 可通过 `build_eod_batch_coordinator` 显式组装：

```text
explicit EODRuntimeStack values
  -> reject duplicate dataset identities
  -> EODBatchCoordinator
  -> canonical dataset ordering
  -> serial EODIncrementalCoordinator execution
```

batch 默认在首个失败后停止，也支持显式 continue-on-failure。dry-run 只执行 current
读取和规划，在 Provider fetch 前结束；它不获取写锁，也不发布 generation。真实运行的
锁从完整 canonical dataset identity 生成稳定 SHA-256 key，并覆盖读取、规划、抓取、
校验和发布全流程。batch 不是跨 dataset 原子事务，后续 dataset 失败不会回滚此前已经
成功发布的独立 generation。dry-run 不持写锁，因此其计划不保证后续执行时仍对应相同
repository state。

只有 exact `EODFullRefreshRequest` 可以进入显式 full-refresh executor。真实执行会先获取写锁，
再在锁内首次读取 current 并调用同一 planner。只有结果为
`full_refresh_required` 才构造覆盖完整 `effective_range` 的 Provider request；其他 planner
状态返回 `not_eligible`，不抓取。replacement candidate 完全来自本次完整 Provider 结果，
不会与旧 bars 合并。partial、缺失交易日、区间外数据或校验失败均不发布；内容 checksum
未变化返回 `unchanged_content`。内容变化时继续复用既有 immutable generation、manifest、
lineage 和原子 `current` pointer。dry-run 是观察性的，不获取写锁、调用 Provider/limiter/
sleeper 或创建 generation；该结果不保留锁或 reservation，返回后 current 仍可能变化。

## Operational responsibility

- 部署方负责日历来源授权、版本标识、更新频率、完整性验证和回滚。
- 日历更新必须先生成新 artifact、离线验证，再原子替换部署引用；应用不会修改源文件。
- `repository_root` 必须位于 persistent volume 或 durable filesystem。Vercel/容器临时
  文件系统不满足要求。
- 内置 `InProcessEODDatasetLockManager` 提供单进程、非阻塞的同 dataset 单写保护；它不
  协调多个进程、容器或主机。多实例生产部署必须注入实现同一协议的共享锁管理器。
- batch 严格串行执行，不实现并行 Provider 请求。只有
  `temporary_provider_failure` 会在当前 Provider 内按显式预算重试，耗尽后才进入下一个
  fallback；其他错误不重试。
- 最小间隔限流按 `(provider_name, endpoint_name)` 在同一 runtime/ProviderChain 内共享，
  不按股票代码拆分，也不是整个 Python 进程的全局单例。重试退避完成后会基于 monotonic
  clock 重新计算限流剩余时间，避免再次等待
  完整间隔。同一 identity 串行取得 invocation slot；不同 identity 只短暂共享 state registry
  锁，不会在某一 identity 睡眠时被全局阻塞。state 的生命周期等于 limiter/runtime，实际
  key 数由最多 32 个已配置 Provider identity 限定。
- 非 dry-run 的 Provider 重试和等待发生在 dataset 写锁内。第一版不提前释放锁，以免在
  current 检查与 publication 之间重新引入 TOCTOU；部署方应使用有界预算。

- maintenance 必须使用与 incremental/full-refresh writer 相同的 dataset lock manager。
  内置进程锁只适用于单进程；多实例部署必须注入共享锁。maintenance 不是 startup hook 或
  background task，只有调用方显式提交 request 时才检查或清理。
- 不得把 unreachable generation 视为自动删除授权。回滚候选、完整历史 generation 和
  unknown artifact 均保留；运维人员应在独立审计后处理超出精确临时残留范围的内容。

## Trade-offs and known limitations

本设计避免伪造交易日期，也保留可审计版本，但需要独立运维流程提供真实日历。当前
batch 仅编排调用方显式给出的 dataset，不发现股票池，也不执行调度。当前仍不包含
分布式限流、随机 jitter、自动 maintenance 调度、完整 generation pruning、API、CLI、
worker、scheduler、monitoring 或自动每日 ingestion。既有 batch 也没有 full-refresh
execution mode；需要完整替换时，调用方必须使用独立 executor 显式执行。不同 runtime
不共享 limiter state，进程内限流也不能协调多个 worker、容器或主机。旧 research
pipeline 尚未迁移到新 EOD stack。

本模块不包含真实交易能力，不调用 DeepSeek，也不改变既有研究结果或历史 artifacts。
