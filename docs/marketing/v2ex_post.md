# [分享创造] AutoWealth AI - 用多智能体协作做投资分析的开源工具

## 前言

大家好，最近花了些时间做了一个开源项目，想在这里和大家分享一下。

起因是这样的：我自己平时会关注一些投资标的，但每次要做分析的时候，技术指标要看一堆、基本面数据要翻好几处、市场情绪更是难以量化。市面上的工具要么功能单一，要么收费昂贵，对个人开发者不太友好。于是就想，能不能自己造一个工具，把多个分析维度整合到一起，让 AI 帮我做初筛？

这就是 **AutoWealth AI** 的由来。

GitHub: https://github.com/Jsoned/autowealth-ai

## 它是什么

AutoWealth AI 是一个基于**多智能体协作**的投资分析引擎。核心思路很简单：不依赖单一模型做决策，而是让三个专业智能体分别从不同维度分析同一只股票，最后通过加权投票机制给出综合建议。

三个智能体分别是：

- **技术分析智能体** - 覆盖 MACD、RSI、布林带、KDJ、均线系统等 12+ 技术指标
- **基本面分析智能体** - 分析 PE/PB 估值、股息率、成长性趋势
- **情绪分析智能体** - 评估价格动量、成交量趋势、波动率

最终决策时，技术分析和基本面各占 35% 权重，情绪分析占 30%。每个智能体独立给出 buy/sell/hold 信号和置信度，协调器综合后输出最终建议。

## 技术栈和架构

项目用 Python 构建，主要技术选型：

- **数据源**: Yahoo Finance（全球股票/ETF）、东方财富 akshare（A 股）、币安（加密货币）
- **分析引擎**: pandas + numpy 做指标计算，纯 Python 实现无重度依赖
- **机器学习**: sklearn 的随机森林和 MLP 神经网络做价格预测，18 维特征工程
- **组合优化**: 马科维茨均值方差模型，支持最大夏普比率和最小方差组合
- **Web 服务**: FastAPI 提供 7 个 RESTful 端点，Pydantic 做类型安全
- **移动端**: Flutter 跨平台 App，深色科技主题
- **回测系统**: 支持买入持有、均线交叉、RSI 策略，含完整绩效指标
- **预警系统**: 价格突破、涨跌幅、成交量异常等 5 种规则，支持 Webhook 推送
- **社交情绪**: 覆盖 Twitter/X、微博、Reddit，360+ 金融情绪词典
- **中文 NLP**: 正则实现的意图识别和实体提取，80+ 股票名称映射，零外部 NLP 依赖

整体架构：

```
用户输入 --> AutoWealth Engine
                |
                +--> DataFetcher (多数据源)
                +--> AgentCoordinator
                |       +--> TechnicalAgent
                |       +--> FundamentalAgent
                |       +--> SentimentAgent
                +--> MLPredictor (ML预测)
                +--> BacktestEngine (回测)
                +--> PortfolioOptimizer (组合优化)
```

## 一些有意思的实现细节

**1. 加权投票决策机制**

协调器不是简单多数投票，而是把每个智能体的置信度和权重相乘后归一化。比如技术分析智能体给出 buy 信号（置信度 80%），权重 35%，那它的买入贡献就是 0.35 * 0.8 = 0.28。三个智能体的 buy/sell/hold 分数加起来，最高的那个就是最终信号。这样即使某个智能体强烈看多，如果另外两个都看空，最终也可能给出 hold。

**2. 零依赖中文 NLP**

中文自然语言交互模块没有用任何 NLP 库，完全基于正则表达式实现意图识别和实体提取。支持 "分析一下茅台"、"帮我看看苹果和微软"、"回测比亚迪" 等自然表达。内置了 80+ 常见股票的中文名称到代码的映射。

**3. 组合优化不依赖 cvxpy**

马科维茨优化模块用 numpy 矩阵运算 + 网格搜索实现，没有引入 cvxpy 等优化求解器，降低了依赖复杂度。

**4. 测试覆盖**

项目目前有 482 个测试用例，覆盖智能体、分析器、回测、ML 预测、API、NLP 等所有模块。

## 使用方式

最简单的用法：

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()
result = engine.analyze("AAPL")
print(result['decision']['signal_type'])   # buy / sell / hold
print(result['decision']['confidence'])   # 置信度百分比
```

也支持命令行：

```bash
python -m autowealth --symbol AAPL
python -m autowealth --batch AAPL GOOGL MSFT
```

启动 Web 服务：

```bash
uvicorn autowealth.api.server:create_app --factory --reload
```

## 适合谁用

- 对量化投资感兴趣，想学习多智能体架构的开发者
- 需要一个本地运行、数据不外传的分析工具的个人投资者
- 想做投资分析类项目练手的同学（代码结构清晰，适合阅读）
- 需要 FastAPI + 多数据源 + ML 预测参考项目的工程师

## 最后

项目完全开源，MIT 协议。目前还在持续迭代中，未来计划接入 GPT 做智能问答、WebSocket 实时行情推送等。

如果觉得有意思，欢迎 Star、Fork、提 Issue。也欢迎 PR，特别是新的技术指标、数据源或者策略方面。

GitHub: https://github.com/Jsoned/autowealth-ai

免责声明：本项目仅供教育和研究目的，不构成任何投资建议。
