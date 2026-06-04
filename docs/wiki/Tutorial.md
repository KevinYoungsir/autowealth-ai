# 使用教程

## 快速开始

### Python API

```python
from autowealth import AutoWealthEngine

# 初始化引擎
engine = AutoWealthEngine()

# 分析单只股票
result = engine.analyze("AAPL")

# 打印结果
print(f"股票代码: {result['symbol']}")
print(f"综合建议: {result['decision']['signal_type']}")
print(f"置信度: {result['decision']['confidence']}%")
print(f"理由: {result['decision']['reasoning']}")
```

### 命令行工具

```bash
# 分析单只股票
python -m autowealth --symbol AAPL

# 批量分析
python -m autowealth --batch AAPL GOOGL MSFT

# 市场概览
python -m autowealth --market
```

### 可视化界面

```bash
streamlit run examples/app.py
```

## 高级用法

### 批量分析

```python
symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "META"]
batch_result = engine.analyze_batch(symbols)

# 获取买入推荐
for symbol, confidence in batch_result['recommendations']['buy']:
    print(f"{symbol}: {confidence}%")
```

### 投资组合分析

```python
holdings = [
    {"symbol": "AAPL", "quantity": 100, "cost_basis": 150.0},
    {"symbol": "GOOGL", "quantity": 50, "cost_basis": 100.0},
]

portfolio = engine.get_portfolio_analysis(holdings)
print(f"总市值: ${portfolio['total_value']:,.2f}")
```

### 自定义智能体权重

```python
from autowealth.agents.coordinator import AgentCoordinator
from autowealth.agents.technical_agent import TechnicalAgent
from autowealth.agents.fundamental_agent import FundamentalAgent

coordinator = AgentCoordinator()
coordinator.register_agent(TechnicalAgent(), weight=0.5)
coordinator.register_agent(FundamentalAgent(), weight=0.5)
```

## 输出解读

### 信号类型

- **BUY** (买入) - 置信度 >= 60%
- **SELL** (卖出) - 置信度 >= 60%
- **HOLD** (观望) - 置信度 40-60%

### 置信度

表示系统对建议的确信程度，范围0-100%。

### 目标价和止损价

- **目标价** - 预期达到的价格
- **止损价** - 建议的止损位置

## 注意事项

1. **仅供学习研究** - 不构成投资建议
2. **投资有风险** - 使用需谨慎
3. **数据延迟** - 免费数据源可能有延迟
