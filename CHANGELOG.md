# 📝 更新日志

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 新增版本化 EOD operation request、immutable job lifecycle 和 Repository Protocol，
  以及同主机 SQLite schema v1 的 durable submit、幂等 alias、claim/lease 和显式 abandonment。
- 新增严格校验的版本化本地 A 股交易日历 artifact contract，以及只负责验证和构造
  单数据集 EOD runtime 的 production composition root。
- 新增 production EOD YAML 配置样例；日历来源与 generation repository 路径必须由
  部署方显式提供。
- 新增显式多数据集 EOD batch coordinator，按 canonical dataset identity 确定性排序并
  串行复用单数据集 coordinator；默认在首个失败后停止，也可显式继续并保留逐数据集结果。
- 新增真实 dry-run 规划路径，以及基于稳定 SHA-256 dataset identity 的单写锁协议和
  进程内实现；dry-run 不调用 Provider、不发布 generation，也不获取写锁。
- 新增 Provider 调用边界的有界临时失败重试、确定性退避、可注入 sleeper/monotonic clock
  以及按 Provider/endpoint 在单 runtime 内共享的进程内最小间隔限流；默认仍为单次调用且不等待。
- Provider attempt 以增量字段保留每次 invocation、retry number、实际退避和限流等待；
  provider chain position、fallback 顺序和既有结果字段保持不变。
- production config schema 升级为 version 2 以承载严格的 resilience section；既有 version 1
  五字段配置继续按单次调用、零等待的兼容默认值读取。
- 新增独立、显式授权的 EOD full-refresh executor；只有既有 planner 返回
  `full_refresh_required` 时才抓取完整 effective range 并发布 replacement generation。
- 新增显式 EOD repository maintenance executor：dry-run 只观察并分类 repository，
  真实执行只删除严格匹配的 stale staging 目录和 `current` 临时文件。
- maintenance 会按 `previous_generation_id` 检查完整 generation lineage；不可达或回滚
  generation 仅报告，不自动删除。

- 新增 path-independent EOD operation catalog：按 canonical dataset identity 排序，
  以完整日历 identity、storage identity、Provider 顺序与版本、重试和限流配置生成稳定指纹。
- 新增显式同步 EOD operation worker：每次 claim 前执行有界过期 lease recovery，
  支持四类 durable job、heartbeat lease、协作式副作用 checkpoint 和确定性 terminal summary。
### 安全
- operation job constructor、import 和读取路径不创建仓储或执行 EOD 操作；幂等键仅保存
  domain-separated SHA-256；schema v1 会严格验证物理表、列、外键及关键 partial unique index，
  已识别版本的物理损坏、record checksum、lifecycle 或不安全路径均关闭式失败且不自动修复。
- 日历和 composition 在 import 时不联网、不读取凭据、不写 repository，也不会自动执行
  Provider fetch、增量更新或 generation publication。
- 生产 EOD generation 必须存放在持久化 volume 或 durable filesystem；容器临时文件系统
  不得作为有效生产存储。
- 非 dry-run 的锁覆盖 current 检查、规划、抓取、校验和发布全流程；重复 dataset、锁冲突、
  Provider/校验异常和缺少 coordinator 均关闭式失败，不会伪造全局成功。
- 只有现有 `temporary_provider_failure` 分类可以重试；不支持、不可用、永久失败、格式错误
  和普通未分类异常均不会重试，诊断不保存原始异常、凭据、绝对路径或 traceback。
- full refresh 不合并旧历史 bars，partial、缺失交易日、区间外数据或 publication 校验失败
  均不激活新 generation；dry-run 不抓取、不限流、不等待、不获取写锁或写 repository。
- 非 dry-run maintenance 在调用方提供的同 dataset 写锁内重新检查 repository、删除精确
  临时残留并再次验证；未知、畸形、符号链接或谱系不明确的 artifact 均关闭式阻止清理。
- maintenance 不删除任何完整 generation，也不改变 `current.json`、manifest 或 parquet。

- worker 在 Provider 调用、publication、下一 dataset、maintenance 删除和 terminal transition
  前检查本地 lease ownership；控制异常原样上抛，失去 lease 后不再开始新的受控副作用。
- catalog 对未知、禁用或 execution context 不匹配的数据集关闭式失败；operation SQLite root
  与 generation repository root 必须分离且互不嵌套。
### 已知限制
- operation job SQLite 与 PR4B worker 仅支持同一主机的 durable filesystem 和单一有意 writer；
  本阶段不含 scheduler、CLI、API、自动 retention 或每日 ingestion。
- 进程内锁不能协调多个进程、容器或主机；生产多实例部署仍需实现同一锁协议的持久化或
  分布式锁管理器。
- 限流器仅协调单个 Python 进程，不是跨进程或分布式配额系统；当前退避不含 jitter。
- 本阶段仍不包含 API、CLI、scheduler、monitoring、自动 maintenance 调度、完整
  generation pruning 或自动每日 ingestion；batch 继续只做默认 incremental 的同步串行编排，
  不隐式执行 full refresh。

## [0.17.1] - 2026-08-13

### 修复
- 修复 GitHub Release draft discovery：不再使用只适用于已公开 Release 的 tag
  endpoint 查找 draft。
- 改为通过 authenticated paginated List releases 精确匹配 tag。
- draft 创建后重新发现并验证唯一匹配 Release，避免成功创建 draft 后立即返回 404。
- 多个同 tag 匹配时 fail-closed，不选择任意 Release。

### 安全
- 继续要求 remote annotated tag commit 精确等于 `origin/main`。
- 已公开 Release 不覆盖；只接受 `draft=true`、`prerelease=false` 的唯一匹配项。
- 保持制品、checksum、exact-three-assets 和 publish-after-validation 门禁。
- 不修改或重新发布失败的 v0.17.0 tag / Draft Release。

### 兼容性
- 本 patch 不修改 v0.17.0 引入的 EOD library capability。
- 不修改 research pipeline、provider behavior、schema/API contract 或生产部署行为。

## [0.17.0] - 2026-08-10

### 新增
- 新增领域级 EOD dataset/provider contract、显式数据集身份和确定性请求规划。
- 新增不可变、版本化的本地 EOD repository，以 generation manifest、内容校验和
  原子 `current` 指针发布有效代次。
- 新增 AKShare A 股 EOD adapter、指数主 adapter、独立指数日线 fallback adapter，
  以及保留逐次尝试证据的确定性 `EODProviderChain`。
- 新增 `EODIncrementalCoordinator`，支持 append-only 增量、overlap refresh 和显式
  `full_refresh_required` 结果。

### 变更
- 只有完整成功且通过校验的候选数据才可发布；partial result 保持 fail-closed。
- 发布前依次执行完整候选集与有效区间校验，重复或缺失交易日会阻止 publication，
  不做静默去重、修复或市场数据填造。
- 内容 checksum 未变化时返回确定性 no-op；repository 负责原子 publication，
  Coordinator 不隐式读取系统时钟或生成 UUID。
- 既有 legacy research pipeline 的行为和数据路径保持不变，尚未迁移到新 EOD stack。

### 安全
- 不新增真实交易能力，也不接入 DeepSeek 决策。
- 不引入隐藏 retry/backoff、rate limiting 或自动数据修复。
- 公开 diagnostics 不暴露凭据、本机路径或 traceback，Provider 失败保持可审计且不伪造数据。
- `qfq`/`hfq` 调整口径在没有明确安全的有界修订策略时返回
  `full_refresh_required`，不会与未复权数据静默混用。

### 已知限制
- 本版本仅提供 library-level incremental EOD infrastructure，不是自动化生产 ingestion。
- `TradingCalendar` 由调用方提供；本版本没有 production composition root 或具体日历实现。
- Coordinator 每次只更新一个 dataset，并采用 single-writer 假设；不提供并发锁或 CAS。
- 不包含 retry/backoff、rate limiting、batch updater、API、CLI、worker、scheduler、
  monitoring 或 orphan cleanup。
- 不迁移 legacy research pipeline；不提供 full-refresh executor。
- `qfq`/`hfq` 默认要求 full refresh，除非调用方提供经过验证的有界修订策略。

## [0.16.0] - 2026-07-29

### 新增
- 分离 research、fetch、signal、execution 和 metrics 窗口。
- 增加 resilient benchmark provider chain、严格质量校验和有界 diagnostics。
- 增加 additive structured warnings。
- 增加 shadow macro validation 和 historical valuation contracts。

### 变更
- 调仓与收益生效日期严格分离，warm-up 不进入正式指标。
- 因子最小样本、coverage 和 unavailable 语义统一。
- Benchmark cache 增加 SHA、coverage、generation 和原子发布校验。
- RunStore、API 和报告增量读取 benchmark、macro 与 warning diagnostics。

### 修复
- Structured warning enrichment 保持 best-effort，不改变研究运行结果。
- 可选 benchmark diagnostics 保持 normal、invalid、absent 兼容。
- 可选 macro diagnostics 损坏不再使必需 manifest 整体失效。

### 安全
- 公开 artifacts 对路径、凭据、headers、traceback 和异常文本统一脱敏。
- 递归公开数据、warning evidence、attempts 和 artifact refs 使用确定性预算。
- 历史 artifacts 不重写；run_status、metrics、curves 和 warning 语义不变。

### 已知限制
- Macro validator 仍为 shadow mode。
- Historical valuation 仍为 contract-only。
- 不新增交易、真实 DeepSeek、参数寻优或历史数据回填。

## [0.15.1] - 2026-07-17

### 新增
- 真实研究报告支持 `zh-CN` 与 `en-US`，未传 locale 时保持 `en-US` 兼容默认值；
  响应新增 `locale` 和 `Content-Language`。
- 新增前后端集中式本地化目录、机器字段中文标签和简体中文系统字体栈。
- 原始 warning 增加派生中文展示结构，保留原文、顺序、数量与风险等级。

### 变更
- 研究看板导航、状态、表格、报告章节、空错态和 mock fallback 统一为简体中文。
- 数据质量首屏按类别显示数量和最多 3 条中文样本，完整原始技术文本改为折叠查看。
- `partial_success`、基准 `unavailable` 和其他稳定机器值继续明确显示原值。

### 安全
- 本地化不修改真实 artifacts 或研究指标，不调用外部翻译、真实 DeepSeek、
  数据 provider 或交易接口，也不增加远程字体依赖。

## [0.15.0] - 2026-07-17

### 新增
- 新增 `GET /research/runs/{run_id}/report` 只读接口，基于真实研究 artifacts
  生成确定性结构化复核报告。
- Research Notes 支持所选真实 `run_id`，展示绩效、风险、因子、基准、宏观、
  数据质量、反方观点和研究边界。
- 新增真实与 mock 报告来源切换测试；真实来源不会调用 demo 或 mock report。

### 变更
- `partial_success`、基准 `unavailable` 和完整 warnings 在报告与页面中保持可见。
- 无真实运行时继续保留 `mock_demo` 演示回退，生产现有研究页面接口保持兼容。

### 安全
- 真实报告生成不调用 DeepSeek、不访问外部网络、不修改 artifacts、不执行交易，
  也不进行参数寻优。

## [0.1.0] - 2026-06-04

### 新增
- 🎉 项目初始发布
- 🤖 多智能体协作系统
  - 技术分析智能体（MACD、RSI、布林带、KDJ、均线）
  - 基本面分析智能体（PE/PB、股息率、成长性）
  - 情绪分析智能体（动量、成交量、波动率）
- 📊 数据获取模块
  - 支持Yahoo Finance数据源
  - 本地缓存机制
- 🎯 投资决策引擎
  - 加权投票决策机制
  - 置信度评估
- 🖥️ 可视化界面
  - Streamlit交互界面
  - 单股分析、批量分析、投资组合管理
- 🛠️ 命令行工具
  - 支持单股分析
  - 批量分析
  - 市场概览

### 技术特性
- Python 3.9+ 支持
- Pydantic 数据验证
- 模块化架构设计
- 完整的类型注解

## 版本说明

### 版本号格式
- **主版本号**：不兼容的API修改
- **次版本号**：向下兼容的功能新增
- **修订号**：向下兼容的问题修复

### 标签说明
- `Added` 新功能
- `Changed` 变更
- `Deprecated` 弃用
- `Removed` 移除
- `Fixed` 修复
- `Security` 安全

[未发布]: https://github.com/KevinYoungsir/autowealth-ai/compare/v0.17.1...HEAD
[0.17.1]: https://github.com/KevinYoungsir/autowealth-ai/compare/v0.17.0...v0.17.1
[0.17.0]: https://github.com/KevinYoungsir/autowealth-ai/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/KevinYoungsir/autowealth-ai/compare/v0.15.1...v0.16.0
