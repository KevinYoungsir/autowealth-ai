<p align="center">
  <img src="https://raw.githubusercontent.com/Jsoned/autowealth-ai/main/docs/logo.jpg" alt="AutoWealth AI Logo" width="200">
</p>

# 🤖 AutoWealth AI

> 基于多智能体的个人财富管理与投资决策引擎

[![GitHub Stars](https://img.shields.io/github/stars/Jsoned/autowealth-ai?style=social)](https://github.com/Jsoned/autowealth-ai/stargazers)
[![License](https://img.shields.io/github/license/autowealth/autowealth-ai)](https://github.com/autowealth/autowealth-ai/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

## 🎯 项目简介

AutoWealth AI 是一款基于**多智能体技术**的智能投资分析引擎。它通过整合技术分析、基本面分析和市场情绪分析，为个人投资者提供专业级的投资决策支持。

### 核心特性

- 🧠 **多智能体协作** - 3个专业AI智能体协同工作，交叉验证投资决策
- 📊 **多维度分析** - 技术指标、基本面数据、市场情绪全覆盖
- 🔒 **本地优先** - 支持本地LLM部署，保护数据隐私
- 📈 **批量处理** - 支持一键分析多只股票，快速筛选投资标的
- 🎨 **可视化界面** - 提供Streamlit交互界面，直观展示分析结果

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AutoWealth Engine                         │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Technical   │  │Fundamental  │  │ Sentiment   │         │
│  │ Analyst     │  │ Analyst     │  │ Analyst     │         │
│  │   Agent     │  │   Agent     │  │   Agent     │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          ▼                                  │
│              ┌─────────────────────┐                       │
│              │  Agent Coordinator   │                       │
│              │  (加权投票决策)      │                       │
│              └──────────┬──────────┘                       │
│                         │                                   │
│    ┌────────────────────┼────────────────────┐              │
│    ▼                    ▼                    ▼              │
│ ┌──────────┐      ┌──────────┐        ┌──────────┐        │
│ │Data      │      │Analyzer  │        │ LLMs     │        │
│ │Fetcher   │      │Modules   │        │ (Optional│        │
│ └──────────┘      └──────────┘        └──────────┘        │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/autowealth/autowealth-ai.git
cd autowealth-ai

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
.\venv\Scripts\activate  # Windows

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

## 📁 项目结构

```
autowealth-ai/
├── autowealth/              # 主包
│   ├── agents/               # 智能体模块
│   │   ├── base_agent.py     # 基础智能体类
│   │   ├── technical_agent.py # 技术分析智能体
│   │   ├── fundamental_agent.py # 基本面分析智能体
│   │   ├── sentiment_agent.py   # 情绪分析智能体
│   │   └── coordinator.py    # 智能体协调器
│   ├── core/                 # 核心功能
│   │   ├── data_fetcher.py   # 数据获取
│   │   ├── analyzer.py       # 分析模块
│   │   └── engine.py         # 主引擎
│   └── config/               # 配置管理
│       └── settings.py
├── examples/                 # 示例代码
│   └── app.py               # Streamlit应用
├── tests/                   # 测试
├── docs/                    # 文档
├── README.md
├── LICENSE
└── requirements.txt
```

## 🤖 智能体系统

### 技术分析智能体 (TechnicalAnalyst)
- MACD指标分析
- RSI超买超卖判断
- 布林带支撑阻力
- KDJ金叉死叉
- 均线多头/空头排列

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

## 📊 投资决策

### 信号类型
| 信号 | 说明 | 置信度阈值 |
|------|------|----------|
| 🟢 BUY | 强烈建议买入 | ≥60% |
| 🟡 HOLD | 建议观望 | 40-60% |
| 🔴 SELL | 建议卖出 | ≥60% |

### 智能体权重
```
技术分析智能体: 35%
基本面分析智能体: 35%
情绪分析智能体: 30%
```

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

## ✨ 已实现功能

### 📊 扩展技术指标（12+指标）
- **OBV** - 能量潮指标，量价配合分析
- **ATR** - 真实波幅，波动率测量
- **DMI** - 趋向指标（+DI, -DI, ADX），趋势强度判断
- **CCI** - 顺势指标，超买超卖识别
- **WR** - 威廉指标，反向超买超卖
- **PSY** - 心理线，市场情绪量化

### 🌐 多数据源支持
- **Yahoo Finance** - 全球股票、ETF、指数
- **东方财富 (akshare)** - A股实时数据
- **币安 (Binance)** - 加密货币交易对

### 💼 组合优化
- **马科维茨均值方差优化** - 有效前沿计算
- **最大夏普比率组合** - 风险调整后收益最大化
- **最小方差组合** - 风险最小化
- **资金分配** - 根据权重自动分配投资金额

### 📈 回测系统
- **策略回测引擎** - 支持买入持有、均线交叉、RSI策略
- **绩效指标** - 总收益、年化收益、最大回撤、夏普比率、胜率
- **权益曲线** - 可视化资金变化
- **交易记录** - 详细买卖记录

### 🪙 加密货币分析
- **币安API集成** - 实时K线数据
- **自动识别** - 自动路由加密货币到币安数据源
- **支持主流币种** - BTC、ETH、SOL等

### 🌐 Web API服务
- **FastAPI** - 高性能异步API
- **7个RESTful端点** - 分析、批量、组合、市场、回测、优化
- **Pydantic模型** - 类型安全的请求/响应
- **CORS支持** - 跨域访问

### 🗣️ 中文自然语言交互
- **意图识别** - 分析、批量、组合、回测、优化
- **实体提取** - 股票代码、数量、成本价、收益率
- **80+股票映射** - "茅台"→"600519.SS"等
- **正则实现** - 零外部NLP依赖

### 🤖 机器学习预测模型
- **随机森林** - sklearn RandomForestRegressor，特征重要性分析
- **MLP神经网络** - 多层感知机，非线性预测
- **18维特征工程** - MA/RSI/MACD/布林带位置/波动率/动量等
- **模型持久化** - pickle序列化，支持保存/加载
- **评估指标** - MSE/MAE/R²完整评估

### 🚨 实时预警系统
- **5种预警规则** - 价格突破、涨跌幅、成交量异常、指标交叉
- **多渠道通知** - 控制台、Webhook（钉钉/飞书/Slack）、邮件预留
- **规则管理** - 动态添加/移除/查询预警规则
- **数据快照** - 触发时自动记录市场数据

### 📱 社交情绪分析
- **多平台覆盖** - Twitter/X、微博、Reddit
- **中英文词典** - 360+情绪词，金融领域专用
- **关键词提取** - 高频词统计+停用词过滤
- **综合评分** - 多平台加权合并情绪分数

### 📲 移动端App（Flutter）
- **跨平台** - iOS + Android 一套代码
- **深色科技主题** - 与Web端一致的视觉风格
- **5大功能页** - 分析、批量、组合、市场、仪表盘
- **交互式图表** - fl_chart价格走势可视化
- **API集成** - 自动连接FastAPI后端

## 📈 未来规划

- [x] ✅ 添加更多技术指标（OBV、ATR、DMI等）
- [x] ✅ 支持更多数据源（东方财富、同花顺等）
- [x] ✅ 增加组合优化功能
- [x] ✅ 添加回测系统
- [x] ✅ 支持加密货币分析
- [x] ✅ 开发Web API服务
- [x] ✅ 添加中文自然语言交互
- [x] ✅ 机器学习预测模型
- [x] ✅ 实时预警系统
- [x] ✅ 社交情绪分析（Twitter/微博）
- [x] ✅ 移动端App
- [ ] GPT集成智能问答
- [ ] 多语言国际化（i18n）
- [ ] 实时行情WebSocket推送
- [ ] 社区功能（策略分享/跟单）

## ⚠️ 免责声明

**本项目仅供教育和研究目的，不构成任何投资建议。**

投资有风险，入市需谨慎。使用本项目造成的任何投资损失，作者不承担任何责任。

## 📜 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

本项目灵感来自：
- [MiroFish](https://github.com/) - 多智能体预测引擎
- [BettaFish](https://github.com/) - 多智能体舆情分析
- [OpenClaw](https://github.com/) - 本地AI助手

---

<p align="center">
  <strong>如果这个项目对您有帮助，请给我们一个 ⭐️</strong>
</p>
