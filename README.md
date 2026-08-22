<div align="center">
<!-- Logo占位 - 建议添加项目Logo -->
<!-- <img src="docs/logo.png" alt="AutoWealth AI" width="200"/> -->

# 🚀 AutoWealth AI
**基于多智能体的个人财富管理与投资决策引擎**

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/KevinYoungsir/autowealth-ai)](https://github.com/KevinYoungsir/autowealth-ai/stargazers)
[![GitHub Issues](https://img.shields.io/github/issues/KevinYoungsir/autowealth-ai)](https://github.com/KevinYoungsir/autowealth-ai/issues)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker)](https://www.docker.com/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API%20Service-009688?logo=fastapi)](https://fastapi.tiangolo.com/)

[English](README_EN.md) | 简体中文
</div>

---

## 🌟 项目简介

AutoWealth AI 是一款基于**多智能体技术**的智能投资分析引擎。它通过整合技术分析、基本面分析和市场情绪分析，为个人投资者提供专业的投资决策支持。

## A 股长期组合研究系统

仓库正在保留原项目说明与旧模块的同时，新增一套相互独立的 A 股长期组合研究能力。新增模块只用于数据研究、因子与宏观评分、组合构建、历史回测、结构化复核和看板展示，不包含真实交易能力。历史研究结果不代表未来表现，也不构成投资建议。

当前研究模块：

- `autowealth/data/`：A 股及指数日线数据、统一 schema、parquet 缓存和质量检查。
- `autowealth/backtest/`：多标的、定期调仓的组合级历史回测与绩效指标。
- `autowealth/factors/`：价值、质量、动量、低波和超买超卖研究评分。
- `autowealth/macro/`：宏观状态、外部风险评分和研究用仓位系数。
- `autowealth/portfolio/`：把预计算评分和宏观系数转换为研究目标权重。
- `autowealth/research/`：编排组合构建、回测和结构化研究摘要。
- `autowealth/agents/`：mock 优先的 DeepSeek 研究摘要、风险复核和反方观点。
- `autowealth/api/research_server.py`：独立 FastAPI 研究聚合接口。
- `autowealth/market_data/`：v0.17.0 领域级增量 EOD 数据基础设施。
- `frontend/`：Next.js、TypeScript 和 Tailwind CSS 研究看板。

### v0.17.0 增量 EOD 基础设施

v0.17.0 在 `autowealth.market_data` 下提供 library-level capability，包括显式 dataset
identity、确定性 request planning、AKShare adapters、provider fallback chain、不可变
generations、原子 `current` pointer、incremental coordinator 和显式 full-refresh executor。

该能力尚未接入自动每日抓取或生产调度。既有真实研究流水线在 v0.17.0 中没有迁移到
这套 EOD stack，其行为和数据路径保持不变。

生产 composition 现在可以从显式 YAML 配置构造单数据集 EOD runtime。交易日历来自
部署方维护的版本化只读 JSON artifact；系统不会联网下载、猜测节假日或把工作日自动
视为交易日。构造过程不会执行 Provider fetch、更新或 publication。配置样例见
`configs/eod_production.example.yaml`，完整 contract 见
`docs/market-data-production-composition.md`。
当前样例使用 production config schema version 2；既有 version 1 配置仍按单次调用、零等待
的兼容默认值加载，不需要为保持旧行为而修改部署文件。

显式 batch coordinator 可将多个已构造 runtime 按 canonical dataset identity 排序后串行
执行。默认策略在首个失败后停止，也可显式继续；每个 dataset 的成功、失败、跳过和
`full_refresh_required` 都独立保留。dry-run 会读取 current 并生成请求计划，但不会调用
Provider、获取写锁或发布 generation。非 dry-run 使用稳定 dataset lock key；内置锁只在
单个 Python 进程内有效，不是多实例分布式锁。batch 不是跨 dataset 原子事务，后续失败
不会回滚此前已成功发布的独立 generation。

`full_refresh_required` 仍只是普通 incremental planner outcome，不会自动抓取完整历史。
调用方必须显式构造 `EODFullRefreshRequest` 并交给 `EODFullRefreshExecutor`；执行器只在 planner
确认 eligible 时请求完整 effective range，候选数据完全来自本次 Provider 结果，不与旧历史合并。完整结果通过
严格覆盖校验后才可发布；旧 generation 保持 immutable，`current` pointer 原子切换。dry-run
只读取 current 和规划，不抓取、不获取写锁或写 repository。现有 batch 默认路径没有新增
full-refresh execution mode。

repository maintenance 同样是显式执行边界。dry-run 不获取锁或修改文件，只分类精确命名的
stale staging 目录、`current` 临时文件、完整 generation 和未知 artifact。真实执行使用与
incremental/full-refresh writer 相同的 dataset lock，并只删除严格匹配的临时残留；删除后会
在锁内重新检查 repository。当前 generation、完整历史 generation、不可达 generation 和
回滚候选均不会自动删除。谱系损坏、未知 generation 内容或符号链接会关闭式阻止清理。

生产 `repository_root` 必须位于持久化 volume 或其他 durable filesystem。当前仍没有
worker、scheduler、EOD API/CLI、自动 maintenance 调度、完整 generation pruning 或自动每日
ingestion。Provider 调用边界现支持显式配置的有界临时失败重试和单 runtime 进程内最小间隔
限流；默认仍只调用一次且不等待。退避确定性且不含 jitter，只有
`temporary_provider_failure` 会重试。batch 继续串行执行，重试与等待期间仍持有对应
dataset 的写锁。

本地启动入口：

```powershell
# 终端 1
.\scripts\start_research_api.ps1

# 终端 2
.\scripts\start_dashboard.ps1
```

本地看板默认位于 `http://127.0.0.1:3000`，研究 API 默认位于 `http://127.0.0.1:8001`。生产环境推荐使用 `https://dashboard.outlook.xin` 和 `https://api.outlook.xin`。

详细说明：

- [本地开发](docs/local-development.md)
- [部署说明](docs/deployment.md)
- [生产部署](docs/production-deployment.md)
- [研究 API](docs/research-api.md)
- [研究流水线](docs/research-pipeline.md)
- [前端看板](frontend/README.md)

### 核心特性

- 🤖 **多智能体协作** — 3个专业AI智能体协同工作，交叉验证投资决策
- 📊 **多维度分析** — 技术指标、基本面数据、市场情绪全覆盖
- 🏠 **本地优先** — 支持本地LLM部署，保护数据隐私
- ⚡ **批量处理** — 支持一键分析多只股票，快速筛选投资标的
- 🎯 **可视化界面** — 提供Streamlit交互界面，直观展示分析结果
- 📱 **移动App** — Flutter跨平台应用，随时随地掌握投资机会
- 🚀 **机器学习预测** — 随机森林 + MLP神经网络，智能预测价格走势
- 🔔 **实时预警系统** — 价格突破、涨跌幅度、成交量异常等多规则监控

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        AutoWealth Engine                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Technical   │  │ Fundamental  │  │  Sentiment   │          │
│  │  Analyst     │  │  Analyst     │  │  Analyst     │          │
│  │  Agent       │  │  Agent       │  │  Agent       │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │               │               │                     │
│         └───────────────┼───────────────┘                     │
│                         ▼                                     │
│              ┌─────────────────────┐                         │
│              │  Agent Coordinator  │                         │
│              │  (加权投票决策)      │                         │
│              └─────────────────────┘                         │
│                         │                                     │
│   ┌─────────────────────┼─────────────────────┐              │
│   ▼                     ▼                     ▼              │
│ ┌─────────┐     ┌──────────┐     ┌──────────┐              │
│ │  Data   │     │ Analyzer │     │  LLMs    │              │
│ │ Fetcher │     │ Modules  │     │ Optional)│              │
│ └─────────┘     └──────────┘     └──────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/KevinYoungsir/autowealth-ai.git
cd autowealth-ai

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 .\venv\Scripts\activate  # Windows

# 安装依赖
pip install -e .

# 安装可选依赖（用于界面）
pip install -e ".[app]"
```

### 配置

创建 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入您的API密钥：

```env
OPENAI_API_KEY=your_openai_api_key_here
# 或者使用本地模型
LOCAL_LLM_URL=http://localhost:11434
LOCAL_LLM_MODEL=llama2
```

### 使用示例

#### Python API

```python
from autowealth import AutoWealthEngine

# 初始化引擎
engine = AutoWealthEngine()

# 分析单只股票
result = engine.analyze("AAPL")

# 打印分析结果
print(f"股票代码: {result['symbol']}")
print(f"综合建议: {result['decision']['signal_type']}")
print(f"置信度: {result['decision']['confidence']}%")
print(f"理由:\n{result['decision']['reasoning']}")

# 批量分析
batch_result = engine.analyze_batch(["AAPL", "GOOGL", "MSFT", "AMZN"])
print(f"推荐买入: {batch_result['recommendations']['buy']}")
```

#### 命令行工具

```bash
# 分析单只股票
python -m autowealth --symbol AAPL

# 批量分析
python -m autowealth --batch AAPL GOOGL MSFT

# 查看市场概览
python -m autowealth --market
```

#### Streamlit 可视化界面

```bash
# 启动界面
streamlit run examples/app.py
```

#### Docker 部署

```bash
# 使用 Docker Compose 一键启动
docker-compose up -d

# 或手动构建
docker build -t autowealth-ai .
docker run -p 8000:8000 autowealth-ai
```

---

## 📁 项目结构

```
autowealth-ai/
├── autowealth/              # 主包
│   ├── agents/              # 智能体模块
│   │   ├── base_agent.py    # 基础智能体类
│   │   ├── technical_agent.py   # 技术分析智能体
│   │   ├── fundamental_agent.py # 基本面分析智能体
│   │   ├── sentiment_agent.py   # 情绪分析智能体
│   │   └── coordinator.py   # 智能体协调器
│   ├── core/                # 核心功能
│   │   ├── data_fetcher.py  # 数据获取
│   │   ├── analyzer.py      # 分析模块
│   │   └── engine.py        # 主引擎
│   └── config/              # 配置管理
│       └── settings.py
├── examples/                # 示例代码
│   └── app.py               # Streamlit应用
├── mobile/                  # Flutter移动端
├── tests/                   # 测试
├── docs/                    # 文档
├── README.md
├── LICENSE
└── requirements.txt
```

---

## 🚀 智能体系统

### 技术分析智能体 (TechnicalAnalyst)
- MACD指标分析
- RSI超买超卖判断
- 布林带支撑阻力
- KDJ金叉死叉
- 均线多头/空头排列
- OBV能量潮、ATR波幅、DMI趋势指标等12+技术指标

### 基本面分析智能体 (FundamentalAnalyst)
- PE/PB估值分析
- 股息率评估
- 成长性趋势判断
- 综合基本面评分

### 情绪分析智能体 (SentimentAnalyst)
- 价格动量分析
- 成交量趋势判断
- 波动率评估
- 市场情绪评分
- 社交情绪分析（Twitter/微博/Reddit）

---

## 🎯 投资决策

### 信号类型

| 信号 | 说明 | 置信度阈值 |
|:---:|:---|:---:|
| 🟢 BUY | 强烈建议买入 | ≥70% |
| 🟡 HOLD | 建议观望 | 40-60% |
| 🔴 SELL | 建议卖出 | ≤30% |

### 智能体权重

```
技术分析智能体: 35%
基本面分析智能体: 35%
情绪分析智能体: 30%
```

---

## ✨ 功能亮点

| 功能 | 描述 |
|------|------|
| 📊 **12+ 技术指标** | MACD、RSI、布林带、KDJ、OBV、ATR、DMI、CCI、WR、PSY 等 |
| 🌍 **多数据源** | Yahoo Finance（全球）、东方财富/akshare（A股）、币安（加密货币） |
| ⚖️ **组合优化** | 马科维茨均值方差、最大夏普比率、最小方差组合 |
| 🔄 **回测系统** | 策略回测、绩效指标、权益曲线、交易记录 |
| 🌐 **Web API** | FastAPI 高性能异步服务，9个RESTful 端点 |
| 🔍 **中文NLP** | 意图识别、实体提取、50+股票名称映射 |
| 🚀 **机器学习** | 随机森林、MLP神经网络、18维特征工程 |
| 🔔 **实时预警** | 5种预警规则、Webhook通知（钉钉/飞书/Slack） |
| 📱 **移动App** | Flutter跨平台、深色主题、交互式图表 |

---

## 🛠️ 开发

### 运行测试

```bash
pytest tests/ -v
```

### 代码格式化

```bash
black autowealth/
flake8 autowealth/
```

---

## 🗺️ 未来规划

- [x] 添加更多技术指标
- [x] 支持更多数据源
- [x] 增加组合优化功能
- [x] 添加回测系统
- [x] 支持加密货币分析
- [x] 开启Web API服务
- [x] 添加中文自然语言交互
- [x] 机器学习预测模型
- [x] 实时预警系统
- [x] 社交情绪分析
- [x] 移动端App
- [ ] GPT集成智能问答
- [ ] 多语言国际化（i18n）
- [ ] 实时行情WebSocket推送
- [ ] 社区功能（策略分享/跟单）

---

## ⚠️ 免责声明

**本项目仅供教育和研究目的，不构成任何投资建议。**
投资有风险，入市需谨慎。使用本项目造成的任何投资损失，作者不承担任何责任。

---

## 📜 许可证

本项目采用 [MIT](LICENSE) 许可证。

---

## 🙏 致谢

本项目灵感来自：
- [MiroFish](https://github.com/) - 多智能体预测引擎
- [BettaFish](https://github.com/) - 多智能体舆情分析
- [OpenClaw](https://github.com/) - 本地AI助手

---

<div align="center">

**如果这个项目对您有帮助，请给我们一个 ⭐️**

[⭐ Star 本项目](https://github.com/KevinYoungsir/autowealth-ai) · [🐛 提交 Issue](https://github.com/KevinYoungsir/autowealth-ai/issues) · [🤝 参与贡献](CONTRIBUTING.md)

</div>
