# 📝 更新日志

所有项目的显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

### 新增
- 添加更多技术指标（OBV、ATR、DMI）
- 支持加密货币分析
- 添加回测系统
- v0.16.0 P0 增加价格与基本面 warm-up 配置、四层窗口 manifest 以及
  factor snapshot 的 `signal_date` / `execution_date` 审计字段。
- v0.16.0 PR2 增加统一 `IndexDataProvider`、canonical benchmark symbol、
  AKShare primary/fallback provider chain 和 `benchmark_diagnostics.json`。
- v0.16.0 PR3 在现有 `warnings.json` 中增量增加 schema version 1 的 structured
  warnings，并通过 RunStore、API 和确定性报告只读暴露；raw warning 保持兼容。

### 优化
- 提升数据分析性能
- 优化可视化界面
- 真实研究信号改用 execution date 前一个组合对齐真实交易日，收盘调仓权重
  只影响成交后的收益区间；正式净值与指标继续严格限定在 research window。
- 因子最小样本要求集中管理，样本不足的输入标记为 unavailable，coverage 与
  实际参与评分的数据保持一致。
- 价格缓存按实际 fetch window 区分并验证覆盖，价格估值前向填充限制为 5 个
  组合交易日。
- 基准缓存增加 symbol、fetch 区间、SHA256、行数、首末日期和 source 校验；
  provider 返回值统一执行有限正数 close、80% 工作日估算总覆盖及首尾边界门槛，
  并保留包含请求窗口和脱敏异常的全部失败 attempt。
- 基准缓存细分 hit、不可读、SHA 不匹配、覆盖不足和 metadata 不一致 reason code；
  新写入使用不可变 generation parquet，并以最后原子替换的 metadata 作为 commit
  marker，旧缓存格式继续兼容读取。
- 新基准诊断通过 RunStore、API 和确定性真实报告只读暴露；旧 run 缺少该可选
  artifact 时继续按原结构读取，`benchmark_metrics.json` 保持兼容。
- Structured warning collector 按完整 raw 字符串保持首次顺序并同步去重；旧 run
  返回 `absent`，损坏结构返回 `invalid`，均不改变 legacy 分类或运行状态。
- Structured enrichment 改为阶段本地、best-effort 提交；漏登记时保留权威 raw
  warning 并发布 raw-only artifact，不再把 metadata 完整性升级为研究任务失败。

### 安全
- P0 不修改历史 research run，不访问真实网络，不调用 DeepSeek，不执行交易，
  不新增参数寻优或当前估值回填。
- PR2 不伪造、插值或替代不可用基准；异常技术文本限制长度并脱敏，artifact
  采用 staging 后原子发布，写入失败不留下半成品 run。
- PR3 对 structured evidence 强制 JSON-safe、有限浮点、相对 artifact 引用及
  路径/凭据检查；不回填历史 warning，不从原文动态推断 code。
- Structured evidence 增加 camelCase/PascalCase 凭据键识别、Bearer 脱敏和被标点
  包裹的 Windows、UNC、POSIX 绝对路径拒绝，同时允许状态计数、URL 和相对引用。

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
