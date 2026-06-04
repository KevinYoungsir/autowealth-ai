# 我用 Python 构建了一个多智能体 AI 投资分析引擎

> 原文首发于掘金 | 标签：Python、AI、量化投资、开源

## 引言

作为一个对量化投资和 AI 都有浓厚兴趣的开发者，我一直在思考一个问题：能不能让多个 AI 智能体像投研团队一样协作，从不同维度分析一只股票，然后综合给出投资建议？

带着这个想法，我开发了 **AutoWealth AI** -- 一个基于多智能体协作的开源投资分析引擎。本文将从技术架构、核心实现、关键代码三个层面，分享整个项目的设计思路。

GitHub: https://github.com/Jsoned/autowealth-ai

## 一、整体架构设计

### 1.1 设计理念

传统量化系统通常是单一策略驱动的，而 AutoWealth AI 的核心创新在于**多智能体协作决策**。我把一个完整的投研团队抽象成了三个专业智能体：

- **TechnicalAnalyst** -- 技术分析智能体，负责量价分析
- **FundamentalAnalyst** -- 基本面分析智能体，负责估值分析
- **SentimentAnalyst** -- 情绪分析智能体，负责市场情绪评估

三个智能体独立分析，由 **AgentCoordinator** 通过加权投票机制综合决策。

### 1.2 系统架构图

```
┌──────────────────────────────────────────────────────────┐
│                   AutoWealth Engine                        │
├──────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │  Technical   │ │ Fundamental  │ │  Sentiment   │      │
│  │  Analyst     │ │  Analyst     │ │  Analyst     │      │
│  │  Agent (35%) │ │  Agent (35%) │ │  Agent (30%) │      │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘      │
│         └────────────────┼────────────────┘               │
│                          ▼                                │
│              ┌─────────────────────┐                      │
│              │  Agent Coordinator  │                      │
│              │  (加权投票决策)      │                      │
│              └──────────┬──────────┘                      │
│                         │                                 │
│    ┌────────────────────┼────────────────────┐            │
│    ▼                    ▼                    ▼            │
│ ┌──────────┐     ┌──────────┐       ┌──────────┐       │
│ │DataFetcher│     │Analyzer  │       │MLPredictor│       │
│ │(多数据源) │     │(12+指标) │       │(RF + MLP)│       │
│ └──────────┘     └──────────┘       └──────────┘       │
└──────────────────────────────────────────────────────────┘
```

## 二、核心模块实现

### 2.1 智能体基类设计

所有智能体继承自 `BaseAgent` 抽象基类，统一输出 `AgentSignal` 数据结构：

```python
from pydantic import BaseModel
from abc import ABC, abstractmethod

class AgentSignal(BaseModel):
    """智能体信号 - 统一的输出格式"""
    agent_name: str
    signal_type: str      # buy, sell, hold
    confidence: float     # 0-100
    reasoning: str
    target_price: float | None = None
    stop_loss: float | None = None
    time_horizon: str = "medium"
    metadata: dict = {}

class BaseAgent(ABC):
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    def analyze(self, symbol: str, data: dict) -> AgentSignal:
        """分析并生成交易信号"""
        pass

    def calculate_confidence(self, factors: list, weights: list | None = None) -> float:
        """计算加权置信度"""
        if weights is None:
            weights = [1.0] * len(factors)
        weighted_sum = sum(f * w for f, w in zip(factors, weights))
        return max(0.0, min(100.0, weighted_sum / sum(weights)))
```

使用 Pydantic 做信号的数据模型，保证了类型安全和序列化能力。每个智能体只需要实现 `analyze` 方法，返回标准化的 `AgentSignal`。

### 2.2 加权投票协调器

协调器是多智能体系统的核心，负责收集信号并综合决策：

```python
class AgentCoordinator:
    def __init__(self):
        self.agents = {}
        self.agent_weights = {
            "TechnicalAnalyst": 0.35,
            "FundamentalAnalyst": 0.35,
            "SentimentAnalyst": 0.30,
        }

    def _aggregate_signals(self, signals: dict) -> dict:
        """加权投票综合决策"""
        buy_score = sell_score = hold_score = 0.0

        for agent_name, signal in signals.items():
            weight = self.agent_weights.get(agent_name, 0.33)
            confidence = signal.confidence / 100.0
            weighted_score = weight * confidence

            if signal.signal_type == "buy":
                buy_score += weighted_score
            elif signal.signal_type == "sell":
                sell_score += weighted_score
            else:
                hold_score += weighted_score

        # 归一化后取最高分
        total = buy_score + sell_score + hold_score
        scores = {
            "buy": buy_score / total * 100,
            "sell": sell_score / total * 100,
            "hold": hold_score / total * 100,
        }
        final_signal = max(scores, key=scores.get)
        return {
            "signal_type": final_signal,
            "confidence": scores[final_signal],
            "scores": scores,
        }
```

关键设计点：不是简单多数投票，而是**置信度加权**。一个高置信度的信号比低置信度的更有影响力。这避免了"两个低置信度 hold 压过了一个高置信度 buy"的不合理情况。

### 2.3 技术指标计算引擎

技术分析模块支持 12+ 指标，全部用 pandas 向量化运算实现：

```python
class TechnicalAnalyzer:
    @staticmethod
    def calculate_macd(data, fast=12, slow=26, signal=9):
        ema_fast = data["Close"].ewm(span=fast, adjust=False).mean()
        ema_slow = data["Close"].ewm(span=slow, adjust=False).mean()
        data["MACD"] = ema_fast - ema_slow
        data["MACD_Signal"] = data["MACD"].ewm(span=signal, adjust=False).mean()
        data["MACD_Histogram"] = data["MACD"] - data["MACD_Signal"]
        return data

    @staticmethod
    def calculate_rsi(data, period=14):
        delta = data["Close"].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss.replace(0, 1e-10)
        data["RSI"] = 100 - (100 / (1 + rs))
        return data

    @staticmethod
    def calculate_bollinger_bands(data, period=20, std_dev=2.0):
        data["BB_Middle"] = data["Close"].rolling(window=period).mean()
        bb_std = data["Close"].rolling(window=period).std()
        data["BB_Upper"] = data["BB_Middle"] + bb_std * std_dev
        data["BB_Lower"] = data["BB_Middle"] - bb_std * std_dev
        return data
```

除 MACD/RSI/布林带外，还实现了 OBV（能量潮）、ATR（真实波幅）、DMI（趋向指标，含 +DI/-DI/ADX）、CCI（顺势指标）、WR（威廉指标）、PSY（心理线）等。

### 2.4 机器学习预测模块

ML 模块提供基于历史数据的预测能力，支持随机森林和 MLP 两种模型：

```python
class MLPredictor:
    def __init__(self, model_type="random_forest"):
        self.model_type = model_type
        self.feature_names = []  # 18维特征

    def prepare_features(self, data):
        """构造18维技术指标特征"""
        df = data.copy()
        # 移动平均线: MA5, MA10, MA20, MA60
        for period in [5, 10, 20, 60]:
            df[f"MA_{period}"] = df["Close"].rolling(period).mean()
        # RSI, MACD, 布林带位置, 波动率, 成交量变化率
        # 动量指标, 收益率, 价格位置
        # ...共18个特征
        return df

    def train(self, data, test_ratio=0.2):
        """训练模型并返回评估指标"""
        df = self.prepare_features(data)
        X = df[self.feature_names].values
        y = df["Target"].values  # 下一期收盘价

        # 标准化 + 训练集/测试集划分
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        if self.model_type == "random_forest":
            model = RandomForestRegressor(n_estimators=100, max_depth=10)
        else:
            model = MLPRegressor(hidden_layer_sizes=(64, 32))

        model.fit(X_train, y_train)
        # 返回 MSE, MAE, R2
```

18 维特征包括：MA(5/10/20/60)、RSI(14)、MACD 及其信号线、布林带位置、波动率、成交量变化率及比率、动量(5/10/20)、收益率、价格位置。

### 2.5 马科维茨组合优化

组合优化模块完全基于 numpy 实现，不依赖 cvxpy：

```python
class PortfolioOptimizer:
    def __init__(self, returns_data):
        self.mean_returns = returns_data.mean().values
        self.cov_matrix = returns_data.cov().values
        self.ann_factor = 252  # 年化因子

    def _sharpe_ratio(self, weights, risk_free_rate=0.02):
        p_return = np.dot(weights, self.mean_returns) * self.ann_factor
        p_vol = np.sqrt(np.dot(weights.T, np.dot(self.cov_matrix, weights)) * self.ann_factor)
        return (p_return - risk_free_rate) / p_vol

    def max_sharpe_ratio(self):
        """通过网格搜索找到最大夏普比率组合"""
        # 遍历权重空间，找到最优组合
```

支持三种优化目标：最大夏普比率、最小方差、目标收益率约束。

### 2.6 FastAPI Web 服务

Web 层用 FastAPI 构建，提供 7 个 RESTful 端点：

```python
app = FastAPI(title="AutoWealth AI API", version="1.0.0")

@app.post("/analyze")           # 单股分析
@app.post("/analyze/batch")     # 批量分析
@app.post("/portfolio/analyze") # 组合分析
@app.get("/market/overview")    # 市场概览
@app.post("/backtest")           # 策略回测
@app.post("/optimize")          # 组合优化
@app.get("/health")              # 健康检查
```

所有请求/响应都用 Pydantic 模型做类型校验，配合 FastAPI 自动生成 OpenAPI 文档。

### 2.7 零依赖中文 NLP

中文自然语言交互模块是项目中比较有趣的部分。没有引入 spaCy、jieba 等库，完全用正则实现：

```python
# 意图识别模式
INTENT_PATTERNS = {
    "analyze": r"(分析|看看|查一下|研究)",
    "batch": r"(批量|一起|分别|同时).*(分析|看看)",
    "portfolio": r"(组合|持仓|仓位|配置)",
    "backtest": r"(回测|回溯|历史)",
    "optimize": r"(优化|调仓|分配)",
}

# 股票名称映射
CHINESE_NAME_TO_SYMBOL = {
    "茅台": "600519.SS",
    "苹果": "AAPL",
    "比特币": "BTC/USDT",
    # ... 80+ 映射
}
```

支持 "分析一下茅台"、"帮我看看苹果和微软"、"回测比亚迪" 等自然表达。

## 三、多数据源设计

数据获取层支持三种数据源，通过股票代码自动路由：

| 数据源 | 覆盖范围 | 代码格式 |
|--------|---------|---------|
| Yahoo Finance | 全球股票、ETF、指数 | AAPL, 600519.SS |
| 东方财富 (akshare) | A 股实时数据 | 600519, 000858 |
| 币安 (Binance) | 加密货币交易对 | BTC/USDT, ETH/USDT |

系统会根据代码格式自动判断使用哪个数据源，用户无需手动指定。

## 四、回测与预警

### 4.1 回测引擎

支持买入持有（buy_hold）、均线交叉（sma_cross）、RSI 策略三种内置策略，输出完整的绩效指标：

- 总收益、年化收益
- 最大回撤
- 夏普比率
- 胜率
- 权益曲线和交易记录

### 4.2 实时预警系统

支持 5 种预警规则：价格突破、涨跌幅超限、成交量异常、指标交叉、自定义阈值。通知渠道支持控制台输出和 Webhook（钉钉/飞书/Slack）。

## 五、项目工程化

- **482 个测试用例**，覆盖所有核心模块
- **GitHub Actions CI**，自动运行测试
- **Docker 支持**，一键部署
- **Flutter 移动端**，iOS + Android 跨平台
- **MIT 开源协议**

## 六、快速上手

```bash
git clone https://github.com/Jsoned/autowealth-ai.git
cd autowealth-ai
pip install -e .

# Python API
python -m autowealth --symbol AAPL

# 批量分析
python -m autowealth --batch AAPL GOOGL MSFT

# 启动 Web 服务
uvicorn autowealth.api.server:create_app --factory --reload

# 启动可视化界面
streamlit run examples/app.py
```

## 写在最后

AutoWealth AI 的定位不是一个"赚钱工具"，而是一个**投资分析的学习和辅助框架**。多智能体协作、加权投票决策、多维分析整合，这些设计思路在其他领域也有参考价值。

项目完全开源，代码结构清晰，每个模块都有完整的类型注解和文档字符串。欢迎对量化投资、多智能体系统、Python 工程化感兴趣的同学来交流。

GitHub: https://github.com/Jsoned/autowealth-ai

> 免责声明：本项目仅供教育和研究目的，不构成任何投资建议。
