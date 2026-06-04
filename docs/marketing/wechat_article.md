# 当 AI 智能体开始帮你分析股票：AutoWealth AI 开源投资分析引擎

> 一个完全开源、本地运行的多智能体投资分析工具，让个人投资者也能拥有 AI 投研团队。

---

## 你是否也有这样的困扰？

每天收盘后，打开行情软件，面对满屏的 K 线和指标，不知道从何看起。

技术分析要看 MACD、RSI、布林带、KDJ......基本面要查 PE、PB、股息率......市场情绪更是难以量化。一个人要把所有维度都照顾到，精力根本不够。

如果有一支 AI 投研团队，每个人负责一个维度，最后综合给出建议呢？

这就是 **AutoWealth AI** 要解决的问题。

---

## 什么是 AutoWealth AI

AutoWealth AI 是一个基于**多智能体协作**的开源投资分析引擎。它模拟了专业投研团队的协作模式，用三个 AI 智能体分别从不同维度分析同一只股票，然后通过加权投票机制给出综合建议。

**[插入图片：系统架构图]**

---

## 三大核心功能

### 1. 多智能体协作分析

三个专业智能体各司其职：

**[插入图片：三个智能体协作示意图]**

| 智能体 | 职责 | 权重 |
|--------|------|------|
| 技术分析智能体 | MACD、RSI、布林带、KDJ、OBV、ATR、DMI 等 12+ 指标 | 35% |
| 基本面分析智能体 | PE/PB 估值、股息率、成长性趋势 | 35% |
| 情绪分析智能体 | 价格动量、成交量趋势、波动率评估 | 30% |

不是简单投票，而是**置信度加权**。每个智能体给出信号的同时附带置信度，协调器综合后输出最终建议和理由。

### 2. 机器学习价格预测

内置随机森林和 MLP 神经网络两种模型，基于 18 维技术指标特征进行价格预测：

- 移动平均线（MA5/10/20/60）
- RSI、MACD 及信号线
- 布林带位置、波动率
- 成交量变化率、动量指标
- 收益率、价格位置

**[插入图片：预测结果可视化截图]**

### 3. 回测与组合优化

**回测系统**支持买入持有、均线交叉、RSI 三种策略，输出年化收益、最大回撤、夏普比率、胜率等完整绩效指标。

**组合优化**基于马科维茨均值方差模型，支持最大夏普比率组合和最小方差组合，帮你科学分配资金。

**[插入图片：回测权益曲线截图]**

---

## 更多亮点

### 多数据源覆盖

| 数据源 | 覆盖范围 | 示例 |
|--------|---------|------|
| Yahoo Finance | 全球股票、ETF | AAPL, TSLA |
| 东方财富 | A 股实时数据 | 600519, 000858 |
| 币安 | 加密货币 | BTC/USDT, ETH/USDT |

系统自动识别代码格式，路由到对应数据源，无需手动配置。

### 社交情绪分析

覆盖 Twitter/X、微博、Reddit 三大平台，内置 360+ 金融领域情绪词典，量化市场情绪。

**[插入图片：社交情绪分析仪表盘截图]**

### 实时预警

支持价格突破、涨跌幅超限、成交量异常、指标交叉等 5 种预警规则，可通过 Webhook 推送到钉钉、飞书、Slack。

### 中文自然语言交互

直接用中文输入："分析一下茅台"、"帮我看看苹果和微软"、"回测比亚迪"。内置 80+ 股票名称映射，零外部 NLP 依赖。

### 全平台支持

- **Python API** -- 几行代码完成分析
- **命令行工具** -- 快速查询
- **Web 服务** -- FastAPI 提供 7 个接口
- **可视化界面** -- Streamlit 交互式仪表盘
- **移动端 App** -- Flutter 开发，iOS + Android

**[插入图片：移动端 App 界面截图]**

---

## 如何使用

### 安装

```bash
git clone https://github.com/Jsoned/autowealth-ai.git
cd autowealth-ai
pip install -e .
```

### Python API

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()

# 分析单只股票
result = engine.analyze("AAPL")
print(f"建议: {result['decision']['signal_type']}")
print(f"置信度: {result['decision']['confidence']}%")

# 批量分析
batch = engine.analyze_batch(["AAPL", "GOOGL", "MSFT"])
print(f"推荐买入: {batch['recommendations']['buy']}")
```

### 命令行

```bash
python -m autowealth --symbol AAPL
python -m autowealth --batch AAPL GOOGL MSFT
```

### Web 服务

```bash
uvicorn autowealth.api.server:create_app --factory --reload
```

### Docker 部署

```bash
docker-compose up -d
```

---

## 技术优势

1. **架构清晰** -- 模块化设计，智能体、分析器、数据获取、ML 预测各司其职
2. **依赖精简** -- 核心功能只用 pandas、numpy、sklearn，组合优化不依赖 cvxpy，NLP 不依赖 jieba
3. **测试完善** -- 482 个测试用例覆盖所有模块，CI 自动化运行
4. **类型安全** -- Pydantic 数据模型，FastAPI 自动生成 API 文档
5. **本地优先** -- 数据不离开你的机器，保护隐私

---

## 适用人群

- **个人投资者** -- 想要一个本地运行、数据不外传的分析辅助工具
- **量化学习者** -- 想要一个代码可读、结构清晰的学习项目
- **Python 开发者** -- 想要参考多智能体架构、FastAPI 实战、ML 工程化
- **技术爱好者** -- 对 AI + 金融交叉领域感兴趣

---

## 项目信息

- **GitHub**: https://github.com/Jsoned/autowealth-ai
- **协议**: MIT（完全开源，自由使用）
- **语言**: Python 3.9+
- **测试**: 482 个用例全部通过
- **部署**: Docker 支持

---

> **免责声明：** 本项目仅供教育和研究目的，不构成任何投资建议。投资有风险，入市需谨慎。使用本项目造成的任何投资损失，作者不承担任何责任。

---

如果觉得这个项目对你有帮助，欢迎在 GitHub 上给一个 Star，也欢迎提 Issue 和 PR 一起完善它。
