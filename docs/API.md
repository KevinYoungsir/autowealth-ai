# API 文档 | API Documentation

> AutoWealth AI FastAPI Web 服务接口文档。包含所有端点说明、请求/响应示例和认证说明。
>
> AutoWealth AI FastAPI Web service API documentation. Includes all endpoint descriptions, request/response examples, and authentication notes.

---

## 目录 | Table of Contents

- [概述 | Overview](#概述--overview)
- [认证说明 | Authentication](#认证说明--authentication)
- [端点列表 | Endpoint List](#端点列表--endpoint-list)
- [端点详情 | Endpoint Details](#端点详情--endpoint-details)
- [数据模型 | Data Models](#数据模型--data-models)
- [错误处理 | Error Handling](#错误处理--error-handling)

---

## 概述 | Overview

AutoWealth AI 提供基于 FastAPI 的 RESTful Web API 服务，支持股票分析、批量分析、投资组合分析、市场概览、策略回测和组合优化等功能。

AutoWealth AI provides a FastAPI-based RESTful Web API service supporting stock analysis, batch analysis, portfolio analysis, market overview, strategy backtesting, and portfolio optimization.

**Base URL**: `http://localhost:8000`

**API 版本**: v1.0.0

**交互式文档**: 启动服务后访问 `http://localhost:8000/docs` (Swagger UI)

---

## 认证说明 | Authentication

当前版本 API **无需认证**即可访问。在生产环境中，建议配置以下安全措施：

The current version of the API is **not authenticated**. In production, the following security measures are recommended:

- API Key 认证（通过 HTTP Header）
- JWT Token 认证
- 速率限制 (Rate Limiting)
- HTTPS 加密

```bash
# 未来版本认证方式（规划中）
curl -H "Authorization: Bearer <token>" \
     http://localhost:8000/analyze
```

---

## 端点列表 | Endpoint List

| 方法 | 路径 | 说明 | 请求体 | 响应模型 |
|------|------|------|--------|---------|
| GET | `/health` | 健康检查 | - | `Dict[str, str]` |
| POST | `/analyze` | 分析单只股票 | `AnalyzeRequest` | `AnalyzeResponse` |
| POST | `/analyze/batch` | 批量分析多只股票 | `BatchAnalyzeRequest` | `BatchAnalyzeResponse` |
| POST | `/portfolio/analyze` | 投资组合分析 | `PortfolioAnalyzeRequest` | `PortfolioAnalyzeResponse` |
| GET | `/market/overview` | 获取市场概览 | - | `MarketOverviewResponse` |
| POST | `/backtest` | 执行策略回测 | `BacktestRequest` | `BacktestResponse` |
| POST | `/optimize` | 投资组合优化 | `OptimizeRequest` | `OptimizeResponse` |

---

## 端点详情 | Endpoint Details

### 1. 健康检查 | Health Check

检查 API 服务是否正常运行。

Check if the API service is running normally.

```
GET /health
```

**请求示例 | Request Example:**

```bash
curl http://localhost:8000/health
```

**响应示例 | Response Example:**

```json
{
  "status": "ok",
  "service": "autowealth-ai"
}
```

---

### 2. 分析单只股票 | Analyze Single Stock

对指定股票进行综合分析，包括技术分析、基本面分析和情绪分析。

Perform comprehensive analysis on a specified stock, including technical, fundamental, and sentiment analysis.

```
POST /analyze
```

**请求体 | Request Body:**

```json
{
  "symbol": "AAPL",
  "include_technical": true,
  "include_fundamental": true,
  "include_sentiment": true
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 股票代码（如 AAPL, 600519.SS, BTCUSDT） |
| `include_technical` | bool | 否 | true | 是否包含技术分析 |
| `include_fundamental` | bool | 否 | true | 是否包含基本面分析 |
| `include_sentiment` | bool | 否 | true | 是否包含情绪分析 |

**响应示例 | Response Example:**

```json
{
  "symbol": "AAPL",
  "success": true,
  "error": null,
  "decision": {
    "signal_type": "buy",
    "confidence": 72.5,
    "reasoning": "综合决策: BUY (置信度: 72.5%)\n\n各智能体分析结果:\n- TechnicalAnalyst (权重35%): BUY (置信度75%)\n- FundamentalAnalyst (权重35%): BUY (置信度70%)\n- SentimentAnalyst (权重30%): HOLD (置信度55%)",
    "target_price": 185.5,
    "stop_loss": 170.2,
    "scores": {
      "buy": 72.5,
      "sell": 10.0,
      "hold": 17.5
    },
    "signal_details": [
      {
        "agent": "TechnicalAnalyst",
        "signal": "buy",
        "confidence": 75,
        "weight": 0.35
      }
    ]
  },
  "individual_signals": {
    "TechnicalAnalyst": {
      "agent_name": "TechnicalAnalyst",
      "signal_type": "buy",
      "confidence": 75,
      "reasoning": "MACD金叉，RSI处于合理区间..."
    }
  },
  "summary": "【AAPL】分析摘要\n综合建议: BUY (置信度: 72.5%)",
  "technical_analysis": {
    "Close": 178.5,
    "RSI": 55.2,
    "MACD": 1.23,
    "MACD_Signal": 0.98
  },
  "fundamental_analysis": {
    "valuation": {
      "pe_ratio": 28.5,
      "pb_ratio": 45.2,
      "valuation_score": 62.3
    },
    "growth": {
      "return_1m": 5.2,
      "return_3m": 12.8,
      "trend": "uptrend",
      "growth_score": 75.6
    }
  },
  "stock_info": {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "sector": "Technology",
    "market_cap": 2800000000000
  }
}
```

**cURL 示例:**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol": "AAPL"}'
```

---

### 3. 批量分析 | Batch Analysis

批量分析多只股票，返回排序后的推荐列表。

Analyze multiple stocks in batch, return sorted recommendation list.

```
POST /analyze/batch
```

**请求体 | Request Body:**

```json
{
  "symbols": ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `symbols` | string[] | 是 | 股票代码列表 |

**响应示例 | Response Example:**

```json
{
  "results": {
    "AAPL": {
      "symbol": "AAPL",
      "success": true,
      "decision": {
        "signal_type": "buy",
        "confidence": 72.5
      }
    }
  },
  "recommendations": {
    "buy": [
      ["AAPL", 72.5],
      ["MSFT", 68.3]
    ],
    "sell": [
      ["TSLA", 65.2]
    ],
    "hold": [
      ["GOOGL", 52.1],
      ["AMZN", 48.5]
    ]
  },
  "summary": {
    "total": 5,
    "success": 5,
    "buy_count": 2,
    "sell_count": 1,
    "hold_count": 2
  }
}
```

**cURL 示例:**

```bash
curl -X POST http://localhost:8000/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["AAPL", "GOOGL", "MSFT"]}'
```

---

### 4. 投资组合分析 | Portfolio Analysis

分析投资组合的持仓情况，计算总市值、盈亏和收益率。

Analyze portfolio holdings, calculate total value, gain/loss, and return rate.

```
POST /portfolio/analyze
```

**请求体 | Request Body:**

```json
{
  "holdings": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "cost_basis": 150.0
    },
    {
      "symbol": "MSFT",
      "quantity": 50,
      "cost_basis": 300.0
    }
  ]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `holdings` | Holding[] | 是 | - | 持仓列表 |
| `holdings[].symbol` | string | 是 | - | 股票代码 |
| `holdings[].quantity` | float | 是 | - | 持仓数量 |
| `holdings[].cost_basis` | float | 否 | 0.0 | 成本价 |

**响应示例 | Response Example:**

```json
{
  "holdings": [
    {
      "symbol": "AAPL",
      "quantity": 100,
      "current_price": 178.5,
      "holding_value": 17850.0,
      "cost_basis": 150.0,
      "gain_loss": 2850.0,
      "decision": {
        "signal_type": "buy",
        "confidence": 72.5
      }
    }
  ],
  "total_value": 32850.0,
  "total_gain_loss": 5350.0,
  "return_pct": 19.45
}
```

---

### 5. 市场概览 | Market Overview

获取全球主要市场指数的实时行情。

Get real-time quotes for major global market indices.

```
GET /market/overview
```

**响应示例 | Response Example:**

```json
{
  "success": true,
  "indices": {
    "^GSPC": {
      "price": 5234.18,
      "change_pct": 0.85,
      "volume": 3250000000
    },
    "^DJI": {
      "price": 39131.53,
      "change_pct": 0.62,
      "volume": 2850000000
    },
    "000001.SS": {
      "price": 3068.42,
      "change_pct": -0.35,
      "volume": 4120000000
    }
  }
}
```

**cURL 示例:**

```bash
curl http://localhost:8000/market/overview
```

---

### 6. 策略回测 | Strategy Backtest

对指定股票执行策略回测，返回绩效指标和交易记录。

Execute strategy backtesting on a specified stock, return performance metrics and trade history.

```
POST /backtest
```

**请求体 | Request Body:**

```json
{
  "symbol": "AAPL",
  "strategy": "sma_cross",
  "initial_capital": 100000.0
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | string | 是 | - | 股票代码 |
| `strategy` | string | 是 | - | 策略名称（buy_hold / sma_cross / rsi） |
| `initial_capital` | float | 否 | 100000.0 | 初始资金 |

**支持的策略 | Supported Strategies:**

| 策略 | 说明 |
|------|------|
| `buy_hold` | 买入持有策略 |
| `sma_cross` | 均线交叉策略（SMA20/SMA60） |
| `rsi` | RSI 超买超卖策略（RSI14） |

**响应示例 | Response Example:**

```json
{
  "symbol": "AAPL",
  "strategy": "sma_cross",
  "metrics": {
    "total_return": 0.1523,
    "annualized_return": 0.1856,
    "max_drawdown": 0.0832,
    "sharpe_ratio": 1.45,
    "win_rate": 0.625,
    "trade_count": 8,
    "final_equity": 115230.0,
    "initial_capital": 100000.0
  },
  "trade_count": 8,
  "trades": [
    {
      "type": "buy",
      "price": 165.5,
      "shares": 603.6,
      "cost": 99.0,
      "timestamp": "2025-03-15",
      "equity": 99801.0
    },
    {
      "type": "sell",
      "price": 172.3,
      "shares": 603.6,
      "cost": 103.9,
      "timestamp": "2025-05-20",
      "equity": 104003.5,
      "pnl": 4120.2,
      "return_pct": 4.13
    }
  ],
  "equity_curve": [100000.0, 99801.0, 101250.0, 104003.5, 102500.0, 105230.0]
}
```

---

### 7. 投资组合优化 | Portfolio Optimization

基于马科维茨均值方差模型优化投资组合权重。

Optimize portfolio weights based on Markowitz mean-variance model.

```
POST /optimize
```

**请求体 | Request Body:**

```json
{
  "symbols": ["AAPL", "GOOGL", "MSFT", "AMZN"],
  "target_return": 0.15
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbols` | string[] | 是 | - | 股票代码列表（至少2只） |
| `target_return` | float | 否 | null | 目标年化收益率（不指定则使用最大夏普比率） |

**响应示例 | Response Example:**

```json
{
  "weights": {
    "AAPL": 0.35,
    "GOOGL": 0.20,
    "MSFT": 0.30,
    "AMZN": 0.15
  },
  "expected_return": 0.1523,
  "volatility": 0.1856,
  "sharpe_ratio": 0.82
}
```

---

## 数据模型 | Data Models

### AnalyzeRequest

```python
class AnalyzeRequest(BaseModel):
    symbol: str           # 股票代码
    include_technical: bool = True   # 包含技术分析
    include_fundamental: bool = True  # 包含基本面分析
    include_sentiment: bool = True    # 包含情绪分析
```

### AnalyzeResponse

```python
class AnalyzeResponse(BaseModel):
    symbol: str
    success: bool
    error: Optional[str] = None
    decision: Optional[Dict[str, Any]] = None
    individual_signals: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None
    technical_analysis: Optional[Dict[str, Any]] = None
    fundamental_analysis: Optional[Dict[str, Any]] = None
    stock_info: Optional[Dict[str, Any]] = None
```

### Holding

```python
class Holding(BaseModel):
    symbol: str          # 股票代码
    quantity: float      # 持仓数量
    cost_basis: float = 0.0  # 成本价
```

### BacktestRequest

```python
class BacktestRequest(BaseModel):
    symbol: str              # 股票代码
    strategy: str            # 策略名称
    initial_capital: float = 100000.0  # 初始资金
```

### OptimizeRequest

```python
class OptimizeRequest(BaseModel):
    symbols: List[str]                   # 股票代码列表
    target_return: Optional[float] = None  # 目标年化收益率
```

---

## 错误处理 | Error Handling

### 错误响应格式 | Error Response Format

当请求失败时，API 返回标准 HTTP 错误码和错误详情：

When a request fails, the API returns standard HTTP error codes and error details:

```json
{
  "detail": "无法获取 AAPL 的数据"
}
```

### HTTP 状态码 | HTTP Status Codes

| 状态码 | 说明 |
|--------|------|
| `200` | 请求成功 |
| `422` | 请求参数验证失败（Pydantic 验证错误） |
| `500` | 服务器内部错误（分析/数据获取失败） |

### 常见错误 | Common Errors

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| `无法获取 XXX 的数据` | 股票代码无效或网络问题 | 检查股票代码格式，确认网络连接 |
| `有效股票数据不足，无法进行优化` | 优化需要至少2只有效股票 | 确保提供至少2只有效数据的股票代码 |
| `不支持的模型类型` | ML 模型类型参数错误 | 使用 `random_forest` 或 `lstm` |

---

## 快速启动 | Quick Start

### 启动 API 服务 | Start API Service

```bash
# 安装 API 依赖
pip install -e ".[api]"

# 启动服务
uvicorn autowealth.api.server:create_app --factory --host 0.0.0.0 --port 8000

# 或使用 Docker
docker-compose up -d
```

### Python 客户端示例 | Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000"

# 分析单只股票
response = requests.post(
    f"{BASE_URL}/analyze",
    json={"symbol": "AAPL"}
)
result = response.json()
print(f"建议: {result['decision']['signal_type']}")
print(f"置信度: {result['decision']['confidence']}%")

# 批量分析
response = requests.post(
    f"{BASE_URL}/analyze/batch",
    json={"symbols": ["AAPL", "GOOGL", "MSFT"]}
)
batch_result = response.json()
print(f"推荐买入: {batch_result['recommendations']['buy']}")

# 市场概览
response = requests.get(f"{BASE_URL}/market/overview")
market = response.json()
for index, data in market["indices"].items():
    print(f"{index}: {data['price']} ({data['change_pct']}%)")
```

### 交互式文档 | Interactive Docs

启动服务后，访问以下地址查看自动生成的交互式 API 文档：

After starting the service, visit the following URLs for auto-generated interactive API docs:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
