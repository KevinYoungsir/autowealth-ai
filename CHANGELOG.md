# 📝 更新日志

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 新增严格校验的版本化本地 A 股交易日历 artifact contract，以及只负责验证和构造
  单数据集 EOD runtime 的 production composition root。
- 新增 production EOD YAML 配置样例；日历来源与 generation repository 路径必须由
  部署方显式提供。

### 安全
- 日历和 composition 在 import 时不联网、不读取凭据、不写 repository，也不会自动执行
  Provider fetch、增量更新或 generation publication。
- 生产 EOD generation 必须存放在持久化 volume 或 durable filesystem；容器临时文件系统
  不得作为有效生产存储。

### 已知限制
- 本阶段仍不包含 batch updater、retry/backoff、锁、API、CLI、worker、scheduler、
  monitoring、full-refresh executor 或自动每日 ingestion。

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
