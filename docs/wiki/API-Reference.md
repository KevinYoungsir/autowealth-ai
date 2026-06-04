# API文档

## AutoWealthEngine

### 初始化

```python
from autowealth import AutoWealthEngine

engine = AutoWealthEngine()
```

### 方法

#### analyze(symbol, include_technical=True, include_fundamental=True, include_sentiment=True)

分析单只股票。

**参数:**
- `symbol` (str) - 股票代码，如 "AAPL"
- `include_technical` (bool) - 是否包含技术分析
- `include_fundamental` (bool) - 是否包含基本面分析
- `include_sentiment` (bool) - 是否包含情绪分析

**返回:**
```python
{
    "symbol": "AAPL",
    "success": True,
    "decision": {
        "signal_type": "buy",  # buy/sell/hold
        "confidence": 75.5,
        "target_price": 185.5,
        "stop_loss": 165.2,
        "reasoning": "..."
    },
    "individual_signals": {...},
    "stock_info": {...}
}
```

#### analyze_batch(symbols)

批量分析多只股票。

**参数:**
- `symbols` (List[str]) - 股票代码列表

**返回:**
```python
{
    "results": {...},
    "recommendations": {
        "buy": [("AAPL", 75.5), ...],
        "sell": [...],
        "hold": [...]
    },
    "summary": {...}
}
```

#### get_market_overview()

获取市场概览。

**返回:**
```python
{
    "success": True,
    "indices": {
        "^GSPC": {"price": 4500.0, "change_pct": 1.2},
        "^DJI": {"price": 35000.0, "change_pct": 0.8}
    }
}
```

#### get_portfolio_analysis(holdings)

分析投资组合。

**参数:**
- `holdings` (List[Dict]) - 持仓列表

**返回:**
```python
{
    "holdings": [...],
    "total_value": 100000.0,
    "total_gain_loss": 5000.0,
    "return_pct": 5.2
}
```

## 便捷函数

### quick_analyze(symbol)

快速分析单只股票。

```python
from autowealth import quick_analyze

result = quick_analyze("AAPL")
```

### batch_analyze(symbols)

批量分析多只股票。

```python
from autowealth import batch_analyze

result = batch_analyze(["AAPL", "GOOGL", "MSFT"])
```

## 智能体系统

### BaseAgent

所有智能体的基类。

### TechnicalAgent

技术分析智能体。

### FundamentalAgent

基本面分析智能体。

### SentimentAgent

情绪分析智能体。

### AgentCoordinator

智能体协调器，负责综合决策。
