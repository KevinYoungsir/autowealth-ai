# AutoWealth Codex 项目规则

> 本文件位于仓库根目录，对整个 AutoWealth 仓库生效。  
> 子目录中的 `AGENTS.md` 可以增加更严格的领域规则，但不得削弱或绕过本文件中的安全、合规、数据真实性和 Git 操作规则。

---

## 1. 规则优先级

Codex 在执行任务时，按以下优先级理解项目要求：

1. 用户在当前任务中明确批准的范围与操作
2. 根目录 `AGENTS.md`
3. 当前版本或里程碑文档
4. `docs/project-status.md`（存在时）
5. `docs/product-development-framework.md`
6. 相关 ADR、接口文档、测试和代码现状

以下规则不因普通任务描述而自动失效：

- 不伪造金融数据
- 不执行真实交易
- 不泄露密钥和个人信息
- 不修改历史研究 artifacts
- 不修改或重定向历史 tag
- 不在工作区不干净时切换分支
- 不执行未经明确批准的 commit、push、PR、merge、release 或 tag

若文档与代码、Git 历史或当前任务发生冲突，立即停止并报告冲突，不得自行猜测。

---

## 2. 强制阅读

在规划或实施实质性工作前，必须阅读：

- `docs/product-development-framework.md`
- `CHANGELOG.md`
- 当前任务涉及的代码、测试和文档
- 当前版本的 milestone 文档（存在时）
- `docs/project-status.md`（存在时）
- `docs/decisions/` 下与任务有关的 ADR（存在时）

长期路线图只用于理解方向，**不代表授权一次性实现后续全部版本**。

若必读文件缺失：

1. 明确报告缺失文件；
2. 使用代码、Git 历史和已有文档进行有限审计；
3. 不得凭空补全项目状态；
4. 在用户确认前不得扩大实施范围。

---

## 3. 产品定位

AutoWealth 的长期定位是：

> A 股数据研究平台 + 用户个人投资工作台 + 会员内容与工具平台

当前及后续系统用于：

- A 股市场数据研究
- 历史回测与策略验证
- 因子、风险与组合研究
- 个股与行业数据分析
- 用户自选、筛选、组合和交易复盘
- 研究内容、工具权益和会员服务

本项目不是：

- 券商交易系统
- 自动下单系统
- 收益保证服务
- 无资质的荐股或投资顾问服务

所有结果只能表达为：

- 研究信号
- 候选清单
- 风险提示
- 历史回测
- 数据分析
- 人工复核结论

不得使用“保证收益”“必涨”“确定买入”“无风险”等表达。

---

## 4. 长期版本顺序

Codex 必须理解以下依赖顺序，但不得提前实施未授权阶段：

```text
v0.16.x  数据质量加固
    ↓
v0.17.x  每日增量数据与每日研究更新
    ↓
v0.18.x  手机、邮箱、微信统一账号体系
    ↓
v0.19.x  个股、自选、行业与提醒
    ↓
v0.20.x  选股记录、组合记录、交易复盘
    ↓
v0.21.x  会员、权益、内容权限与支付
    ↓
v0.22.x  获得合规数据授权后的盘中行情
```

当前阶段必须从：

- 当前 Git 分支
- `docs/project-status.md`
- 当前 milestone
- 最近合并 PR
- `CHANGELOG.md`

共同确认，不得只凭路线图推断。

---

## 5. 总体技术架构

在 v0.x 阶段保持模块化单体，未经批准不得拆分微服务。

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
PostgreSQL + Redis + Parquet/对象存储 + Worker/Scheduler
```

职责边界：

### PostgreSQL

用于：

- 用户和登录身份
- 会话与安全事件
- 自选、筛选记录、组合和复盘
- 会员、权益、订单
- 证券主数据和元数据
- 数据任务、数据版本和质量问题

### Parquet / 对象存储

用于：

- 大规模历史行情
- 每日增量行情快照
- 原始供应商数据
- 因子快照
- 回测和研究 artifacts
- 大型导出文件

### Redis

用于：

- 短期会话
- 验证码
- 限流
- 分布式任务锁
- 热点缓存
- 临时任务状态

### Worker / Scheduler

用于：

- 每日行情与基本面更新
- 数据质量校验
- 因子和行业指标计算
- 组合净值更新
- 用户提醒
- 报告生成
- 会员到期
- 数据修复与重跑

不得在没有明确性能证据和 ADR 的情况下引入 Kafka、复杂微服务或新的基础设施。

---

## 6. 领域边界

### `market_data`

负责：

- 交易日历
- 股票和指数 Provider
- Provider fallback
- Raw / Normalized / Derived 三层数据
- 数据抓取、增量更新、质量检查
- 数据版本、任务、补数和重跑

### `securities`

负责：

- 证券代码标准化
- 上市、退市和状态变化
- 公司行动
- 行业归属
- 指数成分
- 个股资料聚合

### `research`

负责：

- 因子
- point-in-time
- signal / execution 分离
- 组合构建
- 回测
- 指标
- 研究 artifacts
- 确定性报告

### `identity`

负责：

- 统一用户主体
- 手机验证码
- 邮箱验证码
- 微信 OAuth / 扫码
- 多身份绑定、解绑和账号合并
- 会话、设备、恢复和注销

### `watchlist`

负责自选分组、自选股、标签、备注和提醒。

### `screening`

负责筛选条件、运行记录、结果快照、排除原因和版本证据。

### `portfolio`

必须区分：

- research portfolio
- simulated portfolio
- user recorded portfolio

### `journal`

负责交易逻辑、情绪、结果、复盘、附件和行为统计。

### `industry`

负责带有效期的历史行业归属、行业指标和用户行业暴露。

### `membership`

负责套餐和 entitlement，不得在业务代码中散落 `is_vip` 判断。

### `billing`

负责订单、支付回调、退款、优惠券、发票、对账和幂等。

### `admin`

负责数据运维、用户运营、安全审计、会员订单和内容管理。

领域模块不得直接绕过其他领域的数据访问规则。跨领域交互应通过明确服务、协议或仓储接口完成。

---

## 7. Git 强制安全门禁

### 7.1 每次任务开始

必须首先执行：

```powershell
git branch --show-current
git status --short
git log -3 --oneline
git remote -v
```

必须报告：

- 当前分支
- 工作区是否干净
- 最近提交
- `origin` 指向哪个仓库

### 7.2 工作区不干净时

若 `git status --short` 有任何输出：

- 禁止切换到 `main`
- 禁止 `git pull`
- 禁止创建新分支
- 禁止 merge、rebase 或 reset
- 禁止自动 stash
- 禁止删除或回滚用户改动

必须先说明：

1. 修改和新增文件；
2. 它们属于哪个任务；
3. 是否已测试；
4. 当前分支是否正确；
5. 建议继续当前任务、由用户批准 stash，或由用户批准提交。

未经明确批准，不得处理这些改动。

### 7.3 分支规则

- 一个 PR 只解决一个主要问题。
- 新分支必须从干净且最新的目标基线创建。
- 文档 PR 不得混入功能代码。
- 功能 PR 不得顺手加入未来版本能力。
- 不得在错误分支上继续实施。
- 不得把未提交修改跨分支携带。

### 7.4 暂存规则

禁止默认使用：

```powershell
git add .
git add -A
```

应使用明确文件白名单。

暂存后必须执行：

```powershell
git status --short
git diff --cached --name-status
git diff --cached --stat
git diff --cached --check
```

提交前必须确认暂存区只包含当前任务文件。

### 7.5 远程与 PR 规则

默认仓库：

```text
KevinYoungsir/autowealth-ai
```

在 push 或创建 PR 前必须确认：

```powershell
git remote get-url origin
git status -sb
```

PR 默认必须满足：

```text
base repository: KevinYoungsir/autowealth-ai
base branch: main
head repository: KevinYoungsir/autowealth-ai
head branch: 当前 feature/docs 分支
```

除非用户明确要求向上游贡献，否则不得把 PR 提交到上游或原作者仓库。

创建 PR 前必须核对：

- commit 数量
- changed files 数量
- additions/deletions 是否与本次任务相符
- base repository 是否正确

### 7.6 写操作授权

除非当前任务明确授权，否则不得执行：

- `git commit`
- `git push`
- 创建或更新 PR
- merge
- release
- tag
- 删除分支
- force push
- reset
- rebase

永远不得未经确认修改已有 tag 的指向。

---

## 8. 单任务与 PR 范围

每次任务必须明确：

- 当前版本
- 当前分支
- 当前 PR
- 目标
- 允许修改
- 禁止修改
- 测试范围
- 完成条件

禁止把以下工作混在同一 PR：

- benchmark resilience 与 structured warnings
- market data 与 identity
- 账号登录与会员支付
- 数据 ingestion 与大规模前端重构
- 研究逻辑与真实交易
- 文档治理与未提交功能代码

若发现完成目标必须修改范围外模块，应先报告原因、最小修改范围和兼容风险，等待批准。

---

## 9. 数据真实性与研究安全

### 9.1 禁止伪造

不得：

- 用零值或当前值填充历史缺失值
- 用股票数据冒充指数
- 用今天的行业分类回填历史
- 用当前估值回填历史估值
- 用未来公告日期、财报日期或成分股信息
- 为使测试或报告成功而降低数据质量阈值

缺失、失败或覆盖不足必须保持：

```text
unavailable
partial_success
missing-data
insufficient_coverage
```

### 9.2 Point-in-time

所有研究必须遵守：

- `available_date <= signal_date`
- `report_date <= signal_date`
- signal date 严格早于 execution date
- execution 当日 close 不进入信号
- 新权重从 execution close 后生效
- warm-up 不计入正式 metrics

### 9.3 回测约束

必须明确建模或明确披露尚未建模：

- 手续费
- 印花税
- 滑点
- 停牌
- 涨跌停
- ST
- 退市
- 流动性
- 公司行动
- 历史股票池
- 历史行业归属

不得把未建模限制描述为已经解决。

### 9.4 结果展示

收益、回撤、夏普、卡玛、胜率等必须附带：

- 数据区间
- 数据版本
- 假设
- 计算方法
- 失效场景
- 风险提示

---

## 10. 每日数据平台规则

15 年历史数据是历史种子数据集，每日更新是在其上增量追加，不得每天重新抓取完整历史。

推荐流程：

```text
交易日历
→ 确认最后成功日期
→ 拉取缺失日期
→ Provider fallback
→ Schema 校验
→ 覆盖与异常值校验
→ Raw 落盘
→ 标准化
→ 公司行动处理
→ Derived 增量计算
→ 发布 data_version
→ 缓存刷新
→ 告警与审计
```

任务必须支持：

- 幂等
- 重试
- 断点续跑
- 按股票和日期补数
- 失败状态
- 数据版本
- Provider attempts
- 质量问题审计

不得将旧数据静默显示为“今日已更新”。

前端和 API 必须显式返回：

- 数据日期
- 更新时间
- 数据版本
- 数据状态
- 覆盖率或质量提示

---

## 11. Artifact 与缓存规则

- 已存在的 `data/research_runs` 默认只读。
- 不得修改、覆盖、重写或重新格式化历史 run。
- 新 artifact 必须增量兼容。
- artifact 写入应原子化，避免半写入状态。
- manifest 必须保留 schema/version 和摘要。
- 缓存必须记录 source、fetch window、row count、first/last date、hash 和 metadata。
- 覆盖不足、摘要不匹配或不可读缓存不得作为成功结果。
- 测试使用 `tmp_path` 或独立临时目录，不得污染正式缓存。

---

## 12. Provider 设计规则

数据 Provider 必须：

- 位于清晰协议后面
- 使用 canonical symbol
- 不在导入阶段访问网络
- 不静默吞异常
- 不把空数据视为成功
- 记录 provider、endpoint、request window、结果和失败原因
- 支持 fake provider 的离线测试

Provider fallback 成功时仍需保留前序失败证据。

外部网络访问默认禁止。只有当前任务明确批准且标记为 integration 时才允许。

---

## 13. 身份与用户数据安全

账号体系必须采用：

```text
一个 users 用户主体
    ↓
多个 auth_identities
├── phone
├── email
└── wechat
```

### 强制规则

- 手机号、邮箱、微信身份不能作为业务数据主键。
- 所有用户数据只引用内部 `user_id`。
- 后端从已验证会话推导 `user_id`。
- 不信任前端传入的 `user_id`。
- phone/email 保存加密值和独立 lookup hash。
- 验证码、Magic Link 和 Refresh Token 只保存摘要。
- 日志必须脱敏。
- 敏感操作要求重新认证。
- 解绑后至少保留一种可用登录身份。
- 身份冲突不得自动合并账号。
- 账号合并必须双重验证、事务执行并保留审计。

敏感操作包括：

- 修改手机号或邮箱
- 绑定/解绑微信
- 账号合并
- 数据导出
- 注销账号
- 支付和退款变更

---

## 14. 邮箱、短信与微信规则

### 邮箱

第一阶段优先邮箱验证码或 Magic Link，不默认引入密码体系。

必须具备：

- 单次 Token
- 有效期
- 重发冷却
- IP、设备、邮箱限流
- 防账号枚举
- SPF、DKIM、DMARC 配置文档
- 安全邮件和营销邮件分离

### 手机号

必须具备：

- 短信验证码限流
- 防刷
- 错误次数限制
- 运营商/供应商失败处理
- 完整号码不入日志

### 微信

- AppSecret 只在后端环境变量
- OAuth `state` 必须校验并防重放
- 微信身份唯一
- 回调和绑定流程必须可审计

---

## 15. 会员、内容和支付规则

会员系统先实现 entitlement，再接支付。

禁止：

- 业务模块直接依赖 `is_vip`
- 会员文案承诺收益
- VIP 买卖指令
- 必涨股或保本组合
- 将研究内容伪装成确定性投资建议

允许的权益方向：

- 历史数据范围
- 自选和组合容量
- 高级筛选
- 因子历史
- 风险分析
- 提醒
- 导出
- 研究报告归档
- API 能力（后续）

支付模块必须具备：

- 服务端验签
- 回调幂等
- 订单状态机
- 退款审计
- 对账
- 密钥隔离
- 敏感日志脱敏

---

## 16. DeepSeek 与其他大模型

除非当前任务明确授权，否则不得调用 DeepSeek 或其他外部模型。

大模型可用于：

- 研究摘要
- 风险复核
- 异常解释
- 反方观点
- 文案润色

大模型不得：

- 直接决定买卖
- 直接决定仓位和调仓
- 执行交易
- 覆盖结构化事实
- 将推测写入正式 artifact
- 把模型意见描述为确定结论

模型输出必须能追溯到结构化数据、规则和 artifact 证据。

---

## 17. API 设计规则

新 API 默认使用版本前缀：

```text
/api/v1/
```

要求：

- 统一错误结构
- request_id
- 分页
- 幂等
- 权限校验
- 用户数据隔离
- 明确数据日期和版本
- 明确 unavailable / partial_success
- 保持旧 API 字段兼容
- 新字段优先增量添加

错误示例：

```json
{
  "code": "WATCHLIST_LIMIT_REACHED",
  "message": "自选股数量已达到当前套餐上限",
  "request_id": "...",
  "details": {}
}
```

API 层不得替代领域模型，不得把 FastAPI 类型渗透到核心研究或数据模块。

---

## 18. 前端规则

- 保持 zh-CN / en-US 兼容。
- 机器枚举值不得翻译或修改。
- 不隐藏 `partial_success`、`unavailable`、warning 和限制。
- 页面必须展示数据日期、更新时间和质量状态。
- 不硬编码生产 URL、API Key 或密钥。
- 通过集中 API client 访问后端。
- 会员功能以 entitlement 为准。
- 用户私有页面必须验证登录态和权限。
- 不依靠前端实现用户数据隔离。

---

## 19. 依赖、迁移和配置

### 依赖

- 不得无理由添加依赖。
- 添加生产依赖前必须说明用途、替代方案、许可证和安全影响。
- 不得仅为测试通过而下载不必要工具。

### 数据库迁移

未来引入 PostgreSQL 后：

- 所有 schema 修改必须有迁移
- 迁移必须可回滚或说明不可逆原因
- 不得在应用启动时静默破坏性改表
- 唯一约束、索引和外键必须测试

### 配置

- 旧 YAML 默认兼容
- 新配置必须有默认值和严格验证
- 布尔值不得误当整数
- 密钥仅从环境变量或安全配置读取
- `.env`、Token、证书和私钥不得提交

---

## 20. 文档更新映射

按修改范围更新相关文档：

- 策略或因子：`docs/strategy-spec.md`、`docs/factor-definition.md`
- 回测：`docs/backtest-rules.md`
- 数据源或 Provider：`docs/data-source-plan.md`
- 真实研究：`docs/real-data-research.md`
- API：`docs/research-api.md` 或后续 API 规范
- 报告：`docs/real-research-report.md`
- 长期架构：`docs/product-development-framework.md`
- 版本状态：`docs/project-status.md`（存在时）
- 重要架构决定：新增或更新 ADR
- 对用户可见变化：`CHANGELOG.md`

文档必须说明：

- 假设
- 范围
- 数据来源
- 兼容策略
- 已知限制
- 失效场景
- 回滚方式

---

## 21. 标准开发流程

### 阶段 A：只读审计

默认先进行只读审计：

1. 检查 Git；
2. 阅读文档、代码和测试；
3. 画出数据流；
4. 识别风险和兼容点；
5. 列出允许修改文件；
6. 提出测试矩阵；
7. 等待用户批准。

审计阶段不得修改文件。

### 阶段 B：实施

获得批准后：

1. 再次确认分支和工作区；
2. 只修改批准文件；
3. 先写或同步测试；
4. 实现最小完整改动；
5. 更新相关文档；
6. 不跨版本扩展。

### 阶段 C：验证

根据修改范围执行离线验证。

### 阶段 D：Diff 审核

必须输出：

```powershell
git status --short
git diff --name-status
git diff --stat
git diff --check
```

在用户批准前不得执行 Git 写操作。

---

## 22. 本地验证门禁

### Python

收集修改的 Python 文件后执行：

```powershell
python -m black --check --line-length 100 <changed-python-files>
python -m compileall -q autowealth tests
python -m pytest <relevant-tests> -q -p no:cacheprovider
```

测试必须优先使用 fake provider 和临时目录。

### 前端

按需执行：

```powershell
npm test
npm run typecheck
npm run build
```

### 通用

```powershell
git diff --check
git status --short
```

若格式化器修改代码，必须在格式化后重新运行相关测试。

不得运行真实 15 年数据任务、联网 smoke、DeepSeek 或交易接口，除非当前任务明确授权。

---

## 23. CI 与部署门禁

必须等待要求的 CI 全部成功：

```text
backend
frontend
docker
```

CI pending、action required、cancelled 或 failed 时不得建议合并。

部署后按版本要求验证：

- 前端可访问
- 后端 health/API 可访问
- CORS 和 Trusted Hosts
- 中英文接口
- 旧 run 读取
- 新 artifact 读取
- 数据状态和 warning
- 不泄露内部路径或密钥

版本标签只能在当前版本所有 PR、CI 和生产验证完成后创建。

---

## 24. Definition of Done

一个任务只有同时满足以下条件才算完成：

- 当前分支正确
- 起始工作区状态已确认
- 范围未越界
- 新代码有测试
- 相关回归通过
- Black 通过
- compileall 通过
- `git diff --check` 通过
- 旧配置兼容
- 旧 run 兼容
- 历史 artifacts 未修改
- 无伪造数据
- 无密钥泄露
- 未访问未授权网络
- 未调用未授权模型
- 未执行交易
- 文档已更新
- 已知限制已披露
- CI 全绿
- 部署验证通过（发布任务）
- 回滚路径明确

---

## 25. 完成报告格式

每次实施完成后必须输出：

1. 当前分支
2. 当前 HEAD
3. 修改和新增文件
4. 完成范围
5. 明确排除范围
6. 架构与数据流变化
7. 兼容策略
8. 安全与合规影响
9. 测试命令和结果
10. Black / compileall / frontend 检查
11. `git diff --check`
12. `git status --short`
13. 是否访问网络
14. 是否调用 DeepSeek/其他模型
15. 是否修改旧 artifacts
16. 已知限制
17. 建议提交信息

完成后停止，等待用户决定是否 commit、push 或创建 PR。

---

## 26. Codex 自检清单

执行任何任务前，Codex 必须能回答：

- 我现在在哪个分支？
- 工作区是否干净？
- `origin` 是否为 `KevinYoungsir/autowealth-ai`？
- 当前版本和 PR 是什么？
- 这次允许修改哪些文件？
- 明确禁止哪些后续版本能力？
- 是否涉及金融数据真实性？
- 是否涉及用户身份或个人信息？
- 是否涉及联网、模型、交易或支付？
- 需要运行哪些离线测试？
- 是否需要更新文档和 ADR？
- 用户是否已授权 Git 写操作？

任何答案不明确时，先停止并报告，不得自行扩大权限。
