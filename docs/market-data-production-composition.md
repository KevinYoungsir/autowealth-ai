# EOD Production Calendar and Composition

## Decision

AutoWealth 的生产 EOD runtime 使用部署方显式提供的版本化本地交易日历 artifact。
`autowealth.market_data.composition` 只负责读取配置、验证依赖并构造单数据集 runtime；
它不执行抓取、更新或发布。

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

`configs/eod_production.example.yaml` 展示 schema version 1。配置必须显式提供：

- `repository_root`；
- `calendar_source`；
- 完整 `EODDatasetKey`；
- 有序 `provider_order`。

相对路径按最近的项目根目录解析；项目根目录不可识别时按配置文件目录解析。配置不
包含 API Key，也没有用户目录或本机绝对路径默认值。生产环境可显式提供挂载路径。

## Composition flow

```text
YAML configuration
  -> VersionedLocalTradingCalendar
  -> EODDatasetKey
  -> LocalEODFileRepository
  -> AKShare primary/fallback providers
  -> EODProviderChain
  -> EODIncrementalCoordinator
```

`build_eod_runtime` 只执行 `VALIDATE + CONSTRUCT`。AKShare 仍在首次显式 `fetch` 时才
延迟导入；构造 runtime 不会访问网络、创建 generation、写 `current.json` 或调用
Coordinator `update`。

## Operational responsibility

- 部署方负责日历来源授权、版本标识、更新频率、完整性验证和回滚。
- 日历更新必须先生成新 artifact、离线验证，再原子替换部署引用；应用不会修改源文件。
- `repository_root` 必须位于 persistent volume 或 durable filesystem。Vercel/容器临时
  文件系统不满足要求。
- 单 writer 约束继续有效；当前 composition 不提供锁、CAS 或并发写保护。

## Trade-offs and known limitations

本设计避免伪造交易日期，也保留可审计版本，但需要独立运维流程提供真实日历。当前
仍不包含 batch updater、retry/backoff、rate limiting、full-refresh executor、orphan
cleanup、API、CLI、worker、scheduler、monitoring 或自动每日 ingestion。旧 research
pipeline 尚未迁移到新 EOD stack。

本模块不包含真实交易能力，不调用 DeepSeek，也不改变既有研究结果或历史 artifacts。
