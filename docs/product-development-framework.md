# AutoWealth 后续开发总框架（供 Codex 执行）

## 1. 项目定位

AutoWealth 后续定位：

> A 股数据研究平台 + 用户个人投资工作台 + 会员内容平台

核心原则：

- 研究与教育用途，不执行真实交易。
- 不承诺收益，不伪造缺失数据。
- 历史研究可复现、可审计。
- 用户数据按账号强隔离。
- 先完成数据平台，再建设账号与用户功能，最后建设会员商业化。
- 当前继续采用模块化单体，不提前拆微服务。

---

## 2. 总体架构

```text
Next.js 前端
    ↓
FastAPI API
    ↓
领域模块
├── identity
├── market_data
├── securities
├── research
├── screening
├── watchlist
├── portfolio
├── journal
├── industry
├── notification
├── membership
├── billing
└── admin
    ↓
PostgreSQL + Redis + 对象存储/Parquet + Worker/Scheduler
```

### PostgreSQL

保存用户、身份、会话、自选、筛选记录、组合、复盘、会员、订单、任务状态、数据版本、证券主数据等事务数据。

### Parquet / 对象存储

保存 15 年历史行情、每日增量行情、供应商原始数据、因子快照、回测结果、大型研究 artifacts。

### Redis

保存登录会话、验证码、限流状态、任务锁和热点缓存。

### Worker / Scheduler

执行每日行情更新、财报更新、因子计算、行业计算、提醒、报告生成、会员到期和数据修复。

---

## 3. 领域模块

### market_data

职责：

- 交易日历
- 股票/指数 Provider 与 fallback
- Raw、Normalized、Derived 三层数据
- 每日增量抓取
- 数据质量校验
- 数据版本
- ingestion run
- 数据补数和重跑

建议结构：

```text
autowealth/market_data/
├── providers/
├── schemas/
├── normalization/
├── validation/
├── ingestion/
├── versioning/
├── repositories/
└── jobs/
```

### securities

职责：

- 证券主数据
- 代码标准化
- 上市/退市状态
- 公司行动
- 行业归属
- 指数成分
- 个股详情聚合

### research

职责：

- 因子
- 组合构建
- 回测
- point-in-time
- signal/execution
- artifacts
- coverage 和 warning
- 确定性报告

要求：

- 每次结果记录数据版本、模型版本、配置摘要。
- 旧 run 永久只读。
- 新字段增量兼容。
- 禁止未来数据泄漏。

### identity

统一用户主体：

```text
users
  ↓
auth_identities
├── phone
├── email
└── wechat
```

职责：

- 手机验证码登录
- 邮箱验证码登录
- 微信扫码/OAuth
- 多身份绑定
- 解绑
- 账号合并
- 会话、设备、安全事件
- 数据导出与注销

### watchlist

- 多自选分组
- 自选股
- 标签和备注
- 加入原因
- 提醒规则
- 排序和筛选

### screening

- 筛选条件
- 筛选运行记录
- 结果快照
- 排除原因
- 数据版本
- 因子版本
- 用户备注

历史筛选记录不得被最新数据覆盖。

### portfolio

区分：

```text
research portfolio
simulated portfolio
user recorded portfolio
```

保存持仓、交易、调仓、净值、风险、行业暴露、因子暴露和基准比较。

### journal

保存交易前逻辑、买卖原因、持有期、风险条件、情绪、结果、复盘结论和附件。

### industry

保存行业主数据和带有效期的历史行业归属：

```text
effective_from
effective_to
source
```

并提供行业涨跌、市场宽度、成交、估值、因子和用户持仓暴露。

### notification

- 邮件
- 短信
- 站内通知
- 微信通知（后续）
- 自选提醒
- 安全通知
- 会员到期通知

安全通知和营销通知必须分开。

### membership

使用 entitlement，不在代码中散落 `is_vip`：

```text
watchlist.max_count
screening.daily_limit
portfolio.max_count
advanced_factors.enabled
alerts.enabled
exports.enabled
research_history_years
```

### billing

- 支付订单
- 回调
- 退款
- 优惠券
- 发票
- 对账
- 幂等
- 审计

### admin

- 数据任务与质量
- Provider 状态
- 用户与身份
- 账号冲突
- 会员和订单
- 内容管理
- 通知记录
- 管理员操作审计

---

## 4. 数据库核心表

### 用户与认证

```text
users
auth_identities
auth_challenges
sessions
devices
account_link_requests
consent_records
security_events
```

### 行情与研究

```text
securities
trading_calendars
market_bars_daily
market_bars_intraday
corporate_actions
fundamental_reports
valuation_observations
industry_memberships
index_constituents
data_ingestion_runs
data_provider_attempts
data_quality_issues
data_versions
factor_observations
research_runs
```

### 用户投资数据

```text
watchlists
watchlist_items
watchlist_tags
watchlist_alerts
screening_runs
screening_results
portfolios
portfolio_positions
portfolio_transactions
portfolio_snapshots
trade_journals
trade_review_attachments
```

### 商业化

```text
plans
entitlements
plan_entitlements
subscriptions
payment_orders
payment_events
refunds
coupons
invoices
membership_events
```

---

## 5. 数据平台三层

### Raw

记录：

```text
provider
endpoint
request_parameters
fetched_at
payload_hash
raw_file
```

### Normalized

统一字段：

```text
symbol
trade_date
open
high
low
close
volume
amount
adjustment_type
source
data_version
```

### Derived

保存技术指标、因子、行业指标、估值分位、风险指标、组合净值和横截面排名。

---

## 6. 每日增量更新

```text
交易日历检查
→ 确认最后成功日期
→ 拉取缺失日期
→ Provider fallback
→ Schema 校验
→ 覆盖校验
→ 异常值校验
→ 保存 Raw
→ 标准化
→ 公司行动处理
→ 写入 Normalized
→ 增量计算 Derived
→ 发布数据版本
→ 刷新缓存
→ 记录任务与告警
```

每次运行记录：

```text
ingestion_run_id
trade_date
requested_symbols
successful_symbols
failed_symbols
provider_attempts
data_version
quality_issue_count
started_at
completed_at
status
```

要求：

- 幂等
- 可重试
- 可断点续跑
- 可按日期或股票补数
- 不覆盖已审核历史版本
- 失败时不能显示“今日已更新”

---

## 7. 版本路线图

### v0.16.0 数据质量加固

- PR 1：Warm-up / Signal / Execution / Metrics（已完成）
- PR 2：Benchmark Provider Resilience
- PR 3：Structured Warnings
- PR 4：Macro Validator + Valuation Contract

### v0.17.0 每日增量数据平台

建议 PR：

1. `feat(data): add ingestion run and data version models`
2. `feat(data): add incremental daily market update`
3. `feat(data): add daily data quality gates`
4. `feat(research): add incremental factor refresh`
5. `feat(admin): add data operations dashboard`

### v0.17.1 每日研究更新

- 每日因子快照
- 行业快照
- 组合净值
- 确定性报告
- 自选股数据准备
- 数据更新时间和覆盖率

### v0.18.0 Identity Core

建议 PR：

1. `feat(identity): add users identities and sessions`
2. `feat(identity): add email verification sign-in`
3. `feat(identity): add phone verification sign-in`
4. `feat(identity): add account security center`

### v0.18.1 WeChat Identity

- 微信扫码
- 微信移动端授权
- OAuth state
- 微信绑定/解绑
- 手机/邮箱与微信绑定

### v0.18.2 Account Linking & Recovery

- 三身份互绑
- 冲突检测
- 双重验证账号合并
- 手机/邮箱变更
- 账号恢复
- 数据导出和注销

### v0.19.0 Market Workspace

- 个股详情
- 自选
- 行业板块
- 用户提醒
- 数据更新时间和质量状态

### v0.20.0 User Research Workspace

- 选股记录
- 筛选结果快照
- 模拟组合
- 用户组合
- 交易复盘
- 行为分析

### v0.21.0 Membership

- 套餐与 entitlement
- 订阅
- 内容权限
- 支付订单
- 回调
- 退款、优惠券和对账
- 会员运营后台

### v0.22.0 Intraday Data

前提：

- 数据授权明确
- 日更平台稳定
- 用户规模验证

能力：

- 分钟行情
- 盘中自选
- 量价异常
- 盘中提醒
- 实时推送

---

## 8. 前端信息架构

```text
/
├── dashboard
├── markets
│   ├── stocks
│   ├── industries
│   └── indices
├── stock/[symbol]
├── watchlists
├── screening
├── portfolios
├── journal
├── research
├── membership
├── account
│   ├── profile
│   ├── security
│   ├── identities
│   ├── devices
│   └── privacy
└── admin
```

---

## 9. API 规范

统一使用：

```text
/api/v1/
```

领域：

```text
/api/v1/auth/*
/api/v1/users/me
/api/v1/securities/*
/api/v1/market-data/*
/api/v1/watchlists/*
/api/v1/screenings/*
/api/v1/portfolios/*
/api/v1/journals/*
/api/v1/industries/*
/api/v1/membership/*
/api/v1/admin/*
```

要求：

- API 版本化
- 分页
- request_id
- 统一错误结构
- 用户数据按登录态强制过滤
- 后端不信任前端传入的 user_id
- 数据日期、数据版本、质量状态显式返回

---

## 10. 身份安全门禁

第一版账号系统必须具备：

- 手机号和邮箱加密
- lookup hash
- 日志脱敏
- 验证码摘要
- 验证码单次使用
- 重发冷却
- IP/设备/身份限流
- Refresh Token 轮换
- 会话撤销
- OAuth state
- 管理员操作审计
- 用户数据导出
- 账号注销
- 同意记录
- 敏感操作重新认证
- 密钥仅在后端环境变量

禁止记录完整验证码、手机号、邮箱、AppSecret、Refresh Token 和支付密钥。

---

## 11. 会员框架

免费版：

- 基础个股
- 收盘日线
- 1 个自选分组
- 有限筛选
- 1 个模拟组合
- 基础复盘

专业版：

- 多自选分组
- 高级筛选
- 因子历史
- 多组合
- 风险分析
- 提醒
- 导出
- 完整历史范围

研究版：

- 自定义因子权重
- 多模型比较
- 历史横截面排名
- 压力测试
- 批量导出
- 报告归档
- API（后续）

会员售卖工具、数据深度和效率，不售卖收益承诺。

---

## 12. Codex 开发协议

### 审计阶段

- 只读
- 不修改文件
- 输出数据流、风险、文件列表、测试计划
- 等待确认

### 实施阶段

- 独立 feature 分支
- 一个 PR 解决一个核心问题
- 不修改历史 tag
- 不修改旧 artifacts
- 不运行未授权联网任务
- 新能力必须有测试和文档

### 本地门禁

```powershell
git branch --show-current
git status --short
python -m black --check <changed-python-files>
python -m pytest <relevant-tests> -q -p no:cacheprovider
python -m compileall -q autowealth tests
git diff --check
```

前端按需：

```powershell
npm test
npm run typecheck
npm run build
```

### PR 门禁

PR 必须包含：

- Summary
- Main changes
- Compatibility
- Security
- Validation
- Known limitations
- No-network / No-trading
- 修改文件范围

CI 必须通过：

```text
backend
frontend
docker
```

---

## 13. Definition of Done

每个 PR 都必须满足：

- 分支正确
- 起始工作区干净
- 范围未越界
- 新代码有测试
- 旧功能回归通过
- 旧配置兼容
- 旧 run 兼容
- 不修改历史 artifacts
- 不泄露密钥
- 不访问未授权网络
- 不执行交易
- Black 通过
- compileall 通过
- git diff --check 通过
- CI 全绿
- 文档更新
- 部署验证
- 回滚路径明确

---

## 14. 推荐文档

```text
docs/
├── product-roadmap.md
├── system-architecture.md
├── domain-boundaries.md
├── database-schema-plan.md
├── daily-data-platform.md
├── data-versioning.md
├── data-quality.md
├── identity-account-design.md
├── account-linking.md
├── user-investment-workspace.md
├── membership-and-entitlements.md
├── security-and-privacy.md
├── admin-operations.md
├── api-conventions.md
└── release-process.md
```

---

## 15. v0.16.0 完成后的 Codex 任务

先让 Codex只做 v0.17.0 架构设计，不直接编码：

1. 审计当前数据和研究模块。
2. 输出每日数据平台数据流。
3. 设计 ingestion run、data version、quality issue。
4. 设计 PostgreSQL 与 Parquet 边界。
5. 设计调度、幂等、重试和补数。
6. 设计每日因子增量计算。
7. 设计 Admin 数据运维页面。
8. 设计测试、迁移和回滚。
9. 生成架构文档。
10. 等待确认后实施。

---

## 16. 总体原则

> 数据可信优先于功能数量。  
> 日更新稳定优先于账号增长。  
> 账号安全优先于快速注册。  
> 用户数据可追溯优先于界面复杂度。  
> 权益系统优先于支付接入。  
> 会员售卖工具和数据能力，不售卖收益承诺。
