# 有哪些值得推荐的 Python 量化投资开源项目？

作为量化投资开发者和开源爱好者，我想推荐一个自己参与开发的项目：**AutoWealth AI**。

---

## 项目简介

**AutoWealth AI** 是一个基于多智能体协作的智能投资分析引擎，用 Python 构建，完全开源（MIT 协议）。

GitHub: https://github.com/Jsoned/autowealth-ai

## 为什么推荐这个项目

### 1. 多智能体协作决策，不是单一模型

大多数量化工具的决策逻辑是线性的：数据输入 -> 策略计算 -> 信号输出。AutoWealth AI 的不同之处在于，它模拟了一个投研团队的协作模式：

- **技术分析智能体** -- 从量价角度分析，覆盖 MACD、RSI、布林带、KDJ、OBV、ATR、DMI、CCI、WR、PSY 等 12+ 技术指标
- **基本面分析智能体** -- 从估值角度分析 PE/PB、股息率、成长性趋势
- **情绪分析智能体** -- 从市场情绪角度评估动量、成交量、波动率

三个智能体独立分析后，由协调器通过**加权投票机制**综合决策（技术 35% + 基本面 35% + 情绪 30%）。这种设计避免了单一维度分析带来的盲区。

### 2. 功能覆盖面广

相比其他量化项目，AutoWealth AI 在功能覆盖上比较全面：

| 功能模块 | 说明 |
|---------|------|
| 多智能体分析 | 3 个专业智能体协同决策 |
| 技术指标 | 12+ 指标（MACD/RSI/布林带/OBV/ATR/DMI/CCI/WR/PSY） |
| 机器学习预测 | 随机森林 + MLP，18 维特征工程 |
| 回测系统 | 买入持有/均线交叉/RSI 策略，完整绩效指标 |
| 组合优化 | 马科维茨模型，最大夏普比率/最小方差 |
| 实时预警 | 5 种规则，支持 Webhook 推送 |
| 社交情绪分析 | Twitter/微博/Reddit，360+ 金融情绪词典 |
| 多数据源 | Yahoo Finance/东方财富/币安 |
| Web API | FastAPI，7 个 RESTful 端点 |
| 中文 NLP | 正则实现意图识别，80+ 股票名称映射 |
| 移动端 | Flutter App，iOS + Android |

### 3. 与其他项目的对比

**对比 Qlib（微软）：**
Qlib 是一个成熟的量化研究平台，功能强大但学习曲线陡峭，适合专业量化团队。AutoWealth AI 更轻量，面向个人投资者和学习者，几行代码就能上手。

**对比 Backtrader：**
Backtrader 是经典的回测框架，专注于策略回测。AutoWealth AI 则更侧重于多维度分析和智能决策，回测只是其中一个模块。

**对比 Zipline：**
Zipline 是 Quantopian 的回测引擎，同样专注于回测。AutoWealth AI 提供了从数据获取、分析、预测到回测、优化的完整链路。

**对比 TA-Lib：**
TA-Lib 是技术指标计算库，提供原始指标数据。AutoWealth AI 在指标计算之上，通过智能体系统提供了自动化的分析和决策能力。

简单来说，如果你想要一个**开箱即用、功能全面、代码可读性强**的量化分析框架，AutoWealth AI 是一个不错的选择。

### 4. 代码质量

- **482 个测试用例**全部通过
- 完整的类型注解和文档字符串
- 模块化设计，每个模块职责清晰
- GitHub Actions CI 自动化测试
- Docker 一键部署

### 5. 适合什么场景

- **学习量化投资** -- 代码结构清晰，适合作为学习材料
- **个人投资辅助** -- 本地运行，数据不外传，保护隐私
- **多智能体系统研究** -- 加权投票、协调器模式可参考
- **FastAPI 实战参考** -- 完整的 RESTful API 设计
- **快速原型验证** -- 几行代码就能验证一个投资想法

## 快速体验

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()

# 分析单只股票
result = engine.analyze("AAPL")
print(result['decision']['signal_type'])   # buy / sell / hold
print(result['decision']['confidence'])   # 置信度

# 批量分析
batch = engine.analyze_batch(["AAPL", "GOOGL", "MSFT", "AMZN"])
print(batch['recommendations']['buy'])     # 推荐买入列表
```

命令行方式：

```bash
python -m autowealth --symbol AAPL
python -m autowealth --batch AAPL GOOGL MSFT
```

## 最后

量化投资是一个需要持续学习和实践的领域。AutoWealth AI 提供了一个相对完整的分析框架，但请记住：**任何工具都只是辅助，投资决策最终需要自己的判断。**

项目还在持续迭代中，欢迎大家 Star、Fork、提 Issue 和 PR。

GitHub: https://github.com/Jsoned/autowealth-ai

---

> 免责声明：本项目仅供教育和研究目的，不构成任何投资建议。投资有风险，入市需谨慎。
